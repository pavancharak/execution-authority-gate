# Execution Authority Gate: Hybrid Fraud Defense

**Live dashboard: [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev)**

A dual-layer payment fraud defense system combining:
- **Detection Layer** (RandomForest, pattern recognition)
- **Mandate Layer** (deterministic authorization rules)
- **Signing Layer** (Ed25519 cryptographic proof)
- **Authority Layer** (external enforcement gate)

## Architecture

```
Real Fraud Generation (OpenAI temperature=0.9)
    ↓
Detection (RandomForest, 96%+ recall)
    ↓
Mandate (Rule-based authorization)
    ↓
Signing (Ed25519, cryptographic proof)
    ↓
Authority (External enforcement)
    ↓
Audit Log (Immutable, verifiable)
```

## Quick Start

```bash
# Setup
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt

# Run pipeline
cd pipeline/src
python run_pipeline.py

# View dashboard
cd ../../web
python -m http.server 8000
# Open http://localhost:8000
```

## Why This Works

Traditional fraud detection asks: "Does this look suspicious?"

This system asks two questions:
1. **Detection:** "Does this pattern match known fraud?"
2. **Mandate:** "Is this actually authorized?"

Both must pass. Every decision is cryptographically signed and enforced by an external authority.

## Metrics

From the run behind the committed `web/data/dashboard.json`:
- **1,936 transactions** (1,143 legitimate + 793 fraudulent)
- **581 decisions** on the held-out test split: 220 BLOCK / 38 FLAG / 323 ALLOW
- **Detection catch:** 92.4% fraud caught, 7.9% false positive rate
- **Mandate-only blocks:** 26 — real fraud the detector scored as low-risk that the mandate layer caught anyway
- **All decisions signed:** 581/581 verify independently

## Robustness

Numbers will vary run to run once the generate layer's agents 1, 2, 4, and 7 are run against a real `OPENAI_API_KEY` (temperature=0.9, non-deterministic by design) — that's deliberate: it proves the detector holds up across different fraud patterns, not just one fixed dataset.

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

54 hermetic tests run in a few seconds — no API key, no network calls, nothing written outside `tmp_path`. They cover every layer directly (`detect`, `mandate`, `sign`, `generate`'s local agents, `pipeline`), cryptographic properties (key separation, tamper detection, signature uniqueness), and an end-to-end scenario proving the mandate layer catches fraud the detector alone would miss.

3 more tests cover agents 1, 2, 4, and 7 (the ones that call the real OpenAI API) and are skipped by default:

```bash
ALLOW_LIVE_OPENAI=1 OPENAI_API_KEY=sk-... pytest tests/test_generate.py -v
```

## Structure

- **identify/** — Attack taxonomy
- **generate/** — Fraud data generation (real OpenAI)
- **detect/** — RandomForest fraud detector
- **mandate/** — Authorization rule checker
- **sign/** — Ed25519 signing + verification
- **pipeline/** — Orchestration of all layers
- **web/** — Interactive dashboard
- **tests/** — Comprehensive test suite

## Deployment

Live at [execution-authority-gate.fly.dev](https://execution-authority-gate.fly.dev), deployed via `flyctl deploy` from this repo. The deployed container runs `web/server.py` (a small Flask static server with a `/api/status` health check) and serves the committed `web/data/dashboard.json` as-is — the pipeline doesn't run inside the container, so the live numbers stay fixed to whatever was last committed until someone regenerates and recommits that file.

To redeploy after code changes:
```bash
flyctl deploy
```

## The Pitch

"Execution Authority Gate: Fraud detection + mandate enforcement + cryptographic signing + external authority. Real OpenAI generation proves robustness. Every decision verifiable, none can be changed."
