"""
Thin wrapper around the OpenAI API for the agents that use real GPT calls
(Agent 1 identity generation, Agent 2 social engineering transcripts,
Agent 4 KYC bundles, Agent 7 evasion variant suggestions).

Loads OPENAI_API_KEY from the repo root .env file (never committed, see
.gitignore) so the key never has to be pasted into chat, code, or any
committed file. Every call's real token usage is printed with an
approximate cost so nothing runs up a surprise bill.

Every call is also logged to data/api_call_log.json: timestamp, purpose,
model, real token counts, real cost, real latency, and a preview of the
actual prompt and response. The API key itself is never written to that
file or anywhere else outside this process's memory and the local .env
it came from.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
LAYER_ROOT = SRC_DIR.parent  # generate/
REPO_ROOT = LAYER_ROOT.parent  # repo root, where .env lives
DATA_DIR = LAYER_ROOT / "data"
LOG_PATH = DATA_DIR / "api_call_log.json"


def _load_dotenv():
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

DEFAULT_MODEL = "gpt-4o-mini"

# Approximate USD price per token. Verify current pricing at
# openai.com/pricing before relying on this for real budgeting; OpenAI
# changes prices and this table is not fetched live.
PRICING_PER_TOKEN = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}

_client = None
_session_cost = 0.0
_session_calls = 0


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Create a .env file in the repo root "
                "(copy .env.example) with OPENAI_API_KEY=sk-..., then try again."
            )
        from openai import OpenAI

        _client = OpenAI(api_key=api_key)
    return _client


def session_totals():
    return {"calls": _session_calls, "estimated_cost_usd": round(_session_cost, 5)}


def reset_log():
    """Start a fresh call log for a new pipeline run. Call this once, at
    the top of the generation entry point, before any agent runs."""
    DATA_DIR.mkdir(exist_ok=True)
    LOG_PATH.write_text("[]")


def _append_to_log(record):
    DATA_DIR.mkdir(exist_ok=True)
    existing = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else []
    existing.append(record)
    LOG_PATH.write_text(json.dumps(existing, indent=2))


def load_log_summary():
    """Read the accumulated call log and compute real aggregate stats for
    the dashboard's API Activity tab."""
    calls = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else []
    total_tokens = sum(c["total_tokens"] for c in calls)
    total_cost = sum(c["cost_usd"] for c in calls)
    latencies = [c["latency_ms"] for c in calls]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0
    return {
        "calls": calls,
        "summary": {
            "total_calls": len(calls),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 5),
            "avg_latency_ms": avg_latency,
        },
    }


def call_json(system_prompt: str, user_prompt: str, purpose: str, model: str = DEFAULT_MODEL, temperature: float = 0.9) -> dict:
    """Call the model asking for a single JSON object response. Prints
    real token usage and an approximate cost, updates the running session
    total, and appends a real record (timestamp, purpose, tokens, cost,
    latency, prompt/response previews) to data/api_call_log.json. Raises
    if the model doesn't return valid JSON, we'd rather fail loudly than
    silently fabricate empty output."""
    global _session_cost, _session_calls

    client = _get_client()
    started_at = time.time()
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    latency_ms = round((time.time() - started_at) * 1000)

    usage = response.usage
    price = PRICING_PER_TOKEN.get(model, PRICING_PER_TOKEN[DEFAULT_MODEL])
    cost = usage.prompt_tokens * price["input"] + usage.completion_tokens * price["output"]
    _session_cost += cost
    _session_calls += 1
    print(
        f"      [openai] {model}: {usage.prompt_tokens} in + {usage.completion_tokens} out "
        f"(~${cost:.4f}, session total ~${_session_cost:.4f} over {_session_calls} calls)"
    )

    content = response.choices[0].message.content

    _append_to_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose,
        "model": model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
        "prompt_preview": user_prompt[:300],
        "response_preview": content[:300],
    })

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model did not return valid JSON: {e}\nRaw content: {content[:500]}")
