"""
Optional Flask server for the dashboard.

Not required for local use, `python -m http.server` from web/ works
fine (see the README). This exists for deployment: a server for static
files with a health check at /api/status, matching ../Dockerfile and
../fly.toml.

Serves whatever is in web/data/dashboard.json at request time. For a
deployed image that's the version committed to the repo, since the
pipeline isn't run inside the container.

/api/callers/token and /api/enforce/decisions are new (see
EAG-AUDIT-GAPS.md sections 3-4): caller token issuance and signed
decision execution. They are the only routes gated by @require_auth.
The existing dashboard/demo routes below are intentionally left
unauthenticated: they're what the public live demo at parmana.fly.dev
serves to an anonymous browser, and gating them would break that demo
without actually protecting anything (they're read-only or run the
pipeline against inputs the caller already fully controls).
"""

import functools
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import interactive_demo as demo

WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_DIR.parent

for _layer in ("sign",):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))

import caller_auth  # noqa: E402
import decision_executor  # noqa: E402

app = Flask(__name__, static_folder=None, instance_path=str(WEB_DIR / "instance"))
CORS(app)


def require_auth(fn):
    """Requires `Authorization: Bearer <caller_token>`. On success,
    injects the verified CallerIdentity as the route function's first
    positional argument. Returns 401 for a missing/invalid/expired
    token, never executes the wrapped route otherwise (fail closed)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "missing Authorization: Bearer <token> header"}), 401
        token = header[len("Bearer "):].strip()
        caller = caller_auth.AUTHENTICATOR.verify_token(token)
        if caller is None:
            return jsonify({"error": "invalid or expired caller token"}), 401
        return fn(caller, *args, **kwargs)

    return wrapper


@app.get("/api/status")
def status():
    dashboard_path = WEB_DIR / "data" / "dashboard.json"
    return {"ok": True, "dashboard_present": dashboard_path.exists()}


@app.post("/api/callers/token")
def issue_caller_token():
    """Issue a signed token for a registered caller (see
    sign/src/caller_auth.py's PREDEFINED_CALLERS: payment-processor,
    fraud-analyst, audit-system). Body: {"caller_id": "..."}."""
    body = request.get_json(silent=True) or {}
    caller_id = body.get("caller_id")
    if not caller_id:
        return jsonify({"error": "caller_id is required"}), 400
    try:
        token = caller_auth.AUTHENTICATOR.create_token(caller_id)
    except KeyError:
        return jsonify({"error": f"unknown caller_id: {caller_id!r}"}), 404
    return jsonify({"caller_id": caller_id, "token": token})


@app.post("/api/enforce/decisions")
@require_auth
def enforce_decisions(caller):
    """Execute a batch of signed decisions (see
    sign/src/decision_executor.py). Body: {"decisions": [<signed decision>, ...]}.
    Every decision is independently signature-checked and permission-checked
    against the caller before any action is taken; a caller without
    permission for a given decision's final_decision (e.g.
    payment-processor attempting a BLOCK) gets a REJECTED result for
    that decision without affecting the others in the batch."""
    body = request.get_json(silent=True) or {}
    decisions = body.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return jsonify({"error": "decisions must be a non-empty list"}), 400

    executor = decision_executor.DecisionExecutor()
    results = [
        executor.enforce_decision(decision, decision_executor.noop_webhook, caller=caller)
        for decision in decisions
    ]
    return jsonify(
        {
            "caller_id": caller.caller_id,
            "results": results,
            "audit_log": str(executor.log.path.relative_to(REPO_ROOT)),
        }
    )


@app.get("/api/demo/scenarios")
def demo_scenarios():
    return jsonify(demo.list_scenarios())


@app.get("/api/demo/scenario/<scenario_id>")
def demo_scenario(scenario_id):
    scenario = demo.get_scenario(scenario_id)
    if scenario is None:
        return jsonify({"error": f"unknown scenario_id: {scenario_id}"}), 404
    return jsonify(scenario)


@app.get("/api/demo/customers")
def demo_customers():
    return jsonify(demo.list_demo_customers())


@app.post("/api/demo/evaluate")
def demo_evaluate():
    body = request.get_json(silent=True) or {}
    try:
        result = demo.evaluate_transaction(
            customer_id=body.get("customer_id"),
            amount=body.get("amount"),
            merchant=body.get("merchant"),
            hour_of_day=body.get("hour_of_day"),
            ai_generated_signal=body.get("ai_generated_signal", 0.5),
        )
    except demo.ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
