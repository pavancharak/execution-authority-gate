"""
Entry point: python run_pipeline.py

Orchestrates all four layers end to end:

  1. DETECT  — train the RandomForest model, score each held-out test
     transaction, propose BLOCK/FLAG/ALLOW.
  2. MANDATE — derive each customer's mandate from their own good-
     transaction history, check the transaction against it.
  3. COMBINE — a transaction is only ALLOWed if detect says ALLOW *and*
     mandate says allowed. Either layer objecting is enough to BLOCK.
     Neither layer's proposal is final on its own.
  4. SIGN    — the authority signs the combined decision. Nothing above
     is enforceable until this step.

Reads transaction data from ../../generate/data/, trains and saves the
detect-layer model to ../../detect/models/, and writes the signed
decision log to ./decisions/pipeline_decisions.json.
"""

import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SRC_DIR.parent
REPO_ROOT = PIPELINE_ROOT.parent

for _layer in ("detect", "mandate", "sign", "generate"):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))

import detector as det  # noqa: E402
import mandate_checker as mc  # noqa: E402
import authority_signer as auth  # noqa: E402
import signature_verifier as verify  # noqa: E402
import llm_client  # noqa: E402
import decision_log  # noqa: E402
import dashboard_builder  # noqa: E402

DATA_DIR = REPO_ROOT / "generate" / "data"


def load(name):
    path = DATA_DIR / name
    if not path.exists():
        raise RuntimeError(
            f"{path} not found. Run the generate layer first to produce transaction data."
        )
    return json.loads(path.read_text())


def combine_decision(detect_decision, mandate_result):
    """BLOCK wins over everything: either layer objecting blocks the
    transaction. FLAG only happens when detect is unsure AND mandate has
    no objection — a clean mandate doesn't downgrade a detect BLOCK, and
    a clean detect score doesn't upgrade a mandate violation past BLOCK."""
    if detect_decision == "BLOCK" or not mandate_result["mandate_allowed"]:
        return "BLOCK"
    if detect_decision == "FLAG":
        return "FLAG"
    return "ALLOW"


def main():
    print("=" * 70)
    print("PIPELINE: Detect -> Mandate -> Sign")
    print("=" * 70)

    good = load("good_transactions.json")
    fraud = load("fraud_transactions.json")
    all_tx = good + fraud
    print(f"\n[1/4] Loaded {len(good)} legitimate + {len(fraud)} fraudulent transactions")

    print("\n[2/4] Training detect layer (RandomForest)...")
    model, X_test, y_test, tx_test = det.train(all_tx)
    det.save_model(model)
    metrics = det.evaluate(model, X_test, y_test)
    scores = metrics.pop("scores")
    print(f"      fraud_caught_rate={metrics['fraud_caught_rate']:.2%}  false_positive_rate={metrics['false_positive_rate']:.2%}")

    print("\n[3/4] Deriving customer mandates from their good-transaction history...")
    by_customer_good = {}
    for tx in good:
        by_customer_good.setdefault(tx["customer_id"], []).append(tx)
    mandates = {cust_id: mc.derive_mandate_from_history(txs) for cust_id, txs in by_customer_good.items()}
    print(f"      -> {len(mandates)} customer mandates derived")

    print("\n[4/4] Combining detect + mandate, signing every final decision...")
    # Running per-customer totals for this run only, walked in test-set
    # order. The synthetic data has no real timestamps (only hour_of_day),
    # so this is a simplified sequential walk, not true chronological
    # replay — good enough to demonstrate spending-limit and velocity
    # rules firing, not a claim about real elapsed time.
    month_to_date = {}
    tx_count_today = {}
    entries = []

    for tx, score in zip(tx_test, scores):
        detect_decision = det.decision_for_score(score)
        detect_reasons = det._reasons_for(tx, model)

        cust_id = tx["customer_id"]
        mandate = mandates.get(cust_id) or mc.default_mandate(cust_id)
        mtd_total = month_to_date.get(cust_id, 0.0)
        tx_today = tx_count_today.get(cust_id, 0)
        mandate_result = mc.check_mandate(tx, mandate, month_to_date_total=mtd_total, tx_count_today=tx_today)

        final_decision = combine_decision(detect_decision, mandate_result)

        # A blocked transaction shouldn't count against the customer's
        # budget or daily count — it never actually went through.
        if final_decision != "BLOCK":
            month_to_date[cust_id] = mtd_total + tx["amount"]
            tx_count_today[cust_id] = tx_today + 1

        reasons = [f"detect: {r}" for r in detect_reasons] + [f"mandate: {r}" for r in mandate_result["violated_rules"]]
        signed = auth.sign_pipeline_decision(
            tx["transaction_id"],
            score,
            detect_decision,
            mandate_result["mandate_allowed"],
            mandate_result["violated_rules"],
            final_decision,
            reasons,
        )
        entries.append(
            {
                "decision": signed,
                "mandate_checks": mandate_result["checks"],
                "ground_truth": {
                    "is_fraud": tx["is_fraud"],
                    "attack_type": tx.get("attack_type", "none"),
                    "amount": tx["amount"],
                    "merchant": tx["merchant"],
                    "currency": tx.get("currency", "USD"),
                },
            }
        )

    summary = decision_log.summarize(entries)
    print(f"      -> {summary['total']} signed pipeline decisions: {summary['decision_counts']}")
    print(f"      block attribution: {summary['block_attribution']}")

    path = decision_log.write_log(entries)
    print(f"      wrote {path}")

    verified_count = sum(1 for e in entries if verify.verify_record(dict(e["decision"]), "authority"))
    print(f"\nVerification: {verified_count}/{len(entries)} signatures verify independently (public-key check only)")

    print("\nBuilding web dashboard...")
    verification = {
        "total": len(entries),
        "verified": verified_count,
        "all_verified": verified_count == len(entries),
    }
    dashboard_path = dashboard_builder.build(
        good_transactions=good,
        fraud_transactions=fraud,
        detect_metrics=metrics,
        mandates=mandates,
        entries=entries,
        verification=verification,
        api_activity=llm_client.load_log_summary(),
    )
    print(f"      wrote {dashboard_path}")
    print("\nOpen web/index.html (via a local server, e.g. `python -m http.server` from web/) to view it.")


if __name__ == "__main__":
    main()
