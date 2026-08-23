"""Tests for detect/src/detector.py — real functions, not a class API."""

import detector as det


def test_decision_for_score_thresholds():
    assert det.decision_for_score(0.0) == "ALLOW"
    assert det.decision_for_score(0.49) == "ALLOW"
    assert det.decision_for_score(0.50) == "FLAG"
    assert det.decision_for_score(0.79) == "FLAG"
    assert det.decision_for_score(0.80) == "BLOCK"
    assert det.decision_for_score(1.0) == "BLOCK"


def test_build_matrix_shape(synthetic_dataset):
    good, fraud = synthetic_dataset
    X, y = det.build_matrix(good + fraud)
    assert X.shape == (120, len(det.FEATURES))
    assert y.shape == (120,)
    assert set(y.tolist()) == {0, 1}


def test_train_and_evaluate_separates_synthetic_fraud(synthetic_dataset):
    good, fraud = synthetic_dataset
    model, X_test, y_test, tx_test = det.train(good + fraud)

    assert len(X_test) == len(y_test) == len(tx_test)
    assert len(X_test) > 0

    metrics = det.evaluate(model, X_test, y_test)
    scores = metrics.pop("scores")

    # This dataset's fraud/legit distributions barely overlap by
    # construction (see conftest._make_transaction) — a RandomForest
    # should separate them almost perfectly.
    assert metrics["fraud_caught_rate"] > 0.9
    assert metrics["false_positive_rate"] < 0.1
    assert len(scores) == len(X_test)
    assert all(0.0 <= s <= 1.0 for s in scores)

    cm = metrics["confusion_matrix"]
    assert cm["true_positive"] + cm["false_negative"] + cm["true_negative"] + cm["false_positive"] == len(y_test)

    assert len(metrics["top_signals"]) == 3
    assert all("feature" in s and "importance" in s for s in metrics["top_signals"])


def test_generate_decisions_matches_scores(synthetic_dataset):
    good, fraud = synthetic_dataset
    model, X_test, y_test, tx_test = det.train(good + fraud)
    metrics = det.evaluate(model, X_test, y_test)
    scores = metrics.pop("scores")

    entries = det.generate_decisions(model, tx_test, scores)

    assert len(entries) == len(tx_test)
    for entry, tx, score in zip(entries, tx_test, scores):
        assert entry["transaction_id"] == tx["transaction_id"]
        assert entry["proposed_decision"] == det.decision_for_score(score)
        assert entry["ground_truth"]["is_fraud"] == tx["is_fraud"]
        assert isinstance(entry["reasons"], list) and len(entry["reasons"]) >= 1


def test_median_neutral_features(synthetic_dataset):
    good, _fraud = synthetic_dataset
    neutral = det.median_neutral_features(good)
    for key in ("hour_of_day", "seconds_since_prev_tx", "location_mismatch_km", "pattern_similarity", "ai_generated_signal"):
        assert key in neutral
        assert isinstance(neutral[key], float)


def test_save_and_load_model_roundtrip(synthetic_dataset, tmp_path, monkeypatch):
    good, fraud = synthetic_dataset
    model, X_test, y_test, tx_test = det.train(good + fraud)

    fake_model_path = tmp_path / "detector.pkl"
    monkeypatch.setattr(det, "MODEL_PATH", fake_model_path)

    det.save_model(model)
    assert fake_model_path.exists()

    loaded = det.load_model()
    # Same model, same predictions on the same input.
    X, _y = det.build_matrix(tx_test)
    assert (model.predict_proba(X) == loaded.predict_proba(X)).all()


def test_load_model_without_save_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(det, "MODEL_PATH", tmp_path / "does_not_exist.pkl")
    try:
        det.load_model()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
