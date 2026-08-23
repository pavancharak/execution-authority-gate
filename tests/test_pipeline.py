"""Tests for pipeline/src/run_pipeline.py's combine_decision and decision_log.py."""

import run_pipeline as rp
import decision_log


# ---------------------------------------------------------------------------
# combine_decision: BLOCK wins over everything; FLAG only when detect is
# unsure AND mandate has no objection.
# ---------------------------------------------------------------------------

def _mandate_result(allowed, violated=None):
    return {"mandate_allowed": allowed, "violated_rules": violated or []}


def test_combine_allow_when_both_clear():
    assert rp.combine_decision("ALLOW", _mandate_result(True)) == "ALLOW"


def test_combine_blocks_on_detect_block_even_if_mandate_allows():
    assert rp.combine_decision("BLOCK", _mandate_result(True)) == "BLOCK"


def test_combine_blocks_on_mandate_violation_even_if_detect_allows():
    assert rp.combine_decision("ALLOW", _mandate_result(False, ["time_restriction"])) == "BLOCK"


def test_combine_blocks_when_both_object():
    assert rp.combine_decision("BLOCK", _mandate_result(False, ["merchant_whitelist"])) == "BLOCK"


def test_combine_flag_only_when_mandate_has_no_objection():
    assert rp.combine_decision("FLAG", _mandate_result(True)) == "FLAG"


def test_combine_mandate_violation_overrides_flag():
    assert rp.combine_decision("FLAG", _mandate_result(False, ["velocity"])) == "BLOCK"


# ---------------------------------------------------------------------------
# decision_log.py
# ---------------------------------------------------------------------------

def _entry(final, detect, mandate_allowed):
    return {"decision": {"final_decision": final, "detect_decision": detect, "mandate_allowed": mandate_allowed}}


def test_summarize_counts_decisions_and_attributes_blocks():
    entries = [
        _entry("ALLOW", "ALLOW", True),
        _entry("FLAG", "FLAG", True),
        _entry("BLOCK", "BLOCK", True),   # detect_only
        _entry("BLOCK", "ALLOW", False),  # mandate_only
        _entry("BLOCK", "BLOCK", False),  # both
    ]
    summary = decision_log.summarize(entries)

    assert summary["total"] == 5
    assert summary["decision_counts"] == {"BLOCK": 3, "FLAG": 1, "ALLOW": 1}
    assert summary["block_attribution"] == {"detect_only": 1, "mandate_only": 1, "both": 1}


def test_write_log_roundtrips_json(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_log, "DECISIONS_DIR", tmp_path / "decisions")
    entries = [_entry("ALLOW", "ALLOW", True)]

    path = decision_log.write_log(entries)

    assert path.exists()
    import json
    assert json.loads(path.read_text()) == entries
