"""
Seven fraud-simulation agents, each bounded by a signed authorization
token from an external authority (see ../../sign/src/authority_signer.py).

The key property demonstrated here: an agent cannot exceed the operation
count written into its own signed token. The enforcement isn't "the agent
promises to behave", it's a hard check against a number that came from
outside the agent and that the agent cannot rewrite.

Agents 1, 2, and 4 call the real OpenAI API (see llm_client.py) to
generate realistic synthetic content. Agents 5 and 6 are local/statistical
by design: transaction amounts and injection payloads should follow real
distributions and known public techniques, not creative LLM text. Agents
3 and 7 need a trained detector to exist first (see ../../detect), so
their classes live here but they only run after the detect layer has
trained a model.
"""

import json
import random
import sys
import time
import uuid
from pathlib import Path

# Agents get their bounded authorization tokens from the sign layer, and
# their execution logs are written alongside those tokens (sign/tokens/)
# so a signed token and the log of what its agent actually did sit next
# to each other for easy audit.
_SIGN_SRC = Path(__file__).resolve().parent.parent.parent / "sign" / "src"
if str(_SIGN_SRC) not in sys.path:
    sys.path.insert(0, str(_SIGN_SRC))

import authority_signer as auth  # noqa: E402
import signature_verifier as verify  # noqa: E402
import llm_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent  # generate/
DATA_DIR = ROOT / "data"
TOKENS_DIR = auth.TOKENS_DIR  # sign/tokens/

random.seed(42)

FIRST_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Drew", "Skyler"]
LAST_NAMES = ["Chen", "Patel", "Garcia", "Smith", "Kim", "Nguyen", "Brown", "Diaz", "Müller", "Kowalski"]
MERCHANTS = ["QuickMart", "StreamFlix", "CloudHost", "UrbanCafe", "TechBazaar", "FreshGrocer", "TravelEasy", "GameVault"]
CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY"]

FEATURE_KEYS = ["amount", "hour_of_day", "seconds_since_prev_tx", "location_mismatch_km", "pattern_similarity", "ai_generated_signal"]


class TokenLimitExceeded(Exception):
    pass


class BoundedAgent:
    """Base class: every agent must hold a signed token and cannot act
    past its max_operations. Every action is appended to an execution log
    that is written to disk for inspection."""

    def __init__(self, agent_id: str, action: str, requested_operations: int):
        self.agent_id = agent_id
        self.requested_operations = requested_operations
        # The agent ASKS for `requested_operations`; the authority decides
        # what to actually grant. Here the authority grants exactly what's
        # asked (a real deployment might grant less), but the point is the
        # grant is external and signed, not self-declared.
        self.token = auth.issue_agent_token(agent_id, action, requested_operations)
        self.executed = 0
        self.log = []

    def _check_and_count(self):
        if self.executed >= self.token["max_operations"]:
            raise TokenLimitExceeded(
                f"{self.agent_id} attempted to exceed authorized limit "
                f"of {self.token['max_operations']} operations"
            )
        self.executed += 1

    def _record(self, event: dict):
        self.log.append({"seq": self.executed, "timestamp": time.time(), **event})

    def write_log(self):
        path = TOKENS_DIR / f"{self.agent_id}_execution_log.json"
        path.write_text(
            json.dumps(
                {
                    "agent_id": self.agent_id,
                    "token_record_id": self.token["record_id"],
                    "authorized_max": self.token["max_operations"],
                    "actually_executed": self.executed,
                    "within_bounds": self.executed <= self.token["max_operations"],
                    "signature_verifies": verify.verify_record(dict(self.token), "authority"),
                    "events": self.log,
                },
                indent=2,
            )
        )


def _tx_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _batched(total_n, batch_size, generate_batch):
    """Call generate_batch(count) repeatedly in chunks instead of one giant
    request. A single call asking for hundreds of items risks the model's
    response getting cut off mid-JSON and failing to parse; batches of 25
    stay comfortably inside the output limit regardless of how verbose
    each item's schema is."""
    items = []
    while len(items) < total_n:
        remaining = total_n - len(items)
        batch = generate_batch(min(batch_size, remaining))
        if not batch:
            break
        items.extend(batch)
    return items[:total_n]


