# Execution Authority Gate

[![Tests](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml/badge.svg)](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Live dashboard: [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev)**

Execution Authority Gate makes fraud detection, authorization, and cryptographic proof three separate, independent steps, instead of one model's opinion. A trained detector and a deterministic mandate checker each get an equal, unqualified vote on every transaction, either one objecting is enough to stop it, and a third party neither of them controls signs whatever the combined answer is, ALLOW, FLAG, or BLOCK alike, into a tamper evident record.

## Table of Contents

1. [What Is Execution Authority Gate?](#1-what-is-execution-authority-gate)
2. [Core Principle](#2-core-principle)
3. [Architecture Overview](#3-architecture-overview)
4. [Decision Flow](#4-decision-flow)
5. [Code Examples](#5-code-examples)
6. [Real-World Scenarios](#6-real-world-scenarios)
7. [Quick Start](#7-quick-start)
8. [Try It Live](#8-try-it-live)
9. [Metrics and Validation](#9-metrics-and-validation)
10. [Production Deployment and Execution Integration](#10-production-deployment-and-execution-integration)
11. [Testing](#11-testing)
12. [Structure](#12-structure)
13. [Deployment](#13-deployment)
14. [FAQ](#14-faq)
15. [License](#15-license)

---

## 1. What Is Execution Authority Gate?

**One-liner:** A two layer fraud defense pipeline, an ML detector and a deterministic mandate checker, whose combined decision is cryptographically signed by a party neither layer controls, so the decision is provable and unforgeable after the fact.

**Expanded:** Every transaction is scored by a RandomForest fraud detector *and* checked against that specific customer's own derived spending mandate, independently, in parallel. Neither layer sees or trusts the other's reasoning. If either one objects, the transaction is blocked. Whatever the outcome, an external signer, holding a private key neither the detector nor the mandate checker has access to, signs the full decision record with Ed25519. The signature doesn't decide anything; it makes the decision that was already made impossible to alter or forge afterward.

**Not what this project is:**
- Not a single model deciding alone. Detection and mandate are independent and either can veto.
- Not a black box. Every BLOCK cites the specific rule or signal that fired (`web/data/dashboard.json` → `reasons`).
- Not a payment processor. Nothing here moves real money; the execution layer's shipped webhook is a labeled simulation (see [Section 10](#10-production-deployment-and-execution-integration)).
- Not "signing as a veto." Signing runs on every decision, ALLOW included, it is proof of what was decided, not a third check that can change the outcome.

**What this project is:**
- A **Detection Layer** (`detect/`): RandomForest classifier, six features, scores fraud probability.
- A **Mandate Layer** (`mandate/`): deterministic rules derived from each customer's own transaction history.
- A **Policy Layer** (`policy/`): a declarative, versioned rule engine that turns detect + mandate output into a final decision — the shipped default reproduces the original combine logic exactly, as data instead of code; a different policy document can be swapped in without touching detect or mandate at all.
- A **Signing Layer** (`sign/`): Ed25519 signatures over every final decision, with caller identity and the policy that produced the decision embedded in the signed envelope.
- An **Audit Trail** (`pipeline/audit/decisions.jsonl`): append only, committed to git, independently re-verifiable at any time.
- An **Execution Layer** (`sign/src/decision_executor.py`): signed decisions ready for handoff to a payment processor webhook, fail closed and idempotent.

---

## 2. Core Principle

```
DETECTION ≠ AUTHORIZATION ≠ PROOF

Detection asks:      "Does this look like fraud?"        (probabilistic, ML)
Mandate asks:         "Is this actually authorized?"       (deterministic, rules)
Signing asks:         "Can I prove what was decided?"       (cryptographic, Ed25519)

Any layer can block. Only the combination is trusted.
Signing proves the decision; it does not make it.
```

Why this matters:
- **Detector accuracy varies.** It's trained on a real, non-deterministic dataset (see [Robustness](#9-metrics-and-validation)) and its precision is intentionally traded for recall (28.2% precision at 92.2% recall — see the [Judges' Guide](docs/JUDGES_GUIDE.md)).
- **Mandate is explicit and auditable.** Four rules, spending limit, merchant whitelist, time restriction, velocity, all AND'd together, all traceable to `mandate/src/rules.py`.
- **The combination catches what either layer alone would miss.** A transaction that looks statistically ordinary to the detector (low fraud score) can still violate a mandate rule, and vice versa. See the synthetic identity bust-out example in [Section 6](#6-real-world-scenarios).
- **The decision is cryptographically signed**, and the signing key is held by neither the detector nor the mandate checker, so neither layer can self-approve its own output.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        INCOMING TRANSACTION                       │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
                 ┌───────────────┴────────────────┐
                 ▼                                 ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│        DETECT LAYER            │   │        MANDATE LAYER          │
│  detect/src/detector.py        │   │  mandate/src/mandate_checker.py│
│                                 │   │                                │
│  RandomForest, 6 features:      │   │  Derived from the customer's   │
│  amount, hour, log seconds       │   │  own known-good history:       │
│  since prior tx, location        │   │  spending limit, merchant      │
│  mismatch, pattern similarity,   │   │  whitelist, time window,       │
│  AI-generated signal              │   │  daily velocity — all AND'd    │
│                                 │   │                                │
│  Output: fraud_score (0-1) →      │   │  Output: mandate_allowed        │
│  BLOCK | FLAG | ALLOW            │   │  (bool) + violated_rules[]      │
│  Probabilistic, model-dependent   │   │  Deterministic, no ML at all    │
└───────────────┬─────────────────┘   └────────────────┬───────────────┘
                 │                                       │
                 └──────────────────┬────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │          POLICY                  │
                    │  policy/src/policy_engine.py      │
                    │                                    │
                    │  detect_decision, mandate_allowed,  │
                    │  and every mandate rule's pass/fail  │
                    │  become named signals, evaluated       │
                    │  against a declarative, versioned       │
                    │  policy document (first match wins)     │
                    │                                    │
                    │  Output: APPROVE | REQUIRE_OVERRIDE |  │
                    │  REJECT + which rule matched            │
                    │  Shipped default reproduces the          │
                    │  original combine rule exactly            │
                    └────────────────┬────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │         COMBINE                  │
                    │  pipeline/src/run_pipeline.py     │
                    │  combine_decision()                │
                    │                                    │
                    │  thin adapter over the policy        │
                    │  result above:                        │
                    │  REJECT           → BLOCK              │
                    │  REQUIRE_OVERRIDE → FLAG                │
                    │  APPROVE          → ALLOW                │
                    └────────────────┬────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │           SIGN                   │
                    │  sign/src/authority_signer.py     │
                    │                                    │
                    │  Ed25519 over transaction_id,       │
                    │  fraud_score, detect_decision,       │
                    │  mandate_allowed, violated_rules,     │
                    │  final_decision, reasons, caller_id,   │
                    │  policy_id, policy_version,             │
                    │  matched_rule_id                         │
                    │  Neither layer above holds this key   │
                    └────────────────┬────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │        AUDIT TRAIL                │
                    │  pipeline/audit/decisions.jsonl     │
                    │  append-only, committed, re-         │
                    │  verifiable anytime                  │
                    └────────────────┬────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │          EXECUTE                  │
                    │  sign/src/decision_executor.py     │
                    │  POST /api/enforce/decisions        │
                    │                                    │
                    │  verify signature (fail closed) →    │
                    │  check caller permission →            │
                    │  idempotent handoff to a               │
                    │  payment_processor_webhook             │
                    │  (shipped webhook is a labeled          │
                    │  simulation — see Section 10)           │
                    └─────────────────────────────────┘
```

---

## 4. Decision Flow

### `combine_decision` — now a thin adapter over the policy layer

```python
# pipeline/src/run_pipeline.py
def combine_decision(detect_decision, mandate_result, fraud_score=None, amount=None, policy=None):
    result = decide(detect_decision, mandate_result, fraud_score=fraud_score, amount=amount, policy=policy)
    return _OUTCOME_TO_DECISION[result["outcome"]]  # REJECT->BLOCK, REQUIRE_OVERRIDE->FLAG, APPROVE->ALLOW
```

Same function, same call signature as before, same default behavior: BLOCK wins over everything, a clean mandate never downgrades a detect BLOCK, and a clean detect score never upgrades a mandate violation past BLOCK. What changed is *how* that decision gets made — `decide()` builds a signals dict (`detect_decision`, `mandate_allowed`, one boolean per mandate rule) and evaluates it against `policy/policies/transaction-authorization/1.0.0/policy.json`, a declarative rule document, instead of the if/else this function used to contain directly.

### Same signals, different policy, different decision

The whole reason this is a policy *document* and not just a refactor: the same detect + mandate output can be evaluated against a different, business-authored policy to get a different decision — auditably, since the policy that fired is itself signed into the record (`policy_id`, `policy_version`, `matched_rule_id`).

```python
# policy/src/policy_engine.py
from policy_engine import evaluate_policy

signals = {"detect_decision": "FLAG", "mandate_allowed": True, "fraud_score": 0.62}

# The shipped default: FLAG + clean mandate requires step-up review.
evaluate_policy(default_policy, signals)["outcome"]   # "REQUIRE_OVERRIDE"

# A stricter, hand-authored policy that treats any FLAG as a reject.
evaluate_policy(strict_policy, signals)["outcome"]     # "REJECT"
```

See `tests/test_policy_engine.py::test_same_signals_different_policy_different_outcome` for the full runnable version of this example, and `pipeline/src/run_pipeline.py --policy-id`/`--policy-version` to run the whole pipeline against a different policy document.

### Three scenario walkthroughs

**Scenario A — Detect objects, mandate is clean**

```
Transaction: $340 at an unfamiliar merchant, 3:14am, pattern_similarity low
  DETECT   → fraud_score 0.84 → BLOCK
  MANDATE  → within spending limit, but merchant not on whitelist → mandate_allowed=False
  COMBINE  → BLOCK (both layers objected)
  SIGN     → signed BLOCK, reasons: ["detect: pattern_similarity", "mandate: merchant_whitelist"]
```

**Scenario B — Detect is clean, mandate catches it anyway**

```
Transaction: $410, familiar merchant, normal hour, fraud_score 0.31 (ALLOW range)
  DETECT   → ALLOW (looks statistically ordinary)
  MANDATE  → projected month-to-date total exceeds monthly_limit_usd → mandate_allowed=False
  COMBINE  → BLOCK (mandate overrides a clean detect score)
  SIGN     → signed BLOCK, reasons: ["mandate: spending_limit"]
```
This is the case the [synthetic identity bust-out attack](identify/attack-taxonomy.md) is built to test: transactions engineered to look ordinary to a per-transaction classifier while still exceeding the customer's own real spending pattern. In the committed run, 26 of the 446 total blocks came from the mandate layer alone (see [Section 9](#9-metrics-and-validation)).

**Scenario C — Detect is unsure, mandate is clean**

```
Transaction: $95, familiar merchant, normal hour, fraud_score 0.62 (FLAG range)
  DETECT   → FLAG
  MANDATE  → all four rules pass → mandate_allowed=True
  COMBINE  → FLAG (detect unsure, nothing else objects)
  SIGN     → signed FLAG, reasons: ["detect: ai_generated_signal"]
```
In the execution layer, a FLAG maps to `step_up_auth`, not an automatic deny — see `ACTION_FOR_DECISION` in `sign/src/decision_executor.py`.

---

## 5. Code Examples

These are real functions from this repository, not a hypothetical API — every import below resolves in this codebase.

### Score a transaction (detect layer)

```python
# detect/src/detector.py + web/interactive_demo.py's real call pattern
import detector as det
from detector import decision_for_score

def decision_for_score(score: float) -> str:
    if score >= 0.80:
        return "BLOCK"
    if score >= 0.50:
        return "FLAG"
    return "ALLOW"

fraud_score = float(model.predict_proba([det._row(transaction)])[:, 1][0])
detect_decision = decision_for_score(fraud_score)
```

### Check a mandate (mandate layer)

```python
# mandate/src/mandate_checker.py
from mandate_checker import check_mandate, derive_mandate_from_history

mandate = derive_mandate_from_history(customer_transaction_history)
result = check_mandate(
    transaction,
    mandate,
    month_to_date_total=1180.00,
    tx_count_today=3,
)
# {
#   "mandate_allowed": False,
#   "violated_rules": ["spending_limit"],
#   "checks": [
#     {"rule": "spending_limit", "passed": False,
#      "reason": "would exceed monthly limit ($1000.00): $1180.00 so far + $95.00 = $1275.00"},
#     {"rule": "merchant_whitelist", "passed": True, "reason": "..."},
#     {"rule": "time_restriction", "passed": True, "reason": "..."},
#     {"rule": "velocity", "passed": True, "reason": "..."}
#   ]
# }
```

### Evaluate policy and sign

```python
# pipeline/src/run_pipeline.py + sign/src/authority_signer.py
from run_pipeline import decide
from authority_signer import sign_pipeline_decision

# decide() builds the signals dict and evaluates it against the
# shipped default policy (or pass policy=<a different document>).
policy_result = decide(detect_decision, result, fraud_score=fraud_score, amount=transaction["amount"])
final_decision = {"REJECT": "BLOCK", "REQUIRE_OVERRIDE": "FLAG", "APPROVE": "ALLOW"}[policy_result["outcome"]]

signed = sign_pipeline_decision(
    transaction_id=transaction["transaction_id"],
    fraud_score=fraud_score,
    detect_decision=detect_decision,
    mandate_allowed=result["mandate_allowed"],
    violated_mandate_rules=result["violated_rules"],
    final_decision=final_decision,
    reasons=["mandate: spending_limit"],
    policy_id=policy_result["policy_id"],
    policy_version=policy_result["policy_version"],
    matched_rule_id=policy_result["matched_rule_id"],
)
# signed["signature"] is a 128-hex-char Ed25519 signature over the
# canonical JSON encoding of the fields above -- including which policy
# and which rule produced final_decision, so that's tamper evident too.
```

### Verify a signed decision independently

```python
# sign/src/signature_verifier.py
from signature_verifier import verify_record

is_valid = verify_record(signed, signer_name="authority")
# Reads only sign/tokens/authority_public_key.pem — the committed
# public key file, exactly what an outside auditor would check with,
# no access to the private key or this codebase's runtime required.
```

### Execute a signed decision (fail closed, idempotent)

```python
# sign/src/decision_executor.py + sign/src/caller_auth.py
from decision_executor import DecisionExecutor
from caller_auth import AUTHENTICATOR

caller = AUTHENTICATOR.verify_token(caller_token)  # from POST /api/callers/token
executor = DecisionExecutor()
outcome = executor.enforce_decision(
    signed_decision=signed,
    payment_processor_webhook=my_webhook,  # (action, signed_decision) -> dict
    caller=caller,                          # a CallerIdentity, e.g. "payment-processor"
)
# {"status": "EXECUTED" | "ALREADY_EXECUTED" | "REJECTED", "record_id": ...}
# Verifies the signature, checks caller.permissions against final_decision
# (payment-processor can execute ALLOW/FLAG but not BLOCK), enforces
# idempotency on record_id, logs the attempt either way to
# pipeline/audit/executions.jsonl.
```

---

## 6. Real-World Scenarios

### Scenario 1: Legitimate purchase, both layers agree

```
$45 at a merchant the customer uses weekly, 2pm, fraud_score 0.06
DETECT: ALLOW  MANDATE: all four rules pass  → ALLOW, signed, logged.
```

### Scenario 2: Stolen card, detector catches it, mandate is silent

```
$620 at an unfamiliar merchant, 3am, fraud_score 0.91
DETECT: BLOCK (pattern_similarity, hour_of_day)
MANDATE: within spending limit, but merchant not whitelisted → mandate_allowed=False anyway
→ BLOCK, two independent reasons cited, both would have blocked it alone.
```

### Scenario 3: Synthetic identity bust-out, detector misses it, mandate catches it

```
$540, a merchant the customer has used before, mid-afternoon, fraud_score 0.34 (ALLOW range)
DETECT: ALLOW — the transaction's per-transaction features look ordinary
MANDATE: this pushes the customer's month-to-date total past their derived
         monthly_limit_usd → mandate_allowed=False
→ BLOCK. This is exactly why the mandate layer exists independent of the
  detector: a per-transaction classifier has no memory of what the
  customer has already spent this month.
```

### Scenario 4: Detector unsure, execution layer steps up instead of denying

```
$95, familiar merchant, normal hour, fraud_score 0.58 (FLAG range)
DETECT: FLAG   MANDATE: clean
→ FLAG, signed. sign/src/decision_executor.py maps FLAG to
  ACTION_FOR_DECISION["FLAG"] = "step_up_auth", not an automatic deny —
  the payment processor is expected to ask for additional verification,
  not reject the transaction outright.
```

---

## 7. Quick Start

```bash
# Setup
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt

# View the committed dashboard as is
cd web
python -m http.server 8000
# Open http://localhost:8000
```

To regenerate the dashboard from a fresh, self-generated dataset (copy `.env.example` to `.env` and set a real `OPENAI_API_KEY` first, agents 1, 2, 4, and 9 make real, cheap GPT-4o-mini calls):

```bash
cd generate/src && python run_simulation.py   # agents 1,2,4,9 (real OpenAI) + 5,6,8 (local)
cd ../../detect/src && python check_results.py # trains the model agents 3/7 probe
cd ../../generate/src && python probe_agents.py # agents 3,7 (agent 7 is real OpenAI)
cd ../../pipeline/src && python run_pipeline.py # detect + mandate + sign -> dashboard
```

---

## 8. Try It Live

The dashboard opens on the Live Test tab by default at [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev). You do not need to read any numbers first. Just submit a transaction and watch the real pipeline run.

Pick one of six sample customers from the dropdown. Each one has a mandate built from their own real transaction history: a spending limit, a list of merchants they normally use, a window of hours they normally transact in, and a daily transaction limit.

Then fill in:

* Amount, in US dollars
* Merchant, pick one from the list or type your own to see what happens with a merchant the customer has never used
* Hour of day, 0 through 23
* AI generated signal, a number from 0 to 1 that represents how synthetic the transaction pattern looks

Press "Run transaction." The result comes back in four parts:

1. **Detection.** The real trained model scores the transaction for fraud risk, right now.
2. **Mandate.** The real rule engine checks the transaction against that customer's own history.
3. **Signing.** The result is signed with a real Ed25519 key, and the signature is checked right there so you can see it verify.
4. **Authority.** The final decision, ALLOW, FLAG, or BLOCK, with a plain explanation of why.

A good first experiment: submit an amount well under the customer's limit, at a normal hour, at a merchant they already use. Then change one thing at a time, an odd hour, an unfamiliar merchant, a large amount, or a high AI generated signal, and watch which layer objects.

There is also an Attack Walkthrough tab. It shows seven real, already signed decisions pulled straight from an actual pipeline run, one for each attack type this project simulates. Both features need `python web/server.py` running (see Quick Start above), not the static `http.server`.

---

## 9. Metrics and Validation

From the run behind the committed `web/data/dashboard.json`, fully self generated by this repo's own `generate/` layer, including real GPT-4o-mini calls for agents 1, 2, 4, 7, and 9 (27 calls, ~$0.037 total):

- **23,037 transactions at a realistic 2.61% fraud rate** (22,436 legitimate + 601 fraudulent). The legitimate pool is scaled up for free (local generation, no API cost) specifically so the fraud rate can be realistic *without* shrinking the fraud count to a statistically noisy sample. 601 fraud examples means the test split alone has ~180 fraud cases to evaluate on, not a handful.
- Fraud spread across the 7 attack types that actually produce labeled transactions: fake_identity 112, social_engineering 52, kyc_synthetic 100, pattern_copy 100, form_break 100, synthetic_bustout 100, vendor_bec 37. (Agents 3 and 7, limit probing and feedback loop exploit, probe the trained model directly instead of generating transactions, so they're not part of this breakdown; see `identify/attack-taxonomy.md`.)
- **6,912 decisions** on the held out test split: 446 BLOCK / 150 FLAG / 6,316 ALLOW
- **Detection catch:** 92.2% fraud caught, 6.3% false positive rate. The RandomForest uses `class_weight="balanced"` to hold up under this realistic imbalance rather than defaulting to the majority class
- **Mandate only blocks:** 26. Real fraud the detector scored as low risk that the mandate layer caught anyway, most of it the synthetic identity bust out attack, deliberately designed to look ordinary to a per transaction classifier while still exceeding that customer's own derived spending limit
- **All decisions signed:** 6,912/6,912 verify independently
- **Red team (agent 7):** 18 evasion variants tested against the trained model, 10 evaded detection, worse than an earlier run of this dataset (1 of 18 evaded then). See Robustness below for the likely reason

### Why precision is around 28% (and why that's expected)

The detect layer's **precision is 28.2%**: of the 589 transactions it flags (423 false positives + 166 true positives), a little over 1 in 4 is actually fraud. That number looks bad in isolation, so here's the context:

- **Fraud is rare** (180 of 6,912 test set transactions, a bit over 2%). Tuning a classifier to catch over 92% of that rare an event requires flagging aggressively. It is the same tradeoff airport security makes to catch most weapons at the cost of screening plenty of harmless bags. Recall and precision pull against each other; you cannot maximize both when the positive class is this sparse.
- **Precision measures the detect layer alone**, in isolation, on the held out test set. It is *not* the system's real world false accusation rate. A detect layer flag doesn't block anything by itself. It still has to clear the independent, rule based **mandate** layer (spending limits, merchant whitelist, time of day, velocity) before a transaction is denied, and every final decision, ALLOW or BLOCK, is signed and independently verifiable.
- The confusion matrix behind these numbers: of 6,732 legitimate test transactions, 6,309 passed and 423 were flagged; of 180 fraud transactions, 166 were caught and 14 were missed. (`web/data/dashboard.json` → `detect.metrics.confusion_matrix`, also rendered live on the [dashboard](https://execution-authority-gate.fly.dev)'s Detection tab.)

See [`docs/JUDGES_GUIDE.md`](docs/JUDGES_GUIDE.md) for the full walkthrough, including why a detector with low precision and high recall is standard practice in fraud detection rather than a flaw. Every number above is traced to a `file:line` and a runnable verification command in [`CLAIMS.md`](CLAIMS.md).

### Robustness

Numbers vary run to run: agents 1, 2, 4, 7, and 9 call the real OpenAI API at temperature=0.9, not deterministic by design. Running `generate/src/run_simulation.py` again (then `detect/src/check_results.py`, `generate/src/probe_agents.py`, and `pipeline/src/run_pipeline.py`) with your own `OPENAI_API_KEY` will produce different fraud examples and slightly different metrics. That's deliberate, it proves the detector holds up across different fraud patterns, not just one fixed dataset.

Adding the synthetic identity bust out and vendor BEC attacks changed more than the attack count: `amount` moved from a minor signal to the model's second most important feature (`top_signals` in `web/data/dashboard.json`, since both new attacks are large, out of pattern amounts), and adversarial evasion resistance dropped from 1 of 18 to 10 of 18 in the same run. A model that leans harder on amount is easier to nudge with the small numeric adjustments GPT proposes in agent 7's evasion test. This is reported plainly, not smoothed over: broadening the attack taxonomy improved recall (89.1% to 92.2%) and gave the mandate layer more to catch on its own (8 to 26 mandate only blocks), but it came with a real adversarial robustness cost, a genuine tradeoff, not a one directional improvement.

### Submission context

This repository is also the codebase behind a Mastercard hackathon submission ([`Mastercard-Submission-Walkthrough.docx`](Mastercard-Submission-Walkthrough.docx)); the numbers in this section and in [`CLAIMS.md`](CLAIMS.md) are exactly what that walkthrough is based on, no separate or rounder set of figures exists for a pitch.

---

## 10. Production Deployment and Execution Integration

Decisions are ready for execution, not merely advisory: `sign/src/decision_executor.py`
validates a signed decision's signature and the calling identity's
permission before dispatching it to a `payment_processor_webhook`
(ALLOW → settle, FLAG → step up auth, BLOCK → deny), with idempotency so
the same decision is never executed twice, exposed over HTTP at
`POST /api/enforce/decisions` (`web/server.py`, requires a caller token
from `POST /api/callers/token`, see `sign/src/caller_auth.py`). This repo
ships no real payment processor integration; the shipped webhook stub
simulates and labels its own output accordingly. See
[`docs/PRODUCTION_DEPLOYMENT.md`](docs/PRODUCTION_DEPLOYMENT.md) for the
full deployment guide (latency budget, scalability, key management,
regulatory mapping, and a 15 point integration checklist), and
[`CLAIMS.md`](CLAIMS.md) for every metric in this README traced to a
file:line and a runnable verification command.

Decisions are also durable and caller scoped now, closing two of the
gaps `EAG-AUDIT-GAPS.md` documented: every decision is appended,
never overwritten, to `pipeline/audit/decisions.jsonl` (committed to git,
independently verifiable again anytime via `pipeline/src/audit_trail.py`), and can
carry the requesting caller's identity inside the signed envelope itself
(`pipeline/src/run_pipeline.py --caller-id`, `sign/src/caller_auth.py`'s
scoped permissions). See `ARCHITECTURE.md`'s "Gaps closed since the
audit" section for the complete account of what changed, cited to the code.

---

## 11. Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

136 hermetic tests run in a few seconds, no API key, no network calls, nothing written outside `tmp_path`. They cover every layer directly (`detect`, `mandate`, `policy`, `sign`, `generate`'s local agents, `pipeline`), cryptographic properties (key separation, tamper detection, signature uniqueness), the append only audit trail, caller authentication and permission scoping, the decision executor's fail closed and idempotency guarantees, the policy engine's operators/validation/first-match-wins semantics, and a scenario proving end to end that the mandate layer catches fraud the detector alone would miss.

4 more tests cover agents 1, 2, 4, and 9 (the ones that call the real OpenAI API) and are skipped by default:

```bash
ALLOW_LIVE_OPENAI=1 OPENAI_API_KEY=sk-... pytest tests/test_generate.py -v
```

---

## 12. Structure

- **identify/**: Attack taxonomy
- **generate/**: 7 fraud agents + orchestration (`run_simulation.py`, `probe_agents.py`); agents 1, 2, 4, 7 call the real OpenAI API
- **detect/**: RandomForest fraud detector
- **mandate/**: Authorization rule checker
- **policy/**: Declarative policy engine (`src/`) + versioned policy documents (`policies/<policy-id>/<version>/policy.json`)
- **sign/**: Ed25519 signing + verification + caller auth + decision execution
- **pipeline/**: Orchestration of all layers, audit trail
- **web/**: Interactive dashboard, plus an Attack Walkthrough (real precomputed decisions) and a Live Test Harness (runs a submitted transaction through the real pipeline on demand, needs `python web/server.py`, not the static `http.server`). See [Try It Live](#8-try-it-live) above.
- **tests/**: Comprehensive test suite

---

## 13. Deployment

Live at [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev), deployed via `flyctl deploy` from this repo. The deployed container runs `web/server.py` (a small Flask static server with a `/api/status` health check) and serves the committed `web/data/dashboard.json` as is. The pipeline doesn't run inside the container, so the live numbers stay fixed to whatever was last committed until someone regenerates and recommits that file.

To redeploy after code changes:
```bash
flyctl deploy
```

---

## 14. FAQ

**Q: Is this just a fraud detector with extra steps?**
No. The detector is one of two independent layers, not the decision maker. The mandate layer runs the same transaction through a completely separate, deterministic rule set, and either layer can block on its own. Section 9 shows this isn't hypothetical: 26 of the run's 446 blocks came from the mandate layer catching fraud the detector scored as low risk.

**Q: Can the mandate layer override the detector, or vice versa?**
Neither overrides the other. `combine_decision` (Section 4) is a straight OR on blocking: if either layer objects, the result is BLOCK. There's no weighting, no confidence threshold that lets one layer's opinion cancel the other's.

**Q: What does signing actually add, if the decision is already made by then?**
Proof, not a vote. Ed25519 signing runs on every decision, ALLOW included, and the private key belongs to an external authority identity that neither the detector nor the mandate checker can access. That means the recorded fraud_score, mandate result, and final_decision cannot be altered after the fact without invalidating the signature — anyone holding the committed public key (`sign/tokens/authority_public_key.pem`) can verify that independently, without trusting this codebase's runtime at all.

**Q: Does a signed BLOCK mean the transaction was actually stopped from moving money?**
No, and this repo doesn't claim otherwise. Signing makes a decision provable, not enforced. `sign/src/decision_executor.py` is the piece that turns a signed decision into a call against a payment processor, and it's real code with fail-closed and idempotency guarantees, but the webhook it calls in this repo is a labeled simulation (`"simulated": true`), because no real payment processor is wired up. See Section 10 and [`CLAIMS.md`](CLAIMS.md#what-this-project-does-not-claim).

**Q: Why is detector precision only ~28%? Isn't 3 out of 4 flags wrong?**
Yes, in isolation. That's the standard recall/precision tradeoff for a rare-event classifier tuned to catch 92%+ of a ~2.6% fraud rate. What matters is that a detect-layer flag alone never blocks anything — see Section 9's "Why precision is around 28%" and [`docs/JUDGES_GUIDE.md`](docs/JUDGES_GUIDE.md) for the full reasoning.

**Q: Are the 92.2%/6.3% numbers fixed?**
No, by design. Four of the generation agents make real, non-deterministic OpenAI calls (temperature=0.9), so regenerating the dataset produces slightly different numbers each run. This is intentional — see [Robustness](#9-metrics-and-validation) — it's evidence the detector generalizes across fraud patterns rather than being fit to one fixed sample.

**Q: What are the known limits?**
Documented plainly, not smoothed over, in [`CLAIMS.md`](CLAIMS.md#what-this-project-does-not-claim) and `ARCHITECTURE.md`'s "Gaps closed since the audit" section: no real payment processor integration, mandate limits are heuristically derived (not real underwriting policy), and the raw transaction fields (amount, merchant, hour) live in an unsigned `ground_truth` sibling field, not inside the signed envelope itself.

---

## 15. License

MIT, see [LICENSE](LICENSE).
