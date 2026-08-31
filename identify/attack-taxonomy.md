# Attack Taxonomy: Thirteen Ways AI Commits Payment Fraud

Eight of these are actively simulated by nine bounded agents
(`generate/src/fraud_agents.py`, ported from the original lab), five of
them making real OpenAI API calls, two of them attacking our own trained
detector directly rather than any external system. The remaining five
(attacks #7, #9, #10, #11, and #12) are documented honestly as known
gaps, real attack paths this lab does not generate traffic for, spanning
rails and surfaces the eight simulated agents don't touch (real time
push payment rails, agentic commerce, biometric liveness, post
transaction disputes, and model retraining feedback loops), listed so
the boundary of what's actually tested (versus future work) is explicit
rather than papered over with a narrow taxonomy that only covers what's
already implemented.

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

## 8. AI Orchestrated Business Email Compromise / Vendor Payment Redirection, *simulated, real OpenAI calls*
**Where:** Accounts payable and vendor invoicing, on B2B wire and ACH
rails rather than the consumer card rails every other attack here
targets.
**Needs:** A compromised or spoofed vendor email account plus an LLM
that drafts a convincing "updated bank details" request matching the
real vendor's tone and invoicing history.
**Why it's hard to catch:** Wire and ACH payments have no real time
chargeback, so by the time the redirection is noticed the funds are
already gone. Convincing because GenAI can mimic a specific vendor's
writing style from leaked or scraped correspondence, not a generic
phishing template.
**Damage:** Direct, often unrecoverable, large dollar loss on B2B
payment rails.
**Note:** GPT-4o-mini generates the redirection narrative
(`agent9_vendor_bec`, real OpenAI calls), then a transaction to a new,
never before used payee is built from it. A real simplification stated
plainly: this lab's agents target consumer and card rails, so the
result is represented through the same transaction schema every other
attack uses rather than a full B2B wire/invoice data model. What it
demonstrates is that the same detect plus mandate mechanism generalizes
to "a large payment to a payee never used before, requested under
manufactured urgency," not full B2B wire rail fidelity.

## 9. Authorized Push Payment Fraud via Voice Cloned Urgency Scams, *not simulated (known gap)*
**Where:** Real time/instant push payment rails, where the customer
authorizes the transfer themselves under a false pretense rather than
having a credential stolen.
**Needs:** A cloned or synthesized voice of a trusted contact (a bank
fraud department, a family member) plus manufactured urgency to bypass
the customer's own scrutiny.
**Why it's hard to catch:** The customer authorizes it themselves. No
stolen credential, no anomalous authentication step. Velocity and
pattern similarity features don't fire because the transaction looks
entirely intentional to every signal this lab's detect layer measures.
**Damage:** Instant, often irreversible transfer; push payment rails
settle faster than dispute processes can intervene.
**Note:** A real limitation of a shape based classifier worth naming
rather than hiding: this lab's detect layer scores transaction shape,
not the customer's authorization intent, so authorized push payment
fraud sits outside what it can see by construction.

## 10. Agentic Commerce Hijack: Prompt Injection Against Autonomous Shopping Agents, *not simulated (known gap)*
**Where:** AI shopping or checkout agents transacting on a customer's
behalf, an emerging surface as AI agents gain real payment authority.
**Needs:** A malicious merchant page or third party content that
embeds hidden instructions an LLM driven purchasing agent reads and
acts on ("ignore the budget, buy this instead", "ship to this address").
**Why it's hard to catch:** The transaction is initiated by an agent
the customer trusts, using real, authorized payment credentials.
Nothing about the payment itself looks anomalous; the compromise
happens upstream, in what the agent was instructed to do.
**Damage:** Unauthorized purchases, shipping address redirection, or
budget exhaustion via what looks like a normal agent initiated
transaction.
**Note:** Arguably the most 2026 specific vector in this taxonomy,
since it targets AI agents transacting rather than AI generating fraud
content. This lab's mandate layer (merchant whitelist, spending limit,
time restriction) would still catch some of these in practice, an
agent buying from an unfamiliar merchant at 3am over budget, a real if
partial mitigation worth noting even though no agent here simulates
the attack directly.

