"""
Policy layer: evaluates exactly one policy document against a flat bag of
signals and returns a deterministic decision.

This engine does not decide what a signal means. A detector's fraud
score, a mandate rule's pass/fail, and a raw transaction field are all
just named signals to it; the policy document is what says which of them
matter and how (see policy/policies/transaction-authorization/1.0.0/policy.json
for the default). Ordered rules, first match wins. A signal missing from
the input never satisfies a leaf condition, even if some other signal's
value happens to be falsy (False/0/""), so a missing signal is never
confused with a present-but-negative one.

This engine SHALL NOT: authorize execution, execute anything, access
external systems, or sign anything. See pipeline/src/run_pipeline.py for
where its output (APPROVE/REJECT/REQUIRE_OVERRIDE) is mapped to this
repo's ALLOW/FLAG/BLOCK vocabulary and handed to the sign layer.
"""

from operator_evaluator import evaluate as evaluate_operator

APPROVE = "APPROVE"
REJECT = "REJECT"
REQUIRE_OVERRIDE = "REQUIRE_OVERRIDE"

_ACTION_TO_OUTCOME = {
    "approve": APPROVE,
    "require_override": REQUIRE_OVERRIDE,
    "reject": REJECT,
}


def evaluate_policy(policy, signals):
    """Evaluate `policy` against `signals`. Returns a dict: policy_id,
    policy_version, outcome (APPROVE|REJECT|REQUIRE_OVERRIDE), reason,
    matched_rule_id ("none" if nothing matched), evaluated_rules (count),
    matched_path (ordered list of rule ids that were checked)."""

    trace = []
    rule = _find_first_match(policy.get("rules", []), signals, trace)

    return {
        "policy_id": policy.get("policyId"),
        "policy_version": policy.get("policyVersion"),
        "outcome": _to_outcome(rule["outcome"]["action"] if rule else None),
        "reason": rule["outcome"]["reason"] if rule else "no_rule_matched",
        "matched_rule_id": rule["id"] if rule else "none",
        "evaluated_rules": len(trace),
        "matched_path": trace,
    }


def _find_first_match(rules, signals, trace):
    for rule in rules:
        trace.append(rule["id"])
        if _evaluate_condition(rule["condition"], signals):
            return rule
    return None


def _evaluate_condition(condition, signals):
    if "fact" in condition:
        fact = condition["fact"]
        if fact not in signals:
            return False
        return evaluate_operator(signals[fact], condition["operator"], condition.get("value"))

    if "always" in condition:
        return True

    if "all" in condition:
        return all(_evaluate_condition(child, signals) for child in condition["all"])

    if "any" in condition:
        return any(_evaluate_condition(child, signals) for child in condition["any"])

    return False


def _to_outcome(action):
    return _ACTION_TO_OUTCOME.get(action, REJECT)
