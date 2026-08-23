"""
Entry point: python run_simulation.py

Runs five bounded fraud agents (1, 2, 4, 5, 6) against a pool of
legitimate transaction data. Agents 3 (Limit Prober) and 7 (Feedback Loop
Exploit) need a trained detector to exist first — see probe_agents.py,
run after this.

Produces:
  - ../data/good_transactions.json
  - ../data/fraud_transactions.json
  - ../data/fake_identities.json, social_engineering_transcripts.json, kyc_bundles.json
  - ../../sign/tokens/*_auth_token.json     (signed authorization for each agent)
  - ../../sign/tokens/*_execution_log.json  (proof each agent stayed in bounds)

Agents 1, 2, and 4 call the real OpenAI API (see llm_client.py). Set
OPENAI_API_KEY in a repo-root .env file before running (copy .env.example).

Targets are chosen so the 5 attack types that actually produce labeled
fraud transactions (agents 1, 2, 4, 5, 6 — agents 3 and 7 probe the
trained model instead of generating transactions) land close to even at
~100 each, and the legitimate pool is scaled up (free, local — no
OpenAI cost) to bring the overall fraud rate down to a realistic ~2%,
rather than shrinking the fraud count down to statistically meaningless
levels to hit that rate.
"""

import json
import random
from pathlib import Path

from data_generator import generate_good_transactions
from fraud_agents import (
    FakeIdentityAgent,
    SocialEngineerAgent,
    KYCForgerAgent,
    PatternReplicatorAgent,
    InjectionGeneratorAgent,
    make_seed_profiles,
    make_stolen_card_histories,
)

ROOT = Path(__file__).resolve().parent.parent  # generate/
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

FORM_FIELDS = ["amount", "currency", "card_number", "cvv", "billing_zip", "customer_name"]

RAW_FEATURE_FIELDS = [
    "amount", "hour_of_day", "seconds_since_prev_tx",
    "location_mismatch_km", "pattern_similarity", "ai_generated_signal",
]


def inject_realistic_confusion(good, fraud, fraud_camouflage_rate=0.15, legit_anomaly_rate=0.05, seed=17):
    """No feature set catches everything. To keep the detector's reported
    accuracy honest rather than an artifact of clean synthetic separation,
    some fraud (fake-identity and pattern-copy only, not the loud
    form-breaker) is given feature values copied from a real legitimate
    transaction — genuinely indistinguishable behavior, same as a
    well-disguised attacker in production. Symmetrically, some legitimate
    transactions get feature values copied from fraud — genuinely
    anomalous-but-legitimate behavior, the real source of false positives.
    Labels (is_fraud) never change; only the observable features do."""
    rnd = random.Random(seed)
    good = [dict(t) for t in good]
    fraud = [dict(t) for t in fraud]

    camouflage_pool = [t for t in fraud if t["attack_type"] in ("fake_identity", "pattern_copy")]
    for tx in rnd.sample(camouflage_pool, int(len(camouflage_pool) * fraud_camouflage_rate)):
        donor = rnd.choice(good)
        for f in RAW_FEATURE_FIELDS:
            tx[f] = donor[f]

    for tx in rnd.sample(good, int(len(good) * legit_anomaly_rate)):
        donor = rnd.choice(fraud)
        for f in RAW_FEATURE_FIELDS:
            tx[f] = donor[f]

    return good, fraud


