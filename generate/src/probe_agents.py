"""
Entry point: python probe_agents.py

Phase 2: red-teams our OWN trained detector. Run this after the detect
layer has trained and saved a model (e.g. after run_simulation.py +
detect/src/check_results.py or pipeline/src/run_pipeline.py).

Agent 3 (Limit Prober): submits amounts $10 to $10,000 through the real
detector, holding every other feature at the legitimate population's
median, and reads back the real decision boundary. No external API, no
fabricated sandbox — just our own model. Free.

Agent 7 (Feedback Loop Exploit): samples transactions our detector
actually blocked, asks GPT to propose small realistic feature variants,
and re-scores each variant through the real detector to see which ones
actually evade. Genuine adversarial robustness testing against our own
local model. Real OpenAI calls — kept small (a handful of blocked
transactions, a couple of variants each) since this is a real-cost proof
run, not a full-scale reproduction.

Both reports are signed by the external authority and written to
../data/probe_report.json.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _layer in ("detect", "sign"):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))

import detector as det  # noqa: E402
import authority_signer as auth  # noqa: E402
import signature_verifier as verify  # noqa: E402
import llm_client  # noqa: E402
from fraud_agents import LimitProberAgent, FeedbackLoopAgent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent  # generate/
DATA_DIR = ROOT / "data"


def _probe_amount_range(n=50, lo=10, hi=10000):
    step = (hi - lo) / (n - 1)
    return [round(lo + step * i, 2) for i in range(n)]


PROBE_AMOUNTS = _probe_amount_range(50)


def load(name):
    return json.loads((DATA_DIR / name).read_text())


def build_blocked_sample(good, fraud, model, n=3):
    """Score every transaction fresh through the trained model and pick
    the blocked ones closest to the 0.80 threshold — those are the
    genuinely testable cases. The highest-confidence blocks are trivially
    robust to small nudges, testing those would make evasion look
    artificially hard rather than showing a real adversarial result."""
    all_tx = good + fraud
    X, _y = det.build_matrix(all_tx)
    scores = model.predict_proba(X)[:, 1]

    scored = [
        {"tx": tx, "score": float(score)}
        for tx, score in zip(all_tx, scores)
        if det.decision_for_score(float(score)) == "BLOCK"
    ]
    scored.sort(key=lambda e: abs(e["score"] - 0.80))

    sample = []
    for entry in scored[:n]:
        tx = entry["tx"]
        sample.append({
            "transaction_id": tx["transaction_id"],
            "score": entry["score"],
            "amount": tx["amount"],
            "hour_of_day": tx["hour_of_day"],
            "seconds_since_prev_tx": tx["seconds_since_prev_tx"],
            "location_mismatch_km": tx["location_mismatch_km"],
            "pattern_similarity": tx["pattern_similarity"],
            "ai_generated_signal": tx["ai_generated_signal"],
        })
    return sample


def main():
    print("=" * 70)
    print("GENERATE LAYER: Red Team Run (Agents 3 and 7)")
    print("=" * 70)

    model = det.load_model()
    good = load("good_transactions.json")
    fraud = load("fraud_transactions.json")
    neutral_features = det.median_neutral_features(good)

    print("\n[1/2] Agent 3 (Limit Prober, real: tests OUR trained detector) requesting token...")
    agent3 = LimitProberAgent(PROBE_AMOUNTS)
    print(f"      -> token granted: max_operations={agent3.token['max_operations']}, signed record_id={agent3.token['record_id']}")
    probe_results = agent3.run(neutral_features, model, det.decision_for_score)
    threshold = next((r["amount"] for r in probe_results if r["decision"] == "BLOCK"), None)
    for r in probe_results[::10]:
        print(f"      ${r['amount']:>9,.2f}: score={r['score']:.3f} -> {r['decision']}")
    print(f"      -> detector starts blocking at ${threshold}" if threshold else "      -> no amount alone triggered BLOCK")

    print("\n[2/2] Agent 7 (Feedback Loop Exploit, real: GPT + OUR trained detector) requesting token...")
    blocked_sample = build_blocked_sample(good, fraud, model, n=3)
    agent7 = FeedbackLoopAgent(max_variants=10)
    print(f"      -> token granted: max_operations={agent7.token['max_operations']}, signed record_id={agent7.token['record_id']}")
    print(f"      -> sampling {len(blocked_sample)} real blocked transactions, asking GPT for evasion variants...")
    evasion_results = agent7.run(blocked_sample, model, det.decision_for_score, variants_per_tx=2)
    evaded_count = sum(1 for r in evasion_results if r["evaded"])
    print(f"      -> tested {len(evasion_results)} variants, {evaded_count} evaded detection")

    print("\nSigning both reports with the external authority...")
    signed_probe = auth.AUTHORITY.sign_record({
        "record_type": "limit_probe_report",
        "amounts_tested": [r["amount"] for r in probe_results],
        "results": probe_results,
        "threshold_amount": threshold,
    })
    signed_evasion = auth.AUTHORITY.sign_record({
        "record_type": "feedback_loop_report",
        "variants_tested": len(evasion_results),
        "variants_evaded": evaded_count,
        "results": evasion_results,
    })

    probe_report = {"limit_probe": signed_probe, "feedback_loop": signed_evasion}
    (DATA_DIR / "probe_report.json").write_text(json.dumps(probe_report, indent=2))

    probe_valid = verify.verify_record(dict(signed_probe), "authority")
    evasion_valid = verify.verify_record(dict(signed_evasion), "authority")
    print(f"Signature check: limit_probe_report valid={probe_valid}, feedback_loop_report valid={evasion_valid}")

    totals = llm_client.session_totals()
    print(f"\nOpenAI usage this run: {totals['calls']} calls, ~${totals['estimated_cost_usd']:.4f} estimated")
    print("Wrote data/probe_report.json")


if __name__ == "__main__":
    main()
