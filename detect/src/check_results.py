"""
Entry point: python check_results.py

Trains the detector on ../../generate/data/good_transactions.json +
fraud_transactions.json, evaluates it, saves the model, and prints
metrics + a sample of proposed (unsigned) decisions.

This checks the detect layer in isolation. Signing and enforcement
happen later, in ../../pipeline.
"""

import json
from pathlib import Path

import detector as det

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT.parent / "generate" / "data"


def load(name):
    path = DATA_DIR / name
    if not path.exists():
        raise RuntimeError(
            f"{path} not found. Run the generate layer first to produce transaction data."
        )
    return json.loads(path.read_text())


def main():
    print("=" * 70)
    print("DETECT LAYER: Training + Evaluation")
    print("=" * 70)

    good = load("good_transactions.json")
    fraud = load("fraud_transactions.json")
    all_tx = good + fraud
    print(f"\n[1/3] Loaded {len(good)} legitimate + {len(fraud)} fraudulent transactions ({len(all_tx)} total)")

    print("\n[2/3] Training detector (RandomForest)...")
    model, X_test, y_test, tx_test = det.train(all_tx)
    det.save_model(model)
    metrics = det.evaluate(model, X_test, y_test)
    scores = metrics.pop("scores")
    print(f"      fraud_caught_rate={metrics['fraud_caught_rate']:.2%}  false_positive_rate={metrics['false_positive_rate']:.2%}")
    print(f"      top signals: {[s['feature'] for s in metrics['top_signals']]}")
    print(f"      model saved to {det.MODEL_PATH}")

    print("\n[3/3] Generating proposed (unsigned) decisions...")
    decisions = det.generate_decisions(model, tx_test, scores)
    counts = {"BLOCK": 0, "FLAG": 0, "ALLOW": 0}
    for e in decisions:
        counts[e["proposed_decision"]] += 1
    print(f"      -> {len(decisions)} proposed decisions: {counts}")
    print("\nThese are proposals only. Run the pipeline layer to apply mandate")
    print("checks and route them to the sign layer for a final, enforceable decision.")


if __name__ == "__main__":
    main()
