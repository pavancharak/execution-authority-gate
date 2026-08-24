"""
Assembles web/data/dashboard.json from a completed pipeline run, the
single file the web dashboard reads. Everything in it is real output
from this run: nothing here is hand authored sample data.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
IDENTIFY_DIR = ROOT / "identify"
WEB_DATA_DIR = ROOT / "web" / "data"


def _load_attacks():
    path = IDENTIFY_DIR / "attacks.json"
    return json.loads(path.read_text()) if path.exists() else []


def _rule_violation_counts(entries):
    counts = {"spending_limit": 0, "merchant_whitelist": 0, "time_restriction": 0, "velocity": 0}
    for e in entries:
        for check in e["mandate_checks"]:
            if not check["passed"]:
                counts[check["rule"]] += 1
    return counts

def _attack_type_breakdown(fraud_transactions):
    breakdown = {}
    for tx in fraud_transactions:
        key = tx.get("attack_type", "none")
        breakdown[key] = breakdown.get(key, 0) + 1
    return breakdown


def build(
    good_transactions,
    fraud_transactions,
    detect_metrics,
    mandates,
    entries,
    verification,
    api_activity=None,
    sample_size=40,
    seed=7,
):
    rng = random.Random(seed)

    mandate_only_blocks = [
        e for e in entries
        if e["decision"]["final_decision"] == "BLOCK"
        and e["decision"]["detect_decision"] != "BLOCK"
        and not e["decision"]["mandate_allowed"]
    ]

    decision_counts = {"BLOCK": 0, "FLAG": 0, "ALLOW": 0}
    block_attribution = {"detect_only": 0, "mandate_only": 0, "both": 0}
    for e in entries:
        d = e["decision"]
        decision_counts[d["final_decision"]] += 1
        if d["final_decision"] != "BLOCK":
            continue
        detect_blocked = d["detect_decision"] == "BLOCK"
        mandate_blocked = not d["mandate_allowed"]
        if detect_blocked and mandate_blocked:
            block_attribution["both"] += 1
        elif detect_blocked:
            block_attribution["detect_only"] += 1
        elif mandate_blocked:
            block_attribution["mandate_only"] += 1

    dashboard = {
        "meta": {
            "title": "Parmana Authority Gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "attacks": _load_attacks(),
        "simulation": {
            "good_transaction_count": len(good_transactions),
            "fraud_transaction_count": len(fraud_transactions),
            "attack_type_breakdown": _attack_type_breakdown(fraud_transactions),
        },
        "api_activity": api_activity or {"calls": [], "summary": {"total_calls": 0, "total_tokens": 0, "total_cost_usd": 0, "avg_latency_ms": 0}},
        "detect": {
            "metrics": detect_metrics,
        },
        "mandate": {
            "mandates_derived": len(mandates),
            "block_attribution": block_attribution,
            "rule_violation_counts": _rule_violation_counts(entries),
            "sample_mandate_only_blocks": rng.sample(mandate_only_blocks, min(5, len(mandate_only_blocks))),
        },
        "pipeline": {
            "total": len(entries),
            "decision_counts": decision_counts,
            "sample_decisions": rng.sample(entries, min(sample_size, len(entries))),
        },
        "verification": verification,
    }

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = WEB_DATA_DIR / "dashboard.json"
    path.write_text(json.dumps(dashboard, indent=2))
    return path
