"""
Entry point: python run_pipeline.py

Orchestrates all five layers end to end:

  1. DETECT: train the RandomForest model, score each held out test
     transaction, propose BLOCK/FLAG/ALLOW.
  2. MANDATE: derive each customer's mandate from their own good
     transaction history, check the transaction against it.
  3. POLICY: detect's decision and every mandate rule's pass/fail become
     named signals evaluated against a declarative policy document (see
     policy/src/policy_engine.py). The shipped default policy
     (policy/policies/transaction-authorization/1.0.0/policy.json)
     reproduces the original rule exactly: a transaction is only ALLOWed
     if detect says ALLOW *and* every mandate rule passed. Either
     objecting is enough to BLOCK. A different --policy-id/--policy-version
     can be swapped in to get a different decision from the same signals.
  4. COMBINE: combine_decision() is a thin, behavior-preserving adapter
     over the policy layer above -- same function, same signature, now
     backed by data instead of hardcoded control flow.
  5. SIGN: the authority signs the final decision, including which
     policy and rule produced it. Nothing above is enforceable until
     this step.

Reads transaction data from ../../generate/data/, trains and saves the
detect layer model to ../../detect/models/, and writes the signed
decision log to ./decisions/pipeline_decisions.json.
"""

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SRC_DIR.parent
REPO_ROOT = PIPELINE_ROOT.parent

for _layer in ("detect", "mandate", "sign", "generate", "policy"):
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
import audit_trail  # noqa: E402
import caller_auth  # noqa: E402
import policy_engine  # noqa: E402
import policy_loader  # noqa: E402

DATA_DIR = REPO_ROOT / "generate" / "data"

DEFAULT_POLICY_ID = "transaction-authorization"
DEFAULT_POLICY_VERSION = "1.0.0"
DEFAULT_POLICY = policy_loader.load_policy(DEFAULT_POLICY_ID, DEFAULT_POLICY_VERSION)

_OUTCOME_TO_DECISION = {
    policy_engine.APPROVE: "ALLOW",
    policy_engine.REQUIRE_OVERRIDE: "FLAG",
    policy_engine.REJECT: "BLOCK",
}


def load(name):
    path = DATA_DIR / name
    if not path.exists():
        raise RuntimeError(
            f"{path} not found. Run the generate layer first to produce transaction data."
        )
    return json.loads(path.read_text())


def build_policy_signals(detect_decision, mandate_result, fraud_score=None, amount=None):
    """Reshape what detect and mandate already computed into the flat
    signal bag a policy document evaluates against. No new computation:
    every mandate rule's pass/fail (mandate_result["checks"]) becomes its
    own named boolean signal, exactly like detect_decision and
    mandate_allowed -- the policy engine treats all of them the same way,
    it has no built-in notion of "detector" vs "mandate"."""
    signals = {
        "detect_decision": detect_decision,
        "mandate_allowed": mandate_result["mandate_allowed"],
    }
    for check in mandate_result.get("checks", []):
        signals[check["rule"]] = check["passed"]
    if fraud_score is not None:
        signals["fraud_score"] = fraud_score
    if amount is not None:
        signals["amount"] = amount
    return signals


def decide(detect_decision, mandate_result, fraud_score=None, amount=None, policy=None):
    """Evaluate the given policy (default: DEFAULT_POLICY) against the
    signals built from this transaction's detect + mandate results.
    Returns the full policy_engine.evaluate_policy result, including
    policy_id/policy_version/matched_rule_id -- everything the sign layer
    needs to make the policy that produced this decision tamper evident
    too, not just the decision itself."""
    signals = build_policy_signals(detect_decision, mandate_result, fraud_score=fraud_score, amount=amount)
    return policy_engine.evaluate_policy(policy or DEFAULT_POLICY, signals)


