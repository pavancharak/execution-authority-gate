"""Tests for pipeline/src/dashboard_builder.py."""

import json
from pathlib import Path

import pytest

import dashboard_builder as db

REPO_ROOT = Path(__file__).resolve().parent.parent


def _decision_entry(final, detect, mandate_allowed, violated=None, amount=50.0, merchant="QuickMart", attack_type="none", is_fraud=0):
    return {
        "decision": {
            "transaction_id": "tx_test",
            "fraud_score": 0.1,
            "detect_decision": detect,
            "mandate_allowed": mandate_allowed,
            "violated_mandate_rules": violated or [],
            "final_decision": final,
            "signature": "deadbeef",
        },
        "mandate_checks": [
            {"rule": "spending_limit", "passed": True, "reason": "ok"},
            {"rule": "merchant_whitelist", "passed": mandate_allowed, "reason": "ok"},
            {"rule": "time_restriction", "passed": True, "reason": "ok"},
            {"rule": "velocity", "passed": True, "reason": "ok"},
        ],
        "ground_truth": {"is_fraud": is_fraud, "attack_type": attack_type, "amount": amount, "merchant": merchant, "currency": "USD"},
    }


def test_build_writes_expected_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "WEB_DATA_DIR", tmp_path / "web_data")

    entries = [
        _decision_entry("ALLOW", "ALLOW", True),
        _decision_entry("BLOCK", "BLOCK", True, is_fraud=1, attack_type="pattern_copy"),
        _decision_entry("BLOCK", "ALLOW", False, violated=["time_restriction"], is_fraud=1, attack_type="pattern_copy"),
    ]
    detect_metrics = {
        "confusion_matrix": {"true_negative": 1, "false_positive": 0, "false_negative": 0, "true_positive": 2},
        "fraud_caught_rate": 1.0,
        "fraud_missed_rate": 0.0,
        "precision": 1.0,
        "false_positive_rate": 0.0,
        "top_signals": [{"feature": "pattern_similarity", "importance": 0.5}],
    }
    verification = {"total": 3, "verified": 3, "all_verified": True}

    path = db.build(
        good_transactions=[{"customer_id": "c1"}],
        fraud_transactions=[{"attack_type": "pattern_copy"}, {"attack_type": "pattern_copy"}],
        detect_metrics=detect_metrics,
        mandates={"c1": {}},
        entries=entries,
        verification=verification,
    )

    assert path.exists()
    data = json.loads(path.read_text())

    assert data["meta"]["title"] == "Execution Authority Gate"
    assert len(data["attacks"]) == 13  # from the real identify/attacks.json

    assert data["simulation"]["good_transaction_count"] == 1
    assert data["simulation"]["attack_type_breakdown"] == {"pattern_copy": 2}

    assert data["detect"]["metrics"] == detect_metrics

    assert data["mandate"]["mandates_derived"] == 1
    assert data["mandate"]["block_attribution"] == {"detect_only": 1, "mandate_only": 1, "both": 0}
    assert data["mandate"]["rule_violation_counts"]["merchant_whitelist"] == 1
    assert len(data["mandate"]["sample_mandate_only_blocks"]) == 1

    assert data["pipeline"]["total"] == 3
    assert data["pipeline"]["decision_counts"] == {"BLOCK": 2, "FLAG": 0, "ALLOW": 1}

    assert data["verification"] == verification


def test_build_defaults_api_activity_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "WEB_DATA_DIR", tmp_path / "web_data")

    path = db.build(
        good_transactions=[],
        fraud_transactions=[],
        detect_metrics={"confusion_matrix": {}, "fraud_caught_rate": 0, "fraud_missed_rate": 0, "precision": 0, "false_positive_rate": 0, "top_signals": []},
        mandates={},
        entries=[],
        verification={"total": 0, "verified": 0, "all_verified": True},
    )
    data = json.loads(path.read_text())
    assert data["api_activity"]["summary"]["total_calls"] == 0


def test_committed_dashboard_json_has_the_shape_the_web_page_expects():
    """The real, committed web/data/dashboard.json, the one script.js
    actually fetches, has every top level key the page reads."""
    dashboard_path = REPO_ROOT / "web" / "data" / "dashboard.json"
    if not dashboard_path.exists():
        pytest.skip("web/data/dashboard.json not present (run the pipeline layer to generate it)")

    data = json.loads(dashboard_path.read_text())
    for key in ("meta", "attacks", "simulation", "api_activity", "detect", "mandate", "pipeline", "verification"):
        assert key in data

    assert len(data["attacks"]) == 13
    assert "top_signals" in data["detect"]["metrics"]
    assert set(data["mandate"]["block_attribution"].keys()) == {"detect_only", "mandate_only", "both"}
    assert set(data["pipeline"]["decision_counts"].keys()) == {"BLOCK", "FLAG", "ALLOW"}
