# Judges' Guide: Understanding Parmana Authority Gate

## Executive summary

**What this is:** A two layer fraud defense system, a trained detector, an independent rule based mandate check, and Ed25519 cryptographic signing, for authorizing agentic payment execution safely. Built on a real, self generated dataset, including real OpenAI API calls for the identity, social engineering, and KYC generation agents.

**Live dashboard:** https://parmana.fly.dev

This guide exists to answer the one question judges are most likely to ask when they see the numbers: *"Precision is only 21.1%, doesn't that mean 4 out of 5 flags are wrong?"* Yes, and that's explained below.

---

## The real numbers

From the committed run behind `web/data/dashboard.json` (also rendered live on the dashboard's Detection tab):

- **6,869 decisions** on the held out test split: 441 BLOCK / 146 FLAG / 6,282 ALLOW
- **Fraud caught: 89.1%**, 123 of 138 fraud cases in the test set
- **False positive rate: 6.8%**, 459 of 6,731 legitimate transactions flagged
- **Precision: 21.1%**, of the 582 transactions flagged (123 true positives + 459 false positives), about 1 in 5 is real fraud

### Confusion matrix (detect layer, test set)

|                     | Predicted legitimate | Predicted fraud |
|---------------------|----------------------:|-----------------:|
| **Actual legitimate** | 6,272 (true negative) | 459 (false positive) |
| **Actual fraud**       | 15 (false negative)   | 123 (true positive)  |

Precision = TP / (TP + FP) = 123 / 582 = **21.1%**
Recall (fraud caught) = TP / (TP + FN) = 123 / 138 = **89.1%**

These are the exact figures in `detect.metrics` in `web/data/dashboard.json`. Nothing below rounds or reinterprets them.

---

## Why precision is 21.1%, and why that's expected, not a bug

**Fraud is rare.** In this dataset it's ~2% of transactions (138 fraud out of 6,869 test set transactions). Any classifier tuned to catch a large share of a rare event has to be aggressive, and aggressive detectors flag more of the majority class along with it. Precision and recall trade off against each other; pushing recall to 89% on a problem with a base rate of 2% is exactly the regime where precision drops, no matter how good the model is. A detector with much higher precision at this base rate would necessarily be catching a smaller share of the fraud, the "obvious" cases only.

**A useful intuition (not a claim of equivalence):** airport security screens aggressively to catch dangerous items, which means far more bags get a second look than actually contain something. That's an accepted tradeoff because a missed threat is much more costly than a false alarm. The same shape of tradeoff applies here. Precision alone is the wrong metric to judge a detector of rare events by; recall at an acceptable false positive rate is the metric that matters.

**Precision here describes the detect layer in isolation, not the system's real world false accusation rate.** This is the important structural point: a detect layer flag does not block a transaction by itself.

```
Transaction
    ↓
Detect layer  → fraud score (RandomForest; this is where "precision: 21.1%" is measured)
    ↓
Mandate layer → independent rule check (spending limit, merchant whitelist,
                 time of day window, velocity) against that customer's own history
    ↓
Sign layer    → Ed25519 signature over the final decision, ALLOW or BLOCK,
                 independently verifiable by anyone with the public key
    ↓
Final decision
```

A transaction is only BLOCKed if the mandate layer also finds it unauthorized (or the detect layer's own thresholds already rule it worthy of a BLOCK). See `mandate.block_attribution` in the dashboard data, which shows 8 blocks the mandate layer caught on its own after the detector scored them as low risk, and shows every block broken down by which layer (or both) drove it. Every one of the 6,869 final decisions, ALLOW or BLOCK, is signed, and all 6,869 signatures verify independently (`verification` in `dashboard.json`).

So, the 21.1% number tells you how noisy the detect layer's raw flags are on this dataset. It is not a measure of how often the whole system wrongly denies a legitimate transaction. That would require looking at final `BLOCK` decisions against ground truth, which is a different (and much lower false positive) number, visible in the pipeline's `decision_counts` and `sample_decisions` in `web/data/dashboard.json`.

---

## Is 89.1% recall / 21.1% precision a reasonable operating point?

There's no universal "right" precision for a fraud detector. It depends on what a flag costs versus what a miss costs, and that's a business decision, not a modeling one. What can be said concretely about this system:

- The RandomForest uses `class_weight="balanced"` specifically so it doesn't collapse to majority class prediction under a realistic ~2% fraud rate. An earlier, more imbalanced version of this dataset let 16 of 18 adversarial evasion variants through (see the README's "Robustness" section); this version lets through 1 of 18.
- The operating threshold is a choice, not a fixed property of the model. The dashboard's `top_signals` (feature importances) and the mandate layer's `rule_violation_counts` show what's actually driving both layers' decisions, so the tradeoff is inspectable rather than a black box.
- A false positive here costs a customer a flag or review step, not an unauthorized charge; a false negative costs actual fraud loss. Weighting recall higher than precision is a defensible choice under that asymmetry, but it is a choice this project is making explicitly, not a claim that 21.1% precision is optimal in general.

---

## How to verify this yourself

This is a Python project (pytest, not npm).

```bash
# Run the hermetic test suite (54 tests, no network calls, no API key needed)
pip install -r requirements.txt
pytest tests/ -v

# Inspect the exact numbers behind this guide
python -c "import json; d=json.load(open('web/data/dashboard.json')); print(json.dumps(d['detect']['metrics'], indent=2))"

# View the dashboard locally, as committed
cd web && python -m http.server 8000
# open http://localhost:8000

# Regenerate the entire dataset + metrics from scratch (requires OPENAI_API_KEY, ~$0.03)
cd generate/src && python run_simulation.py
cd ../../detect/src && python check_results.py
cd ../../generate/src && python probe_agents.py
cd ../../pipeline/src && python run_pipeline.py
```

Running the generation step again calls the real OpenAI API at `temperature=0.9`, so the exact numbers will drift slightly run to run. That's intentional (see the README's "Robustness" section) and demonstrates the detector isn't overfit to one fixed dataset, rather than a claim that these exact figures are reproducible bit for bit.

