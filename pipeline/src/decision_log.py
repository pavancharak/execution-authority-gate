"""
Writes the pipeline's signed decisions to disk and summarizes them: final
decision counts, and — for blocked transactions — whether the block came
from the detect layer, the mandate layer, or both. That attribution is
the whole point of running two independent layers: a block from the
mandate layer is a transaction the detect layer alone would have missed.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # pipeline/
DECISIONS_DIR = ROOT / "decisions"


def write_log(entries):
    DECISIONS_DIR.mkdir(exist_ok=True)
    path = DECISIONS_DIR / "pipeline_decisions.json"
    path.write_text(json.dumps(entries, indent=2))
    return path


def summarize(entries):
    counts = {"BLOCK": 0, "FLAG": 0, "ALLOW": 0}
    block_attribution = {"detect_only": 0, "mandate_only": 0, "both": 0}

    for e in entries:
        decision = e["decision"]
        final = decision["final_decision"]
        counts[final] += 1
        if final != "BLOCK":
            continue
        detect_blocked = decision["detect_decision"] == "BLOCK"
        mandate_blocked = not decision["mandate_allowed"]
        if detect_blocked and mandate_blocked:
            block_attribution["both"] += 1
        elif detect_blocked:
            block_attribution["detect_only"] += 1
        elif mandate_blocked:
            block_attribution["mandate_only"] += 1

    return {
        "total": len(entries),
        "decision_counts": counts,
        "block_attribution": block_attribution,
    }
