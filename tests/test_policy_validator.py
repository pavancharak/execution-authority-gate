"""Tests for policy/src/policy_validator.py's structural checks, run once
when a policy is loaded (see policy_loader.load_policy), before it is
ever evaluated."""

import pytest

from policy_validator import PolicyValidationError, validate_policy


def _valid_policy(**overrides):
    policy = {
        "policyId": "test-policy",
        "policyVersion": "1.0.0",
        "schemaVersion": "1.0.0",
        "rules": [
            {
                "id": "approve-all",
                "condition": {"always": True},
                "outcome": {"action": "approve", "reason": "because"},
            }
        ],
    }
    policy.update(overrides)
    return policy


def test_valid_policy_passes():
    validate_policy(_valid_policy())  # must not raise


@pytest.mark.parametrize("field", ["policyId", "policyVersion", "schemaVersion"])
def test_missing_identity_field_rejected(field):
    policy = _valid_policy()
    policy[field] = "   "
    with pytest.raises(PolicyValidationError):
        validate_policy(policy)


def test_rules_must_be_a_nonempty_list():
    with pytest.raises(PolicyValidationError):
        validate_policy(_valid_policy(rules=[]))
    with pytest.raises(PolicyValidationError):
        validate_policy(_valid_policy(rules="not-a-list"))


def test_duplicate_rule_id_rejected():
    policy = _valid_policy(rules=[
        {"id": "dup", "condition": {"always": True}, "outcome": {"action": "approve", "reason": "x"}},
        {"id": "dup", "condition": {"always": True}, "outcome": {"action": "reject", "reason": "y"}},
    ])
    with pytest.raises(PolicyValidationError):
        validate_policy(policy)


def test_rule_missing_outcome_fields_rejected():
    base_rule = {"id": "r1", "condition": {"always": True}}
    with pytest.raises(PolicyValidationError):
        validate_policy(_valid_policy(rules=[dict(base_rule)]))  # no outcome at all
    with pytest.raises(PolicyValidationError):
        validate_policy(_valid_policy(rules=[{**base_rule, "outcome": {"reason": "x"}}]))  # no action
    with pytest.raises(PolicyValidationError):
        validate_policy(_valid_policy(rules=[{**base_rule, "outcome": {"action": "approve", "reason": "  "}}]))


def test_unsupported_operator_rejected():
    policy = _valid_policy(rules=[
        {
            "id": "r1",
            "condition": {"fact": "amount", "operator": "does_not_exist", "value": 1},
            "outcome": {"action": "reject", "reason": "x"},
        }
    ])
    with pytest.raises(PolicyValidationError):
        validate_policy(policy)


def test_matches_requires_a_valid_regex_string():
    def policy_with_matches_value(value):
        return _valid_policy(rules=[
            {
                "id": "r1",
                "condition": {"fact": "merchant", "operator": "matches", "value": value},
                "outcome": {"action": "reject", "reason": "x"},
            }
        ])

    with pytest.raises(PolicyValidationError):
        validate_policy(policy_with_matches_value(123))  # not a string

    with pytest.raises(PolicyValidationError):
        validate_policy(policy_with_matches_value("("))  # invalid regex

    validate_policy(policy_with_matches_value(r"^tx_\d+$"))  # must not raise


@pytest.mark.parametrize("connective", ["all", "any"])
def test_empty_all_or_any_rejected(connective):
    policy = _valid_policy(rules=[
        {"id": "r1", "condition": {connective: []}, "outcome": {"action": "reject", "reason": "x"}}
    ])
    with pytest.raises(PolicyValidationError):
        validate_policy(policy)


def test_always_must_be_literally_true():
    policy = _valid_policy(rules=[
        {"id": "r1", "condition": {"always": False}, "outcome": {"action": "reject", "reason": "x"}}
    ])
    with pytest.raises(PolicyValidationError):
        validate_policy(policy)