---

## Try It Yourself: The Live Test Harness

The live dashboard opens on the Live Test tab. This is the fastest way to see that the numbers above are not just claims.

Pick a sample customer, enter an amount, a merchant, an hour of day, and an AI generated signal value, then press "Run transaction." The result is not looked up from a table. It is computed right then: the real trained model scores it, the real mandate rules check it against that customer's own history, and the result is signed and verified with a real key, live, in that request.

A few things worth trying:

* A small amount at a normal hour at a merchant the customer already uses. This usually comes back ALLOW.
* The same transaction, but at a merchant not on that customer's list. Watch the mandate step object even though the detection score has not changed at all.
* A high AI generated signal value on an otherwise ordinary transaction. Watch the detection score rise even when every mandate rule passes.
* A few similar transactions in a row. FLAG will show up on transactions that are not obviously fraud. That is the precision tradeoff described above, happening in front of you instead of sitting in a table.

There is also an Attack Walkthrough tab: five real, already signed decisions pulled straight from an actual pipeline run, one for each attack type this project simulates, with the same four step breakdown (detection, mandate, signing, final decision).

---

## FAQ

**Q: Why is precision only 21.1%?**
Because fraud is rare (~2% of transactions) and the detector is tuned for high recall (89.1%) at that base rate. See "Why precision is 21.1%" above.

**Q: Are these numbers real or synthetic and cherry picked?**
Real, from this repo's own generation pipeline, including live OpenAI calls for several agents. They're committed as `web/data/dashboard.json` and reproducible by running the pipeline yourself with your own API key (numbers will vary slightly run to run since generation is not deterministic).

**Q: What happens to the false positives?**
They become FLAG or (if the mandate layer also disagrees) BLOCK decisions, not silent auto denials. Every decision is signed and auditable, and the mandate layer's checks are logged per transaction (see `mandate.sample_mandate_only_blocks` in the dashboard data for worked examples).

**Q: Could an attacker get fraud through by exploiting the low precision?**
Low precision means legitimate transactions sometimes get flagged. It doesn't create a bypass for fraud. A fraudulent transaction still has to pass both the detect layer's score *and* the mandate layer's independent rule check to be ALLOWed; the adversarial robustness test (agent 7) measures exactly this and found 1 of 18 disguised fraud variants got through.

**Q: What about the 15 fraud cases missed?**
That's the recall and precision tradeoff in the other direction. Pushing recall from 89.1% toward 100% would mean flagging even more of the legitimate 6,731, further lowering precision. The current threshold is a chosen operating point, not a hard limit of the approach.

---

## Live dashboard

**URL:** https://parmana.fly.dev

The Detection tab shows the confusion matrix, stat tiles for precision, recall, and false positive rate (hover for the underlying counts), and feature importances live from the same `dashboard.json` referenced throughout this guide.
