# Execution-Authority-Gate: Architectural Gap Audit

Audited at commit `63cd740` (2026-08-24). Methodology: read `pipeline/`, `detect/`,
`mandate/`, `sign/`, `web/`, `tests/`, and `.gitignore` directly; traced the code path
from `pipeline/src/run_pipeline.py` end to end; ran the actual signer/verifier against
a real record from `pipeline/decisions/pipeline_decisions.json` to empirically confirm
what is and isn't tamper-evident. Every claim below cites `file:line`. Where
`ARCHITECTURE.md` asserts something the code doesn't do, that is called out explicitly.

---

## 1. Refusal Durability

### BLOCK Storage
- **Stored? PARTIAL, WEAKLY.** Every decision (not just BLOCK — ALLOW/FLAG/BLOCK
  alike) is appended in-memory during a pipeline run and written as one JSON array via
  `decision_log.write_log()`, `pipeline/src/decision_log.py:16-20`, which calls
  `path.write_text(json.dumps(entries, indent=2))` — a full **overwrite** of
  `pipeline/decisions/pipeline_decisions.json`, not an append-only log. Running the
  pipeline twice destroys the previous run's decisions.
  - Critically, `pipeline/decisions/` is **excluded from git**
    (`.gitignore:225`). There is no database, no object store, no external API
    call — confirmed by grep: no `requests`/`httpx`/`urllib`/webhook usage anywhere
    outside the unrelated OpenAI client used by the synthetic-data generator
    (`generate/src/llm_client.py`). The only persistence is a single local,
    git-ignored, overwrite-on-write JSON file.
- **Signed? YES, but not BLOCK-specific.** `sign_pipeline_decision()`
  (`sign/src/authority_signer.py:151-175`) is called for **every** final decision —
  ALLOW, FLAG, and BLOCK alike (`pipeline/src/run_pipeline.py:119-127`). There is no
  BLOCK-specific signing path; a BLOCK gets no stronger cryptographic treatment than
  an ALLOW.
- **Verifiable afterward? PARTIAL.** `signature_verifier.verify_record()`
  (`sign/src/signature_verifier.py:18-34`) checks a record's Ed25519 signature
  against `sign/tokens/{signer}_public_key.pem` using only public material, and
  is genuinely independent of the private key. However:
  - There is **no dedicated verify endpoint or CLI script** — grep across the repo
    for `verify_record` callers found only `run_pipeline.py`, `signature_verifier.py`
    itself, and test files. No `web/server.py` route, no `scripts/verify.py`. The only
    place verification is invoked in the actual pipeline is immediately after signing,
    in the same process, in the same run (`pipeline/src/run_pipeline.py:149-150`) — not
    as a later, separate re-verification.
  - `sign/tokens/keys/` (the private keys) and `sign/tokens/*.pem` (the public
    keys) are **also git-ignored** (`.gitignore:228-230`) and regenerated fresh
    on first run if absent (`sign/src/authority_signer.py:41-73`). That means a
    signature produced by one environment's keypair **cannot be verified by a fresh
    checkout of this repo** — the public key that would let anyone verify old
    signatures isn't committed anywhere durable. Verification is only meaningful
    within a single environment's lifetime, unless the operator manually preserves
    `sign/tokens/` outside git.

**Empirical check performed:** loaded a real BLOCK record from
`pipeline/decisions/pipeline_decisions.json`, verified its signature
(`True`), then mutated the record's sibling `ground_truth.amount` and
`mandate_checks[0].reason` fields (which sit outside the signed envelope — see
§2) and re-verified the same `decision` object's signature. It still returned
`True`, because those fields were never part of what got signed. See §2 for
detail.

**Gap:** Decisions are signed at creation time, but "stored" means a single
mutable, git-ignored local file that a second pipeline run silently replaces, and
"verifiable" means a function exists and works in-process — not that any operator,
judge, or downstream system has a durable, append-only, independently-fetchable
record to check against later. There is no BLOCK-specific durability guarantee
beyond what every ALLOW decision also gets.

---

## 2. Signal Verification

### Signals in Mandate Rules (`mandate/src/rules.py`, `mandate/src/mandate_checker.py`)

