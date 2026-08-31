

\# Execution Authority Gate — Examples



These examples demonstrate the separation between \*\*probabilistic AI detection\*\* and \*\*deterministic execution authority\*\*.



The detector provides a risk signal. The policy layer evaluates that signal together with deterministic mandates and produces the final authorization decision.



> \*\*Detector recommends. Policy decides. Mandates constrain. Cryptography proves.\*\*



\---



\## Policy



All three examples use the same policy:



```text

Policy ID:      transaction-authorization

Policy Version: 1.0.0



Policy location:



policy/policies/transaction-authorization/1.0.0/policy.json



The examples demonstrate that the final decision is governed by policy rather than by the detector's recommendation alone.



Example 01 — Legitimate Purchase



File:



01-legitimate-purchase.json

Scenario



A low-risk transaction is evaluated.



The detector produces:



Fraud score: 0.12

Detector:    ALLOW



All deterministic mandate checks pass:



Spending limit:     PASS

Merchant whitelist: PASS

Time restriction:   PASS

Velocity:           PASS



The policy therefore produces:



APPROVE

Decision Flow

Transaction

&#x20;   ↓

Detector

&#x20;   ↓

ALLOW

&#x20;   ↓

Mandates PASS

&#x20;   ↓

Policy

&#x20;   ↓

APPROVE

Expected Result

Action:           approve

Matched rule:     approve-default

What It Demonstrates



The normal authorization path:



AI signal + valid mandates

&#x20;       ↓

deterministic policy decision

&#x20;       ↓

APPROVE

Example 02 — High-Risk New Account



File:



02-high-risk-new-account.json

Scenario



A high-value transaction is initiated from a high-risk account.



The detector produces:



Fraud score: 0.68

Detector:    FLAG



The deterministic mandate layer reports a violation:



Mandate: VIOLATED



The policy therefore rejects the transaction.



Decision Flow

Transaction

&#x20;   ↓

Detector

&#x20;   ↓

FLAG

&#x20;   ↓

Mandate VIOLATED

&#x20;   ↓

Policy

&#x20;   ↓

REJECT

Expected Result

Action:           reject

Matched rule:     reject-mandate-violation

What It Demonstrates



A detector signal does not independently authorize execution.



The final decision is produced by the policy layer after evaluating the available deterministic constraints.



Example 03 — Detector Misses, Mandate Catches



File:



03-detector-miss-mandate-catches.json

The Critical Scenario



This is the key architectural example.



The AI detector sees the individual transaction as low risk:



Fraud score: 0.24

Detector:    ALLOW



If the detector were the execution authority, the transaction could proceed.



But the account-level spending mandate identifies a violation.



Account State

Month-to-date spending: $18,000

Current transaction:      $4,200

&#x20;                        -------

Calculated total:       $22,200



Monthly spending limit: $20,000



Therefore:



$22,200 > $20,000



The spending mandate fails.



Final Decision

Detector: ALLOW

Mandate:  VIOLATED

Policy:   REJECT

Expected Result

Action:           reject

Matched rule:     reject-mandate-violation

Reason:           monthly spending limit exceeded

Why Example 03 Matters



Example 03 demonstrates the fundamental separation between detection and authorization.



The detector does not have execution authority.



It produces a probabilistic recommendation:



ALLOW



The policy layer evaluates the recommendation together with deterministic organizational constraints.



The mandate says:



NOT ALLOWED



The policy therefore produces:



REJECT



The architecture is:



┌───────────────────┐

│    AI DETECTOR    │

│                   │

│ Probabilistic     │

│ recommendation    │

└─────────┬─────────┘

&#x20;         │

&#x20;         │ signal

&#x20;         ▼

┌───────────────────┐

│   POLICY ENGINE   │

│                   │

│ Deterministic     │

│ authority         │

└─────────┬─────────┘

&#x20;         │

&#x20;         │ evaluates

&#x20;         ▼

┌───────────────────┐

│     MANDATES      │

│                   │

│ Absolute rules    │

└─────────┬─────────┘

&#x20;         │

&#x20;         ▼

┌───────────────────┐

│  FINAL DECISION   │

│                   │

│     REJECT        │

└───────────────────┘



The important property is:



A detector ALLOW signal cannot override a deterministic mandate violation.



Three Examples Together

Example	Detector	Mandate	Policy	Final

Legitimate Purchase	ALLOW	PASS	APPROVE	APPROVE

High-Risk Account	FLAG	VIOLATED	REJECT	REJECT

Detector Miss	ALLOW	VIOLATED	REJECT	REJECT



This illustrates three different relationships between probabilistic detection and deterministic authorization.



Architecture Demonstrated



The examples correspond to the following execution-authority model:



&#x20;                   TRANSACTION

&#x20;                        │

&#x20;                        ▼

&#x20;               ┌────────────────┐

&#x20;               │  AI DETECTOR   │

&#x20;               │                │

&#x20;               │ Risk signal    │

&#x20;               └───────┬────────┘

&#x20;                       │

&#x20;                       ▼

&#x20;               ┌────────────────┐

&#x20;               │ MANDATE CHECKS │

&#x20;               │                │

&#x20;               │ Hard limits    │

&#x20;               │ Constraints    │

&#x20;               └───────┬────────┘

&#x20;                       │

&#x20;                       ▼

&#x20;               ┌────────────────┐

&#x20;               │ POLICY ENGINE  │

&#x20;               │                │

&#x20;               │ Decision rules │

&#x20;               └───────┬────────┘

&#x20;                       │

&#x20;                       ▼

&#x20;                FINAL DECISION

&#x20;                 APPROVE/REJECT

&#x20;                       │

&#x20;                       ▼

&#x20;               CRYPTOGRAPHIC

&#x20;                  SIGNING

&#x20;                       │

&#x20;                       ▼

&#x20;                 AUDIT / EXECUTE

Detector vs. Policy



The detector answers:



How risky does this transaction appear?



The policy answers:



Is this transaction authorized to execute under the organization's rules?



These are different questions.



A detector may produce:



fraud\_score = 0.24



That score does not itself establish execution authority.



The policy layer provides the deterministic authorization boundary.



Mandates vs. Recommendations



A recommendation can be probabilistic.



A mandate is an organizational constraint.



For example:



Detector:

ALLOW



Mandate:

monthly spending limit exceeded



Policy:

REJECT



The architecture therefore prevents a low-risk detector score from silently becoming permission to execute.



Policy Versioning



Each example identifies the governing policy:



transaction-authorization

version 1.0.0



This is important because authorization decisions depend on the rules that were in force when the decision was made.



A policy version can therefore become part of the decision evidence.



Conceptually:



Transaction

&#x20;   +

Detector Signal

&#x20;   +

Mandate Result

&#x20;   +

Policy ID

&#x20;   +

Policy Version

&#x20;   +

Matched Rule

&#x20;   +

Final Decision

Cryptographic Evidence



After the policy produces the final decision, the decision can be cryptographically signed.



The resulting evidence can establish:



What was evaluated

&#x20;       ↓

What the detector recommended

&#x20;       ↓

What mandates applied

&#x20;       ↓

Which policy governed

&#x20;       ↓

Which rule matched

&#x20;       ↓

What decision was produced

&#x20;       ↓

Whether the evidence verifies



This creates a verifiable decision trail rather than relying only on application logs.



Reproducibility



The examples are intended to provide concrete scenarios for the repository's authorization architecture.



They should be treated as evidence scenarios until they have been executed through the repository's actual pipeline.



The distinction is important:



Scenario definition

&#x20;       ≠

Executed pipeline result



A result should only be described as reproduced or verified after the corresponding repository pipeline has actually produced it.



Files

examples/

├── 01-legitimate-purchase.json

├── 02-high-risk-new-account.json

├── 03-detector-miss-mandate-catches.json

└── README.md

Core Principle



The examples demonstrate one central principle:



AI can be intelligent without being in charge.



The detector can provide sophisticated probabilistic signals while the organization retains deterministic authority over execution.



AI

&#x20;│

&#x20;│ recommendation

&#x20;▼

POLICY

&#x20;│

&#x20;│ authorization

&#x20;▼

DECISION

&#x20;│

&#x20;│ cryptographic evidence

&#x20;▼

EXECUTION

Summary



Execution Authority Gate separates four responsibilities:



1\. Detection



AI identifies potential risk.



2\. Policy



Deterministic rules determine what is authorized.



3\. Mandates



Non-negotiable constraints prevent prohibited actions.



4\. Cryptographic Evidence



The resulting decision can be signed and independently verified.



The architectural boundary is simple:



Detector recommends.

Policy decides.

Mandates constrain.

Cryptography proves.

