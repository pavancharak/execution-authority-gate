# Architecture: Detect, Mandate, Sign

## Layer 1: Generate

Four of the seven fraud agents (fake identity, social engineering, KYC forgery, and the feedback loop evasion agent) make real OpenAI API calls (temperature=0.9, GPT-4o-mini) to produce genuine, non deterministic fraud variation. The remaining three (pattern replication, form fuzzing, limit probing) are local and statistical by design, since their realism comes from matching a real distribution or a real threshold search, not generative text. See identify/attack-taxonomy.md and generate/src/fraud_agents.py.

## Layer 2: Detect

RandomForest classifier (detect/src/detector.py) scores transaction fraud probability from six features: amount, hour of day, log seconds since the previous transaction, location mismatch, pattern similarity, and the AI generated signal.

**Metrics computed by `evaluate()`:** confusion matrix, recall (fraud caught rate), false positive rate, precision, F1 score, and ROC AUC. These are not fixed constants: the underlying dataset regenerates from real, non deterministic OpenAI calls each run, so exact figures move run to run by design (see README.md's Robustness section). For the current committed run's actual numbers, read `web/data/dashboard.json`'s `detect.metrics`, or README.md's Metrics section.

## Layer 3: Mandate

Deterministic rule checker (mandate/src/mandate_checker.py) verifies authorization, independent of the detect layer's score. A mandate is derived from each customer's own known good transaction history, not a hand authored global policy.

**Rules (mandate/src/rules.py), all must pass:**
- Spending limit enforcement
- Merchant whitelist
- Time based restriction
- Velocity check

## Layer 4: Sign

Every final decision, ALLOW, FLAG, and BLOCK alike, is signed with Ed25519 (sign/src/authority_signer.py) by an external authority identity. Neither the detector nor the mandate checker holds that private key, so neither can forge or self approve a decision.

**What this actually guarantees:**
- The signed fields (`transaction_id`, `fraud_score`, `detect_decision`, `mandate_allowed`, `violated_mandate_rules`, `final_decision`, `reasons`, and the signing timestamp) cannot be altered afterward without invalidating the signature. Verified empirically in EAG-AUDIT-GAPS.md.
- A separate REVIEWER key signs human overrides, so an override can never be mistaken for, or forged as, an authority decision.
- Signing is not enforcement. It makes the combined decision provable and tamper evident after the fact. It does not by itself stop money from moving; this repo has no execution or enforcement integration. See "Known limits" below.

## Decision Flow

```
Transaction
    ↓
[DETECT] fraud_score = model.predict_proba(tx)
         decision_for_score(fraud_score) -> BLOCK | FLAG | ALLOW
    ↓
[MANDATE] mandate_checker.check_mandate(tx, customer_mandate)
          -> mandate_allowed (True/False), violated_rules
    ↓
[COMBINE] combine_decision(detect_decision, mandate_result)
          detect BLOCK, or any mandate rule violated  -> final = BLOCK
          detect FLAG and mandate clean                -> final = FLAG
          otherwise                                     -> final = ALLOW
    ↓
[SIGN] authority_signer.sign_pipeline_decision(...)
       Ed25519 signature over transaction_id, fraud_score, detect_decision,
       mandate_allowed, violated_mandate_rules, final_decision, reasons
    ↓
[LOG] decision_log.write_log(...) -> pipeline/decisions/pipeline_decisions.json
[DASHBOARD] dashboard_builder.build(...) -> web/data/dashboard.json
```

There is no enforcement or execution step after signing. Nothing in this repo moves money, calls a payment processor, or notifies a downstream system. This is a decision only authorization layer. See EAG-AUDIT-GAPS.md, section 3, for the full, code cited account.

## Why Dual Layers

**Example:** $180 transaction, customer mandate is "max $200/month groceries"

| Scenario | Detection | Mandate | Result |
|----------|-----------|---------|--------|
| Normal purchase | Low risk | Within limit | ALLOW |
| Stolen card | High risk | Within limit | BLOCK (detection) |
| Over limit | Low risk | Exceeded | BLOCK (mandate) |
| Stolen + over | High risk | Exceeded | BLOCK (both) |

Both detection and mandate must pass.

## Verification

A real signed pipeline decision, field names exactly as `sign/src/authority_signer.py`'s `sign_pipeline_decision` produces them:

```json
{
  "record_type": "pipeline_decision",
  "transaction_id": "tx_04213",
  "fraud_score": 0.8421,
  "detect_decision": "BLOCK",
  "mandate_allowed": false,
  "violated_mandate_rules": ["spending_limit", "time_restriction"],
  "final_decision": "BLOCK",
  "reasons": ["detect: pattern_similarity", "mandate: spending_limit", "mandate: time_restriction"],
  "record_id": "b3b0b8f2-2f31-4b0a-9b8e-3f6b6b0a1c02",
  "signed_at": 1755963600.0,
  "signer": "authority",
  "signature": "9f2c...(128 hex chars)"
}
```

Running `signature_verifier.verify_record` on this record against the authority's public key confirms the listed fields were produced by the authority identity and have not changed since signing.

**What this does not prove:** the transaction's raw amount, merchant, and hour live in a separate, unsigned `ground_truth` sibling field written by the pipeline, not inside this signed envelope, so they are not protected by this signature. Nor does a valid signature mean the decision was ever enforced anywhere. See EAG-AUDIT-GAPS.md for the full, empirically confirmed account of what is and isn't tamper evident.

## Known limits

This document previously claimed an `[ENFORCE] authority_gateway.enforce(signed_decision)` step and "enforced externally" as a guarantee. Neither exists anywhere in the code: a repo wide grep for `authority_gateway` and `.enforce(` found zero matches outside this file's own earlier draft. Corrected above. For the complete gap analysis (decision durability, key durability, execution integration, caller authentication), see EAG-AUDIT-GAPS.md.
