"""
Cryptographic guarantees the sign layer is supposed to provide, tested
directly rather than assumed. Complements test_signer.py's per-function
tests with properties that should hold across many inputs.
"""


def test_signatures_are_unique_across_many_payloads(isolated_sign_env):
    auth, _verify = isolated_sign_env
    signatures = {auth.sign_block_decision(f"tx_{i}", i / 100, "FLAG", [])["signature"] for i in range(50)}
    assert len(signatures) == 50


def test_verification_fails_without_the_public_key_file(isolated_sign_env, tmp_path):
    auth, verify = isolated_sign_env
    decision = auth.sign_block_decision("tx_1", 0.5, "FLAG", [])
    assert verify.verify_record(dict(decision), "authority") is True

    (auth.TOKENS_DIR / "authority_public_key.pem").unlink()
    assert verify.verify_record(dict(decision), "authority") is False


def test_verification_cannot_be_satisfied_by_a_different_authoritys_key(tmp_path, monkeypatch):
    """Two independently-generated 'authority' identities, in two
    separate directories, must not cross-verify each other's records —
    proves verification is tied to the specific key on disk, not the
    signer name alone."""
    import authority_signer as auth
    import signature_verifier as verify

    def _fresh_env(subdir):
        tokens_dir = tmp_path / subdir
        keys_dir = tokens_dir / "keys"
        keys_dir.mkdir(parents=True)
        monkeypatch.setattr(auth, "TOKENS_DIR", tokens_dir)
        monkeypatch.setattr(auth, "KEYS_DIR", keys_dir)
        monkeypatch.setattr(auth, "AUTHORITY", auth.Signer("authority"))
        monkeypatch.setattr(verify, "TOKENS_DIR", tokens_dir)
        return tokens_dir

    _fresh_env("env_a")
    record_a = auth.sign_block_decision("tx_1", 0.5, "BLOCK", [])
    pub_key_a = (auth.TOKENS_DIR / "authority_public_key.pem").read_bytes()

    _fresh_env("env_b")
    assert verify.verify_record(dict(record_a), "authority") is False, "signed under env_a's key, verified under env_b's — should fail"

    pub_key_b = (auth.TOKENS_DIR / "authority_public_key.pem").read_bytes()
    assert pub_key_a != pub_key_b


def test_canonical_encoding_differs_for_different_content(isolated_sign_env):
    auth, _verify = isolated_sign_env
    a = auth._canonical({"amount": 100})
    b = auth._canonical({"amount": 101})
    assert a != b


def test_mandate_allowed_is_exactly_no_violations(make_transaction):
    """mandate_allowed must always be equivalent to violated_rules being
    empty — the two fields can never disagree, across many random
    transactions against many random mandates."""
    import random

    import mandate_checker as mc

    rng = random.Random(99)
    known_rules = {"spending_limit", "merchant_whitelist", "time_restriction", "velocity"}

    for _ in range(30):
        tx = make_transaction(is_fraud=bool(rng.getrandbits(1)), hour_of_day=rng.randint(0, 23), amount=rng.uniform(1, 2000))
        mandate = mc.default_mandate("cust_x")
        mandate["monthly_limit_usd"] = rng.uniform(10, 500)
        mandate["max_tx_per_day"] = rng.randint(1, 10)

        result = mc.check_mandate(tx, mandate, month_to_date_total=rng.uniform(0, 500), tx_count_today=rng.randint(0, 10))

        assert result["mandate_allowed"] == (len(result["violated_rules"]) == 0)
        assert set(result["violated_rules"]) <= known_rules
