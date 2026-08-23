"""
Shared fixtures. Every layer here is a flat, non-packaged module (no
top-level src/ package — see the README's layer layout), so we put each
layer's src/ directory on sys.path once, then every test file imports
modules by their bare name (import detector, import mandate_checker,
...), exactly like the source files import each other.
"""

import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

for _layer in ("detect", "mandate", "sign", "generate", "pipeline"):
    _layer_src = REPO_ROOT / _layer / "src"
    if str(_layer_src) not in sys.path:
        sys.path.insert(0, str(_layer_src))


@pytest.fixture
def isolated_sign_env(tmp_path, monkeypatch):
    """A sign layer pointed entirely at tmp_path, never touching the
    repo's real sign/tokens/.

    authority_signer.py creates its AUTHORITY/REVIEWER singletons (and
    signature_verifier.py copies TOKENS_DIR via `from authority_signer
    import ... TOKENS_DIR`) once, at import time — both bound to the
    real sign/tokens/ path. Reassigning authority_signer.TOKENS_DIR
    later would not change signature_verifier's already-copied value,
    so every module that captured a copy has to be patched here.
    """
    import authority_signer as auth
    import signature_verifier as verify

    tokens_dir = tmp_path / "tokens"
    keys_dir = tokens_dir / "keys"
    keys_dir.mkdir(parents=True)

    monkeypatch.setattr(auth, "TOKENS_DIR", tokens_dir)
    monkeypatch.setattr(auth, "KEYS_DIR", keys_dir)
    monkeypatch.setattr(auth, "AUTHORITY", auth.Signer("authority"))
    monkeypatch.setattr(auth, "REVIEWER", auth.Signer("reviewer"))
    monkeypatch.setattr(verify, "TOKENS_DIR", tokens_dir)

    return auth, verify


@pytest.fixture
def isolated_generate_env(isolated_sign_env, monkeypatch):
    """Extends isolated_sign_env to fraud_agents.py, which also copies
    TOKENS_DIR at import time (`TOKENS_DIR = auth.TOKENS_DIR`, evaluated
    once against the real path)."""
    auth, verify = isolated_sign_env
    import fraud_agents as fa

    monkeypatch.setattr(fa, "TOKENS_DIR", auth.TOKENS_DIR)
    return auth, verify, fa


def _make_transaction(rng, is_fraud, **overrides):
    """A transaction shaped like the real schema everywhere in this
    repo: transaction_id, customer_id, amount, merchant, hour_of_day,
    seconds_since_prev_tx, location_mismatch_km, pattern_similarity,
    ai_generated_signal, is_fraud, attack_type. Fraud examples are drawn
    from a visibly different distribution than legitimate ones so a
    RandomForest can actually separate them in a handful of rows."""
    if is_fraud:
        base = dict(
            amount=round(rng.uniform(400, 900), 2),
            hour_of_day=rng.randint(0, 5),
            seconds_since_prev_tx=round(rng.uniform(0.5, 20), 2),
            location_mismatch_km=round(rng.uniform(800, 4000), 1),
            pattern_similarity=round(rng.uniform(0.1, 0.4), 3),
            ai_generated_signal=round(rng.uniform(0.6, 0.95), 3),
            attack_type="pattern_copy",
        )
    else:
        base = dict(
            amount=round(rng.uniform(10, 120), 2),
            hour_of_day=rng.randint(8, 20),
            seconds_since_prev_tx=round(rng.uniform(3600, 90000), 1),
            location_mismatch_km=round(rng.uniform(0, 20), 1),
            pattern_similarity=round(rng.uniform(0.8, 0.98), 3),
            ai_generated_signal=round(rng.uniform(0.0, 0.2), 3),
            attack_type="none",
        )
    tx = {
        "transaction_id": f"tx_{rng.randrange(10**9):09d}",
        "customer_id": overrides.pop("customer_id", f"cust_{rng.randrange(10**6):06d}"),
        "customer_name": "Test Customer",
        "currency": "USD",
        "merchant": overrides.pop("merchant", rng.choice(["QuickMart", "CloudHost", "UrbanCafe"])),
        "is_fraud": int(is_fraud),
    }
    tx.update(base)
    tx.update(overrides)
    return tx


@pytest.fixture
def make_transaction():
    """Factory fixture: make_transaction(is_fraud, **overrides) -> dict."""
    rng = random.Random(1234)
    return lambda is_fraud, **overrides: _make_transaction(rng, is_fraud, **overrides)


@pytest.fixture
def synthetic_dataset():
    """60 legitimate + 60 fraudulent transactions from clearly separated
    distributions — enough signal for detector.train()'s RandomForest to
    reliably tell them apart in a fast, hermetic test."""
    rng = random.Random(42)
    good = [_make_transaction(rng, is_fraud=False) for _ in range(60)]
    fraud = [_make_transaction(rng, is_fraud=True) for _ in range(60)]
    return good, fraud
