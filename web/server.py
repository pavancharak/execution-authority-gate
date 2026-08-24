"""
Optional Flask server for the dashboard.

Not required for local use — `python -m http.server` from web/ works
fine (see the README). This exists for deployment: a static-file server
with a health check at /api/status, matching ../Dockerfile and
../fly.toml.

Serves whatever is in web/data/dashboard.json at request time — for a
deployed image that's the version committed to the repo, since the
pipeline isn't run inside the container.
"""

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import interactive_demo as demo

WEB_DIR = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=None, instance_path=str(WEB_DIR / "instance"))
CORS(app)


@app.get("/api/status")
def status():
    dashboard_path = WEB_DIR / "data" / "dashboard.json"
    return {"ok": True, "dashboard_present": dashboard_path.exists()}


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
