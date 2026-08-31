"""
Tests for generate/src/fraud_agents.py.

Agents 5 (PatternReplicatorAgent), 6 (InjectionGeneratorAgent), and 8
(BustOutAgent) are local and statistical, no OpenAI calls, so they're
tested directly, every run. Agents 1, 2, 4, 7, 9 call the real OpenAI
API and only run when ALLOW_LIVE_OPENAI=1 and OPENAI_API_KEY are both
set (see the bottom of this file). They cost real money, so they're
opt in.
"""

import os

import pytest


def test_bounded_agent_issues_a_real_signed_token(isolated_generate_env):
    _auth, verify, fa = isolated_generate_env
    agent = fa.PatternReplicatorAgent(max_transactions=10)

    assert agent.token["agent_id"] == "agent5_pattern_replicator"
    assert agent.token["max_operations"] == 10
    assert verify.verify_record(dict(agent.token), "authority") is True


def test_bounded_agent_raises_once_limit_exceeded(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    agent = fa.PatternReplicatorAgent(max_transactions=3)

    for _ in range(3):
        agent._check_and_count()

    with pytest.raises(fa.TokenLimitExceeded):
        agent._check_and_count()


def test_pattern_replicator_respects_token_cap(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    histories = [{"customer_id": "cust_1", "customer_name": "Test", "avg_amount": 42.5, "currency": "USD"}]

    agent = fa.PatternReplicatorAgent(max_transactions=7)
    # Ask for more than the token allows. The agent should stop at the
    # token's max_operations, not the requested target_count.
    txs = agent.run(histories, target_count=100)

    assert len(txs) == 7
    assert all(tx["is_fraud"] == 1 and tx["attack_type"] == "pattern_copy" for tx in txs)
    assert all(tx["generated_by"] == "agent5_pattern_replicator" for tx in txs)


def test_injection_generator_produces_labeled_fraud(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    agent = fa.InjectionGeneratorAgent(max_attempts=15)

    txs = agent.run(["amount", "currency"], target_count=15)

    assert len(txs) == 15
    assert all(tx["attack_type"] == "form_break" for tx in txs)
    assert all(tx["payload_sample"] in fa.InjectionGeneratorAgent.PAYLOADS for tx in txs)


def test_write_log_records_execution_and_verifies(isolated_generate_env):
    auth, verify, fa = isolated_generate_env
    agent = fa.InjectionGeneratorAgent(max_attempts=5)
    agent.run(["amount"], target_count=5)

    log_path = auth.TOKENS_DIR / "agent6_injection_generator_execution_log.json"
    assert log_path.exists()

    import json
    log = json.loads(log_path.read_text())
    assert log["actually_executed"] == 5
    assert log["within_bounds"] is True
    assert log["signature_verifies"] is True


def test_make_seed_profiles(make_transaction):
    import fraud_agents as fa

    txs = [make_transaction(False, customer_id="cust_1", amount=10), make_transaction(False, customer_id="cust_1", amount=20)]
    seeds = fa.make_seed_profiles(txs, n=5)

    assert len(seeds) == 1
    assert seeds[0]["customer_id"] == "cust_1"
    assert seeds[0]["avg_amount"] == 15.0


def test_make_stolen_card_histories(make_transaction):
    import fraud_agents as fa

    txs = [make_transaction(False, customer_id="cust_2", amount=100)]
    histories = fa.make_stolen_card_histories(txs, n=5)

    assert histories[0]["customer_id"] == "cust_2"
    assert histories[0]["avg_amount"] == 100


def test_make_bustout_targets_requires_minimum_history(make_transaction):
    import fraud_agents as fa

    rich_history = [make_transaction(False, customer_id="cust_rich", amount=50) for _ in range(5)]
    thin_history = [make_transaction(False, customer_id="cust_thin", amount=50) for _ in range(2)]

    targets = fa.make_bustout_targets(rich_history + thin_history, n=10, min_history=4)

    assert len(targets) == 1
    assert targets[0]["customer_id"] == "cust_rich"
    assert targets[0]["count"] == 5


def test_make_bustout_targets_computes_the_same_derived_limit_mandate_uses(make_transaction):
    import fraud_agents as fa

    txs = [make_transaction(False, customer_id="cust_1", amount=amt) for amt in (10, 20, 30, 40)]
    targets = fa.make_bustout_targets(txs, n=10, min_history=4)

    assert targets[0]["avg_amount"] == 25.0
    assert targets[0]["count"] == 4


def test_bustout_agent_exceeds_the_customers_own_derived_limit(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    targets = [{
        "customer_id": "cust_1", "customer_name": "Test", "avg_amount": 100.0, "count": 4,
        "currency": "USD", "merchants": ["QuickMart"], "hours": [12],
        "median_location_mismatch": 2.0, "median_pattern_similarity": 0.9, "median_ai_signal": 0.1,
    }]

    agent = fa.BustOutAgent(max_transactions=10)
    txs = agent.run(targets, target_count=1)

    assert len(txs) == 1
    tx = txs[0]
    derived_limit = 100.0 * 4 * 1.5  # same formula mandate_checker.derive_mandate_from_history uses
    assert tx["amount"] > derived_limit
    assert tx["merchant"] == "QuickMart"  # stays within the customer's own typical shape
    assert tx["hour_of_day"] == 12
    assert tx["attack_type"] == "synthetic_bustout"
    assert tx["is_fraud"] == 1


def test_bustout_agent_respects_token_cap(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    targets = [
        {
            "customer_id": f"cust_{i}", "customer_name": "Test", "avg_amount": 50.0, "count": 4,
            "currency": "USD", "merchants": ["QuickMart"], "hours": [12],
            "median_location_mismatch": 2.0, "median_pattern_similarity": 0.9, "median_ai_signal": 0.1,
        }
        for i in range(10)
    ]

    agent = fa.BustOutAgent(max_transactions=3)
    txs = agent.run(targets, target_count=10)

    assert len(txs) == 3
    assert all(tx["generated_by"] == "agent8_bustout" for tx in txs)


# ---------------------------------------------------------------------------
# Live OpenAI tests, opt in only (real API calls, real cost).
# Run with: ALLOW_LIVE_OPENAI=1 OPENAI_API_KEY=sk-... pytest tests/test_generate.py -v
# ---------------------------------------------------------------------------

live_openai = pytest.mark.skipif(
    os.getenv("ALLOW_LIVE_OPENAI") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="set ALLOW_LIVE_OPENAI=1 and OPENAI_API_KEY to run live OpenAI tests",
)


@live_openai
def test_fake_identity_agent_generates_real_identities(isolated_generate_env, make_transaction):
    _auth, _verify, fa = isolated_generate_env
    seed_profiles = [{"avg_amount": 60.0}]

    agent = fa.FakeIdentityAgent(max_identities=2)
    txs = agent.run(seed_profiles, tx_per_identity=(1, 2))

    assert len(txs) > 0
    assert all(tx["attack_type"] == "fake_identity" for tx in txs)


@live_openai
def test_social_engineer_agent_generates_real_transcripts(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    seed_profiles = [{"customer_id": "cust_1", "customer_name": "Test", "avg_amount": 60.0, "currency": "USD"}]

    agent = fa.SocialEngineerAgent(max_conversations=2)
    txs = agent.run(seed_profiles)

    # Not every conversation "succeeds", so this only asserts the run
    # completes and produces well formed output when it does.
    assert all(tx["attack_type"] == "social_engineering" for tx in txs)


@live_openai
def test_kyc_forger_agent_generates_real_bundles(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    agent = fa.KYCForgerAgent(max_kyc=2)
    txs = agent.run()

    assert len(txs) > 0
    assert all(tx["attack_type"] == "kyc_synthetic" for tx in txs)


@live_openai
def test_vendor_bec_agent_generates_real_narratives(isolated_generate_env):
    _auth, _verify, fa = isolated_generate_env
    seed_profiles = [{"customer_id": "cust_1", "customer_name": "Test", "avg_amount": 60.0, "currency": "USD"}]

    agent = fa.VendorBECAgent(max_narratives=2)
    txs = agent.run(seed_profiles)

    # Not every narrative "succeeds", so this only asserts the run
    # completes and produces well formed output when it does.
    assert all(tx["attack_type"] == "vendor_bec" for tx in txs)
