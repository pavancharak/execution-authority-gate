# Architecture: 4-Layer Execution Authority

## Layer 1: Generate

Real OpenAI API calls (temperature=0.9) produce genuine fraud variation.

## Layer 2: Detect

XGBoost classifier scores transaction fraud probability.

**Metrics:**
- Recall: 95%+
- FPR: 8-9%
- ROC AUC: 0.98+

## Layer 3: Mandate

Deterministic rule checker verifies authorization.

**Rules:**
- Spending limit enforcement
- Merchant category whitelist
- Time-based restrictions
- Velocity checks

## Layer 4: Sign + Authority

Every decision signed (Ed25519) and enforced externally.

**Guarantees:**
- Timestamp immutable
- Authority verifiable
- Decision unchangeable
- Full audit trail

## Decision Flow

```
Transaction
    ↓
[DETECT] fraud_score = model.predict(tx)
    ↓
if fraud_score > threshold:
    decision = BLOCK
else:
    [MANDATE] allowed, reason = mandate_checker.check(tx)
    ↓
    if not allowed:
        decision = BLOCK
    else:
        decision = ALLOW
    ↓
[SIGN] signed_decision = authority.sign(
    {decision, fraud_score, mandate_reason, timestamp}
)
    ↓
[ENFORCE] authority_gateway.enforce(signed_decision)
    ↓
AUDIT LOG entry recorded (immutable)
```

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

Every decision can be verified:

```json
{
  "transaction_id": "tx_abc123",
  "fraud_score": 42,
  "fraud_decision": "LOW_RISK",
  "mandate_check": "EXCEEDED_MONTHLY_LIMIT",
  "final_decision": "BLOCK",
  "signed_by": "authority-001",
  "signature": "Ed25519(...)",
  "timestamp": "2026-08-23T12:34:56Z",
  "verified": true
}
```

Authority signature proves:
- Decision wasn't changed
- Timestamp is accurate
- Authority approved it
