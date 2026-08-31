# Production Deployment Guide

This document describes what would need to be true for Execution Authority
Gate to run as a production authorization system, not the demo prototype
committed in this repo. It is written to be checked against the code, the
same standard `EAG-AUDIT-GAPS.md` holds this project to: where a claim
below is already implemented, it names the file; where it isn't, it says
so plainly. Nothing here should be read as "already running in production."
This repo has never processed a real transaction.

## Scope: what this system is and is not

Execution Authority Gate is a **decision ready authorization layer**: it detects, checks
against a mandate, signs, and (as of the execution layer described below)
can hand a signed decision to a downstream integration for enforcement.
It is not a payment processor, not a ledger, and does not itself move
money. Every claim in this document uses "execution ready" rather than
"enforced" for that reason. See `ARCHITECTURE.md`'s "Known limits"
section for the full history of that distinction being corrected after
an earlier draft overstated it.

## Latency SLA

Estimated per layer budget for a single transaction, synchronous path,
target under 200ms end to end:

| Layer | Work | Budget |
|---|---|---|
| Detect | `RandomForestClassifier.predict_proba` on 6 features, `detect/src/detector.py` | under 100ms |
| Mandate | 4 deterministic rule checks against a cached customer mandate, `mandate/src/mandate_checker.py` | under 50ms |
| Sign | One Ed25519 sign operation, `sign/src/authority_signer.py` | under 10ms |
| Execute | Signature verify, idempotency lookup, and webhook dispatch, `sign/src/decision_executor.py` | under 20ms (excluding the downstream processor's own latency, which is out of this system's control) |
| **Total** | | **under 200ms**, not counting network round trip to the payment processor itself |

These are engineering estimates based on the operations involved (a
single forest inference, four comparisons in memory, one signature),
not a load test run against this repo. `detect/src/detector.py`'s
model (`n_estimators=80, max_depth=5`) is small enough that inference on
a single row takes well under a millisecond on commodity hardware in
isolation; the 100ms budget above is deliberately generous to leave
headroom for feature assembly and network overhead in a real request path.

## Scalability

- **Detect**: stateless once the model is loaded (`detect/src/detector.py::load_model`).
  A `RandomForestClassifier` this size can score single rows fast enough
  to exceed 10K tx/sec per instance; horizontal autoscaling behind a load
  balancer, not retraining per transaction, is the scaling lever.
  Retraining (see "Model drift" below) is a separate, offline, scheduled
  job, never on the request path.
- **Mandate**: each customer's mandate (`mandate/src/mandate_checker.py::derive_mandate_from_history`)
  is derived once from historical transactions and does not change per
  transaction. In production this is a cache lookup (e.g. Redis,
  keyed on `customer_id`), not a recomputation from full history on
  every request. `month_to_date` and `tx_count_today` (currently
  dicts held in memory, scoped to one `run_pipeline.py` process, see
  `pipeline/src/run_pipeline.py` lines 96 to 97) would need to move to a
  real per customer counter store (e.g. Redis `INCR` with a key scoped
  to the day or month) to survive across requests and instances.
- **Sign**: Ed25519 signing is single purpose and fast, but the private
  key must have exactly one place it can be used from (see Key
  Management below), so this layer scales by adding stateless replicas
  in front of a single signing endpoint backed by an HSM or KMS, not by
  distributing the private key itself.
- **Executor**: `sign/src/decision_executor.py`'s idempotency check
  (`ExecutionLog.already_executed`) currently does a linear scan over a
  JSONL file, adequate for this repo's demo scale but not for 100M
  tx/day. Production scale needs the idempotency check backed by an
  indexed store (a database unique constraint on `record_id`, or a
  keyed cache), which is exactly the kind of swap described in
  "Audit trail" below.
- **Target**: at 100M tx/day (about 1,160 tx/sec average, with realistic
  peak multiples of 5 to 10x), the detect and mandate layers scale
  horizontally without architectural change; the signing and audit
  writes are the layers that need a single, durable, highly available
  backing store rather than more compute.

## Deployment Architecture

```
                     ┌─────────────────┐
   transaction  ───▶ │ Detection service │  stateless, autoscales
                     │ (detect/src)      │
                     └─────────┬─────────┘
                               │ fraud_score, detect_decision
                               ▼
                     ┌─────────────────┐
                     │ Mandate service   │  per customer rules cached
                     │ (mandate/src)     │  in Redis, keyed on customer_id
                     └─────────┬─────────┘
                               │ mandate_allowed, violated_rules
                               ▼
                     ┌─────────────────┐
                     │ Signing service   │  HSM/KMS backed, single
                     │ (sign/src)        │  logical writer, high
                     │                   │  availability via stateless
                     └─────────┬─────────┘  replicas in front of the HSM
                               │ signed decision
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
       ┌──────────────────┐       ┌────────────────────┐
       │ Decision executor │       │ Audit trail          │
       │ (sign/src/        │──────▶│ append only Postgres │
       │  decision_executor)│      │ table + JSONL backup │
       │                    │      │ (pipeline/src/        │
       │ POST to payment    │      │  audit_trail.py)      │
       │ processor webhook  │      └────────────────────┘
       └────────┬───────────┘
                 ▼
       external payment processor
       (not part of this repo)
```

