"""
Tests for sign/src/caller_auth.py: caller identity, token issuance and
verification, and permission scoping (see EAG-AUDIT-GAPS.md section 4,
"no caller authentication mechanism exists").
"""

import time

import pytest

import caller_auth


@pytest.fixture
def authenticator():
    """A fresh, isolated authenticator with its own random secret, never
    touching sign/tokens/keys/caller_auth_secret.key."""
    import secrets

    return caller_auth.CallerAuthenticator(secret=secrets.token_bytes(32))


def test_create_token_for_known_caller_round_trips(authenticator):
    token = authenticator.create_token("fraud-analyst")
    identity = authenticator.verify_token(token)

    assert identity is not None
    assert identity.caller_id == "fraud-analyst"
    assert identity.permissions == ["ALLOW", "FLAG", "BLOCK"]


def test_create_token_for_unknown_caller_raises(authenticator):
    with pytest.raises(KeyError):
        authenticator.create_token("nonexistent-caller")


def test_verify_token_rejects_tampered_payload(authenticator):
    token = authenticator.create_token("payment-processor")
    payload_b64, _, signature = token.rpartition(".")

    # Attacker swaps in a different payload, still validly shaped, while
    # keeping the original signature.
    forged_payload = caller_auth._b64encode(b'{"caller_id":"fraud-analyst","permissions":["ALLOW","FLAG","BLOCK"],"rate_limit":200,"issued_at":0,"expires_at":9999999999}')
    forged_token = f"{forged_payload}.{signature}"

    assert authenticator.verify_token(forged_token) is None


def test_verify_token_rejects_tampered_signature(authenticator):
    token = authenticator.create_token("payment-processor")
    payload_b64, _, signature = token.rpartition(".")
    bad_signature = "0" * len(signature)

    assert authenticator.verify_token(f"{payload_b64}.{bad_signature}") is None


def test_verify_token_rejects_expired_token(authenticator):
    token = authenticator.create_token("fraud-analyst", ttl_seconds=-1)  # already expired

    assert authenticator.verify_token(token) is None


def test_verify_token_rejects_malformed_input(authenticator):
    assert authenticator.verify_token("") is None
    assert authenticator.verify_token("not-a-token") is None
    assert authenticator.verify_token(None) is None


def test_payment_processor_can_execute_allow_and_flag_not_block(authenticator):
    caller = authenticator.verify_token(authenticator.create_token("payment-processor"))

    assert authenticator.can_execute(caller, "ALLOW") is True
    assert authenticator.can_execute(caller, "FLAG") is True
    assert authenticator.can_execute(caller, "BLOCK") is False


def test_fraud_analyst_can_execute_all_decision_types(authenticator):
    caller = authenticator.verify_token(authenticator.create_token("fraud-analyst"))

    for decision_type in ("ALLOW", "FLAG", "BLOCK"):
        assert authenticator.can_execute(caller, decision_type) is True


def test_audit_system_is_read_only(authenticator):
    caller = authenticator.verify_token(authenticator.create_token("audit-system"))

    for decision_type in ("ALLOW", "FLAG", "BLOCK"):
        assert authenticator.can_execute(caller, decision_type) is False


def test_can_execute_rejects_none_caller(authenticator):
    assert authenticator.can_execute(None, "ALLOW") is False


def test_tokens_from_different_secrets_do_not_verify_across_instances():
    import secrets

    auth_a = caller_auth.CallerAuthenticator(secret=secrets.token_bytes(32))
    auth_b = caller_auth.CallerAuthenticator(secret=secrets.token_bytes(32))

    token = auth_a.create_token("fraud-analyst")

    assert auth_b.verify_token(token) is None


def test_register_caller_allows_a_new_identity(authenticator):
    authenticator.register_caller("custom-service", permissions=["FLAG"], rate_limit=10)

    token = authenticator.create_token("custom-service")
    caller = authenticator.verify_token(token)

    assert caller.caller_id == "custom-service"
    assert authenticator.can_execute(caller, "FLAG") is True
    assert authenticator.can_execute(caller, "BLOCK") is False


def test_token_carries_rate_limit_and_expiry(authenticator):
    before = time.time()
    token = authenticator.create_token("audit-system", ttl_seconds=120)
    caller = authenticator.verify_token(token)

    assert caller.rate_limit == 5000
    assert before + 119 <= caller.expires_at <= before + 121
