"""
Backend for the dashboard's interactive demo: the Attack Walkthrough tab
(reads precomputed, already signed real decisions) and the Live Test
Harness tab (runs a real transaction through the actual detect to
mandate to sign pipeline, on demand, in this process).

Loads the same detect/mandate/policy/sign modules the offline pipeline
(pipeline/src/run_pipeline.py) uses, so a live evaluation here is the
real thing, not a simulation. Same trained model, same mandate rules,
same shipped policy document, same authority keypair.
"""

import json
import sys
from pathlib import Path
from threading import Lock

WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_DIR.parent

for _layer in ("detect", "mandate", "sign", "policy"):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))

import detector as det  # noqa: E402
import mandate_checker as mc  # noqa: E402
import authority_signer as auth  # noqa: E402
import signature_verifier as verify  # noqa: E402
import policy_engine  # noqa: E402
import policy_loader  # noqa: E402

# Same shipped policy document and engine pipeline/src/run_pipeline.py
# evaluates against, loaded independently here so the live demo doesn't
# have to import the offline pipeline's heavier module (data file
# resolution, llm_client, etc.) just to reach the policy layer.
_POLICY = policy_loader.load_policy("transaction-authorization", "1.0.0")
_OUTCOME_TO_DECISION = {
    policy_engine.APPROVE: "ALLOW",
    policy_engine.REQUIRE_OVERRIDE: "FLAG",
    policy_engine.REJECT: "BLOCK",
}

SCENARIOS_PATH = WEB_DIR / "data" / "attack_scenarios.json"
DEMO_CUSTOMERS_PATH = WEB_DIR / "data" / "demo_customers.json"

# Neutral defaults for the features the Live Test form doesn't expose.
# Values close to the median of the real legitimate population, same
# idea as detect/src/detector.py's median_neutral_features, so
# amount, merchant, hour, and ai signal are what's actually driving
# the score, not noise from fields the judge never touched.
#
# These are computed from the committed run's generate/data/good_transactions.json
# (median seconds_since_prev_tx, location_mismatch_km, pattern_similarity)
# rather than loaded live, since generate/data/ is intentionally excluded
# from the deployed container (see .dockerignore). The previous values
# here (3600.0 / 5.0 / 0.85) were stale relative to the actual trained
# model and put every single Live Test submission at or above the BLOCK
# threshold regardless of amount, hour, or ai_generated_signal, i.e. the
# harness could never return ALLOW. Recompute and update these if the
# generate layer is rerun and the population shifts meaningfully:
# `python -c "import json,detector as det; print(det.median_neutral_features(json.load(open('../generate/data/good_transactions.json'))))"`
# from web/ with detect/src on sys.path.
NEUTRAL_FEATURES = {
    "seconds_since_prev_tx": 209031.25,
    "location_mismatch_km": 3.2,
    "pattern_similarity": 0.935,
}

MIN_AMOUNT = 0.01
MAX_AMOUNT = 1_000_000.0

_model_lock = Lock()
_model = None


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            _model = det.load_model()
        return _model


def _load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_scenarios():
    scenarios = _load_json(SCENARIOS_PATH) or []
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "stage": s["stage"],
            "why_hard_to_catch": s["why_hard_to_catch"],
            "final_decision": s["example"]["decision"]["final_decision"],
            "fraud_score": s["example"]["decision"]["fraud_score"],
            "verified": s["example"]["verified"],
        }
        for s in scenarios
    ]


def get_scenario(scenario_id):
    scenarios = _load_json(SCENARIOS_PATH) or []
    for s in scenarios:
        if s["id"] == scenario_id:
            return s
    return None


def list_demo_customers():
    data = _load_json(DEMO_CUSTOMERS_PATH) or {"customers": [], "merchants": []}
    return data


class ValidationError(ValueError):
    pass