# ---------------------------------------------------------------------------
# Agent 1: Fake Identity Generator (REAL, GPT-4o-mini)
# ---------------------------------------------------------------------------
class FakeIdentityAgent(BoundedAgent):
    """Calls the OpenAI API to fabricate coherent synthetic identities,
    then generates a handful of transactions per identity. Hard to catch
    because each individual transaction looks ordinary; the tell is that
    the *identity itself* has no history before it suddenly appears."""

    def __init__(self, max_identities: int = 10):
        super().__init__("agent1_fake_identity", "generate_fake_identities", max_identities)

    def _generate_identities_via_openai(self, n, seed_profiles):
        avg_spend = sum(s["avg_amount"] for s in seed_profiles) / len(seed_profiles)
        result = llm_client.call_json(
            system_prompt=(
                "You generate synthetic customer identities for a fraud-detection red-team "
                "exercise at a payment company. These are fictional people, not real individuals. "
                "Output only JSON."
            ),
            user_prompt=(
                f"Generate {n} coherent synthetic customer identities. Real customers at this "
                f"merchant spend around ${avg_spend:.0f} per transaction on average. For each "
                'identity include: "full_name", "typical_monthly_spend_usd" (a plausible number '
                'near that average), "typical_hour_of_day" (0-23), and "currency" (one of USD, '
                'EUR, GBP, INR, JPY). Respond as JSON: {"identities": [...]}.'
            ),
            purpose="Agent 1: Fake Identity Generation",
        )
        return result.get("identities", [])[:n]

    def run(self, seed_profiles, tx_per_identity=(4, 8)):
        n = min(len(seed_profiles), self.token["max_operations"])
        identities = _batched(n, 25, lambda k: self._generate_identities_via_openai(k, seed_profiles))
        (DATA_DIR / "fake_identities.json").write_text(json.dumps(identities, indent=2))

        transactions = []
        for identity in identities:
            self._check_and_count()
            fake_name = identity.get("full_name") or f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            fake_id = f"cust_fake_{uuid.uuid4().hex[:8]}"
            n_tx = random.randint(*tx_per_identity)
            base_amount = max(5.0, float(identity.get("typical_monthly_spend_usd", 100)) / 4)
            for _ in range(n_tx):
                tx = {
                    "transaction_id": _tx_id("tx"),
                    "customer_id": fake_id,
                    "customer_name": fake_name,
                    "amount": round(max(1.0, random.gauss(base_amount, base_amount * 0.15)), 2),
                    "currency": identity.get("currency", "USD"),
                    "merchant": random.choice(MERCHANTS),
                    "hour_of_day": int(identity.get("typical_hour_of_day", random.randint(8, 22))) % 24,
                    "seconds_since_prev_tx": round(random.uniform(3600, 86400), 1),
                    "location_mismatch_km": round(random.uniform(0, 15), 1),
                    "pattern_similarity": round(random.uniform(0.75, 0.97), 3),
                    "ai_generated_signal": round(random.uniform(0.10, 0.45), 3),
                    "is_fraud": 1,
                    "attack_type": "fake_identity",
                    "generated_by": self.agent_id,
                    "token_record_id": self.token["record_id"],
                }
                transactions.append(tx)
            self._record({"event": "fake_identity_created", "fake_customer_id": fake_id, "tx_generated": n_tx, "openai_identity": fake_name})
        self.write_log()
        return transactions