def main():
    print("=" * 70)
    print("GENERATE LAYER: Simulation Run")
    print("=" * 70)

    import llm_client
    llm_client.reset_log()

    print("\n[1/6] Generating legitimate transaction population...")
    # Scaled up (free, local) so a ~500-transaction fraud population lands
    # at a realistic ~2% fraud rate instead of needing to shrink fraud
    # down to a handful of examples, which would make recall/FPR
    # statistically meaningless (a single misclassified example swinging
    # the headline number by several points).
    good_transactions = generate_good_transactions(n_customers=5000, avg_tx_per_customer=5, max_transactions=30000)
    (DATA_DIR / "good_transactions.json").write_text(json.dumps(good_transactions, indent=2))
    print(f"      -> {len(good_transactions)} legitimate transactions written to data/good_transactions.json")

    seeds = make_seed_profiles(good_transactions, n=40)
    histories = make_stolen_card_histories(good_transactions, n=25)

    # The 5 attack types below are the only ones that produce labeled
    # fraud transactions (agent 3 probes the trained model's decision
    # boundary, agent 7 tests evasion — neither generates a labeled
    # transaction; see identify/attack-taxonomy.md). Targets are chosen
    # per type's real yield so the ~100-target lands close to even:
    # FakeIdentityAgent produces ~4-8 tx per identity, SocialEngineerAgent
    # only ~40-60% of conversations succeed into a transaction, KYCForger
    # is 1:1. Agents 1/2/4 batch up to 25 items per real OpenAI call, so
    # even these larger targets are only a handful of calls.
    print("\n[2/6] Agent 1 (Fake Identity Generator, REAL OpenAI call) requesting token...")
    agent1 = FakeIdentityAgent(max_identities=17)
    print(f"      -> token granted: max_operations={agent1.token['max_operations']}, signed record_id={agent1.token['record_id']}")
    fraud_identity = agent1.run(seeds)
    print(f"      -> executed {agent1.executed}/{agent1.token['max_operations']} authorized identities, producing {len(fraud_identity)} transactions")

    print("\n[3/6] Agent 2 (Social Engineer, REAL OpenAI call) requesting token...")
    agent2 = SocialEngineerAgent(max_conversations=200)
    print(f"      -> token granted: max_operations={agent2.token['max_operations']}, signed record_id={agent2.token['record_id']}")
    fraud_social = agent2.run(seeds)
    print(f"      -> executed {agent2.executed}/{agent2.token['max_operations']} authorized transcripts, {len(fraud_social)} led to a follow-up transaction")

    print("\n[4/6] Agent 4 (KYC Forger, REAL OpenAI call) requesting token...")
    agent4 = KYCForgerAgent(max_kyc=100)
    print(f"      -> token granted: max_operations={agent4.token['max_operations']}, signed record_id={agent4.token['record_id']}")
    fraud_kyc = agent4.run()
    print(f"      -> executed {agent4.executed}/{agent4.token['max_operations']} authorized bundles, producing {len(fraud_kyc)} transactions")

    print("\n[5/6] Agent 5 (Pattern Replicator, local/statistical) requesting token...")
    agent5 = PatternReplicatorAgent(max_transactions=1000)
    print(f"      -> token granted: max_operations={agent5.token['max_operations']}, signed record_id={agent5.token['record_id']}")
    fraud_pattern = agent5.run(histories, target_count=100)
    print(f"      -> executed {agent5.executed}/{agent5.token['max_operations']} authorized transactions, producing {len(fraud_pattern)}")

    print("\n[6/6] Agent 6 (Injection Attack Generator, known public payloads) requesting token...")
    agent6 = InjectionGeneratorAgent(max_attempts=1000)
    print(f"      -> token granted: max_operations={agent6.token['max_operations']}, signed record_id={agent6.token['record_id']}")
    fraud_form = agent6.run(FORM_FIELDS, target_count=100)
    print(f"      -> executed {agent6.executed}/{agent6.token['max_operations']} authorized attempts, producing {len(fraud_form)}")

    fraud_transactions = fraud_identity + fraud_social + fraud_kyc + fraud_pattern + fraud_form

    print("\n[confusion] Injecting realistic feature overlap (camouflaged fraud + anomalous-but-legit)...")
    good_transactions, fraud_transactions = inject_realistic_confusion(good_transactions, fraud_transactions)
    (DATA_DIR / "good_transactions.json").write_text(json.dumps(good_transactions, indent=2))
    (DATA_DIR / "fraud_transactions.json").write_text(json.dumps(fraud_transactions, indent=2))

    totals = llm_client.session_totals()

    total_tx = len(good_transactions) + len(fraud_transactions)
    fraud_rate = len(fraud_transactions) / total_tx
    breakdown = {}
    for tx in fraud_transactions:
        breakdown[tx["attack_type"]] = breakdown.get(tx["attack_type"], 0) + 1

    print(f"\nDataset composition: {len(good_transactions)} legitimate + {len(fraud_transactions)} fraud "
          f"({total_tx} total, {fraud_rate:.2%} fraud rate)")
    print(f"Attack type breakdown: {breakdown}")
    print("Every fraudulent transaction is traceable to a signed token that bounded how many its agent could make.")
    print(f"OpenAI usage this run: {totals['calls']} calls, ~${totals['estimated_cost_usd']:.4f} estimated")
    print("Wrote data/*.json, ../../sign/tokens/*_auth_token.json, ../../sign/tokens/*_execution_log.json")
    print("\nNext: run `python ../../pipeline/src/run_pipeline.py`, then `python probe_agents.py` for Agents 3 and 7.")


if __name__ == "__main__":
    main()