This repo implements every box above except "external payment
processor" and the Postgres backing for the audit trail (the current
implementation is JSONL only, see "Audit trail" below).

## Key Management

- **Private signing key**: `sign/src/authority_signer.py` currently
  generates and persists an Ed25519 private key to a local file
  (`sign/tokens/keys/authority_private.pem`) on first use, and that
  file is git ignored (correct for a demo: private keys must never be
  committed). In production, this key must live in an HSM or a managed
  KMS (AWS KMS, GCP Cloud KMS, HashiCorp Vault) with signing performed
  via an API call that never returns the raw key material, not a file
  on a filesystem any process can read.
- **Public key**: committed to git at `sign/tokens/authority_public_key.pem`
  and `sign/tokens/reviewer_public_key.pem` (see `.gitignore`, which
  explicitly excepts these two files from the pattern that otherwise
  ignores `sign/tokens/*.pem`). This is what makes verification
  reproducible: `sign/src/signature_verifier.py::verify_record` reads
  only this file, never the private key, so anyone with a checkout of
  this repo, including a judge or auditor with no other credentials,
  can independently verify any previously signed decision, current or
  historical, without needing access to the signer.
- **Caller auth secret**: `sign/src/caller_auth.py` uses a separate
  HMAC SHA256 secret (`sign/tokens/keys/caller_auth_secret.key`,
  git ignored) to sign caller tokens. This is a distinct trust boundary
  from the Ed25519 key that signs decisions, by design: a caller proving
  its own identity should never be the same secret that makes a
  decision's *content* authoritative (see `caller_auth.py`'s module
  docstring for why conflating the two would reintroduce
  self authorization).
- **Key rotation policy**: quarterly rotation recommended for both the
  signing key and the caller auth secret. Rotating the Ed25519 signing
  key requires publishing the new public key alongside the old one (so
  historical decisions still verify against the key that actually
  signed them) and updating `sign/src/authority_signer.py`'s
  `_load_or_create_keypair` to select the active key by a version field
  embedded in each signed record. That version field does not exist in
  the current schema and is a concrete gap: today, rotating the key
  would make the new key sign new decisions but the code has no
  explicit mechanism to record which key version signed a given
  historical record. This is called out honestly rather than implied
  as solved.

## Regulatory Compliance

- **PCI DSS**: the append only audit trail (`pipeline/src/audit_trail.py`)
  satisfies the non repudiation intent of PCI DSS Requirement 10 (track
  and monitor all access to cardholder data and system resources) for
  the decisioning layer specifically: every decision, its signature,
  and (once caller auth is wired to every call site) the requesting
  caller are durably recorded and cannot be silently altered without
  invalidating the signature. This repo's mandate and detect layers do
  not themselves store cardholder data (PAN, CVV); a real deployment
  must separately confirm PCI DSS scope for wherever `amount`,
  `merchant`, and similar transaction fields are persisted (currently
  the unsigned `ground_truth` sibling field, see `ARCHITECTURE.md`'s
  Verification section for what is and isn't inside the signed
  envelope).
- **RBI (India)**: the mandate layer's per customer spending limit,
  merchant whitelist, time restriction, and velocity checks
  (`mandate/src/rules.py`) are the same shape of control RBI's
  transaction monitoring guidance for AML expects: deterministic,
  auditable rules independent of a black box model score. This repo
  does not implement RBI's specific reporting formats (e.g. STR
  filing) and would need that built as a separate downstream consumer
  of the audit trail.
- **GDPR**: the audit trail is the durable record a customer dispute or
  data subject access request would be answered from (what decision
  was made, when, on what evidence, by what authority). Because
  `ground_truth` (which can contain data derived from a data subject)
  is currently unsigned and not redacted, a production deployment needs
  a defined retention and erasure policy for the audit trail consistent
  with GDPR Article 17, which an append only log makes structurally
  harder (erasing one record without breaking the trail's append only
  property for every other record is an open design question this repo
  does not resolve).

## Limitations & Mitigations

- **6.8% false positive rate**: a FLAG from the detect layer does not
  auto block; `pipeline/src/run_pipeline.py::combine_decision` only
  escalates FLAG to BLOCK if the mandate layer also objects, and
  `sign/src/decision_executor.py`'s `ACTION_FOR_DECISION` maps FLAG to
  `step_up_auth`, not `deny`. A legitimate customer hitting a false
  positive is asked to step up authentication, not turned away.
