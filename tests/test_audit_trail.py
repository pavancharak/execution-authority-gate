"""
Tests for pipeline/src/audit_trail.py: the append only decision log
that replaces pipeline_decisions.json, which used to be overwritten on
every run (see EAG-AUDIT-GAPS.md section 1).
"""

import json

import audit_trail


def _entry(auth, transaction_id="tx_1", final_decision="BLOCK"):
    signed = auth.sign_pipeline_decision(
        transaction_id, 0.91, "BLOCK", False, ["velocity"], final_decision, ["mandate: velocity"]
    )
    return {
        "decision": signed,
        "mandate_checks": [],
        "ground_truth": {"is_fraud": 1, "attack_type": "pattern_copy", "amount": 500.0, "merchant": "X", "currency": "USD"},
    }


def test_append_decision_writes_a_new_line(tmp_path, isolated_sign_env):
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry = _entry(auth)

    appended = trail.append_decision(entry)

    assert appended is True
    lines = trail.path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["decision"]["record_id"] == entry["decision"]["record_id"]


def test_append_decision_is_idempotent_on_record_id(tmp_path, isolated_sign_env):
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry = _entry(auth)

    first = trail.append_decision(entry)
    second = trail.append_decision(entry)  # same record_id, replayed

    assert first is True
    assert second is False
    lines = trail.path.read_text().strip().splitlines()
    assert len(lines) == 1  # never duplicated


def test_append_is_never_a_rewrite(tmp_path, isolated_sign_env):
    """Appending entry B must not touch the line entry A already wrote:
    this is what makes the trail durable across pipeline runs, unlike
    decision_log.write_log's full path.write_text() overwrite."""
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry_a = _entry(auth, transaction_id="tx_a")
    entry_b = _entry(auth, transaction_id="tx_b")

    trail.append_decision(entry_a)
    first_line = trail.path.read_text().splitlines()[0]
    trail.append_decision(entry_b)

    lines = trail.path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == first_line  # entry_a's line is untouched


def test_append_many_skips_duplicates_and_counts_new(tmp_path, isolated_sign_env):
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry_a = _entry(auth, transaction_id="tx_a")
    entry_b = _entry(auth, transaction_id="tx_b")
    trail.append_decision(entry_a)

    appended = trail.append_many([entry_a, entry_b, entry_b])

    assert appended == 1  # only entry_b is new; the second entry_b is a dup within the batch too
    assert len(trail.path.read_text().strip().splitlines()) == 2


def test_get_decision_returns_the_matching_entry(tmp_path, isolated_sign_env):
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry_a = _entry(auth, transaction_id="tx_a")
    entry_b = _entry(auth, transaction_id="tx_b")
    trail.append_many([entry_a, entry_b])

    found = trail.get_decision(entry_b["decision"]["record_id"])

    assert found is not None
    assert found["decision"]["transaction_id"] == "tx_b"


def test_get_decision_returns_none_for_unknown_id(tmp_path, isolated_sign_env):
    _auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    assert trail.get_decision("does-not-exist") is None


def test_verify_all_confirms_every_real_signature(tmp_path, isolated_sign_env):
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    trail.append_many([_entry(auth, transaction_id="tx_a"), _entry(auth, transaction_id="tx_b")])

    report = trail.verify_all(signer_name="authority")

    assert report["total"] == 2
    assert report["verified"] == 2
    assert report["all_verified"] is True
    assert report["failed_record_ids"] == []


def test_verify_all_catches_a_tampered_entry_written_directly_to_disk(tmp_path, isolated_sign_env):
    """Simulates an attacker editing the trail on disk directly (not
    through append_decision). verify_all must catch it the same way a
    judge verifying the file again later would."""
    auth, _verify = isolated_sign_env
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    entry = _entry(auth, transaction_id="tx_a")
    trail.append_decision(entry)

    tampered = json.loads(trail.path.read_text().strip())
    tampered["decision"]["fraud_score"] = 0.01  # rewritten after signing
    trail.path.write_text(json.dumps(tampered) + "\n")

    report = trail.verify_all(signer_name="authority")

    assert report["verified"] == 0
    assert report["all_verified"] is False
    assert tampered["decision"]["record_id"] in report["failed_record_ids"]


def test_append_decision_requires_a_record_id(tmp_path):
    trail = audit_trail.AuditTrail(tmp_path / "decisions.jsonl")
    import pytest

    with pytest.raises(ValueError):
        trail.append_decision({"decision": {"transaction_id": "tx_1"}})
