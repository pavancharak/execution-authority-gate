# Execution Authority Gate: Hybrid Fraud Defense

[![Tests](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml/badge.svg)](https://github.com/pavancharak/execution-authority-gate/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Live dashboard: [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev)**

A two layer payment fraud defense system combining:
- **Detection Layer** (RandomForest, pattern recognition)
- **Mandate Layer** (deterministic authorization rules)
- **Signing Layer** (Ed25519 cryptographic proof)
- **Caller Scoping** (callers authenticated with HMAC, permission scoped by decision type)
- **Execution Layer** (signed decisions ready for execution by a payment processor webhook, fail closed and idempotent)

## Architecture

```
Real Fraud Generation (OpenAI temperature=0.9)
    ↓
Detection (RandomForest, ~92% recall at a realistic 2 to 3% fraud rate)
    ↓
Mandate (Rule based authorization)
    ↓
Signing (Ed25519, cryptographic proof; caller identity embedded in the signed envelope)
    ↓
Audit Trail (append only, committed to git, independently verifiable again anytime)
    ↓
Execution (caller authenticated, signature checked, idempotent handoff to a payment processor webhook)
```

## Quick Start

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

To regenerate the dashboard from a fresh, self generated dataset (copy `.env.example` to `.env` and set a real `OPENAI_API_KEY` first, agents 1, 2, 4, and 9 make real, cheap GPT-4o-mini calls):

```bash
cd generate/src && python run_simulation.py   # agents 1,2,4,9 (real OpenAI) + 5,6,8 (local)
cd ../../detect/src && python check_results.py # trains the model agents 3/7 probe
cd ../../generate/src && python probe_agents.py # agents 3,7 (agent 7 is real OpenAI)
cd ../../pipeline/src && python run_pipeline.py # detect + mandate + sign -> dashboard
```

## In Plain Language

Before a transaction is allowed through, two independent checks have to agree. Neither one trusts the other's reasoning:

1. **Does this look like fraud?** A model trained on real transaction patterns scores every transaction for risk.
2. **Is this actually authorized?** A separate, rule based check compares the transaction against that specific customer's own history: spending limits, merchants, hours, frequency, regardless of what the fraud model thinks.

Either one objecting is enough to block it. Then, whatever the outcome, a third step signs the final decision with a private key nobody else holds, producing a tamper evident record anyone can verify independently. Signing isn't a vote. Every decision gets signed, ALLOW or BLOCK. It's what makes the first two layers' decision provable and unforgeable after the fact, not a third check that can veto anything.

**Real results, from a live, self generated run, not a cherry picked demo:**
- Catches 92.2% of fraud
- 6.3% false alarm rate on legitimate activity
- Every one of 6,912 decisions is signed and independently verifiable, 6,912/6,912 checked out
- A separate adversarial test asked GPT to disguise already blocked fraud so it would slip past the model; 10 of 18 attempts succeeded. (That's a narrow robustness result on a small sample, not a claim about a general evasion rate, and it is worse than an earlier run of this dataset, see Robustness below for why.)

## Try It Live

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

## Metrics

From the run behind the committed `web/data/dashboard.json`, fully self generated by this repo's own `generate/` layer, including real GPT-4o-mini calls for agents 1, 2, 4, 7, and 9 (27 calls, ~$0.037 total):
- **23,037 transactions at a realistic 2.61% fraud rate** (22,436 legitimate + 601 fraudulent). The legitimate pool is scaled up for free (local generation, no API cost) specifically so the fraud rate can be realistic *without* shrinking the fraud count to a statistically noisy sample. 601 fraud examples means the test split alone has ~180 fraud cases to evaluate on, not a handful.
- Fraud spread across the 7 attack types that actually produce labeled transactions: fake_identity 112, social_engineering 52, kyc_synthetic 100, pattern_copy 100, form_break 100, synthetic_bustout 100, vendor_bec 37. (Agents 3 and 7, limit probing and feedback loop exploit, probe the trained model directly instead of generating transactions, so they're not part of this breakdown; see `identify/attack-taxonomy.md`.)
- **6,912 decisions** on the held out test split: 446 BLOCK / 150 FLAG / 6,316 ALLOW
- **Detection catch:** 92.2% fraud caught, 6.3% false positive rate. The RandomForest uses `class_weight="balanced"` to hold up under this realistic imbalance rather than defaulting to the majority class
- **Mandate only blocks:** 26. Real fraud the detector scored as low risk that the mandate layer caught anyway, most of it the new synthetic identity bust out attack, deliberately designed to look ordinary to a per transaction classifier while still exceeding that customer's own derived spending limit
- **All decisions signed:** 6,912/6,912 verify independently
- **Red team (agent 7):** 18 evasion variants tested against the trained model, 10 evaded detection, worse than an earlier run of this dataset (1 of 18 evaded then). See Robustness below for the likely reason

### Why precision is around 28% (and why that's expected)

The detect layer's **precision is 28.2%**: of the 589 transactions it flags (423 false positives + 166 true positives), a little over 1 in 4 is actually fraud. That number looks bad in isolation, so here's the context:

- **Fraud is rare** (180 of 6,912 test set transactions, a bit over 2%). Tuning a classifier to catch over 92% of that rare an event requires flagging aggressively. It is the same tradeoff airport security makes to catch most weapons at the cost of screening plenty of harmless bags. Recall and precision pull against each other; you cannot maximize both when the positive class is this sparse.
- **Precision measures the detect layer alone**, in isolation, on the held out test set. It is *not* the system's real world false accusation rate. A detect layer flag doesn't block anything by itself. It still has to clear the independent, rule based **mandate** layer (spending limits, merchant whitelist, time of day, velocity) before a transaction is denied, and every final decision, ALLOW or BLOCK, is signed and independently verifiable.
- The confusion matrix behind these numbers: of 6,732 legitimate test transactions, 6,309 passed and 423 were flagged; of 180 fraud transactions, 166 were caught and 14 were missed. (`web/data/dashboard.json` → `detect.metrics.confusion_matrix`, also rendered live on the [dashboard](https://execution-authority-gate.fly.dev)'s Detection tab.)

See [`docs/JUDGES_GUIDE.md`](docs/JUDGES_GUIDE.md) for the full walkthrough, including why a detector with low precision and high recall is standard practice in fraud detection rather than a flaw.

## Robustness

Numbers vary run to run: agents 1, 2, 4, 7, and 9 call the real OpenAI API at temperature=0.9, not deterministic by design. Running `generate/src/run_simulation.py` again (then `detect/src/check_results.py`, `generate/src/probe_agents.py`, and `pipeline/src/run_pipeline.py`) with your own `OPENAI_API_KEY` will produce different fraud examples and slightly different metrics. That's deliberate, it proves the detector holds up across different fraud patterns, not just one fixed dataset.

Adding the synthetic identity bust out and vendor BEC attacks changed more than the attack count: `amount` moved from a minor signal to the model's second most important feature (`top_signals` in `web/data/dashboard.json`, since both new attacks are large, out of pattern amounts), and adversarial evasion resistance dropped from 1 of 18 to 10 of 18 in the same run. A model that leans harder on amount is easier to nudge with the small numeric adjustments GPT proposes in agent 7's evasion test. This is reported plainly, not smoothed over: broadening the attack taxonomy improved recall (89.1% to 92.2%) and gave the mandate layer more to catch on its own (8 to 26 mandate only blocks), but it came with a real adversarial robustness cost, a genuine tradeoff, not a one directional improvement.

## Production Deployment and Execution Integration

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

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

89 hermetic tests run in a few seconds, no API key, no network calls, nothing written outside `tmp_path`. They cover every layer directly (`detect`, `mandate`, `sign`, `generate`'s local agents, `pipeline`), cryptographic properties (key separation, tamper detection, signature uniqueness), the append only audit trail, caller authentication and permission scoping, the decision executor's fail closed and idempotency guarantees, and a scenario proving end to end that the mandate layer catches fraud the detector alone would miss.

4 more tests cover agents 1, 2, 4, and 9 (the ones that call the real OpenAI API) and are skipped by default:

```bash
ALLOW_LIVE_OPENAI=1 OPENAI_API_KEY=sk-... pytest tests/test_generate.py -v
```

## Structure

- **identify/**: Attack taxonomy
- **generate/**: 7 fraud agents + orchestration (`run_simulation.py`, `probe_agents.py`); agents 1, 2, 4, 7 call the real OpenAI API
- **detect/**: RandomForest fraud detector
- **mandate/**: Authorization rule checker
- **sign/**: Ed25519 signing + verification
- **pipeline/**: Orchestration of all layers
- **web/**: Interactive dashboard, plus an Attack Walkthrough (real precomputed decisions) and a Live Test Harness (runs a submitted transaction through the real pipeline on demand, needs `python web/server.py`, not the static `http.server`). See "Try It Live" above.
- **tests/**: Comprehensive test suite

## Deployment

Live at [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev), deployed via `flyctl deploy` from this repo. The deployed container runs `web/server.py` (a small Flask static server with a `/api/status` health check) and serves the committed `web/data/dashboard.json` as is. The pipeline doesn't run inside the container, so the live numbers stay fixed to whatever was last committed until someone regenerates and recommits that file.

To redeploy after code changes:
```bash
flyctl deploy
```

## The Pitch

"Execution Authority Gate: Fraud detection + mandate enforcement + cryptographic signing + external authority. Real OpenAI generation proves robustness. Every decision verifiable, none can be changed."

## License

MIT, see [LICENSE](LICENSE).