- **10.9% false negative rate** (`1 - fraud_caught_rate`): an accepted
  tradeoff at this recall/precision operating point (see README.md's
  "Why precision is 21.1%" section for the full reasoning). Mitigated,
  not eliminated, by the independent mandate layer, which caught 8 real
  fraud transactions the detector alone scored as low risk in the
  committed run (`web/data/dashboard.json` → block attribution →
  `mandate_only`).
- **Model drift**: `detect/models/detector.pkl` is trained once, at
  pipeline run time, on a fixed dataset. Production needs a scheduled
  retraining pipeline (monthly is a reasonable starting cadence) using
  real chargeback labels as ground truth once they're available, not
  the synthetic fraud labels this repo trains on. This repo does not
  implement that scheduler; it is a gap, not a hidden feature.

## Integration Checklist

For a payment processor integrating with this system's execution layer
(`sign/src/decision_executor.py` / `POST /api/enforce/decisions`):

1. Obtain a caller token via `POST /api/callers/token` with a registered
   `caller_id` (see `sign/src/caller_auth.py::PREDEFINED_CALLERS`;
   `payment-processor` is the predefined identity scoped to ALLOW/FLAG,
   not BLOCK).
2. Confirm the token's `expires_at` and request a new one before expiry;
   tokens are not silently renewed.
3. Fetch the authority's public key from `sign/tokens/authority_public_key.pem`
   (committed to git, so a fresh checkout or a pinned copy both work) and
   verify out of band that it matches what your integration expects, not
   just what the API returns at runtime.
4. Send signed decisions to `POST /api/enforce/decisions` with
   `Authorization: Bearer <token>`, body `{"decisions": [...]}`.
5. Handle each result's `status`: `EXECUTED`, `ALREADY_EXECUTED`, or
   `REJECTED` (with a `reason`). Never retry a `REJECTED` decision with
   the same payload expecting a different outcome; a rejection reflects
   either an invalid signature or a permission the caller does not have,
   neither of which changes on retry.
6. Treat `ALREADY_EXECUTED` as a success, not an error: it means this
   exact decision (by `record_id`) was already handed to your webhook,
   idempotency guarantees you will not settle it twice.
7. Implement your actual `payment_processor_webhook` callable (or HTTP
   endpoint, if adapting `decision_executor.py`'s callable contract to a
   real HTTP call) to perform the action named in each result:
   `settle` for ALLOW, `step_up_auth` for FLAG, `deny` for BLOCK.
8. Never call your own settle or deny logic directly from a signed
   decision without going through `enforce_decision`: that function is
   what enforces signature validity, caller permission, and idempotency
   together. Bypassing it reintroduces exactly the gaps
   `EAG-AUDIT-GAPS.md` documented.
9. Log your own webhook's response alongside `sign/src/decision_executor.py::ExecutionLog`'s
   entry (`executor.log.path`) for your own reconciliation; the
   execution log records what this system attempted, not what your
   downstream system ultimately did with it.
10. Do not treat a `FLAG` to `step_up_auth` action as equivalent to
    `ALLOW`; require the step up to actually complete before settling.
11. Rotate your caller token on the schedule this deployment's operator
    sets (see Key Management), not indefinitely.
12. Verify every decision's signature yourself before acting on it, even
    though `enforce_decision` already does this on the server side; an
    integration with defense in depth does not trust a single
    verification point.
13. Reconcile your own settlement records against `pipeline/src/audit_trail.py`'s
    `decisions.jsonl` on a regular cadence (e.g. daily) to catch any
    drift between what was authorized and what was actually settled.
14. Confirm your integration handles `BLOCK` decisions correctly if
    your `caller_id` is `fraud-analyst` (full access) rather than
    `payment-processor` (ALLOW/FLAG only); most payment processor
    integrations should use the latter and let a human reviewer's
    `fraud-analyst` token handle BLOCK escalation.
15. Before going live, run this repo's test suite
    (`pytest tests/ -v`) against your fork or deployment to confirm no
    local changes broke the signature, idempotency, or permission
    guarantees this checklist depends on.

## Audit trail: current state vs. production target

Today: `pipeline/src/audit_trail.py`'s `AuditTrail` writes one JSON line
per decision to `pipeline/audit/decisions.jsonl`, append only, never
rewritten, idempotent on `record_id`. This is a real durability
improvement over the previous `pipeline/decisions/pipeline_decisions.json`
(a single JSON array, fully overwritten on every pipeline run, and git
ignored, see `EAG-AUDIT-GAPS.md` section 1), and the JSONL file is not
git ignored, so it can be committed as durable evidence.

At production scale, JSONL alone does not provide indexed lookups, so
the target architecture adds a Postgres table (`decisions(record_id
PRIMARY KEY, transaction_id, signed_at, final_decision, signature, ...)`)
as the primary store, with the JSONL file retained as a portable backup
with no dependencies, and as the artifact judges or auditors without
database access can still verify directly (`AuditTrail.verify_all()`
requires nothing but this repo and the committed public key). This repo
implements the JSONL half of that target; the Postgres half is not
built and is named here as the concrete next step, not implied as done.