# ---------------------------------------------------------------------------
# Agent 2: Social Engineer (REAL, GPT-4o-mini)
# ---------------------------------------------------------------------------
class SocialEngineerAgent(BoundedAgent):
    """Calls the OpenAI API to generate fictional customer-support call
    transcripts where a caller attempts social engineering tactics
    (urgency, impersonation, fabricated emergencies) to get a support
    agent to reveal a recovery code or authorize a card reissue. Text
    transcripts only; no audio, no real people, no real support systems
    are contacted."""

    def __init__(self, max_conversations: int = 8):
        super().__init__("agent2_social_engineer", "generate_social_engineering_transcripts", max_conversations)

    def _generate_conversations_via_openai(self, n):
        result = llm_client.call_json(
            system_prompt=(
                "You generate fictional, synthetic customer-support call transcripts for a "
                "fraud-detection red-team exercise at a payment company. This is training data "
                "for a detector to recognize social engineering patterns, not a real interaction. "
                "No real people, companies, or account data. Output only JSON."
            ),
            user_prompt=(
                f"Generate {n} short call-center transcripts where a caller (the attacker) tries "
                "a social engineering tactic on a support agent to get an account recovery code, "
                "a security-question reset, or a card reissue authorized. For each include: "
                '"tactic" (short label, e.g. "urgency", "impersonating IT", "fake charity '
                'emergency"), "transcript" (8-14 lines, alternating "AGENT:" and "CALLER:" '
                'prefixes), and "outcome" ("succeeded" or "failed"). Published call-center '
                "red-team studies find social engineering succeeds against live agents a "
                "meaningful fraction of the time, it is not a solved problem. Reflect that "
                'realistically: across the batch, roughly 40-60% of "outcome" values should be '
                '"succeeded", not a rate you pick to make the story convenient. Respond as JSON: '
                '{"conversations": [...]}.'
            ),
            purpose="Agent 2: Social Engineering Transcripts",
        )
        return result.get("conversations", [])[:n]

    def run(self, seed_profiles):
        n = min(self.token["max_operations"], self.requested_operations)
        conversations = _batched(n, 25, self._generate_conversations_via_openai)
        (DATA_DIR / "social_engineering_transcripts.json").write_text(json.dumps(conversations, indent=2))

        transactions = []
        for convo in conversations:
            self._check_and_count()
            self._record({"event": "transcript_generated", "tactic": convo.get("tactic"), "outcome": convo.get("outcome")})
            if convo.get("outcome") != "succeeded":
                continue
            seed = random.choice(seed_profiles)
            tx = {
                "transaction_id": _tx_id("tx"),
                "customer_id": seed["customer_id"],
                "customer_name": seed.get("customer_name", "Account Takeover Victim"),
                "amount": round(max(5.0, random.gauss(seed["avg_amount"] * 2.5, seed["avg_amount"])), 2),
                "currency": seed.get("currency", "USD"),
                "merchant": random.choice(MERCHANTS),
                "hour_of_day": random.randint(0, 5),
                "seconds_since_prev_tx": round(random.uniform(30, 600), 1),
                "location_mismatch_km": round(random.uniform(500, 6000), 1),
                "pattern_similarity": round(random.uniform(0.2, 0.5), 3),
                "ai_generated_signal": round(random.uniform(0.3, 0.6), 3),
                "is_fraud": 1,
                "attack_type": "social_engineering",
                "tactic": convo.get("tactic"),
                "generated_by": self.agent_id,
                "token_record_id": self.token["record_id"],
            }
            transactions.append(tx)
        self.write_log()
        return transactions


# ---------------------------------------------------------------------------
# Agent 3: Limit Prober (REAL, tests OUR trained detector, not GPT)
# ---------------------------------------------------------------------------
class LimitProberAgent(BoundedAgent):
    """Runs after the detect layer's model is trained. Submits test
    transactions at increasing amounts, holding every other feature at
    the legitimate population's median, and reads back the detector's own
    score. This is an honest attack: probing our own real detector to
    find its decision boundary, not a fabricated external API."""

    def __init__(self, amounts, max_probes=None):
        super().__init__("agent3_limit_prober", "probe_detection_thresholds", max_probes or len(amounts))
        self.amounts = amounts[: self.token["max_operations"]]

    def run(self, neutral_features, model, decision_for_score_fn):
        results = []
        for amount in self.amounts:
            self._check_and_count()
            row = dict(neutral_features)
            row["amount"] = amount
            import numpy as np

            feature_vector = np.array([[
                row["amount"], row["hour_of_day"], np.log1p(row["seconds_since_prev_tx"]),
                row["location_mismatch_km"], row["pattern_similarity"], row["ai_generated_signal"],
            ]])
            score = float(model.predict_proba(feature_vector)[0][1])
            decision = decision_for_score_fn(score)
            results.append({"amount": amount, "score": round(score, 4), "decision": decision})
            self._record({"event": "probe", "amount": amount, "score": round(score, 4), "decision": decision})
        self.write_log()
        return results


