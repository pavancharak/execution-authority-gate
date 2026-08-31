# Execution Authority Gate

[![Tests](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml/badge.svg)](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Live dashboard: [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev)**

# Execution Authority Gate

## Deterministic Authorization for AI-Driven Transactions

AI can detect risk. **It should not be the authority that decides whether an action executes.**

Execution Authority Gate separates **AI-generated signals** from **execution authority**.

The detector produces a probabilistic recommendation. The policy engine evaluates that recommendation against deterministic business rules, mandates, and risk appetite. The resulting decision is cryptographically signed and auditable before execution.

**Detector recommends. Policy decides. Mandates constrain. Cryptography proves.**

---

## The Problem

Modern fraud and AI systems increasingly rely on machine-learning detectors.

These systems are powerful, but their outputs are inherently probabilistic:

* fraud scores
* confidence levels
* anomaly scores
* classifications
* risk recommendations

Execution is different.

A financial transaction ultimately requires a deterministic answer:

> **APPROVE or REJECT**

The critical control problem is therefore not simply:

> “Can AI detect fraud?”

It is:

> **“How does an organization convert a probabilistic AI recommendation into an authorized, deterministic, auditable execution decision?”**

Execution Authority Gate provides that control layer.

---

# Core Architecture

```text
                    TRANSACTION
                         │
                         ▼
              ┌─────────────────────┐
              │   AI DETECTOR       │
              │                     │
              │ Probabilistic       │
              │ fraud/risk signal   │
              │                     │
              │ score: 0 → 1        │
              │ ALLOW / FLAG / BLOCK│
              └──────────┬──────────┘
                         │
                         │ signal
                         ▼
              ┌─────────────────────┐
              │   POLICY ENGINE     │
              │                     │
              │ Deterministic       │
              │ decision authority  │
              │                     │
              │ • business rules    │
              │ • risk appetite     │
              │ • mandates          │
              │ • detector signal   │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  FINAL DECISION     │
              │                     │
              │ APPROVE / REJECT    │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ CRYPTOGRAPHIC SIGN  │
              │                     │
              │ Ed25519             │
              │ policy/version      │
              │ matched rule        │
              └──────────┬──────────┘
                         │
                         ▼
                  AUDIT / EXECUTE
```

The detector does **not** directly authorize execution.

Its output becomes an input to the policy layer.

---
## Quick Start — Run the Examples

The repository includes three concrete authorization scenarios demonstrating the separation between AI detection and execution authority.

### 1. Install dependencies

From the repository root:

```powershell
pip install -r requirements.txt
```

### 2. Run the full test suite

```powershell
pytest -q
```

Expected result:

```text
136 passed, 4 skipped
```

### 3. Run the end-to-end pipeline

```powershell
python .\pipeline\src\run_pipeline.py
```

The pipeline executes:

```text
Detect → Mandate → Policy → Sign
```

A successful run produces signed decisions and independently verifies the signatures.

Example output:

```text
6,912 signed pipeline decisions

BLOCK: 446
FLAG:  150
ALLOW: 6,316

Verification: 6912/6912 signatures verify independently
```

Generated artifacts include:

```text
pipeline/decisions/pipeline_decisions.json
pipeline/audit/decisions.jsonl
web/data/dashboard.json
```

### 4. Run the authorization examples

The `examples/` directory contains three focused scenarios:

```text
examples/
├── 01-legitimate-purchase.json
├── 02-high-risk-new-account.json
├── 03-detector-miss-mandate-catches.json
├── README.md
└── run_examples.py
```

Run:

```powershell
python .\examples\run_examples.py
```

The examples demonstrate:

```text
Example 01
Detector: ALLOW
Mandate:  PASS
Policy:   APPROVE
```

```text
Example 02
Detector: FLAG
Mandate:  VIOLATED
Policy:   REJECT
```

Most importantly:

```text
Example 03
Detector: ALLOW
Mandate:  VIOLATED
Policy:   REJECT
```

Example 03 demonstrates the core Execution Authority Gate property:

> **A detector recommendation does not have execution authority.**

Even when the AI detector produces `ALLOW`, a deterministic mandate violation causes the policy layer to produce `REJECT`.

### 5. Run the web dashboard

After running the pipeline:

```powershell
cd web
python -m http.server
```

Open:

```text
http://localhost:8000
```

The dashboard reads the generated:

```text
web/data/dashboard.json
```

### Repository validation

A healthy repository should pass:

```powershell
pytest -q
```

and the end-to-end pipeline should complete with:

```text
Verification: 6912/6912 signatures verify independently
```

The examples provide focused scenarios; the full pipeline provides the large-scale end-to-end execution and signing demonstration.


# How It Works

<img width="1507" height="641" alt="image" src="https://github.com/user-attachments/assets/7acd2bda-7d02-48c0-a467-34bbc6e50b6b" />


## 1. Detector Generates a Signal

The AI detector analyzes the transaction and produces a probabilistic signal.

Example:

```text
fraud_score = 0.24
detector_signal = ALLOW
```

The detector is advisory.

It answers:

> “How risky does this transaction appear?”

It does **not** answer:

> “Is this transaction authorized to execute?”

---

## 2. Policy Engine Receives the Signal

The policy engine consumes the detector output together with deterministic context.

Inputs can include:

* detector signal
* fraud score
* account state
* transaction amount
* spending history
* compliance status
* business rules
* risk appetite
* mandate results

The policy engine applies these inputs according to a versioned policy.

The same detector signal can therefore produce different outcomes under different business policies.

```text
Same detector signal
        │
        ├── Conservative policy ──► REJECT
        │
        └── Permissive policy ────► APPROVE
```

This separates **model behavior** from **business authority**.

---

# 3. Mandates Enforce Absolute Rules

Some conditions are not matters of probability or risk preference.

They are mandatory constraints.

Examples include:

* spending limits
* merchant restrictions
* account restrictions
* time restrictions
* velocity limits
* compliance requirements

A mandate can therefore override an otherwise favorable detector recommendation.

Example:

```text
Detector: ALLOW
Mandate: VIOLATED
Policy: REJECT
```

The important distinction is:

**A detector recommendation is advisory.
A mandate violation is enforceable.**

---

# 4. Policy Produces the Final Decision

The policy engine produces a deterministic execution decision:

```text
APPROVE
```

or

```text
REJECT
```

The decision is associated with:

* policy ID
* policy version
* matched rule ID
* detector signal
* mandate result
* decision evidence

This makes the decision explainable rather than an opaque consequence of an AI score.

---

# 5. The Decision Is Cryptographically Signed

Before execution, the decision can be signed using Ed25519.

The signed evidence binds the decision to its governing context.

Conceptually:

```text
Transaction
    +
Detector Signal
    +
Mandate Result
    +
Policy ID
    +
Policy Version
    +
Matched Rule
    +
Final Decision
          │
          ▼
    Cryptographic Signature
```

This provides an independently verifiable record of what decision was produced and under which policy.

---

# The Critical Proof

The most important demonstration is a case where the detector **does not detect the problem**, but the policy layer still prevents the transaction from executing.

<img width="1055" height="926" alt="image" src="https://github.com/user-attachments/assets/82afae9a-9eb4-4575-a839-18932d5ccbf8" />


## Example 1 — Legitimate Purchase

```text
Transaction:
$450 purchase by established customer

Detector:
fraud_score = 0.12
signal = ALLOW

Mandate:
clean

Policy:
APPROVE
```

The detector and policy are aligned.

---

## Example 2 — High-Risk New Account

```text
Transaction:
$8,500 wire transfer from a new account

Detector:
fraud_score = 0.68
signal = FLAG

Mandate:
KYC / AML / account-age requirements violated

Policy:
REJECT
```

Here both the probabilistic signal and deterministic constraints point toward rejection.

---

# Example 3 — Detector Misses, Mandate Catches

This is the critical architectural demonstration.

```text
Transaction:
$4,200 electronics purchase

Detector:
fraud_score = 0.24
signal = ALLOW
```

From the individual transaction's perspective, the transaction appears legitimate.

But the account-level state tells a different story:

```text
Month-to-date spending:  $18,000
Current transaction:      $4,200
                         -------
Total:                   $22,200

Monthly limit:           $20,000

Mandate:                 VIOLATED
```

The policy therefore produces:

```text
Detector:      ALLOW
Mandate:       VIOLATED
Policy:        REJECT
```

The matched rule identifies the governing reason:

```text
reject-mandate-violation
```

### Why this matters

A per-transaction detector can miss patterns that only become visible when account-level constraints are evaluated.

The policy layer provides a deterministic enforcement boundary between:

**what the model recommends**

and

**what the organization permits**.

This is the core value of separating detection from execution authority.

---

# Policy Layer

Policies are declarative and versioned.

A policy can define rules such as:

```text
spending_limit
merchant_whitelist
time_restriction
velocity
```

The policy engine evaluates rules deterministically.

A simplified conceptual flow is:

```python
detector_signal = detector.evaluate(transaction)

decision = policy.decide(
    detector_signal=detector_signal,
    mandate_result=mandate_result,
    business_context=business_context,
)

signed_decision = signer.sign(decision)
```

The model does not need to be retrained when business policy changes.

The policy can change independently from the detector.

---

# Declarative Policy Model

A policy can be represented as versioned configuration rather than hard-coded decision logic.

Conceptually:

```json
{
  "policy_id": "transaction-authorization",
  "version": "1.0.0",
  "rules": [
    {
      "id": "reject-mandate-violation",
      "condition": "mandate_passed == false",
      "decision": "REJECT"
    },
    {
      "id": "approve-default",
      "condition": "true",
      "decision": "APPROVE"
    }
  ]
}
```

This creates an explicit separation between:

```text
Policy definition
        ↓
Policy evaluation
        ↓
Decision
        ↓
Cryptographic evidence
```

---

# Architecture Layers

## Layer 1 — Detector

**Role:** Probabilistic input

Produces:

* fraud score
* anomaly score
* classification
* recommendation

The detector is not the execution authority.

---

## Layer 2 — Mandates

**Role:** Absolute enforcement

Mandates represent rules that must be satisfied regardless of the detector's confidence.

Examples:

* spending limits
* compliance requirements
* merchant restrictions
* velocity controls

---

## Layer 3 — Policy Engine

**Role:** Deterministic decision authority

Consumes:

* detector signals
* mandate results
* business rules
* risk appetite

Produces:

```text
APPROVE / REJECT
```

---

## Layer 4 — Cryptographic Signing

**Role:** Evidence and verification

The signed decision records:

* policy ID
* policy version
* matched rule
* final decision
* relevant decision context

The resulting artifact can be independently verified.

---

# Why This Architecture Matters

## 1. AI Is Not the Authority

AI can recommend.

The organization retains control over authorization.

---

## 2. Policy Can Change Without Model Retraining

Business rules can evolve independently from the underlying detector.

---

## 3. Decisions Are Explainable

Instead of only recording:

```text
fraud_score = 0.24
```

the system can record:

```text
policy = transaction-authorization
rule = reject-mandate-violation
decision = REJECT
```

---

## 4. Different Businesses Can Apply Different Policies

The same detector can feed different policies.

```text
Detector
   │
   ├── Bank A policy ──► REJECT
   │
   ├── Bank B policy ──► APPROVE
   │
   └── Bank C policy ──► REVIEW
```

The AI model does not need to become the business's policy engine.

---

## 5. Decisions Become Verifiable Evidence

Cryptographic signing creates an evidence trail connecting:

```text
Input
  ↓
Signal
  ↓
Policy
  ↓
Rule
  ↓
Decision
  ↓
Signature
```

This is particularly important for regulated environments where organizations need to demonstrate not only **what happened**, but **why the action was authorized**.

---

# Determinism

The policy layer is designed to make authorization behavior deterministic.

Given the same:

* policy version
* detector signal
* mandate state
* business context

the policy engine should produce the same decision.

This enables:

* reproducibility
* testing
* replay
* auditability
* verification

The policy itself becomes part of the decision evidence.

---

# Testing

The policy layer includes dedicated automated tests covering:

* policy validation
* policy loading
* deterministic operators
* rule evaluation
* rule ordering
* first-match behavior
* mandate enforcement
* detector/policy interaction
* different-policy outcomes
* backward compatibility

The key behavioral property is:

```text
Same detector signals
+
Different policy
=
Potentially different authorized outcome
```

That demonstrates that authorization authority resides in policy rather than in the detector.

---

# Metrics

The repository's reported fraud metrics should be interpreted as **system-level metrics**, not as claims about the detector alone.

Reported figures include:

| Metric              | Value |
| ------------------- | ----: |
| Recall              | 92.2% |
| False Positive Rate |  6.3% |
| Precision           | 28.2% |

These figures describe the evaluated decision system and should not be interpreted as evidence that the AI detector independently achieves the same performance.

The distinction matters because the architecture intentionally combines probabilistic detection with deterministic policy enforcement.

---

# Security and Auditability

Every governed decision can carry cryptographic evidence.

The evidence can include:

```text
decision_id
transaction_id
detector_signal
fraud_score
mandate_result
policy_id
policy_version
matched_rule_id
final_decision
signature
verification result
```

This allows downstream systems and auditors to establish:

1. What transaction was evaluated.
2. What the detector recommended.
3. Which mandates applied.
4. Which policy version governed the decision.
5. Which rule fired.
6. What final decision was produced.
7. Whether the evidence remains cryptographically valid.

---

# Repository Structure

```text
execution-authority-gate/
│
├── policy/
│   ├── src/
│   │   ├── operator_evaluator.py
│   │   ├── policy_validator.py
│   │   ├── policy_engine.py
│   │   └── policy_loader.py
│   │
│   └── policies/
│       └── transaction-authorization/
│           └── 1.0.0/
│               └── policy.json
│
├── pipeline/
│   └── src/
│       └── run_pipeline.py
│
├── sign/
│   └── src/
│       └── authority_signer.py
│
├── web/
│   └── interactive_demo.py
│
├── tests/
│   └── test_policy_*.py
│
├── ARCHITECTURE.md
├── CLAIMS.md
└── README.md
```

---

# Design Principle

The architecture can be reduced to one principle:

> **AI can be intelligent without being in charge.**

The detector can be sophisticated, probabilistic, and continuously improving.

The execution boundary remains deterministic and governed by explicit organizational policy.

```text
AI
 │
 │ recommendation
 ▼
POLICY
 │
 │ authorization
 ▼
DECISION
 │
 │ cryptographic evidence
 ▼
EXECUTION
```

---

# What Execution Authority Gate Provides

Execution Authority Gate provides a control boundary for systems where AI can recommend actions but organizations need deterministic authority over whether those actions execute.

### Detection

AI identifies potential risk.

### Decision

Policy determines what the organization permits.

### Enforcement

Mandates impose non-negotiable constraints.

### Evidence

Cryptographic signing records and verifies the resulting decision.

---

# Positioning

**Execution Authority Gate is not another fraud detector.**

It is the authorization and governance layer between AI recommendations and real-world execution.

The distinction is fundamental:

```text
Fraud Detection
      ≠
Fraud Authorization
      ≠
Fraud Enforcement
```

Execution Authority Gate connects these functions while keeping their responsibilities separate.

---

# Status

The current implementation demonstrates:

* Declarative policy evaluation
* Deterministic policy decisions
* Detector-to-policy integration
* Mandate enforcement
* Versioned policies
* Rule-level decision evidence
* Cryptographic signing
* Automated testing
* Real pipeline scenarios
* Audit-oriented decision records

The architecture is designed for environments where **AI recommendations must remain subject to explicit organizational authority before execution**.

---

# Important Claim Boundary

This repository demonstrates the architecture and its tested behavior.

It does **not** by itself establish that the system has been deployed in a production financial institution, certified by a regulator, or independently validated at production scale.

Production deployment would require institution-specific:

* policies
* data
* controls
* integrations
* security review
* compliance validation
* operational testing

The purpose of the system is to provide the deterministic authorization boundary those environments can build upon.

---

# Conclusion

AI systems increasingly influence decisions that have real-world consequences.

The central question is no longer only:

> **“Can the AI detect the risk?”**

It is:

> **“Who has the authority to decide whether the AI-driven action is allowed to execute?”**

Execution Authority Gate answers that question with an explicit architecture:

```text
Detector
   ↓
Probabilistic Signal

Policy
   ↓
Deterministic Decision

Mandates
   ↓
Absolute Constraints

Cryptography
   ↓
Verifiable Evidence

Execution
```

**Detector recommends.
Policy decides.
Mandates constrain.
Cryptography proves.**
