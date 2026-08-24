"""
Tests wiring detect + mandate + sign together end to end, the same way
pipeline/src/run_pipeline.py does, but against the hermetic synthetic
dataset and an isolated sign environment, not real files on disk.
"""

import detector as det
import mandate_checker as mc
import run_pipeline as rp


def _run_mini_pipeline(good, fraud, auth, verify):
    model, X_test, y_test, tx_test = det.train(good + fraud)
    metrics = det.evaluate(model, X_test, y_test)
    scores = metrics.pop("scores")

    by_customer = {}
    for tx in good:
        by_customer.setdefault(tx["customer_id"], []).append(tx)
    mandates = {cust_id: mc.derive_mandate_from_history(txs) for cust_id, txs in by_customer.items()}

    entries = []
    for tx, score in zip(tx_test, scores):
        detect_decision = det.decision_for_score(score)
        mandate = mandates.get(tx["customer_id"]) or mc.default_mandate(tx["customer_id"])
        mandate_result = mc.check_mandate(tx, mandate, month_to_date_total=0.0, tx_count_today=0)
        final_decision = rp.combine_decision(detect_decision, mandate_result)

        signed = auth.sign_pipeline_decision(
            tx["transaction_id"], score, detect_decision, mandate_result["mandate_allowed"],
            mandate_result["violated_rules"], final_decision, [],
        )
        entries.append({"decision": signed, "ground_truth": {"is_fraud": tx["is_fraud"]}})

    return entries, metrics


def test_full_pipeline_signs_every_decision_and_all_verify(synthetic_dataset, isolated_sign_env):
    auth, verify = isolated_sign_env
    good, fraud = synthetic_dataset

    entries, _metrics = _run_mini_pipeline(good, fraud, auth, verify)

    assert len(entries) > 0
    assert all(e["decision"]["final_decision"] in ("BLOCK", "FLAG", "ALLOW") for e in entries)
    assert all(verify.verify_record(dict(e["decision"]), "authority") for e in entries)


def test_final_decision_is_never_looser_than_either_layer(synthetic_dataset, isolated_sign_env):
    """BLOCK from either layer must always propagate to the final
    decision. This is the property the whole two layer pitch rests
    on."""
    auth, verify = isolated_sign_env
    good, fraud = synthetic_dataset

    entries, _metrics = _run_mini_pipeline(good, fraud, auth, verify)

    for e in entries:
        d = e["decision"]
        if d["detect_decision"] == "BLOCK" or not d["mandate_allowed"]:
            assert d["final_decision"] == "BLOCK"
        elif d["detect_decision"] == "ALLOW" and d["mandate_allowed"]:
            assert d["final_decision"] == "ALLOW"


def test_mandate_catches_fraud_the_detector_scores_as_low_risk(make_transaction, isolated_sign_env):
    """Construct the exact scenario the architecture exists for: a
    customer with a known, narrow pattern (one merchant, one hour
    window) whose stolen card gets used at a normal amount but the
    wrong hour. The transaction is engineered to look statistically
    unremarkable so we assert on the mandate outcome directly rather
    than relying on a trained model's score, which isn't the point of
    this test."""
    auth, verify = isolated_sign_env

    history = [make_transaction(False, customer_id="cust_1", merchant="UrbanCafe", amount=20, hour_of_day=10) for _ in range(10)]
    mandate = mc.derive_mandate_from_history(history)

    stolen_card_tx = make_transaction(True, customer_id="cust_1", merchant="UrbanCafe", amount=20, hour_of_day=2)

    mandate_result = mc.check_mandate(stolen_card_tx, mandate, month_to_date_total=0.0, tx_count_today=0)
    assert mandate_result["mandate_allowed"] is False
    assert "time_restriction" in mandate_result["violated_rules"]

    # Even if detect were to score this as low risk, the final decision
    # must still be BLOCK because the mandate layer objects.
    final_decision = rp.combine_decision("ALLOW", mandate_result)
    assert final_decision == "BLOCK"

    signed = auth.sign_pipeline_decision(
        stolen_card_tx["transaction_id"], 0.05, "ALLOW", False, mandate_result["violated_rules"], final_decision, []
    )
    assert verify.verify_record(dict(signed), "authority") is True
