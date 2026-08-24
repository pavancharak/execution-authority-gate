"""Generates the legitimate transaction population used to train/test the
detector alongside the fraud agents' output. No authorization token is
needed here because this isn't an attack. It's the baseline of normal
customer behavior the detector must learn NOT to flag."""

import random
import uuid

from fraud_agents import FIRST_NAMES, LAST_NAMES, MERCHANTS, CURRENCIES

random.seed(7)


def generate_good_transactions(n_customers=200, avg_tx_per_customer=5, max_transactions=2500):
    transactions = []
    for _ in range(n_customers):
        cust_id = f"cust_{uuid.uuid4().hex[:8]}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        currency = random.choice(CURRENCIES)
        typical_hour = random.randint(7, 22)
        base_amount = random.uniform(8, 300)
        n_tx = max(1, int(random.gauss(avg_tx_per_customer, 2)))
        for _ in range(n_tx):
            # A small slice of otherwise legitimate activity is genuinely
            # unusual (traveling customer, gift purchase, AI shopping
            # assistant/autofill) so the detector faces realistic overlap
            # instead of a clean separation it could never see in practice.
            is_edge_case = random.random() < 0.16
            tx = {
                "transaction_id": f"tx_{uuid.uuid4().hex[:10]}",
                "customer_id": cust_id,
                "customer_name": name,
                "amount": round(max(1.0, random.gauss(base_amount, base_amount * 0.25)), 2),
                "currency": currency,
                "merchant": random.choice(MERCHANTS),
                "hour_of_day": max(0, min(23, int(random.gauss(typical_hour, 2)))),
                "seconds_since_prev_tx": round(random.uniform(3600, 5 * 86400), 1),
                "location_mismatch_km": round(random.uniform(20, 180), 1) if is_edge_case else round(abs(random.gauss(2, 3)), 1),
                "pattern_similarity": round(random.uniform(0.6, 0.88), 3) if is_edge_case else round(random.uniform(0.9, 0.995), 3),
                "ai_generated_signal": round(random.uniform(0.3, 0.55), 3) if is_edge_case else round(random.uniform(0.02, 0.28), 3),
                "is_fraud": 0,
                "attack_type": "none",
                "generated_by": "legit_customer_activity",
                "token_record_id": None,
            }
            transactions.append(tx)
    return transactions[:max_transactions] if len(transactions) > max_transactions else transactions
