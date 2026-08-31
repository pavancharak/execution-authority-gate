"""
Structural validation of a policy document, run once when a policy is
loaded (see policy_loader.py), before it is ever evaluated. Catches
authoring mistakes (duplicate rule ids, a rule with no outcome, an
unsupported operator, a bad regex) as a load-time error instead of a
silent no-match at evaluation time.
"""

import re

from operator_evaluator import OPERATORS


class PolicyValidationError(ValueError):
    pass


def validate_policy(policy):
    if not policy:
        raise PolicyValidationError("Policy is required.")

    if not str(policy.get("policyId") or "").strip():
        raise PolicyValidationError("policyId is required.")
    if not str(policy.get("policyVersion") or "").strip():
        raise PolicyValidationError("policyVersion is required.")
    if not str(policy.get("schemaVersion") or "").strip():
        raise PolicyValidationError("schemaVersion is required.")

    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise PolicyValidationError("Policy rules must be an array.")
    if len(rules) == 0:
        raise PolicyValidationError("Policy must contain at least one rule.")

    bound_signals = policy.get("boundSignals")
    if bound_signals is not None:
        if not isinstance(bound_signals, dict):
            raise PolicyValidationError("Policy boundSignals must be an object.")
        for signal_key, intent_path in bound_signals.items():
            if not str(signal_key).strip():
                raise PolicyValidationError("Policy boundSignals keys cannot be empty.")
            if not isinstance(intent_path, str) or not intent_path.strip():
                raise PolicyValidationError(
                    f"Policy boundSignals[{signal_key!r}] must be a non-empty string dot-path."
                )

    rule_ids = set()
    for rule in rules:
        rule_id = rule.get("id")
        if not str(rule_id or "").strip():
            raise PolicyValidationError("Policy rule id is required.")
        if rule_id in rule_ids:
            raise PolicyValidationError(f"Duplicate policy rule id {rule_id!r}.")
        rule_ids.add(rule_id)

        _validate_condition(rule.get("condition"))

        outcome = rule.get("outcome")
        if not outcome:
            raise PolicyValidationError(f"Policy rule {rule_id!r} is missing an outcome.")
        if not outcome.get("action"):
            raise PolicyValidationError(f"Policy rule {rule_id!r} is missing an outcome action.")
        if not str(outcome.get("reason") or "").strip():
            raise PolicyValidationError(f"Policy rule {rule_id!r} is missing an outcome reason.")


def _validate_condition(condition):
    if not isinstance(condition, dict):
        raise PolicyValidationError("Invalid policy condition.")

    if "fact" in condition:
        if not str(condition.get("fact") or "").strip():
            raise PolicyValidationError("Policy condition fact is required.")

        operator = condition.get("operator")
        if operator not in OPERATORS:
            raise PolicyValidationError(f"Unsupported operator {operator!r}.")

        if operator == "matches":
            value = condition.get("value")
            if not isinstance(value, str):
                raise PolicyValidationError("'matches' requires a regex string.")
            try:
                re.compile(value)
            except re.error:
                raise PolicyValidationError(f"Invalid regular expression {value!r}.")
        return

    if "all" in condition:
        children = condition["all"]
        if not isinstance(children, list) or len(children) == 0:
            raise PolicyValidationError("'all' must contain at least one condition.")
        for child in children:
            _validate_condition(child)
        return

    if "any" in condition:
        children = condition["any"]
        if not isinstance(children, list) or len(children) == 0:
            raise PolicyValidationError("'any' must contain at least one condition.")
        for child in children:
            _validate_condition(child)
        return

    if "always" in condition:
        if condition["always"] is not True:
            raise PolicyValidationError("'always' must be true.")
        return

    raise PolicyValidationError("Invalid policy condition.")
