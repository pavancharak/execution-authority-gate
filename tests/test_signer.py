"""
Tests for sign/src/authority_signer.py and signature_verifier.py.

Every test uses isolated_sign_env (see conftest.py) so nothing here
touches the repo's real sign/tokens/ or generates real keys that live long.
"""


def test_issue_agent_token_is_bounded_and_signed(isolated_sign_env):
    auth, verify = isolated_sign_env

    token = auth.issue_agent_token("agent_test", "test_action", max_operations=5)

    assert token["agent_id"] == "agent_test"
    assert token["max_operations"] == 5
    assert token["signer"] == "authority"
    assert "signature" in token
    assert verify.verify_record(dict(token), "authority") is True


def test_sign_block_decision_verifies(isolated_sign_env):
    auth, verify = isolated_sign_env
    decision = auth.sign_block_decision("tx_1", 0.91, "BLOCK", ["pattern_similarity"])
    assert decision["decision"] == "BLOCK"
    assert verify.verify_record(dict(decision), "authority") is True


def test_sign_pipeline_decision_verifies(isolated_sign_env):
    auth, verify = isolated_sign_env
    decision = auth.sign_pipeline_decision(
        "tx_1", 0.12, "ALLOW", False, ["time_restriction"], "BLOCK", ["mandate: time_restriction"]
    )
    assert decision["final_decision"] == "BLOCK"
    assert decision["violated_mandate_rules"] == ["time_restriction"]
    assert verify.verify_record(dict(decision), "authority") is True


def test_key_separation_authority_vs_reviewer(isolated_sign_env):
    """A record signed by one identity must never verify against the
    other's public key. This is the whole point of using two keys."""
    auth, verify = isolated_sign_env

    decision = auth.sign_block_decision("tx_1", 0.5, "FLAG", [])
    override = auth.sign_override("tx_1", "FLAG", "ALLOW", "reviewer_x", "manual review cleared it")

    assert verify.verify_record(dict(decision), "authority") is True
    assert verify.verify_record(dict(decision), "reviewer") is False

    assert verify.verify_record(dict(override), "reviewer") is True
    assert verify.verify_record(dict(override), "authority") is False


def test_tampering_invalidates_signature(isolated_sign_env):
    auth, verify = isolated_sign_env
    decision = auth.sign_block_decision("tx_1", 0.91, "BLOCK", ["pattern_similarity"])

    tampered = dict(decision)
    tampered["fraud_score"] = 0.01  # attacker tries to rewrite the score after signing

    assert verify.verify_record(tampered, "authority") is False


def test_verify_unknown_signer_returns_false(isolated_sign_env):
    auth, verify = isolated_sign_env
    decision = auth.sign_block_decision("tx_1", 0.91, "BLOCK", [])
    assert verify.verify_record(dict(decision), "nonexistent_signer") is False


def test_verify_record_without_signature_returns_false(isolated_sign_env):
    _auth, verify = isolated_sign_env
    assert verify.verify_record({"transaction_id": "tx_1"}, "authority") is False


def test_two_signings_of_the_same_payload_are_not_identical(isolated_sign_env):
    """Each signed record gets a fresh record_id/signed_at, so signing
    the same logical decision twice produces two different (both valid)
    signatures. This is intentional, not a determinism bug. It means
    two signing events are always distinguishable."""
    auth, verify = isolated_sign_env

    first = auth.sign_block_decision("tx_1", 0.91, "BLOCK", ["pattern_similarity"])
    second = auth.sign_block_decision("tx_1", 0.91, "BLOCK", ["pattern_similarity"])

    assert first["signature"] != second["signature"]
    assert first["record_id"] != second["record_id"]
    assert verify.verify_record(dict(first), "authority") is True
    assert verify.verify_record(dict(second), "authority") is True


def test_canonical_encoding_is_order_independent(isolated_sign_env):
    auth, _verify = isolated_sign_env
    a = auth._canonical({"b": 1, "a": 2})
    b = auth._canonical({"a": 2, "b": 1})
    assert a == b


def test_keys_persist_across_signer_instances(tmp_path, monkeypatch):
    """A second Signer("authority") pointed at the same directory loads
    the existing key rather than generating a new one."""
    import authority_signer as auth

    tokens_dir = tmp_path / "tokens"
    keys_dir = tokens_dir / "keys"
    keys_dir.mkdir(parents=True)
    monkeypatch.setattr(auth, "TOKENS_DIR", tokens_dir)
    monkeypatch.setattr(auth, "KEYS_DIR", keys_dir)

    signer_1 = auth.Signer("authority")
    signer_2 = auth.Signer("authority")

    payload = {"x": 1}
    sig_1 = signer_1.sign_record(dict(payload))
    sig_2 = signer_2.sign_record(dict(payload))

    # Different Signer objects, same underlying key material: the public
    # key file each would have written is identical.
    pub_bytes_1 = signer_1._private_key.public_key().public_bytes(
        encoding=auth.serialization.Encoding.PEM, format=auth.serialization.PublicFormat.SubjectPublicKeyInfo
    )
    pub_bytes_2 = signer_2._private_key.public_key().public_bytes(
        encoding=auth.serialization.Encoding.PEM, format=auth.serialization.PublicFormat.SubjectPublicKeyInfo
    )
    assert pub_bytes_1 == pub_bytes_2
