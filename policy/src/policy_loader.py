"""
Loads a policy document from policy/policies/<policy_id>/<version>/policy.json
and validates it before handing it to policy_engine.evaluate_policy.

Single-policy-per-run by design: this repo doesn't route between many
policies for many tenants at once, it runs one policy document against
every transaction in a given pipeline run (see run_pipeline.py's
--policy-id/--policy-version).
"""

import json
from pathlib import Path

from policy_validator import validate_policy

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"


def load_policy(policy_id, version):
    path = POLICIES_DIR / policy_id / version / "policy.json"
    if not path.exists():
        raise FileNotFoundError(f"No policy at {path}")

    policy = json.loads(path.read_text())
    validate_policy(policy)
    return policy
