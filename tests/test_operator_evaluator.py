"""Tests for policy/src/operator_evaluator.py's deterministic operators."""

import pytest

import operator_evaluator as op


def test_eq_and_neq():
    assert op.evaluate("BLOCK", "eq", "BLOCK") is True
    assert op.evaluate("BLOCK", "eq", "ALLOW") is False
    assert op.evaluate("BLOCK", "neq", "ALLOW") is True
    assert op.evaluate("BLOCK", "neq", "BLOCK") is False


@pytest.mark.parametrize("operator,a,b,expected", [
    ("gt", 5, 3, True),
    ("gt", 3, 5, False),
    ("gte", 5, 5, True),
    ("lt", 3, 5, True),
    ("lte", 5, 5, True),
])
def test_numeric_comparisons(operator, a, b, expected):
    assert op.evaluate(a, operator, b) is expected


def test_numeric_comparisons_reject_non_numeric_operands():
    # A string that looks numeric still isn't a number: the operator
    # must not silently coerce it, or a signal typo could slip past.
    assert op.evaluate("5", "gt", 3) is False
    assert op.evaluate(5, "gt", "3") is False
    # bool is technically an int subclass in Python; a policy author
    # writing true/false never means "compare this as a number".
    assert op.evaluate(True, "gt", 0) is False


def test_between():
    assert op.evaluate(50, "between", [0, 100]) is True
    assert op.evaluate(150, "between", [0, 100]) is False
    assert op.evaluate(50, "between", [0]) is False  # malformed range


def test_in_and_not_in_require_a_list_expected():
    assert op.evaluate("UrbanCafe", "in", ["UrbanCafe", "QuickMart"]) is True
    assert op.evaluate("Sketchy", "in", ["UrbanCafe", "QuickMart"]) is False
    assert op.evaluate("Sketchy", "not_in", ["UrbanCafe", "QuickMart"]) is True
    assert op.evaluate("UrbanCafe", "in", "UrbanCafe,QuickMart") is False


def test_contains_family():
    assert op.evaluate(["spending_limit", "velocity"], "contains", "velocity") is True
    assert op.evaluate(["spending_limit"], "not_contains", "velocity") is True
    assert op.evaluate(["a", "b", "c"], "contains_all", ["a", "b"]) is True
    assert op.evaluate(["a", "b"], "contains_all", ["a", "z"]) is False
    assert op.evaluate(["a", "b"], "contains_any", ["z", "b"]) is True
    assert op.evaluate(["a", "b"], "contains_any", ["y", "z"]) is False


def test_string_operators():
    assert op.evaluate("mastercard/execution-authority-gate", "starts_with", "mastercard/") is True
    assert op.evaluate("attack.log", "ends_with", ".log") is True
    assert op.evaluate("tx_0001", "matches", r"^tx_\d+$") is True
    assert op.evaluate("txabc", "matches", r"^tx_\d+$") is False


def test_existence_operators_treat_none_as_absent():
    assert op.evaluate(None, "exists", None) is False
    assert op.evaluate(0, "exists", None) is True
    assert op.evaluate(False, "exists", None) is True
    assert op.evaluate(None, "not_exists", None) is True


def test_boolean_operators_are_strict():
    assert op.evaluate(True, "is_true", None) is True
    assert op.evaluate(1, "is_true", None) is False  # truthy, but not True
    assert op.evaluate(False, "is_false", None) is True
    assert op.evaluate(0, "is_false", None) is False  # falsy, but not False


def test_null_operators():
    assert op.evaluate(None, "is_null", None) is True
    assert op.evaluate(0, "is_null", None) is False
    assert op.evaluate(0, "is_not_null", None) is True


@pytest.mark.parametrize("value,expected_len", [
    ("abcd", 4),
    (["a", "b", "c"], 3),
    ({"a": 1, "b": 2}, 2),
    (5, 0),  # a number has no length
])
def test_length_of(value, expected_len):
    assert op.evaluate(value, "length_eq", expected_len) is True
    assert op.evaluate(value, "length_gt", expected_len) is False
    assert op.evaluate(value, "length_gte", expected_len) is True
    assert op.evaluate(value, "length_lt", expected_len) is False
    assert op.evaluate(value, "length_lte", expected_len) is True


@pytest.mark.parametrize("value,expected_type", [
    (None, "null"),
    (True, "boolean"),
    ([1, 2], "array"),
    ("x", "string"),
    (5, "number"),
    (5.5, "number"),
    ({"a": 1}, "object"),
])
def test_type_is(value, expected_type):
    assert op.evaluate(value, "type_is", expected_type) is True
    assert op.evaluate(value, "type_is", "not_a_real_type") is False


def test_unsupported_operator_raises():
    with pytest.raises(ValueError):
        op.evaluate(1, "does_not_exist", 1)
