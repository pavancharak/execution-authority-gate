"""Tests for mandate/src/rules.py and mandate_checker.py."""

import rules
import mandate_checker as mc


# ---------------------------------------------------------------------------
# rules.py, four independent checks
# ---------------------------------------------------------------------------

def test_check_spending_limit():
    ok, _ = rules.check_spending_limit(amount=50, month_to_date_total=100, monthly_limit_usd=200)
    assert ok is True

    blocked, reason = rules.check_spending_limit(amount=150, month_to_date_total=100, monthly_limit_usd=200)
    assert blocked is False
    assert "monthly limit" in reason


def test_check_merchant_whitelist():
    ok, reason = rules.check_merchant_whitelist("QuickMart", None)
    assert ok is True
    assert "no merchant restriction" in reason

    ok, _ = rules.check_merchant_whitelist("QuickMart", ["QuickMart", "CloudHost"])
    assert ok is True

    blocked, reason = rules.check_merchant_whitelist("GameVault", ["QuickMart", "CloudHost"])
    assert blocked is False
    assert "GameVault" in reason


def test_check_time_restriction():
    ok, _ = rules.check_time_restriction(hour_of_day=10, allowed_hours=(6, 23))
    assert ok is True

    blocked, reason = rules.check_time_restriction(hour_of_day=3, allowed_hours=(6, 23))
    assert blocked is False
    assert "outside" in reason


def test_check_velocity():
    ok, _ = rules.check_velocity(tx_count_today=2, max_tx_per_day=8)
    assert ok is True

    blocked, reason = rules.check_velocity(tx_count_today=8, max_tx_per_day=8)
    assert blocked is False
    assert "daily transaction count" in reason


# ---------------------------------------------------------------------------
# mandate_checker.py
# ---------------------------------------------------------------------------

def test_default_mandate_has_no_merchant_restriction():
    mandate = mc.default_mandate("cust_new")
    assert mandate["customer_id"] == "cust_new"
    assert mandate["allowed_merchants"] is None


def test_derive_mandate_from_history_uses_real_history(make_transaction):
    history = [
        make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10),
        make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=25, hour_of_day=11),
        make_transaction(False, customer_id="cust_1", merchant="CloudHost", amount=30, hour_of_day=12),
    ]
    mandate = mc.derive_mandate_from_history(history)

    assert mandate["customer_id"] == "cust_1"
    assert mandate["allowed_merchants"] == ["CloudHost", "QuickMart"]
    assert mandate["allowed_hours"] == (8, 14)  # min(10)-2, max(12)+2
    assert mandate["monthly_limit_usd"] == round((20 + 25 + 30) / 3 * 3 * 1.5, 2)


def test_derive_mandate_from_empty_history_falls_back_to_default():
    mandate = mc.derive_mandate_from_history([])
    assert mandate == mc.default_mandate()


def test_check_mandate_allows_within_bounds(make_transaction):
    history = [make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10) for _ in range(5)]
    mandate = mc.derive_mandate_from_history(history)
    tx = make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10)

    result = mc.check_mandate(tx, mandate, month_to_date_total=0.0, tx_count_today=0)
    assert result["mandate_allowed"] is True
    assert result["violated_rules"] == []
    assert len(result["checks"]) == 4


def test_check_mandate_blocks_on_any_single_violation(make_transaction):
    history = [make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10) for _ in range(5)]
    mandate = mc.derive_mandate_from_history(history)

    # Amount and merchant are fine, only the hour is off.
    tx = make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=3)

    result = mc.check_mandate(tx, mandate, month_to_date_total=0.0, tx_count_today=0)
    assert result["mandate_allowed"] is False
    assert result["violated_rules"] == ["time_restriction"]


def test_check_mandate_blocks_on_velocity(make_transaction):
    history = [make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10) for _ in range(5)]
    mandate = mc.derive_mandate_from_history(history)
    tx = make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10)

    result = mc.check_mandate(tx, mandate, month_to_date_total=0.0, tx_count_today=mandate["max_tx_per_day"])
    assert result["mandate_allowed"] is False
    assert "velocity" in result["violated_rules"]


def test_check_mandate_combines_multiple_violations(make_transaction):
    history = [make_transaction(False, customer_id="cust_1", merchant="QuickMart", amount=20, hour_of_day=10) for _ in range(5)]
    mandate = mc.derive_mandate_from_history(history)

    bad_tx = make_transaction(
        False, customer_id="cust_1", merchant="GameVault", amount=mandate["monthly_limit_usd"] * 2, hour_of_day=3
    )
    result = mc.check_mandate(bad_tx, mandate, month_to_date_total=0.0, tx_count_today=0)

    assert result["mandate_allowed"] is False
    assert set(result["violated_rules"]) == {"spending_limit", "merchant_whitelist", "time_restriction"}
