"""
Individual mandate rules. Each function checks one thing and returns
(passed: bool, reason: str) — deterministic, no ML, no LLM. Composed
together in mandate_checker.py.
"""


def check_spending_limit(amount, month_to_date_total, monthly_limit_usd):
    projected = month_to_date_total + amount
    if projected > monthly_limit_usd:
        return False, (
            f"would exceed monthly limit (${monthly_limit_usd:.2f}): "
            f"${month_to_date_total:.2f} so far + ${amount:.2f} = ${projected:.2f}"
        )
    return True, f"within monthly limit (${projected:.2f} of ${monthly_limit_usd:.2f})"


def check_merchant_whitelist(merchant, allowed_merchants):
    if not allowed_merchants:
        return True, "no merchant restriction on this mandate"
    if merchant in allowed_merchants:
        return True, f"{merchant} is an allowed merchant"
    return False, f"{merchant} is not in the customer's allowed merchant list"


def check_time_restriction(hour_of_day, allowed_hours):
    start, end = allowed_hours
    if start <= hour_of_day <= end:
        return True, f"hour {hour_of_day} is within the allowed window ({start}-{end})"
    return False, f"hour {hour_of_day} is outside the allowed window ({start}-{end})"


def check_velocity(tx_count_today, max_tx_per_day):
    if tx_count_today >= max_tx_per_day:
        return False, f"would exceed the max daily transaction count ({max_tx_per_day})"
    return True, f"within the daily transaction count limit ({tx_count_today + 1} of {max_tx_per_day})"