| Signal | Source | Independently verifiable after the fact? |
|---|---|---|
| `amount` | Transaction payload, `tx["amount"]` (`mandate_checker.py:62`) | **N** — stored unsigned in `ground_truth.amount` (`run_pipeline.py:136`), outside the signed envelope (empirically confirmed tamperable without invalidating the signature) |
| `merchant` | Transaction payload, `tx["merchant"]` (`mandate_checker.py:65`) | **N** — same as above, `ground_truth.merchant` is unsigned |
| `hour_of_day` | Transaction payload, `tx["hour_of_day"]` (`mandate_checker.py:68`) | **N** — not stored anywhere in `pipeline_decisions.json` at all, only paraphrased inside an unsigned free-text `reason` string (e.g. `"hour 5 is outside the allowed window (6-23)"`, `mandate/src/rules.py:26-30`) |
| `month_to_date_total` | Computed in-memory by the pipeline itself as a running per-customer sum over the test-set walk order (`run_pipeline.py:96,106,115`) | **N** — not derived from any ledger/authoritative balance; explicitly documented as "not a claim about real elapsed time" (`run_pipeline.py:91-95`); not persisted at all |
| `tx_count_today` | Same in-memory pipeline bookkeeping (`run_pipeline.py:97,107,116`) | **N** — same caveats as above |
| `monthly_limit_usd` | **Derived**, not sourced externally: `avg_amount * count * 1.5` over the customer's own historical good transactions (`mandate_checker.py:48`, inside `derive_mandate_from_history`, lines 32-52) | **N** — the mandate itself is recomputed fresh each pipeline run from data that is git-ignored (`generate/data/*.json`, `.gitignore:223`) and not saved per-decision |
| `allowed_merchants` | Derived from customer history (`mandate_checker.py:49`) | **N** — same as above |
| `allowed_hours` | Derived from customer history (`mandate_checker.py:50`) | **N** — same as above |
| `max_tx_per_day` | Derived from customer history (`mandate_checker.py:51`) | **N** — same as above |

### Signals in the Detect Model (`detect/src/detector.py`)

| Signal | Source | Independently verifiable after the fact? |
|---|---|---|
| `amount`, `hour_of_day`, `seconds_since_prev_tx` (→ `log_seconds_since_prev_tx`), `location_mismatch_km`, `pattern_similarity`, `ai_generated_signal` | Transaction payload (`detector.py:22-29` `FEATURES`, `_row()` at `detector.py:32-40`) | **N** — none of these six raw feature values are persisted in `pipeline_decisions.json`; only `amount` survives, and only in the unsigned `ground_truth` block |
| `fraud_score` | `model.predict_proba(X_test)[:, 1]` (`detector.py:76`), a `RandomForestClassifier` trained fresh each pipeline run (`detector.py:49-59`) | **Weakly Y for the number itself, N for recomputing it** — the score value IS inside the signed envelope (`fraud_score` field, `authority_signer.py:168`), so it's tamper-evident as a *number*. But it cannot be **recomputed/re-derived** later to check the model didn't hallucinate it, because: (a) the six raw features that produced it aren't stored per-transaction, (b) `detect/models/*.pkl` is git-ignored (`.gitignore:224`) and gets overwritten every run (`detector.py:62-65`), and (c) the source dataset comes from an LLM call at `temperature=0.9` (`generate/src/llm_client.py:114,127`), which is non-deterministic even with the same prompt, and that dataset (`generate/data/*.json`) is also git-ignored (`.gitignore:223`) |

**Gap:** The only signal that is both signed and independently checkable as a
*value* is `fraud_score` — and even that can't be **recomputed** from scratch
after the fact, because its inputs (raw features, trained model, source
dataset) are all ephemeral/git-ignored. Every other signal that feeds a
BLOCK/ALLOW decision (`amount`, `merchant`, `hour_of_day`,
`month_to_date_total`, `tx_count_today`, the four derived mandate parameters)
is either unsigned, not persisted at all, or both. Asking "was the fraud_score
actually 87, and was it computed from the transaction I think it was computed
from?" cannot be answered from this repo's persisted artifacts alone.

---

## 3. Execution Authority

### Decision → Action Trace
- **Decision made at:** `pipeline/src/run_pipeline.py:110` (`combine_decision()`,
  defined `run_pipeline.py:54-63`) — combines the detect layer's proposal
  (`detect/src/detector.py:125-130`, `decision_for_score`) and the mandate layer's
  result (`mandate/src/mandate_checker.py:55-82`, `check_mandate`).
- **Signed at:** `pipeline/src/run_pipeline.py:119-127`, calling
  `sign/src/authority_signer.py:151-175` (`sign_pipeline_decision`).
- **Executed at:** **NOT IMPLEMENTED anywhere in this repo.** After signing, the
  pipeline only (a) writes the decision to a local JSON file
  (`decision_log.write_log`, `pipeline/src/decision_log.py:16-20`) and (b) builds a
  static dashboard summary (`pipeline/src/dashboard_builder.py`,
  `run_pipeline.py:152-167`). Nothing in the codebase moves money, calls a payment
  processor, updates an external ledger, or notifies any downstream system. A
  repo-wide grep for `execute|charge|transfer|payment_api|move_money|debit|stripe|
  payment_gateway` (case-insensitive) matched only the synthetic **fraud-agent
  simulator's** internal operation counter (`generate/src/fraud_agents.py:69-92`,
  `self.executed` — a red-team harness tracking how many attack attempts a
  simulated attacker made against its token budget, unrelated to real transaction
  execution).
