"""
Tests for sign/src/decision_executor.py: the execution layer that
turns a signed decision into an action against a payment processor
webhook (see EAG-AUDIT-GAPS.md section 3, "NOT IMPLEMENTED anywhere in
this repo").
"""

import pytest

import caller_auth
import decision_executor


def _signed(auth, final_decision="ALLOW", transaction_id="tx_1"):
    return auth.sign_pipeline_decision(
        transaction_id, 0.1, "ALLOW", True, [], final_decision, ["mandate: none"]
    )


@pytest.fixture
def recording_webhook():
    calls = []

    def webhook(action, signed_decision):
        calls.append((action, signed_decision["transaction_id"]))
        return {"ok": True, "action": action}

    webhook.calls = calls
    return webhook


@pytest.fixture
def executor(tmp_path):
    return decision_executor.DecisionExecutor(log_path=tmp_path / "executions.jsonl")


def test_allow_decision_settles(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "ALLOW")

    result = executor.enforce_decision(decision, recording_webhook)

    assert result["status"] == "EXECUTED"
    assert result["action"] == "settle"
    assert recording_webhook.calls == [("settle", "tx_1")]


def test_flag_decision_triggers_step_up_auth(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "FLAG")

    result = executor.enforce_decision(decision, recording_webhook)

    assert result["status"] == "EXECUTED"
    assert result["action"] == "step_up_auth"


def test_block_decision_denies(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "BLOCK")

    result = executor.enforce_decision(decision, recording_webhook)

    assert result["status"] == "EXECUTED"
    assert result["action"] == "deny"


def test_tampered_signature_is_rejected_and_never_reaches_webhook(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = dict(_signed(auth, "ALLOW"))
    decision["fraud_score"] = 0.99  # tampered after signing

    result = executor.enforce_decision(decision, recording_webhook)

    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_signature"
    assert recording_webhook.calls == []


def test_same_decision_is_never_executed_twice(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "ALLOW")

    first = executor.enforce_decision(decision, recording_webhook)
    second = executor.enforce_decision(decision, recording_webhook)

    assert first["status"] == "EXECUTED"
    assert second["status"] == "ALREADY_EXECUTED"
    assert len(recording_webhook.calls) == 1  # webhook only ever called once


def test_every_attempt_is_logged_including_rejections(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    good = _signed(auth, "ALLOW", transaction_id="tx_good")
    bad = dict(_signed(auth, "ALLOW", transaction_id="tx_bad"))
    bad["fraud_score"] = 0.99

    executor.enforce_decision(good, recording_webhook)
    executor.enforce_decision(bad, recording_webhook)

    logged = executor.log.read_all()
    assert len(logged) == 2
    statuses = {e["transaction_id"]: e["status"] for e in logged}
    assert statuses["tx_good"] == "EXECUTED"
    assert statuses["tx_bad"] == "REJECTED"


def test_caller_without_permission_is_rejected(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "BLOCK")
    caller = caller_auth.CallerIdentity(
        caller_id="payment-processor", permissions=["ALLOW", "FLAG"], rate_limit=1000, expires_at=9999999999
    )

    result = executor.enforce_decision(decision, recording_webhook, caller=caller)

    assert result["status"] == "REJECTED"
    assert result["reason"] == "caller_not_permitted"
    assert recording_webhook.calls == []


def test_caller_with_permission_executes(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = _signed(auth, "BLOCK")
    caller = caller_auth.CallerIdentity(
        caller_id="fraud-analyst", permissions=["ALLOW", "FLAG", "BLOCK"], rate_limit=200, expires_at=9999999999
    )

    result = executor.enforce_decision(decision, recording_webhook, caller=caller)

    assert result["status"] == "EXECUTED"
    assert result["caller_id"] == "fraud-analyst"


def test_missing_record_id_is_rejected(isolated_sign_env, executor, recording_webhook):
    auth, _verify = isolated_sign_env
    decision = dict(_signed(auth, "ALLOW"))
    del decision["record_id"]

    result = executor.enforce_decision(decision, recording_webhook)

    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_record_id"
