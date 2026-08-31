# Executive Summary: Execution Authority Gate

## One-liner

A fraud-defense pipeline where an ML detector and a deterministic mandate checker both get an independent vote on every transaction, and a declarative policy layer — not hardcoded code — decides how those votes combine into a signed, auditable decision.

## The problem

A fraud detector's output is a probability, not a decision. Turning that probability into a binary allow/block call, in a way a business can inspect, adjust, and defend to a regulator, is a separate problem from training a good classifier — and it's usually solved with scattered if/else logic buried in application code, not something anyone outside the engineering team can read or audit.

## The solution

Four layers, each independently testable:

1. **Detect** (`detect/`) — RandomForest classifier, 6 features, scores fraud probability. Advisory only; it cannot block anything by itself.
2. **Mandate** (`mandate/`) — deterministic rules (spending limit, merchant whitelist, time-of-day, daily velocity) derived from each customer's own transaction history, checked independently of the detector's score.
3. **Policy** (`policy/`) — the detector's decision and every mandate rule's pass/fail become named signals, evaluated against a declarative, versioned rule document (`policy/policies/transaction-authorization/1.0.0/policy.json`), first match wins. The shipped default: either the detector flagging BLOCK, or any mandate rule failing, rejects the transaction; a detector FLAG with a clean mandate requires step-up review; everything else is approved. A different policy document, evaluated against the same signals, can produce a different — but equally auditable — decision.
4. **Sign** (`sign/`) — every decision, including which policy and which specific rule produced it, is signed with Ed25519 by an identity neither the detector nor the mandate checker controls.

## Proof

Three real transactions run through the actual pipeline this session, every signature verified independently:

| Scenario | Detect | Mandate | Policy | Final |
|---|---|---|---|---|
| Legitimate purchase | ALLOW (0.12) | clean | APPROVE | ALLOW |
| High-risk, unfamiliar merchant, odd hour | FLAG (0.68) | violated | REJECT | BLOCK |
| Ordinary-looking purchase, but over the customer's real monthly spend | ALLOW (0.24) | violated (spending limit) | REJECT | BLOCK |

The third case is the one the mandate layer exists for: a transaction whose per-transaction features look ordinary to the detector, but which the customer's own accumulated spending — invisible to a per-transaction classifier — puts over their actual limit. In the committed production run (not these three examples), this exact pattern accounts for 26 of 446 total blocks: a measured count, not an anecdote. See [`MASTERCARD_SUBMISSION_PROOF.md`](MASTERCARD_SUBMISSION_PROOF.md) for the full signed record and verification steps.

## By the numbers

From the committed run behind `web/data/dashboard.json`, cited to file:line in [`CLAIMS.md`](CLAIMS.md):

- 23,037 transactions, 2.61% fraud rate
- 92.22% recall, 6.28% false positive rate, 28.18% precision (the standard recall/precision tradeoff for a rare-event classifier — see [`docs/JUDGES_GUIDE.md`](docs/JUDGES_GUIDE.md))
- 6,912 decisions, all signed, all independently verified
- 136 automated tests pass (47 of them new, added with the policy layer), 4 skipped by design (opt-in, real-OpenAI-API tests)

## What this does not claim

- Not deployed to production, and this repo has never processed a real transaction — see [`docs/PRODUCTION_DEPLOYMENT.md`](docs/PRODUCTION_DEPLOYMENT.md) for what real deployment would still require: per-customer counters moved to a shared store (currently in-process memory, scoped to one pipeline run), private keys backed by an HSM/KMS instead of a local file, and a real payment processor wired in behind the existing execution contract (`sign/src/decision_executor.py`'s webhook is a labeled simulation today).
- Not a claim that 92.2%/6.3% are fixed constants — they come from a non-deterministic data generation process (real OpenAI calls) and move slightly on regeneration by design.
- Not a claim that the policy layer supports multi-tenant routing across many policies at once — it evaluates one policy document per pipeline run.

## Repository

https://github.com/pavancharak/execution-authority-gate
Live dashboard: https://execution-authority-gate.fly.dev
