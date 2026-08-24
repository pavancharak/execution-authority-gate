"""
Entry point: python build_demo_data.py

Builds two small, static JSON files for the web dashboard's interactive
demo (Attack Walkthrough + Live Test Harness), from real artifacts this
repo's own pipeline already produced — nothing here is hand-authored:

  web/data/attack_scenarios.json — one real, already-signed decision per
    attack type, pulled straight from pipeline/decisions/pipeline_decisions.json,
    merged with the attack's narrative from identify/attacks.json.

  web/data/demo_customers.json — a small, curated set of real customers'
    derived mandates (see mandate/src/mandate_checker.py), for the Live
    Test Harness's customer picker. Deliberately small and committed
    (unlike the full generate/data/ dataset) so it can ship in the
    deployed image without bundling the whole synthetic dataset.

Requires pipeline/decisions/pipeline_decisions.json and generate/data/
to already exist (run generate/src/run_simulation.py and
pipeline/src/run_pipeline.py first).
"""

import json
import random
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SRC_DIR.parent
REPO_ROOT = PIPELINE_ROOT.parent

for _layer in ("mandate", "sign"):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))

import mandate_checker as mc  # noqa: E402
import signature_verifier as verify  # noqa: E402

IDENTIFY_DIR = REPO_ROOT / "identify"
GENERATE_DATA_DIR = REPO_ROOT / "generate" / "data"
DECISIONS_PATH = PIPELINE_ROOT / "decisions" / "pipeline_decisions.json"
WEB_DATA_DIR = REPO_ROOT / "web" / "data"

# Prefer a BLOCK example for drama, except pattern_copy — its one ALLOW
# example (out of 28 real generated instances) is a more interesting
# story: a copied spending pattern legitimate enough to slip the detect
# layer, still a real outcome from a real run.
PREFERRED_DECISION = {
    "fake_identity": "BLOCK",
    "social_engineering": "BLOCK",
    "kyc_synthetic": "BLOCK",
    "pattern_copy": "ALLOW",
    "form_break": "BLOCK",
}

RULE_LABELS = {
    "spending_limit": "Spending limit",
    "merchant_whitelist": "Merchant whitelist",
    "time_restriction": "Time-of-day window",
    "velocity": "Daily velocity",
}


def build_scenarios(rng):
    attacks = json.loads((IDENTIFY_DIR / "attacks.json").read_text())
    decisions = json.loads(DECISIONS_PATH.read_text())

    by_type = {}
    for e in decisions:
        by_type.setdefault(e["ground_truth"]["attack_type"], []).append(e)

    scenarios = []
    for attack in attacks:
        candidates = by_type.get(attack["id"])
        if not candidates:
            continue
        preferred = PREFERRED_DECISION.get(attack["id"])
        pool = [c for c in candidates if c["decision"]["final_decision"] == preferred] or candidates
        example = rng.choice(pool)
        example["verified"] = verify.verify_record(dict(example["decision"]), "authority")

        scenarios.append(
            {
                "id": attack["id"],
                "name": attack["name"],
                "stage": attack["stage"],
                "why_hard_to_catch": attack["why_hard_to_catch"],
                "example": example,
            }
        )
    return scenarios


def build_demo_customers(rng, count=6):
    good = json.loads((GENERATE_DATA_DIR / "good_transactions.json").read_text())

    by_customer = {}
    for tx in good:
        by_customer.setdefault(tx["customer_id"], []).append(tx)

    # Only customers with a reasonable amount of history make an
    # interesting demo mandate (tight-enough limits to actually trigger
    # PASS/FAIL depending on what the judge types into the form).
    eligible = [cid for cid, txs in by_customer.items() if len(txs) >= 6]
    chosen = rng.sample(eligible, min(count, len(eligible)))

    customers = []
    for cid in chosen:
        txs = by_customer[cid]
        mandate = mc.derive_mandate_from_history(txs)
        customers.append(
            {
                "customer_id": cid,
                "customer_name": txs[0]["customer_name"],
                "transaction_count": len(txs),
                "mandate": mandate,
            }
        )
    return customers


def all_merchants(customers):
    seen = set()
    merchants = []
    for c in customers:
        for m in c["mandate"]["allowed_merchants"] or []:
            if m not in seen:
                seen.add(m)
                merchants.append(m)
    return sorted(merchants)


def main():
    rng = random.Random(11)

    scenarios = build_scenarios(rng)
    customers = build_demo_customers(rng)

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DATA_DIR / "attack_scenarios.json").write_text(json.dumps(scenarios, indent=2))
    (WEB_DATA_DIR / "demo_customers.json").write_text(
        json.dumps({"customers": customers, "merchants": all_merchants(customers)}, indent=2)
    )

    print(f"wrote {len(scenarios)} attack scenarios -> web/data/attack_scenarios.json")
    print(f"wrote {len(customers)} demo customers -> web/data/demo_customers.json")


if __name__ == "__main__":
    main()
