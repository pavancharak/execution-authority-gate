"""
Mandate layer: deterministic authorization rules, independent of the
detect layer's fraud score. A transaction can look statistically normal
(low fraud score) and still be unauthorized (over budget, wrong merchant,
odd hour, too many today) — that's the case this layer exists to catch.

A mandate is derived from a customer's own known-good transaction
history: this is "the customer's actual $200/month grocery budget", not
a hand-authored policy. See derive_mandate_from_history.
"""

import rules

DEFAULT_MONTHLY_LIMIT_USD = 1000.0
DEFAULT_ALLOWED_HOURS = (6, 23)
DEFAULT_MAX_TX_PER_DAY = 8


def default_mandate(customer_id=None):
    """Used when a customer has no transaction history to derive a
    mandate from (e.g. a brand-new account) — deliberately loose, since
    there's nothing yet to base a tighter policy on."""
    return {
        "customer_id": customer_id,
        "monthly_limit_usd": DEFAULT_MONTHLY_LIMIT_USD,
        "allowed_merchants": None,
        "allowed_hours": DEFAULT_ALLOWED_HOURS,
        "max_tx_per_day": DEFAULT_MAX_TX_PER_DAY,
    }


def derive_mandate_from_history(customer_transactions):
    """Build a customer-specific mandate from their own known-good
    transactions: monthly cap based on their real historical volume,
    merchants they've actually used, the hours they actually transact in
    (with a small margin), and daily velocity a bit above their observed
    max."""
    if not customer_transactions:
        return default_mandate()

    amounts = [t["amount"] for t in customer_transactions]
    avg_amount = sum(amounts) / len(amounts)
    merchants = sorted({t["merchant"] for t in customer_transactions})
    hours = [t["hour_of_day"] for t in customer_transactions]

    return {
        "customer_id": customer_transactions[0]["customer_id"],
        "monthly_limit_usd": round(avg_amount * len(customer_transactions) * 1.5, 2),
        "allowed_merchants": merchants,
        "allowed_hours": (max(0, min(hours) - 2), min(23, max(hours) + 2)),
        "max_tx_per_day": max(DEFAULT_MAX_TX_PER_DAY, len(customer_transactions) // 4 + 2),
    }


def check_mandate(transaction, mandate, month_to_date_total=0.0, tx_count_today=0):
    """Run every mandate rule against a transaction. ALL must pass — this
    is deliberately AND, not OR: a transaction within its spending limit
    but at 3am from a merchant the customer has never used should still
    fail the mandate, even if the detect layer scored it as low risk."""
    checks = [
        ("spending_limit",) + rules.check_spending_limit(
            transaction["amount"], month_to_date_total, mandate["monthly_limit_usd"]
        ),
        ("merchant_whitelist",) + rules.check_merchant_whitelist(
            transaction["merchant"], mandate.get("allowed_merchants")
        ),
        ("time_restriction",) + rules.check_time_restriction(
            transaction["hour_of_day"], mandate.get("allowed_hours", DEFAULT_ALLOWED_HOURS)
        ),
        ("velocity",) + rules.check_velocity(
            tx_count_today, mandate.get("max_tx_per_day", DEFAULT_MAX_TX_PER_DAY)
        ),
    ]

    violated = [name for name, passed, _ in checks if not passed]

    return {
        "transaction_id": transaction.get("transaction_id"),
        "mandate_allowed": len(violated) == 0,
        "violated_rules": violated,
        "checks": [{"rule": name, "passed": passed, "reason": reason} for name, passed, reason in checks],
    }
