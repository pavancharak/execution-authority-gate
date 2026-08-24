"""
Detection layer: trains a classifier on transaction features and scores
new transactions for fraud risk.

This layer only detects. It does not sign or enforce anything. A
proposed decision from `decision_for_score` is not final until the
mandate layer and the signing layer (see ../../mandate, ../../sign) have
both run on it. That composition happens in ../../pipeline.
"""

import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, recall_score, precision_score

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "detector.pkl"

FEATURES = [
    "amount",
    "hour_of_day",
    "log_seconds_since_prev_tx",
    "location_mismatch_km",
    "pattern_similarity",
    "ai_generated_signal",
]


def _row(tx):
    return [
        tx["amount"],
        tx["hour_of_day"],
        np.log1p(tx["seconds_since_prev_tx"]),
        tx["location_mismatch_km"],
        tx["pattern_similarity"],
        tx["ai_generated_signal"],
    ]


def build_matrix(transactions):
    X = np.array([_row(t) for t in transactions], dtype=float)
    y = np.array([t["is_fraud"] for t in transactions], dtype=int)
    return X, y


def train(transactions, test_size=0.3, random_state=13):
    X, y = build_matrix(transactions)
    X_train, X_test, y_train, y_test, tx_train, tx_test = train_test_split(
        X, y, transactions, test_size=test_size, random_state=random_state, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=80, max_depth=5, min_samples_leaf=12, random_state=random_state,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)
    return model, X_test, y_test, tx_test


def save_model(model):
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


def load_model():
    if not MODEL_PATH.exists():
        raise RuntimeError("No trained model found. Run check_results.py first.")
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def evaluate(model, X_test, y_test):
    scores = model.predict_proba(X_test)[:, 1]
    preds = (scores >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, preds).ravel()
    recall = recall_score(y_test, preds)
    precision = precision_score(y_test, preds)
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0

    importances = sorted(zip(FEATURES, model.feature_importances_), key=lambda kv: -kv[1])

    return {
        "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)},
        "fraud_caught_rate": round(float(recall), 4),
        "fraud_missed_rate": round(1 - float(recall), 4),
        "precision": round(float(precision), 4),
        "false_positive_rate": round(float(false_positive_rate), 4),
        "top_signals": [{"feature": f, "importance": round(float(i), 4)} for f, i in importances[:3]],
        "scores": scores,
    }


def _reasons_for(tx, model):
    """Cheap, explainable by eye rationale: which features look most
    unusual for this transaction, weighted by what the model actually
    relies on."""
    importances = dict(zip(FEATURES, model.feature_importances_))
    row = dict(zip(FEATURES, _row(tx)))
    unusualness = {
        "amount": min(1.0, row["amount"] / 800),
        "hour_of_day": 0.0,
        "log_seconds_since_prev_tx": max(0.0, 1 - row["log_seconds_since_prev_tx"] / 8),
        "location_mismatch_km": min(1.0, row["location_mismatch_km"] / 2000),
        "pattern_similarity": max(0.0, 1 - row["pattern_similarity"]) if row["pattern_similarity"] < 0.7 else 0.0,
        "ai_generated_signal": row["ai_generated_signal"],
    }
    scored = sorted(
        ((f, unusualness[f] * importances.get(f, 0)) for f in FEATURES),
        key=lambda kv: -kv[1],
    )
    return [f for f, s in scored[:2] if s > 0.01] or ["no single dominant signal"]


def median_neutral_features(good_transactions):
    """Median feature values from the legitimate population, used to
    isolate the amount signal when probing thresholds: every other
    feature is held at a typical, unremarkable value."""
    keys = ["hour_of_day", "seconds_since_prev_tx", "location_mismatch_km", "pattern_similarity", "ai_generated_signal"]
    return {k: float(np.median([t[k] for t in good_transactions])) for k in keys}


def decision_for_score(score: float) -> str:
    if score >= 0.80:
        return "BLOCK"
    if score >= 0.50:
        return "FLAG"
    return "ALLOW"


def generate_decisions(model, tx_test, scores):
    """Proposed (unsigned) decisions for every test transaction. This is
    the detect layer's full output. The mandate layer, then the sign
    layer, still have to run before any of these is a final, enforceable
    decision."""
    entries = []
    for tx, score in zip(tx_test, scores):
        decision = decision_for_score(score)
        reasons = _reasons_for(tx, model)
        entries.append(
            {
                "transaction_id": tx["transaction_id"],
                "fraud_score": round(float(score), 4),
                "proposed_decision": decision,
                "reasons": reasons,
                "ground_truth": {
                    "is_fraud": tx["is_fraud"],
                    "attack_type": tx.get("attack_type", "none"),
                    "amount": tx["amount"],
                    "merchant": tx["merchant"],
                    "currency": tx.get("currency", "USD"),
                },
            }
        )
    return entries
