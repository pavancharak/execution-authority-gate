"""
Execution layer: turns a signed decision into an action against a
downstream payment processor.

EAG-AUDIT-GAPS.md section 3 found this had no implementation at all:
signing was the last step in the pipeline, nothing called a payment
processor, moved money, or notified any downstream system.
DecisionExecutor is that missing handoff. It does not itself talk to a
real payment network (this repo has no such integration to call); it
defines the contract a real one would plug into
(payment_processor_webhook, any callable of the shape
`(action, signed_decision) -> dict`) and enforces the properties that
handoff must have regardless of which processor sits behind it:

  - never execute a decision whose signature doesn't verify (fail
    closed on tampering, see sign/src/signature_verifier.py)
  - never execute a decision on behalf of a caller not permitted to
    execute that decision type (see sign/src/caller_auth.py)
  - never execute the same signed decision twice (idempotency, keyed on
    the decision's record_id, the same id sign/src/authority_signer.py
    assigns once at signing time)
  - log every execution attempt, allowed or rejected, to an
    append only trail (see pipeline/src/audit_trail.py for the sibling
    decision trail this mirrors)
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # sign/
REPO_ROOT = ROOT.parent
EXECUTION_LOG_PATH = REPO_ROOT / "pipeline" / "audit" / "executions.jsonl"

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
import signature_verifier as verify  # noqa: E402

# final_decision -> action taken against the payment processor.
ACTION_FOR_DECISION = {
    "ALLOW": "settle",
    "FLAG": "step_up_auth",
    "BLOCK": "deny",
}


class ExecutionLog:
    """Append only JSONL log of execution attempts, mirroring
    pipeline/src/audit_trail.py's AuditTrail. Kept as a separate file
    (executions.jsonl, not decisions.jsonl) because it records a
    different fact: not "this decision was made" but "this decision was
    handed to a payment processor, and here is what happened"."""

    def __init__(self, path: Path = EXECUTION_LOG_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: dict):
        entry = dict(entry)
        entry.setdefault("logged_at", time.time())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def read_all(self):
        entries = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def already_executed(self, record_id: str) -> bool:
        """True if some prior entry for this record_id reached EXECUTED.
        A prior REJECTED attempt (bad signature, bad permission) does
        NOT count: rejecting a request doesn't consume the decision, so
        a later, valid attempt should still be able to execute it."""
        for entry in self.read_all():
            if entry.get("record_id") == record_id and entry.get("status") == "EXECUTED":
                return True
        return False


class DecisionExecutor:
    """Validates and executes signed decisions against a payment
    processor webhook. Holds no private key and cannot sign anything;
    it only ever checks a signature that already exists (see
    sign/src/authority_signer.py, which is where trust actually
    originates)."""

    def __init__(self, log_path: Path = EXECUTION_LOG_PATH, signer_name: str = "authority"):
        self.signer_name = signer_name
        self.log = ExecutionLog(log_path)

    def enforce_decision(self, signed_decision: dict, payment_processor_webhook, caller=None) -> dict:
        """Execute one signed decision.

        signed_decision: a record produced by
            authority_signer.sign_pipeline_decision (must contain
            record_id, transaction_id, final_decision, signature).
        payment_processor_webhook: callable(action: str, signed_decision: dict) -> dict.
            The downstream integration point. This repo ships no real
            payment processor, so tests and demos pass a stub; a
            production deployment passes something that actually calls
            one (see docs/PRODUCTION_DEPLOYMENT.md).
        caller: optional sign.caller_auth.CallerIdentity. When given,
            the caller must be permitted to execute this decision's
            final_decision type (see caller_auth.CallerAuthenticator.can_execute),
            or execution is rejected before the webhook is ever called.

        Returns a result dict with at least {"status", "record_id"}.
        status is one of: EXECUTED, ALREADY_EXECUTED, REJECTED.
        Every call, including rejections, is appended to the execution
        log before returning.
        """
        record_id = signed_decision.get("record_id")
        transaction_id = signed_decision.get("transaction_id")
        final_decision = signed_decision.get("final_decision")

        if not record_id:
            result = {
                "status": "REJECTED",
                "reason": "missing_record_id",
                "record_id": None,
                "transaction_id": transaction_id,
            }
            self.log.append(result)
            return result

        # Fail closed: a decision whose signature doesn't verify is
        # never executed, no matter what final_decision claims.
        if not verify.verify_record(dict(signed_decision), self.signer_name):
            result = {
                "status": "REJECTED",
                "reason": "invalid_signature",
                "record_id": record_id,
                "transaction_id": transaction_id,
            }
            self.log.append(result)
            return result

        if caller is not None:
            import caller_auth

            if not caller_auth.AUTHENTICATOR.can_execute(caller, final_decision):
                result = {
                    "status": "REJECTED",
                    "reason": "caller_not_permitted",
                    "record_id": record_id,
                    "transaction_id": transaction_id,
                    "caller_id": caller.caller_id,
                    "final_decision": final_decision,
                }
                self.log.append(result)
                return result

        if self.log.already_executed(record_id):
            result = {
                "status": "ALREADY_EXECUTED",
                "record_id": record_id,
                "transaction_id": transaction_id,
            }
            self.log.append(result)
            return result

        action = ACTION_FOR_DECISION.get(final_decision)
        if action is None:
            result = {
                "status": "REJECTED",
                "reason": f"unknown_final_decision:{final_decision!r}",
                "record_id": record_id,
                "transaction_id": transaction_id,
            }
            self.log.append(result)
            return result

        webhook_response = payment_processor_webhook(action, signed_decision)

        result = {
            "status": "EXECUTED",
            "record_id": record_id,
            "transaction_id": transaction_id,
            "final_decision": final_decision,
            "action": action,
            "caller_id": caller.caller_id if caller is not None else None,
            "webhook_response": webhook_response,
        }
        self.log.append(result)
        return result


def noop_webhook(action: str, signed_decision: dict) -> dict:
    """Reference payment_processor_webhook: does not call anything
    real, just echoes what would have been sent. Used by the demo API
    route (web/server.py's /api/enforce/decisions) and by default in
    tests, so this repo never claims to have moved real money."""
    return {
        "simulated": True,
        "action": action,
        "transaction_id": signed_decision.get("transaction_id"),
    }