- **`ARCHITECTURE.md` overstates this layer.** `ARCHITECTURE.md:57` shows a step
  `[ENFORCE] authority_gateway.enforce(signed_decision)` in the documented decision
  flow, and line 28 claims "Every decision signed (Ed25519) and **enforced
  externally**." A repo-wide grep for `authority_gateway` and `.enforce(` matched
  **zero** occurrences outside `ARCHITECTURE.md` itself. This function/module does
  not exist in the code. "Enforced externally" is not demonstrated — it is asserted
  in documentation only, with no external system, webhook, queue, or API call
  wired up anywhere in this repo to hand the decision to.
- **Type: DECISION-ONLY.**

**Gap:** This repo is a fraud-detection-and-authorization *decision* layer. It has
no execution capability and no evidence of a real handoff to one — no outbound
HTTP call, no message queue publish, no webhook, no database write to an external
system of record. If Parmana needs the gate to actually stop money from moving
(not just produce a correctly-signed opinion that money *should* be stopped), that
integration does not exist yet and would need to be built from scratch.

---

## 4. Caller Scoping

### Authentication & Authorization
- **Caller auth mechanism: NONE.** The only network-facing code is
  `web/server.py:1-45`, a Flask app serving a static dashboard
  (`web/data/dashboard.json`) plus a `/api/status` health check
  (`web/server.py:26-29`). It has no login, no API key check, no JWT
  verification, no request-level authorization of any kind — `CORS(app)` at
  `web/server.py:23` allows any origin. The pipeline itself
  (`pipeline/src/run_pipeline.py`) is invoked as a local CLI script (`python
  run_pipeline.py`) with no caller-identity concept at all.
- **Caller identity captured per decision? NO.** Every signed record's `signer`
  field is hardcoded to the string `"authority"` (`sign/src/authority_signer.py:97`,
  `AUTHORITY = Signer("authority")`, used in `sign_record`, `authority_signer.py:91`).
  There is no field anywhere in a `pipeline_decision` record identifying *who
  requested* the transaction be evaluated — no client ID, no user ID, no service
  name.