# ---------------------------------------------------------------------------
# Agent 4: KYC Forger (REAL, GPT-4o-mini)
# ---------------------------------------------------------------------------
class KYCForgerAgent(BoundedAgent):
    """Calls the OpenAI API to generate synthetic identity bundles
    (metadata only, no images) internally consistent enough to plausibly
    pass basic automated format checks, then hands them to our own
    detector to see how many it flags as synthetic."""

    def __init__(self, max_kyc: int = 10):
        super().__init__("agent4_kyc_forger", "generate_synthetic_kyc_bundles", max_kyc)

    def _generate_bundles_via_openai(self, n):
        result = llm_client.call_json(
            system_prompt=(
                "You generate synthetic identity metadata bundles for a fraud-detection "
                "red-team exercise testing whether a detector can distinguish coherent-but-fake "
                "identities from real ones. Fictional data only, no real addresses or real "
                "people. Output only JSON."
            ),
            user_prompt=(
                f"Generate {n} synthetic identity bundles. For each include: \"full_name\", "
                '"date_of_birth" (ISO date), "city", "country", "stated_occupation", '
                '"stated_annual_income_usd", and a one-sentence "coherence_notes" explaining why '
                "the fields are internally consistent (age fits occupation, income fits the "
                'city\'s cost of living, etc). Respond as JSON: {"bundles": [...]}.'
            ),
            purpose="Agent 4: KYC Bundle Generation",
        )
        return result.get("bundles", [])[:n]

    def run(self):
        n = min(self.token["max_operations"], self.requested_operations)
        bundles = _batched(n, 25, self._generate_bundles_via_openai)
        (DATA_DIR / "kyc_bundles.json").write_text(json.dumps(bundles, indent=2))

        transactions = []
        for bundle in bundles:
            self._check_and_count()
            income = float(bundle.get("stated_annual_income_usd", 40000) or 40000)
            base_amount = max(5.0, income / 240)
            tx = {
                "transaction_id": _tx_id("tx"),
                "customer_id": f"cust_kyc_{uuid.uuid4().hex[:8]}",
                "customer_name": bundle.get("full_name", "Synthetic Applicant"),
                "amount": round(max(1.0, random.gauss(base_amount, base_amount * 0.2)), 2),
                "currency": "USD",
                "merchant": random.choice(MERCHANTS),
                "hour_of_day": random.randint(8, 21),
                "seconds_since_prev_tx": round(random.uniform(3600, 172800), 1),
                "location_mismatch_km": round(random.uniform(0, 20), 1),
                "pattern_similarity": round(random.uniform(0.7, 0.93), 3),
                "ai_generated_signal": round(random.uniform(0.35, 0.65), 3),
                "is_fraud": 1,
                "attack_type": "kyc_synthetic",
                "generated_by": self.agent_id,
                "token_record_id": self.token["record_id"],
            }
            transactions.append(tx)
            self._record({"event": "kyc_bundle_generated", "full_name": bundle.get("full_name")})
        self.write_log()
        return transactions


