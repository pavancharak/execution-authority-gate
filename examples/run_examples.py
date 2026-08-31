import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

for layer in ("policy", "mandate", "sign", "detect", "generate"):
    layer_src = REPO_ROOT / layer / "src"
    if str(layer_src) not in sys.path:
        sys.path.insert(0, str(layer_src))

import policy_engine
import policy_loader


EXAMPLES_DIR = Path(__file__).resolve().parent

POLICY_ID = "transaction-authorization"
POLICY_VERSION = "1.0.0"

policy = policy_loader.load_policy(POLICY_ID, POLICY_VERSION)


def load_example(filename):
    path = EXAMPLES_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_example(filename):
    example = load_example(filename)
    inputs = example["inputs"]

    checks = [
        {
            "rule": "spending_limit",
            "passed": inputs["spending_limit"],
        },
        {
            "rule": "merchant_whitelist",
            "passed": inputs["merchant_whitelist"],
        },
        {
            "rule": "time_restriction",
            "passed": inputs["time_restriction"],
        },
        {
            "rule": "velocity",
            "passed": inputs["velocity"],
        },
    ]

    mandate_result = {
        "mandate_allowed": inputs["mandate_allowed"],
        "checks": checks,
    }

    signals = {
        "detect_decision": inputs["detect_decision"],
        "mandate_allowed": inputs["mandate_allowed"],
        "fraud_score": inputs["fraud_score"],
        "amount": inputs["amount"],
    }

    for check in checks:
        signals[check["rule"]] = check["passed"]

    result = policy_engine.evaluate_policy(policy, signals)

    print("=" * 70)
    print(example["title"])
    print("=" * 70)
    print(f"Detector:       {inputs['detect_decision']}")
    print(f"Fraud score:    {inputs['fraud_score']}")
    print(f"Mandate allowed:{inputs['mandate_allowed']}")
    print(f"Policy:         {POLICY_ID}@{POLICY_VERSION}")
    print(f"Outcome:        {result['outcome']}")
    print(f"Matched rule:   {result['matched_rule_id']}")

    expected = example["expected"]

    expected_action = expected["action"]

    outcome_to_action = {
        policy_engine.APPROVE: "approve",
        policy_engine.REQUIRE_OVERRIDE: "flag",
        policy_engine.REJECT: "reject",
    }

    actual_action = outcome_to_action[result["outcome"]]

    print(f"Expected:       {expected_action}")
    print(f"Result:         {'PASS' if actual_action == expected_action else 'FAIL'}")
    print()

    return actual_action == expected_action


def main():
    files = [
        "01-legitimate-purchase.json",
        "02-high-risk-new-account.json",
        "03-detector-miss-mandate-catches.json",
    ]

    results = [run_example(filename) for filename in files]

    print("=" * 70)
    print(f"EXAMPLES: {sum(results)}/{len(results)} passed")
    print("=" * 70)

    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
