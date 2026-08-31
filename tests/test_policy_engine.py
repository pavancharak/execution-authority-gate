"""
Tests for policy/src/policy_engine.py, and the concrete proof of the
value proposition this layer exists for: the same detect + mandate
signals, evaluated against two different policy documents, can produce
two different decisions -- because policy is now data, not hardcoded
control flow. See policy_loader.load_policy("transaction-authorization",
"1.0.0") for the shipped default this repo actually runs.
"""

import policy_engine as pe
import policy_loader


def _policy(rules, policy_id="test-policy", version="1.0.0"):
    return {
        "policyId": policy_id,
        "policyVersion": version,
        "schemaVersion": "1.0.0",
        "rules": rules,
    }


def _rule(rule_id, condition, action, reason="because"):
    return {"id": rule_id, "condition": condition, "outcome": {"action": action, "reason": reason}}


# ---------------------------------------------------------------------------
# Core evaluation semantics
# ---------------------------------------------------------------------------

def test_first_match_wins():
    policy = _policy([
        _rule("first", {"always": True}, "approve", "matches first"),
        _rule("second", {"always": True}, "reject", "never reached"),
    ])
    result = pe.evaluate_policy(policy, {})
    assert result["outcome"] == pe.APPROVE
    assert result["matched_rule_id"] == "first"
    assert result["matched_path"] == ["first"]


def test_default_reject_when_nothing_matches():
    policy = _policy([
        _rule("only", {"fact": "amount", "operator": "gt", "value": 1000}, "reject"),
    ])
    result = pe.evaluate_policy(policy, {"amount": 5})
    assert result["outcome"] == pe.REJECT
    assert result["matched_rule_id"] == "none"
    assert result["reason"] == "no_rule_matched"
    assert result["evaluated_rules"] == 1


def test_missing_fact_never_satisfies_a_leaf_condition():
    policy = _policy([
        _rule("needs-vip", {"fact": "vip", "operator": "is_true", "value": None}, "approve"),
        _rule("fallback", {"always": True}, "reject"),
    ])
    result = pe.evaluate_policy(policy, {})  # "vip" not present at all
    assert result["outcome"] == pe.REJECT
    assert result["matched_rule_id"] == "fallback"


def test_missing_fact_is_distinct_from_a_falsy_present_signal():
    """A signal that's present but False/0 must still be checkable --
    the engine must not treat "falsy" as "missing"."""
    policy = _policy([
        _rule("mandate-violated", {"fact": "mandate_allowed", "operator": "is_false"}, "reject"),
        _rule("fallback", {"always": True}, "approve"),
    ])
    result = pe.evaluate_policy(policy, {"mandate_allowed": False})
    assert result["outcome"] == pe.REJECT
    assert result["matched_rule_id"] == "mandate-violated"


def test_all_condition_requires_every_child():
    policy = _policy([
        _rule(
            "approve-clean",
            {"all": [
                {"fact": "detect_decision", "operator": "eq", "value": "ALLOW"},
                {"fact": "mandate_allowed", "operator": "is_true"},
            ]},
            "approve",
        ),
        _rule("fallback", {"always": True}, "reject"),
    ])
    both_clear = pe.evaluate_policy(policy, {"detect_decision": "ALLOW", "mandate_allowed": True})
    one_fails = pe.evaluate_policy(policy, {"detect_decision": "ALLOW", "mandate_allowed": False})
    assert both_clear["outcome"] == pe.APPROVE
    assert one_fails["outcome"] == pe.REJECT


def test_any_condition_requires_at_least_one_child():
    policy = _policy([
        _rule(
            "reject-either-objects",
            {"any": [
                {"fact": "detect_decision", "operator": "eq", "value": "BLOCK"},
                {"fact": "mandate_allowed", "operator": "is_false"},
            ]},
            "reject",
        ),
        _rule("fallback", {"always": True}, "approve"),
    ])
    neither = pe.evaluate_policy(policy, {"detect_decision": "ALLOW", "mandate_allowed": True})
    one_objects = pe.evaluate_policy(policy, {"detect_decision": "BLOCK", "mandate_allowed": True})
    assert neither["outcome"] == pe.APPROVE
    assert one_objects["outcome"] == pe.REJECT


def test_require_override_action_maps_to_require_override_outcome():
    policy = _policy([_rule("flag", {"always": True}, "require_override")])
    result = pe.evaluate_policy(policy, {})
    assert result["outcome"] == pe.REQUIRE_OVERRIDE


# ---------------------------------------------------------------------------
# The actual value proposition: same signals, different policy document,
# different decision.
# ---------------------------------------------------------------------------

def test_same_signals_different_policy_different_outcome():
    signals = {
        "detect_decision": "FLAG",
        "mandate_allowed": True,
        "fraud_score": 0.62,
    }

    strict_policy = _policy([
        _rule("reject-any-flag", {"fact": "detect_decision", "operator": "eq", "value": "FLAG"}, "reject"),
        _rule("fallback", {"always": True}, "approve"),
    ], policy_id="strict")

    lenient_policy = _policy([
        _rule("approve-if-mandate-clean", {"fact": "mandate_allowed", "operator": "is_true"}, "approve"),
        _rule("fallback", {"always": True}, "reject"),
    ], policy_id="lenient")

    strict_result = pe.evaluate_policy(strict_policy, signals)
    lenient_result = pe.evaluate_policy(lenient_policy, signals)

    assert strict_result["outcome"] == pe.REJECT
    assert lenient_result["outcome"] == pe.APPROVE


def test_shipped_default_policy_reproduces_the_original_combine_rule():
    """The exact policy this repo ships and run_pipeline.py loads by
    default (policy/policies/transaction-authorization/1.0.0/policy.json)
    must behave exactly like the original hardcoded combine_decision:
    BLOCK on detect BLOCK or a mandate violation, FLAG only when detect
    is unsure and mandate is clean, ALLOW otherwise."""
    policy = policy_loader.load_policy("transaction-authorization", "1.0.0")

    def outcome_for(detect_decision, mandate_allowed):
        return pe.evaluate_policy(
            policy, {"detect_decision": detect_decision, "mandate_allowed": mandate_allowed}
        )["outcome"]

    assert outcome_for("ALLOW", True) == pe.APPROVE
    assert outcome_for("BLOCK", True) == pe.REJECT
    assert outcome_for("ALLOW", False) == pe.REJECT
    assert outcome_for("BLOCK", False) == pe.REJECT
    assert outcome_for("FLAG", True) == pe.REQUIRE_OVERRIDE
    assert outcome_for("FLAG", False) == pe.REJECT  # mandate violation overrides FLAG