# ---------------------------------------------------------------------------
# Agent 5: Spending Pattern Replicator (local / statistical, no LLM)
# ---------------------------------------------------------------------------
class PatternReplicatorAgent(BoundedAgent):
    """Given a real (stolen) transaction history, replays the same
    amount/timing/merchant *shape* at high velocity, the classic
    card-testing-then-draining pattern. Deliberately statistical rather
    than LLM-generated: transaction amounts should follow the real
    distribution being copied, not creative text generation."""

    def __init__(self, max_transactions: int = 1000):
        super().__init__("agent5_pattern_replicator", "copy_spending_pattern", max_transactions)

    def run(self, stolen_card_histories, target_count: int):
        target_count = min(target_count, self.token["max_operations"])
        transactions = []
        history_idx = 0
        while len(transactions) < target_count:
            history = stolen_card_histories[history_idx % len(stolen_card_histories)]
            history_idx += 1
            self._check_and_count()
            amount = round(max(1.0, random.gauss(history["avg_amount"], history["avg_amount"] * 0.2)), 2)
            # ~35% of the campaign runs "low and slow" to evade velocity
            # checks, spacing transactions out like a genuine customer would.
            evasive = random.random() < 0.35
            tx = {
                "transaction_id": _tx_id("tx"),
                "customer_id": history["customer_id"],
                "customer_name": history.get("customer_name", "Stolen Card Holder"),
                "amount": amount,
                "currency": history.get("currency", "USD"),
                "merchant": random.choice(MERCHANTS),
                "hour_of_day": random.randint(0, 23),
                "seconds_since_prev_tx": round(random.uniform(1800, 25000), 1) if evasive else round(random.uniform(0.5, 45), 2),
                "location_mismatch_km": round(random.uniform(5, 60), 1) if random.random() < 0.7 else round(random.uniform(300, 3000), 1),
                "pattern_similarity": round(random.uniform(0.65, 0.94), 3),
                "ai_generated_signal": round(random.uniform(0.20, 0.55), 3),
                "is_fraud": 1,
                "attack_type": "pattern_copy",
                "generated_by": self.agent_id,
                "token_record_id": self.token["record_id"],
            }
            transactions.append(tx)
            self._record({"event": "pattern_tx_generated", "source_customer": history["customer_id"]})
        self.write_log()
        return transactions


# ---------------------------------------------------------------------------
# Agent 6: Injection Attack Generator (local, known public payloads, no LLM)
# ---------------------------------------------------------------------------
class InjectionGeneratorAgent(BoundedAgent):
    """Throws malformed / adversarial input at a payment form using known,
    publicly documented payload techniques (SQL injection, script tags,
    boundary values), not GPT output, these are standard security-testing
    strings. Loud and easy to catch individually, but used to find the one
    gap that lets later attacks through quietly."""

    PAYLOADS = [
        "' OR '1'='1", "<script>alert(1)</script>", "../../etc/passwd",
        "0" * 40, "-999999.99", "9" * 20 + ".00", "NaN", "Infinity",
        "'; DROP TABLE transactions;--", "‮99.9‮", "0x41414141",
    ]

    def __init__(self, max_attempts: int = 1000):
        super().__init__("agent6_injection_generator", "probe_payment_form", max_attempts)

    def run(self, form_fields, target_count: int):
        target_count = min(target_count, self.token["max_operations"])
        transactions = []
        for _ in range(target_count):
            self._check_and_count()
            field = random.choice(form_fields)
            payload = random.choice(self.PAYLOADS)
            amount_field_hit = field == "amount"
            try:
                amount = abs(float(payload)) if amount_field_hit and payload.replace(".", "", 1).lstrip("-").isdigit() else round(random.uniform(1, 500), 2)
            except ValueError:
                amount = round(random.uniform(1, 500), 2)
            tx = {
                "transaction_id": _tx_id("tx"),
                "customer_id": f"cust_probe_{uuid.uuid4().hex[:8]}",
                "customer_name": "Form Probe",
                "amount": amount,
                "currency": random.choice(CURRENCIES + ["XXX", "???"]),
                "merchant": random.choice(MERCHANTS),
                "hour_of_day": random.randint(0, 23),
                "seconds_since_prev_tx": round(random.uniform(0.1, 5), 2),
                "location_mismatch_km": round(random.uniform(0, 8000), 1),
                "pattern_similarity": round(random.uniform(0.05, 0.4), 3),
                "ai_generated_signal": round(random.uniform(0.6, 0.95), 3),
                "is_fraud": 1,
                "attack_type": "form_break",
                "probed_field": field,
                "payload_sample": payload,
                "generated_by": self.agent_id,
                "token_record_id": self.token["record_id"],
            }
            transactions.append(tx)
            self._record({"event": "malformed_attempt", "field": field})
        self.write_log()
        return transactions