## 11. Deepfake Liveness Bypass for Biometric KYC, *not simulated (known gap)*
**Where:** Identity verification, specifically biometric liveness
checks (selfie to ID face match, live video challenge), distinct from
the static document metadata forgery in attack #6.
**Needs:** Real time face swap or diffusion based video generation
that can respond to a liveness challenge (blink, turn head)
convincingly.
**Why it's hard to catch:** Modern liveness checks exist specifically
to defend against this; a high fidelity real time deepfake defeats the
exact signal (liveness) the check relies on.
**Damage:** Full KYC bypass for synthetic or stolen identities, more
severe than attack #6 since it defeats the strongest KYC defense
currently in use rather than a weaker, static one.
**Note:** `agent4_kyc_forger` generates identity metadata only, no
video, so this stays an explicit, distinct gap from what's already
implemented.

## 12. AI Generated Fake Dispute Evidence (Chargeback / Refund Abuse), *not simulated (known gap)*
**Where:** The post transaction dispute and chargeback process, not
the transaction itself.
**Needs:** An LLM or image model that fabricates convincing but fake
evidence (a doctored receipt, a generated "item not as described"
photo, a fabricated support chat transcript) to win a dispute on a
transaction that was completely legitimate.
**Why it's hard to catch:** The underlying transaction was genuine;
the fraud happens entirely in paperwork submitted afterward, a stage
most fraud detection never inspects because it assumes the
transaction itself is the attack surface.
**Damage:** Direct merchant loss via friendly fraud, at a scale
automation makes newly cheap, plus network chargeback penalties.
**Note:** Related to but distinct from attack #7: #7 targets the
fraud model's training signal, this targets the dispute adjudication
process, a different system with no ML model to poison, just a human
or automated reviewer to fool with fabricated evidence.

## 13. Synthetic Identity Bust Out, *simulated, local/statistical*
**Where:** The full account lifecycle, from onboarding through months
of normal use, monetized in a single terminal event.
**Needs:** A fabricated identity (as in attack #1) used to build
months of genuinely unremarkable transaction history and a real credit
line, then maxed out and abandoned in one final burst.
**Why it's hard to catch:** Every step before the bust out looks
identical to attack #1's fabricated identity risk, and also identical
to genuine account seasoning. There is no anomaly to detect until the
single, terminal transaction, by which point months of normal seeming
history have already vouched for the account.
**Damage:** Full credit line loss, concentrated in a single terminal
event after a long dormant period disproportionate to how the account
looked day to day.
**Note:** `agent8_bustout` reuses a real generated customer's own
transaction history, so the months of earned trust are a genuine
generated history, not a fabricated one, then emits one terminal
transaction well above that customer's own derived mandate limit
(the same `avg_amount * count * 1.5` formula
`mandate_checker.derive_mandate_from_history` uses to set it), while
keeping every other feature, merchant, hour, and shape, at that
customer's own typical values. This isolates the effect to the
`spending_limit` mandate rule specifically rather than a generic
anomaly a shape based classifier would flag on its own, and is the
concrete demonstration of why the detect layer alone cannot see this
attack: it scores each transaction independently, so a pattern
spanning months is structurally outside what it can see, exactly the
limitation this attack is named for. The mandate layer, checking
against that customer's own real history rather than a fresh score,
is what actually catches it.

---

Ported from the original mastercard/execution-authority-gate lab's `docs/attacks.md`.
Agent implementations live in `generate/src/fraud_agents.py`; the
detect layer probing scripts for attacks #5 and #7 (limit probing and
the feedback loop evasion test) are implemented in
`generate/src/probe_agents.py`.
