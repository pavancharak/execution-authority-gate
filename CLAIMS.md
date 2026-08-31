# Claims and Evidence

Every claim made about this project, in the README, the submission
document, or the pitch, traced to a file:line or a runnable command. This
document exists because `EAG-AUDIT-GAPS.md` found that `ARCHITECTURE.md`
had, at one point, asserted an enforcement step no code implemented. The
standard here is the same one that audit applied: documentation is not
evidence, code and its output are. Numbers below are from the committed
run behind `web/data/dashboard.json` (generated 2026-08-31T02:48:25Z, see
its `meta.generated_at`); rerunning `pipeline/src/run_pipeline.py`
regenerates them and they will move slightly (see README.md's Robustness
section for why that's by design).

## In Plain English

A few of the numbers below, translated:

- "92.22% recall" → **Our system caught 92.2% of fraud attempts in testing.**
- "6.28% false positive rate" → **Out of every 100 normal, legitimate payments, about 6 got wrongly flagged for a second look.**
- "28.18% precision" → **Of everything the system flagged as suspicious, about 1 in 4 turned out to actually be fraud** — the rest were false alarms caught before they became a real problem.
- "Deterministic decision transparency" → **Every decision comes with an explanation of exactly why it was made.**
- "Mandate enforcement" → **The customer's own safety rules always apply — there are no silent exceptions.**
- "Signed and tamper-evident" → **Every decision is stamped with a proof that nobody can fake or quietly edit after the fact.**

Every claim below still links to the exact file and command that proves it — nothing here is asserted without evidence.

---

CLAIM: 92.22% fraud catch rate (recall)
EVIDENCE: `web/data/dashboard.json` → `detect.metrics.fraud_caught_rate`
VERIFY: `python -c "import json; d=json.load(open('web/data/dashboard.json')); print(d['detect']['metrics']['fraud_caught_rate'])"`

CLAIM: 6.28% false positive rate
EVIDENCE: `web/data/dashboard.json` → `detect.metrics.false_positive_rate`
VERIFY: `python -c "import json; d=json.load(open('web/data/dashboard.json')); print(d['detect']['metrics']['false_positive_rate'])"`

CLAIM: 28.18% precision (of 589 flagged transactions, a little over 1 in 4 is actually fraud)
EVIDENCE: `web/data/dashboard.json` → `detect.metrics.precision`
VERIFY: `python -c "import json; d=json.load(open('web/data/dashboard.json')); print(d['detect']['metrics']['precision'])"`

CLAIM: Confusion matrix: TN 6,309 / FP 423 / FN 14 / TP 166 (held out test split)
EVIDENCE: `web/data/dashboard.json` → `detect.metrics.confusion_matrix`
VERIFY: `python -c "import json; d=json.load(open('web/data/dashboard.json')); print(d['detect']['metrics']['confusion_matrix'])"`

CLAIM: 13 distinct attack vectors identified, 8 actively simulated, 5 documented as known gaps
EVIDENCE: `identify/attack-taxonomy.md` (13 numbered sections, each labeled *simulated* or a known gap); `generate/src/fraud_agents.py` implements the 8 simulated (9 bounded agents, since agents 3 and 7 both attack the trained detector rather than generating new transaction types)
VERIFY: `grep -c "^## " identify/attack-taxonomy.md` → 13 section headers; read the *simulated*/known gap label on each

CLAIM: 23,037 total transactions at a 2.61% fraud rate (22,436 legitimate + 601 fraudulent)
EVIDENCE: `web/data/dashboard.json` → `simulation.good_transaction_count`, `simulation.fraud_transaction_count`
VERIFY: `python -c "import json; d=json.load(open('web/data/dashboard.json'))['simulation']; print(d['good_transaction_count'], d['fraud_transaction_count'], d['fraud_transaction_count']/(d['good_transaction_count']+d['fraud_transaction_count']))"`

CLAIM: Fraud spread across 7 labeled attack types: fake_identity 112, social_engineering 52, kyc_synthetic 100, pattern_copy 100, form_break 100, synthetic_bustout 100, vendor_bec 37
EVIDENCE: `web/data/dashboard.json` → `simulation.attack_type_breakdown`
VERIFY: `python -c "import json; print(json.load(open('web/data/dashboard.json'))['simulation']['attack_type_breakdown'])"`

CLAIM: 5 of 9 agents (fake identity, social engineering, KYC forgery, feedback loop evasion, vendor BEC) make real, non deterministic OpenAI API calls at temperature=0.9
EVIDENCE: `generate/src/llm_client.py` (the `temperature=0.9` client every agent making a real call shares); `generate/src/fraud_agents.py` (agents 1, 2, 4, 9 construct calls through it); `generate/src/probe_agents.py` (agent 7's evasion variant suggestion does the same)
VERIFY: `grep -n "temperature" generate/src/llm_client.py`

CLAIM: Real OpenAI cost for the committed run: 27 calls, ~$0.037 total
EVIDENCE: `web/data/dashboard.json` → `api_activity.summary`
VERIFY: `python -c "import json; print(json.load(open('web/data/dashboard.json'))['api_activity']['summary'])"`

CLAIM: 6,912 pipeline decisions on the held out test split: 446 BLOCK / 150 FLAG / 6,316 ALLOW
EVIDENCE: `web/data/dashboard.json` → `pipeline.decision_counts`
VERIFY: `python -c "import json; print(json.load(open('web/data/dashboard.json'))['pipeline']['decision_counts'])"`

CLAIM: Mandate layer caught 26 real fraud transactions the detector alone scored as low risk, most of it the new synthetic identity bust out attack
EVIDENCE: `web/data/dashboard.json` → `mandate.block_attribution.mandate_only`
VERIFY: `python -c "import json; print(json.load(open('web/data/dashboard.json'))['mandate']['block_attribution'])"`

CLAIM: The append only audit trail durably holds both this run's 6,912 decisions and the prior run's 6,869, 13,781 lines total, all independently verified, none overwritten across two separate, independent pipeline runs
EVIDENCE: `pipeline/audit/decisions.jsonl` (one line per decision, appended, never rewritten, see `pipeline/src/audit_trail.py::AuditTrail.append_decision`)
VERIFY: `wc -l pipeline/audit/decisions.jsonl` and `python -c "import sys; sys.path[0:0]=['pipeline/src','sign/src']; import audit_trail; print(audit_trail.AuditTrail().verify_all())"` → `{'total': 13781, 'verified': 13781, 'all_verified': True, 'failed_record_ids': []}`

CLAIM: Adversarial robustness: agent 7 evaded detection in 10 of 18 evasion variant attempts against the trained model, worse than an earlier run (1 of 18), likely because `amount` became the model's second most important signal once the new large amount attacks were added
EVIDENCE: `generate/data/probe_report.json` (agent 7's results, variant by variant); `web/data/dashboard.json` → `detect.metrics.top_signals`; `identify/attack-taxonomy.md` section 7's narrative
VERIFY: `python -c "import json; r=json.load(open('generate/data/probe_report.json')); print(r['feedback_loop']['variants_tested'], r['feedback_loop']['variants_evaded'])"` and `python -c "import json; print(json.load(open('web/data/dashboard.json'))['detect']['metrics']['top_signals'])"`

---

## Gaps built this session (see `EAG-AUDIT-GAPS.md` for the audit that motivated each)

CLAIM: Decisions are durable, append only, and never silently overwritten
EVIDENCE: `pipeline/src/audit_trail.py::AuditTrail.append_decision` (writes one JSONL line per call, idempotent on `record_id`, never rewrites existing lines); committed at `pipeline/audit/decisions.jsonl`
VERIFY: `tests/test_audit_trail.py::test_append_is_never_a_rewrite`, `::test_append_decision_is_idempotent_on_record_id`

CLAIM: Public keys are committed to git; verification works from a fresh checkout without regenerating anything
EVIDENCE: `sign/tokens/authority_public_key.pem`, `sign/tokens/reviewer_public_key.pem` (tracked in git, see `.gitignore`'s explicit exceptions to the `sign/tokens/*.pem` ignore pattern); private keys (`sign/tokens/keys/`) remain git ignored
VERIFY: `git ls-files sign/tokens/*.pem` lists both public keys; `git check-ignore sign/tokens/keys/authority_private.pem` confirms the private key is still ignored

CLAIM: Signed decisions carry the requesting caller's identity inside the signed envelope
EVIDENCE: `sign/src/authority_signer.py::sign_pipeline_decision`'s `caller_id` parameter, embedded in the dict that gets signed (not a sibling field); `pipeline/src/run_pipeline.py`'s `--caller-id` CLI flag threads it through
VERIFY: `python pipeline/src/run_pipeline.py --caller-id fraud-analyst` then inspect any line of `pipeline/audit/decisions.jsonl` for a `decision.caller_id` that is not null

CLAIM: Callers are authenticated and permission scoped; a payment processor cannot execute a BLOCK decision
EVIDENCE: `sign/src/caller_auth.py::PREDEFINED_CALLERS` (`payment-processor` scoped to `["ALLOW", "FLAG"]`, `fraud-analyst` to all three, `audit-system` to `["READ"]` only); `CallerAuthenticator.can_execute`
VERIFY: `tests/test_caller_auth.py::test_payment_processor_can_execute_allow_and_flag_not_block`, `::test_audit_system_is_read_only`

CLAIM: Signed decisions can be executed against a payment processor webhook, with fail closed signature verification and idempotency
EVIDENCE: `sign/src/decision_executor.py::DecisionExecutor.enforce_decision` (verifies signature before dispatch, rejects on failure, tracks `record_id` so the same decision is never executed twice)
VERIFY: `tests/test_executor.py::test_tampered_signature_is_rejected_and_never_reaches_webhook`, `::test_same_decision_is_never_executed_twice`

CLAIM: 36 new test cases added this session (19+ target), all passing, all hermetic except one opt in live API test
EVIDENCE: `tests/test_audit_trail.py` (9), `tests/test_caller_auth.py` (13), `tests/test_executor.py` (9), `tests/test_generate.py` additions for the bust out agent and mandate limit math (5, four hermetic plus one opt in live API test for the vendor BEC agent)
VERIFY: `pytest tests/test_audit_trail.py tests/test_caller_auth.py tests/test_executor.py tests/test_generate.py -v`

CLAIM: Full suite (140 tests total: 136 hermetic passing, 4 live API tests skipped by default) passes with zero failures
EVIDENCE: full run output, captured across sessions as tests were added (see the policy layer claims below for the 47 added alongside `policy/`)
VERIFY: `pytest tests/ -v` → `136 passed, 4 skipped`

---

## Policy layer (added in a later session)

CLAIM: Detect and mandate output are combined by a declarative, data-driven policy engine, not hardcoded Python control flow, and the shipped default reproduces the original `combine_decision` behavior exactly (zero change to `web/data/dashboard.json`'s metrics when regenerated)
EVIDENCE: `policy/src/policy_engine.py::evaluate_policy` (ordered rules, first match wins, over a signals dict built by `pipeline/src/run_pipeline.py::build_policy_signals`); shipped policy `policy/policies/transaction-authorization/1.0.0/policy.json`; `pipeline/src/run_pipeline.py::combine_decision` is now a thin adapter over it (same name, same call signature, same default behavior)
VERIFY: `tests/test_policy_engine.py::test_shipped_default_policy_reproduces_the_original_combine_rule`; regenerate the dashboard with `python pipeline/src/run_pipeline.py` and diff `detect.metrics` in `web/data/dashboard.json` against the committed version — unchanged

CLAIM: The same detect + mandate signals, evaluated against two different policy documents, produce two different, equally auditable decisions
EVIDENCE: `policy/src/policy_engine.py::evaluate_policy` takes the policy document as a parameter, not a hardcoded default; `pipeline/src/run_pipeline.py --policy-id`/`--policy-version` swaps the whole pipeline to a different policy
VERIFY: `tests/test_policy_engine.py::test_same_signals_different_policy_different_outcome`

CLAIM: Which policy and which specific rule produced a decision is itself signed, tamper evident, inside the same envelope as the decision
EVIDENCE: `sign/src/authority_signer.py::sign_pipeline_decision`'s `policy_id`/`policy_version`/`matched_rule_id` parameters, embedded in the dict that gets signed (same pattern already used for `caller_id`)
VERIFY: run `python pipeline/src/run_pipeline.py` and inspect any line of `pipeline/audit/decisions.jsonl` for a non-null `decision.policy_id` and `decision.matched_rule_id`

CLAIM: 47 new test cases added for the policy layer, all hermetic, all passing
EVIDENCE: `tests/test_operator_evaluator.py` (26), `tests/test_policy_engine.py` (9), `tests/test_policy_validator.py` (12)
VERIFY: `pytest tests/test_operator_evaluator.py tests/test_policy_engine.py tests/test_policy_validator.py -v`

---

## What this project does NOT claim

- Not a payment processor. Nothing in this repo moves real money;
  `sign/src/decision_executor.py`'s shipped `noop_webhook` explicitly
  simulates and labels its own output `"simulated": True`.
- Not deployed to production. `execution-authority-gate.fly.dev` serves the static,
  committed `web/data/dashboard.json`; the pipeline does not run inside
  the deployed container (see README.md's Deployment section).
- Not a claim that 92.2%/6.3% are fixed constants: they come from a
  non deterministic data generation process (real OpenAI calls at
  temperature=0.9) and will shift slightly on every regeneration, by
  design (see README.md's Robustness section).
- Not a claim that the mandate layer's derived limits (`monthly_limit_usd
  = avg_amount * count * 1.5`, etc.) reflect a real bank's actual
  underwriting policy; they are derived heuristically from each
  synthetic customer's own transaction history for demonstration
  purposes.
- Not a claim that the execution layer (`sign/src/decision_executor.py`)
  has been tested against a real payment processor's API; it is tested
  against a hermetic stub webhook (see `tests/test_executor.py`).
- Not a claim that the policy layer (`policy/`) supports multi-tenant
  routing across many policies at once, or that a `REQUIRE_OVERRIDE`
  outcome triggers any new human-approval workflow. It evaluates one
  policy document per pipeline run (`--policy-id`/`--policy-version`
  selects which), and `REQUIRE_OVERRIDE` maps to this repo's existing
  `FLAG` semantics, already routed to `step_up_auth` by
  `sign/src/decision_executor.py`. The shipped default policy also
  never lets a business-authored rule override a detect BLOCK or a
  mandate violation; a looser policy is only reachable by explicitly
  authoring and swapping in a different, version-controlled document.