def combine_decision(detect_decision, mandate_result, fraud_score=None, amount=None, policy=None):
    """BLOCK wins over everything: either layer objecting blocks the
    transaction. FLAG only happens when detect is unsure AND mandate has
    no objection. A clean mandate doesn't downgrade a detect BLOCK, and
    a clean detect score doesn't upgrade a mandate violation past BLOCK.

    This is now a thin adapter over the policy layer (policy/src/policy_engine.py):
    the shipped DEFAULT_POLICY re-encodes exactly this behavior as data
    instead of the if/else this function used to contain directly. Same
    signature, same return values as before -- swap in a different
    `policy` document and the same detect/mandate signals can produce a
    different decision, which is the point (see decide() above for the
    full policy result, including which rule matched and why)."""
    result = decide(detect_decision, mandate_result, fraud_score=fraud_score, amount=amount, policy=policy)
    return _OUTCOME_TO_DECISION[result["outcome"]]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the detect -> mandate -> sign pipeline.")
    parser.add_argument(
        "--caller-id",
        default=None,
        help=(
            "Identity requesting this pipeline run (see sign/src/caller_auth.py). "
            "Must be a registered caller (e.g. fraud-analyst, payment-processor, "
            "audit-system). Optional; omitted runs are signed with no caller_id, "
            "same as before this flag existed."
        ),
    )
    parser.add_argument(
        "--policy-id",
        default=DEFAULT_POLICY_ID,
        help=(
            "Policy document to evaluate every transaction against (see "
            "policy/policies/<policy-id>/<policy-version>/policy.json). "
            f"Defaults to {DEFAULT_POLICY_ID!r}."
        ),
    )
    parser.add_argument(
        "--policy-version",
        default=DEFAULT_POLICY_VERSION,
        help=f"Version of --policy-id to load. Defaults to {DEFAULT_POLICY_VERSION!r}.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    caller_id = args.caller_id
    if caller_id is not None and caller_id not in caller_auth.AUTHENTICATOR._registry:
        raise SystemExit(
            f"Unknown --caller-id {caller_id!r}. Registered callers: "
            f"{sorted(caller_auth.AUTHENTICATOR._registry)}"
        )

    if args.policy_id == DEFAULT_POLICY_ID and args.policy_version == DEFAULT_POLICY_VERSION:
        selected_policy = DEFAULT_POLICY
    else:
        selected_policy = policy_loader.load_policy(args.policy_id, args.policy_version)

    print("=" * 70)
    print("PIPELINE: Detect -> Mandate -> Policy -> Sign")
    print(f"Policy: {selected_policy['policyId']}@{selected_policy['policyVersion']}")
    if caller_id:
        print(f"Caller: {caller_id}")
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

    print("\n[3/4] Deriving customer mandates from their good transaction history...")
    by_customer_good = {}
    for tx in good:
        by_customer_good.setdefault(tx["customer_id"], []).append(tx)
    mandates = {cust_id: mc.derive_mandate_from_history(txs) for cust_id, txs in by_customer_good.items()}
    print(f"      -> {len(mandates)} customer mandates derived")

    print("\n[4/4] Combining detect + mandate, signing every final decision...")
    # Running per customer totals for this run only, walked in test set
    # order. The synthetic data has no real timestamps (only hour_of_day),
    # so this is a simplified sequential walk, not true chronological
    # replay. Good enough to demonstrate spending limit and velocity
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

        policy_result = decide(
            detect_decision,
            mandate_result,
            fraud_score=score,
            amount=tx["amount"],
            policy=selected_policy,
        )
        final_decision = _OUTCOME_TO_DECISION[policy_result["outcome"]]

        # A blocked transaction shouldn't count against the customer's
        # budget or daily count. It never actually went through.
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
            caller_id=caller_id,
            policy_id=policy_result["policy_id"],
            policy_version=policy_result["policy_version"],
            matched_rule_id=policy_result["matched_rule_id"],
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

    trail = audit_trail.AuditTrail()
    appended = trail.append_many(entries)
    print(f"      appended {appended} new decisions to append only audit trail: {trail.path}")

    verified_count = sum(1 for e in entries if verify.verify_record(dict(e["decision"]), "authority"))
    print(f"\nVerification: {verified_count}/{len(entries)} signatures verify independently (public key check only)")

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