# ---------------------------------------------------------------------------
# Agent 7: Feedback Loop Exploit (REAL, GPT-4o-mini + our trained detector)
# ---------------------------------------------------------------------------
class FeedbackLoopAgent(BoundedAgent):
    """Runs after the detect layer's model is trained. Takes a sample of
    transactions our own detector actually blocked, asks GPT to propose
    small, realistic feature adjustments an adversary might try, then
    re-scores each variant through our real detector to see whether it
    actually evades. Genuine adversarial robustness testing against our
    own local model, no external system involved."""

    def __init__(self, max_variants: int = 15):
        super().__init__("agent7_feedback_loop", "generate_evasion_variants", max_variants)

    def _propose_variants_via_openai(self, blocked_tx, k):
        result = llm_client.call_json(
            system_prompt=(
                "You are red-teaming a fraud detection model as part of an authorized security "
                "exercise on synthetic test data. Propose small, realistic numeric adjustments to "
                "a transaction's features. Output only JSON."
            ),
            user_prompt=(
                f"A fraud model blocked this transaction with fraud score {blocked_tx['score']:.3f}. "
                f"Its features: amount={blocked_tx['amount']}, hour_of_day={blocked_tx['hour_of_day']}, "
                f"seconds_since_prev_tx={blocked_tx['seconds_since_prev_tx']}, "
                f"location_mismatch_km={blocked_tx['location_mismatch_km']}, "
                f"pattern_similarity={blocked_tx['pattern_similarity']}, "
                f"ai_generated_signal={blocked_tx['ai_generated_signal']}. "
                f"Propose {k} variants: small, plausible adjustments to these six numeric fields "
                "(don't change amount by more than 20%) that an adversary might try to reduce the "
                'fraud score. Respond as JSON: {"variants": [{"amount":.., "hour_of_day":.., '
                '"seconds_since_prev_tx":.., "location_mismatch_km":.., "pattern_similarity":.., '
                '"ai_generated_signal":..}, ...]}.'
            ),
            purpose="Agent 7: Evasion Variant Suggestion",
        )
        return result.get("variants", [])[:k]

    def run(self, blocked_sample, model, decision_for_score_fn, variants_per_tx=3):
        import numpy as np

        report = []
        for blocked_tx in blocked_sample:
            variants = self._propose_variants_via_openai(blocked_tx, variants_per_tx)
            for variant in variants:
                if self.executed >= self.token["max_operations"]:
                    break
                self._check_and_count()
                try:
                    row = [
                        float(variant.get(k, blocked_tx[k])) for k in
                        ["amount", "hour_of_day", "seconds_since_prev_tx", "location_mismatch_km", "pattern_similarity", "ai_generated_signal"]
                    ]
                except (TypeError, ValueError):
                    continue
                feature_vector = np.array([[row[0], row[1], np.log1p(row[2]), row[3], row[4], row[5]]])
                new_score = float(model.predict_proba(feature_vector)[0][1])
                new_decision = decision_for_score_fn(new_score)
                evaded = new_decision != "BLOCK"
                report.append({
                    "transaction_id": blocked_tx["transaction_id"],
                    "original_score": blocked_tx["score"],
                    "variant_features": dict(zip(FEATURE_KEYS, row)),
                    "new_score": round(new_score, 4),
                    "new_decision": new_decision,
                    "evaded": evaded,
                })
                self._record({"event": "evasion_variant_tested", "transaction_id": blocked_tx["transaction_id"], "evaded": evaded})
        self.write_log()
        return report


def make_seed_profiles(good_transactions, n=10):
    by_customer = {}
    for tx in good_transactions:
        by_customer.setdefault(tx["customer_id"], []).append(tx)
    customers = list(by_customer.items())[:n]
    seeds = []
    for cust_id, txs in customers:
        amounts = [t["amount"] for t in txs]
        seeds.append(
            {
                "customer_id": cust_id,
                "customer_name": txs[0].get("customer_name", "Customer"),
                "avg_amount": sum(amounts) / len(amounts),
                "currency": txs[0]["currency"],
                "typical_hour": txs[0]["hour_of_day"],
            }
        )
    return seeds


def make_stolen_card_histories(good_transactions, n=25):
    by_customer = {}
    for tx in good_transactions:
        by_customer.setdefault(tx["customer_id"], []).append(tx)
    customers = list(by_customer.items())[:n]
    histories = []
    for cust_id, txs in customers:
        amounts = [t["amount"] for t in txs]
        histories.append(
            {
                "customer_id": cust_id,
                "customer_name": txs[0].get("customer_name", "Customer"),
                "avg_amount": sum(amounts) / len(amounts),
                "currency": txs[0]["currency"],
            }
        )
    return histories
