"""
Durable, append-only decision log.

pipeline/src/decision_log.py writes pipeline_decisions.json as a single
JSON array via a full path.write_text() on every run, so a second
pipeline run silently replaces whatever the first one wrote, and the
file is git ignored (see EAG-AUDIT-GAPS.md, section 1). This module
exists to fix that: every decision is appended as one line of a JSONL
file, never rewritten, and the file lives at a path that CAN be
committed to git (the whole point of durability is that history
survives independent of any one environment).

decision_log.write_log() is left in place and still called by
run_pipeline.py for backward compatibility; this module is the
new, primary durability guarantee.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # pipeline/
AUDIT_DIR = ROOT / "audit"
AUDIT_PATH = AUDIT_DIR / "decisions.jsonl"


class AuditTrail:
    """Append-only JSONL decision log.

    Idempotency is keyed on the signed decision's `record_id` (assigned
    once, at signing time, by authority_signer.Signer.sign_record). The
    same record_id is never appended twice, so replaying a batch, or
    re-running a step that already wrote its result, cannot duplicate
    an entry.
    """

    def __init__(self, path: Path = AUDIT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _record_id(self, entry: dict) -> str:
        decision = entry.get("decision", entry)
        record_id = decision.get("record_id")
        if not record_id:
            raise ValueError("entry has no decision.record_id; cannot be appended to the audit trail")
        return record_id

    def known_ids(self) -> set:
        ids = set()
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                decision = row.get("decision", row)
                rid = decision.get("record_id")
                if rid:
                    ids.add(rid)
        return ids

    def append_decision(self, entry: dict) -> bool:
        """Append one signed decision entry (the same shape run_pipeline.py
        builds: {"decision": {...signed...}, "mandate_checks": [...],
        "ground_truth": {...}}). Returns True if it was newly appended,
        False if this record_id was already present (idempotent no-op)."""
        record_id = self._record_id(entry)
        if record_id in self.known_ids():
            return False
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return True

    def append_many(self, entries) -> int:
        """Append a batch, skipping any already-known record_id. Returns
        the count of entries actually appended."""
        existing = self.known_ids()
        appended = 0
        with self.path.open("a", encoding="utf-8") as f:
            for entry in entries:
                record_id = self._record_id(entry)
                if record_id in existing:
                    continue
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                existing.add(record_id)
                appended += 1
        return appended

    def get_decision(self, record_id: str):
        """Return the entry with this record_id, or None. The trail is
        append-only, so the LAST matching line wins (there should only
        ever be one, given append_decision's idempotency, but a reader
        should not assume a hand-edited file preserves that)."""
        found = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                decision = row.get("decision", row)
                if decision.get("record_id") == record_id:
                    found = row
        return found

    def read_all(self):
        entries = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def verify_all(self, signer_name: str = "authority"):
        """Walk the entire trail and verify every signature independently,
        using only the public key on disk (see sign/src/signature_verifier.py).
        Returns {"total": N, "verified": N, "all_verified": bool,
        "failed_record_ids": [...]}."""
        import sys

        sign_src = ROOT.parent / "sign" / "src"
        if str(sign_src) not in sys.path:
            sys.path.insert(0, str(sign_src))
        import signature_verifier as verify

        entries = self.read_all()
        failed = []
        verified = 0
        for entry in entries:
            decision = entry.get("decision", entry)
            if verify.verify_record(dict(decision), signer_name):
                verified += 1
            else:
                failed.append(decision.get("record_id"))

        return {
            "total": len(entries),
            "verified": verified,
            "all_verified": verified == len(entries),
            "failed_record_ids": failed,
        }