- **What looks like caller auth but isn't:** `issue_agent_token()`
  (`sign/src/authority_signer.py:101-118`) issues a signed, bounded token
  (`agent_id`, `action`, `max_operations`, TTL) and is used in
  `generate/src/fraud_agents.py:68` (`self.token = auth.issue_agent_token(...)`).
  This is part of the **synthetic red-team simulation** — it models a fraud agent
  (an attacker) being granted a bounded number of operations, so the simulation can
  check whether the attacker exceeded its granted budget
  (`generate/src/fraud_agents.py:73,91-92`). It is not a caller-authorization
  system for legitimate callers of the mandate/pipeline system, and grants no
  differentiated *permissions* — every simulated agent gets exactly what it asks
  for (`fraud_agents.py:65-67` comment: "the authority grants exactly what's
  asked (a real deployment might grant less)").
- **Scoped permissions (RBAC/capabilities)? NO.** Grep for
  `RBAC|scope|permission|role|Authorization|Bearer` across `*.py` found only the
  above token-budget mechanism and an unrelated `.env.example` comment about the
  OpenAI API key (`generate/src/run_simulation.py:17`). There is no concept of
  caller A having different rights than caller B anywhere in the code that
  produces or signs a decision.

**Gap:** There is no caller authentication, no caller identity on decision
records, and no permission scoping. Every decision is signed by a single,
undifferentiated "authority" identity regardless of who — or what system —
triggered the pipeline run. The only "bounded permission" concept in the repo
exists purely inside the attack simulator, to test whether a simulated attacker
stays within its own self-requested budget, not to gate real callers.

---

## 5. Audit Completeness

### Test Coverage by Decision Type

Counted by reading every test function in `tests/*.py` (81 test functions across 8
files: `test_dashboard.py`(3), `test_detector.py`(7), `test_generate.py`(10),
`test_integration.py`(3), `test_mandate.py`(11), `test_pipeline.py`(8),
`test_properties.py`(5), `test_signer.py`(10) — plus `test_generate.py`, which is
unrelated to decisions).

- **ALLOW decision tests:** ~6 test functions directly assert or exercise an ALLOW
  outcome: `test_pipeline.py::test_combine_allow_when_both_clear` (17),
  `test_pipeline.py::test_combine_flag_only_when_mandate_has_no_objection` (32, FLAG
  not ALLOW but adjacent), `test_mandate.py::test_check_mandate_allows_within_bounds`
  (80-88), `test_detector.py::test_decision_for_score_thresholds` (6-12, ALLOW
  threshold), `test_integration.py::test_final_decision_is_never_looser_than_either_layer`
  (49-63, asserts the ALLOW branch), `test_dashboard.py::test_build_writes_expected_shape`
  (34-80, includes one ALLOW fixture entry).
- **BLOCK decision tests:** ~11 test functions directly assert or exercise a BLOCK
  outcome: `test_pipeline.py` (3 combine-tests at 20-29, 36-37, plus the summarize
  test at 48-60), `test_mandate.py` (`test_check_mandate_blocks_on_any_single_violation`
  91-100, `test_check_mandate_blocks_on_velocity` 103-110,
  `test_check_mandate_combines_multiple_violations` 113-123),
  `test_integration.py::test_mandate_catches_fraud_the_detector_scores_as_low_risk`
  (66-93), `test_signer.py` (`test_sign_block_decision_verifies` 21-25,
  `test_tampering_invalidates_signature` 53-60), `test_properties.py`
  (`test_verification_cannot_be_satisfied_by_a_different_authoritys_key` 23-49, uses
  a BLOCK record), `test_dashboard.py::test_build_writes_expected_shape` (2 BLOCK
  fixture entries).
- **Verification (re-verify a signed BLOCK) tests:** 5 test functions call
  `verify_record` on a record whose `final_decision`/`decision` is BLOCK:
  `test_signer.py::test_sign_block_decision_verifies` (21-25),
  `test_signer.py::test_sign_pipeline_decision_verifies` (28-35, `final_decision ==
  "BLOCK"`), `test_signer.py::test_tampering_invalidates_signature` (53-60),
  `test_integration.py::test_mandate_catches_fraud_the_detector_scores_as_low_risk`
  (66-93), `test_properties.py::test_verification_cannot_be_satisfied_by_a_different_authoritys_key`
  (23-49). `test_integration.py::test_full_pipeline_signs_every_decision_and_all_verify`
  (38-46) also verifies every entry in a batch generically, which necessarily
  includes some BLOCKs, but doesn't isolate/target BLOCK specifically.

**Gaps:**
- **No test re-verifies a BLOCK decision after it has been written to and re-read
  from `pipeline_decisions.json`.** Every verification test in the suite signs and
  verifies in the same in-memory step, inside `isolated_sign_env` (an ephemeral
  tmp-dir fixture, per `test_signer.py`'s docstring at lines 1-6). None load the
  real, on-disk `pipeline/decisions/pipeline_decisions.json` and check a record's
  signature against the persisted public key — the exact "verify it later" scenario
  §1 of this audit calls out as unimplemented in the pipeline itself.
- **No test asserts that `ground_truth` or `mandate_checks` are tamper-evident** —
  every tampering test (`test_signer.py::test_tampering_invalidates_signature`)
  mutates a field that's *inside* the signed envelope (`fraud_score`); none attempt
  to mutate `ground_truth.amount` or `mandate_checks[*].reason` to confirm (or, as
  this audit found, disconfirm) that those are protected too.
- **No test exercises caller identity or permission scoping**, because — per §4 —
  no such mechanism exists to test.
- **No test exercises the claimed `[ENFORCE]` step from `ARCHITECTURE.md`**,
  because — per §3 — no such code exists to test.

---

## Summary

Execution-Authority-Gate is a **decision-only fraud-and-mandate authorization
layer**, not an execution layer, and its own `ARCHITECTURE.md` overstates what
the code does: it documents an `[ENFORCE] authority_gateway.enforce(...)` step and
"enforced externally" as a guarantee, but no such enforcement code, external call,
or handoff exists anywhere in the repository. What *is* solidly implemented: a
genuine two-layer decision (`detect` + `mandate`) combined so either layer can
force a BLOCK (`run_pipeline.py:54-63`), and real Ed25519 signing/verification
with correct key separation and tamper-evidence for the fields that are actually
inside the signed envelope (empirically confirmed). What's missing for
trustworthy authorization at Parmana: (1) durable, append-only, git-tracked or
externally-stored decision records — today it's one overwritable, git-ignored
local JSON file, with the signing keys themselves also git-ignored and
regenerated per environment; (2) signed evidentiary detail — only `fraud_score`
and the mandate rule *names* are inside the signature, while the transaction
amount, merchant, hour, and every mandate parameter live in unsigned sibling
fields that can be silently edited without breaking verification; (3) any actual
execution or enforcement integration — this repo produces a correctly-signed
opinion and stops; (4) caller authentication and permission scoping — there is
no concept of who is asking for a decision, so nothing prevents one undifferentiated
"authority" identity from being invoked by anyone with local code access. In
short, EAG is a credible fraud-detection-plus-authorization *decisioning* prototype
with real cryptography where it applies it, but it is not yet a system whose BLOCK
outcomes are durable, whose inputs are independently re-verifiable, or that has any
authority over what actually happens next.
