# Execution Authority Gate: Policy Layer Proof

Supporting evidence for the Mastercard submission, covering the
declarative policy layer added to the detect/mandate/sign pipeline. Every
number and code reference below is either quoted from [`CLAIMS.md`](CLAIMS.md)
(already independently verifiable against the committed
`web/data/dashboard.json`) or reproduced live in this document's own
verification section. Nothing here is estimated or rounded for effect.

## What changed

`pipeline/src/run_pipeline.py`'s decision logic used to be a hardcoded
`if/else` (`combine_decision`). It is now a declarative, versioned rule
document (`policy/policies/transaction-authorization/1.0.0/policy.json`),
evaluated by `policy/src/policy_engine.py`. The detect layer's decision
and every individual mandate rule's pass/fail become named signals in a
flat dict; the policy document's ordered rules decide, first match wins.
The shipped default is a literal re-encoding of the original logic — no
behavior changed for existing users, and mandate violations and detect
BLOCKs still always block; see [`ARCHITECTURE.md`](ARCHITECTURE.md#layer-35-policy)
for the full layer description and [`CLAIMS.md`](CLAIMS.md#policy-layer-added-in-a-later-session)
for the itemized claims and verify commands.

## Three real transactions through the actual pipeline

Run this session, through the real `mandate_checker`, `policy_engine`,
and `authority_signer` modules — not simulated, not hand-typed output.

| Scenario | Detect | Mandate | Policy outcome | Matched rule | Final |
|---|---|---|---|---|---|
| 1. Legitimate purchase, familiar merchant, within limit | ALLOW (score 0.12) | clean | APPROVE | `approve-default` | **ALLOW** |
| 2. Unfamiliar merchant, 3am, large amount | FLAG (score 0.68) | violated (`spending_limit`, `merchant_whitelist`, `time_restriction`) | REJECT | `reject-mandate-violation` | **BLOCK** |
| 3. Ordinary-looking purchase that pushes the customer over their monthly limit | ALLOW (score 0.24) — looks legitimate per-transaction | violated (`spending_limit`: $18,000 month-to-date + $4,200 current > $20,000 limit) | REJECT | `reject-mandate-violation` | **BLOCK** |

All three signed decisions verified independently
(`signature_verifier.verify_record(dict(signed), "authority") == True`),
using only the committed public key file — no access to the private key
or this session's runtime required.

Scenario 3 is the concrete case the mandate layer exists for: a
transaction whose per-transaction features (amount, merchant, hour) look
ordinary to the detector, but which a customer's own accumulated spending
history — something a per-transaction classifier structurally cannot see —
puts over their real limit. The detector alone would have allowed it; the
mandate layer, running independently, caught it. In the committed
production run, this pattern accounts for 26 of the 446 total blocks (see
Metrics below) — not a single constructed example, a measured count.

The real signed record shape for a rejected decision (field names exactly
as `authority_signer.sign_pipeline_decision` produces them):

```json
{
  "record_type": "pipeline_decision",
  "transaction_id": "txn_example_3_bustout",
  "fraud_score": 0.24,
  "detect_decision": "ALLOW",
  "mandate_allowed": false,
  "violated_mandate_rules": ["spending_limit"],
  "final_decision": "BLOCK",
  "reasons": ["mandate: spending_limit"],
  "caller_id": null,
  "policy_id": "transaction-authorization",
  "policy_version": "1.0.0",
  "matched_rule_id": "reject-mandate-violation",
  "record_id": "4f153239-532f-4726-a463-0caceba11600",
  "signed_at": 1788183922.4803858,
  "signer": "authority",
  "signature": "1eb0c5ca7b9881b4b85b7874630e56151032d78afa760a87f8f0c22fc10e7bbeb04038a154ecf5f2a7c8d1bd17d07cf11f814a2d0417a500941bca6afd10ec04"
}
```

(Captured live for this document; `record_id` and `signature` will differ on any other run — `signed_at` is a Unix timestamp, and the signature is non-deterministic by design, see `tests/test_signer.py::test_two_signings_of_the_same_payload_are_not_identical`.)

## Metrics (committed production run, not these three examples)

From `web/data/dashboard.json`, cited with file:line evidence in
[`CLAIMS.md`](CLAIMS.md):

- 23,037 transactions, 2.61% fraud rate (22,436 legitimate + 601 fraudulent)
- 6,912 decisions on the held-out test split: 446 BLOCK / 150 FLAG / 6,316 ALLOW
- Detection: 92.22% recall, 6.28% false positive rate, 28.18% precision
- Confusion matrix: TN 6,309 / FP 423 / FN 14 / TP 166
- Mandate-only blocks (detector scored low risk, mandate caught it anyway): **26**
- All 6,912 decisions signed and independently verified

See [`docs/JUDGES_GUIDE.md`](docs/JUDGES_GUIDE.md) for why 28% precision
at 92% recall is the expected, standard tradeoff for a rare-event
classifier, not a flaw, and [`CLAIMS.md`](CLAIMS.md#what-this-project-does-not-claim)
for what this project explicitly does not claim (no real payment
processor integration, not deployed with the pipeline running live,
metrics move slightly on regeneration by design since data generation
uses real, non-deterministic OpenAI calls).

## Test coverage

```
pytest tests/ -v
```

136 passed, 4 skipped (the 4 are opt-in tests that call the real OpenAI
API, unrelated to the policy layer). 47 of the 136 are new, covering the
policy engine's 24 operators, structural validation, first-match-wins
evaluation, and — the concrete proof of the underlying value
proposition — the same detect+mandate signals evaluated against two
different policy documents producing two different, equally auditable
outcomes (`tests/test_policy_engine.py::test_same_signals_different_policy_different_outcome`).
The 9 tests that already existed for the pre-policy-layer
`combine_decision` function pass unmodified — the refactor is
behavior-preserving by construction, not by claim.

## Verify this yourself

```bash
pytest tests/ -v                                    # 136 passed, 4 skipped
python pipeline/src/run_pipeline.py                  # regenerate the dashboard;
                                                      # detect.metrics is unchanged
python -c "import json; d=json.load(open('web/data/dashboard.json')); print(d['detect']['metrics'])"
```

## Repository

https://github.com/pavancharak/execution-authority-gate
Live dashboard: https://execution-authority-gate.fly.dev
