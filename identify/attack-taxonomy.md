# Attack Taxonomy: Seven Ways AI Commits Payment Fraud

Six of these are actively simulated by seven bounded agents
(`generate/src/fraud_agents.py`, ported from the original lab), four of
them making real OpenAI API calls, two of them attacking our own trained
detector directly rather than any external system. One is documented
honestly as a known gap, a real attack path this lab does not generate
traffic for, listed so the boundary of what's actually tested (versus
future work) is explicit.

## 1. AI Fabricated Identity, *simulated, real OpenAI calls*
**Where:** Account creation / onboarding.
**Needs:** A generative model, a few real customer profiles to imitate, an
open signup path.
**Why it's hard to catch:** Each transaction looks statistically normal
because the AI copies real spending shape. There's no history to compare
against on transaction #1.
**Damage:** New account fraud, promo abuse, mule accounts.
**Agent:** `agent1_fake_identity`, GPT-4o-mini generates each identity.

## 2. Spending Pattern Replication (Card Testing & Draining), *simulated*
**Where:** Authorization / payment processing.
**Needs:** A stolen card/token and a generator that mimics the
cardholder's usual amount/merchant/timing shape at machine speed.
**Why it's hard to catch:** Amounts and merchants resemble genuine
history; the anomaly is velocity and cumulative volume, visible only in
aggregate.
**Damage:** Direct monetary loss, chargebacks, network penalties.
**Agent:** `agent5_pattern_replicator`, local/statistical by design:
amounts should follow the real distribution being copied, not creative
LLM text.

## 3. Payment Form / API Fuzzing, *simulated*
**Where:** Client input into backend processing.
**Needs:** Knowledge of the form/API schema and an automated fuzzer.
**Why it's hard to catch:** Loud individually, but used as reconnaissance.
The one field that doesn't reject cleanly becomes tomorrow's entry
point.
**Damage:** Crashes, injection vulnerabilities, a discovered bypass used
later.
**Agent:** `agent6_injection_generator`, known public payloads, no LLM
needed.

## 4. AI Voice/Chat Social Engineering, *simulated, real OpenAI calls (text only)*
**Where:** Customer authentication via call center or chat support.
**Needs:** Voice cloning or a conversational model plus leaked personal
data about the victim.
**Why it's hard to catch:** Convincing enough to pass authentication
questions based on personal knowledge.
**Damage:** Account takeover, unauthorized card issuance, disabled fraud
alerts.
**Agent:** `agent2_social_engineer`, GPT-4o-mini generates fictional
call center transcripts. Text only: no voice cloning, no audio, no real
support line contacted.

## 5. Authorization Limit Probing, *simulated, real: attacks our own detector*
**Where:** Authorization.
**Needs:** A stolen card and a script submitting many small transactions
across merchants to map fraud thresholds before one large charge.
**Why it's hard to catch:** Each probe sits under thresholds set per
transaction; only visible when correlated across merchants.
**Damage:** Reveals defenders' thresholds, exploited in a precisely sized
charge that follows.
**Agent:** `agent3_limit_prober`, runs after the detect layer's model is
trained (`generate/src/probe_agents.py`) and submits real amounts from
$10 to $10,000 through the actual model, no fabricated external API.

## 6. AI Generated KYC Document Forgery, *simulated, real OpenAI calls (metadata only)*
**Where:** Identity verification (KYC).
**Needs:** An image generation model producing plausible ID documents or
selfies that pass liveness/document checks.
**Why it's hard to catch:** Can be tuned to defeat the exact verification
model in use, given query access.
**Damage:** Bypasses KYC entirely; enables fully synthetic identities.
**Agent:** `agent4_kyc_forger`, GPT-4o-mini generates identity metadata
bundles (name, DOB, address, occupation), no document images, then our
own detector scores them.

## 7. Feedback Loop Poisoning of the Fraud Model, *not simulated (known gap)*
**Where:** Post decision, dispute/chargeback feedback ingestion.
**Needs:** Repeated small transactions plus false dispute signals meant to
teach a retraining pipeline that fraud patterns are normal.
**Why it's hard to catch:** Attacks the training data, not the
transaction. The model's own confidence goes up, not down.
**Damage:** Long term degradation of detection accuracy.
**Note:** `agent7_feedback_loop` is related but distinct. It generates
real time evasion variants against the already trained model, it does
not poison a retraining pipeline. Actually poisoning a feedback loop
would require a persistent retraining process this lab doesn't run, so
this attack stays an honest gap.

---

Ported from the original mastercard/parmana lab's `docs/attacks.md`.
Agent implementations live in `generate/src/fraud_agents.py`; the
detect layer probing scripts for attacks #5 and #7 (limit probing and
the feedback loop evasion test) are implemented in
`generate/src/probe_agents.py`.