def _validate_inputs(customer_id, amount, merchant, hour_of_day, ai_generated_signal):
    customers = {c["customer_id"]: c for c in list_demo_customers()["customers"]}
    if customer_id not in customers:
        raise ValidationError(f"Unknown demo customer_id: {customer_id!r}")

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError("amount must be a number")
    if not (MIN_AMOUNT <= amount <= MAX_AMOUNT):
        raise ValidationError(f"amount must be between {MIN_AMOUNT} and {MAX_AMOUNT}")

    if not isinstance(merchant, str) or not (1 <= len(merchant) <= 80):
        raise ValidationError("merchant must be a string that is not empty (max 80 chars)")

    try:
        hour_of_day = int(hour_of_day)
    except (TypeError, ValueError):
        raise ValidationError("hour_of_day must be an integer")
    if not (0 <= hour_of_day <= 23):
        raise ValidationError("hour_of_day must be between 0 and 23")

    try:
        ai_generated_signal = float(ai_generated_signal)
    except (TypeError, ValueError):
        raise ValidationError("ai_generated_signal must be a number")
    if not (0.0 <= ai_generated_signal <= 1.0):
        raise ValidationError("ai_generated_signal must be between 0.0 and 1.0")

    return customers[customer_id], amount, merchant, hour_of_day, ai_generated_signal


def evaluate_transaction(customer_id, amount, merchant, hour_of_day, ai_generated_signal):
    """Runs one live transaction through the real pipeline: detect ->
    mandate -> sign -> verify. Raises ValidationError on bad input."""
    customer, amount, merchant, hour_of_day, ai_generated_signal = _validate_inputs(
        customer_id, amount, merchant, hour_of_day, ai_generated_signal
    )

    tx = {
        "transaction_id": f"demo_{customer_id}_{int(amount * 100)}_{hour_of_day}",
        "customer_id": customer_id,
        "amount": amount,
        "merchant": merchant,
        "hour_of_day": hour_of_day,
        "ai_generated_signal": ai_generated_signal,
        **NEUTRAL_FEATURES,
    }

    model = _get_model()
    score = float(model.predict_proba([det._row(tx)])[:, 1][0])
    detect_decision = det.decision_for_score(score)
    detect_reasons = det._reasons_for(tx, model)

    mandate = customer["mandate"]
    mandate_result = mc.check_mandate(tx, mandate, month_to_date_total=0.0, tx_count_today=0)

    signals = {
        "detect_decision": detect_decision,
        "mandate_allowed": mandate_result["mandate_allowed"],
        "fraud_score": score,
        "amount": amount,
    }
    for check in mandate_result["checks"]:
        signals[check["rule"]] = check["passed"]
    policy_result = policy_engine.evaluate_policy(_POLICY, signals)
    final_decision = _OUTCOME_TO_DECISION[policy_result["outcome"]]

    reasons = [f"detect: {r}" for r in detect_reasons] + [f"mandate: {r}" for r in mandate_result["violated_rules"]]
    signed = auth.sign_pipeline_decision(
        tx["transaction_id"],
        score,
        detect_decision,
        mandate_result["mandate_allowed"],
        mandate_result["violated_rules"],
        final_decision,
        reasons,
        policy_id=policy_result["policy_id"],
        policy_version=policy_result["policy_version"],
        matched_rule_id=policy_result["matched_rule_id"],
    )
    verified = verify.verify_record(dict(signed), "authority")

    return {
        "transaction": {
            "customer_id": customer_id,
            "customer_name": customer["customer_name"],
            "amount": amount,
            "merchant": merchant,
            "hour_of_day": hour_of_day,
            "ai_generated_signal": ai_generated_signal,
        },
        "mandate_used": mandate,
        "mandate_checks": mandate_result["checks"],
        "decision": signed,
        "verified": verified,
        "note": "Single transaction demo: month to date spend and today's transaction count are assumed zero going in. The spending limit and velocity rules still run for real, just without a running session history to accumulate against.",
    }
