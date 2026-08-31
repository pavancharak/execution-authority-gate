"""
Deterministic policy operator evaluation.

Every operator is pure and side effect free: given the same actual,
operator, and expected value it always returns the same bool. No clocks,
no randomness, no external systems. This is what a policy rule's leaf
condition (see policy_engine.py) is checked against.
"""

import re

OPERATORS = frozenset(
    [
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "in",
        "not_in",
        "contains",
        "not_contains",
        "contains_all",
        "contains_any",
        "starts_with",
        "ends_with",
        "matches",
        "exists",
        "not_exists",
        "is_true",
        "is_false",
        "is_null",
        "is_not_null",
        "length_eq",
        "length_gt",
        "length_gte",
        "length_lt",
        "length_lte",
        "type_is",
    ]
)


def _is_number(value):
    # bool is a subclass of int in Python; a policy author writing
    # true/false never means "compare this as a number".
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_string(value):
    return isinstance(value, str)


def _length(value):
    if _is_string(value) or isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 0


def _type_of(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def evaluate(actual, operator, expected=None):
    """Evaluate one policy operator. Raises ValueError for an operator
    not in OPERATORS (policy_validator.validate_policy should already
    have caught that before this ever runs)."""

    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected

    if operator == "gt":
        return _is_number(actual) and _is_number(expected) and actual > expected
    if operator == "gte":
        return _is_number(actual) and _is_number(expected) and actual >= expected
    if operator == "lt":
        return _is_number(actual) and _is_number(expected) and actual < expected
    if operator == "lte":
        return _is_number(actual) and _is_number(expected) and actual <= expected
    if operator == "between":
        return (
            _is_number(actual)
            and isinstance(expected, (list, tuple))
            and len(expected) == 2
            and _is_number(expected[0])
            and _is_number(expected[1])
            and expected[0] <= actual <= expected[1]
        )

    if operator == "in":
        return isinstance(expected, (list, tuple)) and actual in expected
    if operator == "not_in":
        return isinstance(expected, (list, tuple)) and actual not in expected

    if operator == "contains":
        return (
            isinstance(actual, (list, tuple))
            and expected is not None
            and expected in actual
        )
    if operator == "not_contains":
        return (
            isinstance(actual, (list, tuple))
            and expected is not None
            and expected not in actual
        )
    if operator == "contains_all":
        return (
            isinstance(actual, (list, tuple))
            and isinstance(expected, (list, tuple))
            and all(v in actual for v in expected)
        )
    if operator == "contains_any":
        return (
            isinstance(actual, (list, tuple))
            and isinstance(expected, (list, tuple))
            and any(v in actual for v in expected)
        )

    if operator == "starts_with":
        return _is_string(actual) and _is_string(expected) and actual.startswith(expected)
    if operator == "ends_with":
        return _is_string(actual) and _is_string(expected) and actual.endswith(expected)
    if operator == "matches":
        return _is_string(actual) and _is_string(expected) and re.search(expected, actual) is not None

    if operator == "exists":
        return actual is not None
    if operator == "not_exists":
        return actual is None

    if operator == "is_true":
        return actual is True
    if operator == "is_false":
        return actual is False

    if operator == "is_null":
        return actual is None
    if operator == "is_not_null":
        return actual is not None

    if operator == "length_eq":
        return _is_number(expected) and _length(actual) == expected
    if operator == "length_gt":
        return _is_number(expected) and _length(actual) > expected
    if operator == "length_gte":
        return _is_number(expected) and _length(actual) >= expected
    if operator == "length_lt":
        return _is_number(expected) and _length(actual) < expected
    if operator == "length_lte":
        return _is_number(expected) and _length(actual) <= expected

    if operator == "type_is":
        return _is_string(expected) and _type_of(actual) == expected

    raise ValueError(f"Unsupported policy operator: {operator!r}")
