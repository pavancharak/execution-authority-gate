"""
External Authority. Signs decisions and authorization tokens.

This module simulates an authority that lives OUTSIDE the fraud agents and
OUTSIDE the fraud detector. Neither the agents nor the detector hold the
private keys used here. They can only ask this module to sign something;
they cannot forge a signature themselves, and anyone (including a judge)
can verify a signature later using only the matching public key file in
tokens/ (see signature_verifier.py).

Two independent keypairs are used on purpose, to keep two different kinds
of authority separable:

  - AUTHORITY key: issues agent authorization tokens, and signs the
    detector's block/flag/allow decisions.
  - REVIEWER key: signs human override decisions. A different key means an
    override can never be mistaken for (or forged as) an authority
    decision, and vice versa.
"""

import json
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
TOKENS_DIR = ROOT / "tokens"
KEYS_DIR = TOKENS_DIR / "keys"
KEYS_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_DIR.mkdir(parents=True, exist_ok=True)


def _canonical(obj: dict) -> bytes:
    """Deterministic byte encoding so signing/verification agree exactly."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_or_create_keypair(name: str):
    priv_path = KEYS_DIR / f"{name}_private.pem"
    pub_path = TOKENS_DIR / f"{name}_public_key.pem"

    if priv_path.exists():
        private_key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        private_key = Ed25519PrivateKey.generate()
        priv_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        public_key = private_key.public_key()
        pub_path.write_bytes(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    if not pub_path.exists():
        public_key = private_key.public_key()
        pub_path.write_bytes(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    return private_key


class Signer:
    """A single external authority identity (its own keypair)."""

    def __init__(self, name: str):
        self.name = name
        self._private_key = _load_or_create_keypair(name)

    def sign_record(self, payload: dict) -> dict:
        """Return payload plus signature, as an envelope. Payload is untouched
        (all fields the judge cares about are visible in plaintext); the
        signature only proves *this signer* produced it and it wasn't
        altered afterward."""
        body = dict(payload)
        body.setdefault("record_id", str(uuid.uuid4()))
        body.setdefault("signed_at", time.time())
        body["signer"] = self.name
        signature = self._private_key.sign(_canonical(body))
        return {**body, "signature": signature.hex()}


# The two authority identities used throughout this project.
AUTHORITY = Signer("authority")
REVIEWER = Signer("reviewer")


def issue_agent_token(agent_id: str, action: str, max_operations: int, ttl_seconds: int = 3600) -> dict:
    """AUTHORITY issues a signed, bounded permission token to an agent.
    The agent cannot raise max_operations after the fact. Any attempt to
    claim a higher number is directly contradicted by this signed file."""
    now = time.time()
    token = AUTHORITY.sign_record(
        {
            "token_type": "agent_authorization",
            "agent_id": agent_id,
            "action": action,
            "max_operations": max_operations,
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        }
    )
    path = TOKENS_DIR / f"{agent_id}_auth_token.json"
    path.write_text(json.dumps(token, indent=2))
    return token


def sign_block_decision(transaction_id: str, score: float, decision: str, reasons: list) -> dict:
    """AUTHORITY signs the detector's block/flag/allow decision. The
    detector proposes; only the authority's signature makes it official."""
    return AUTHORITY.sign_record(
        {
            "record_type": "block_decision",
            "transaction_id": transaction_id,
            "fraud_score": round(float(score), 4),
            "decision": decision,
            "reasons": reasons,
        }
    )


def sign_override(transaction_id: str, original_decision: str, new_decision: str, reviewer_name: str, justification: str) -> dict:
    """REVIEWER (a human, not the detector) signs an override. Uses a
    DIFFERENT key than AUTHORITY, so an override can never be confused
    with, or forged as, an authority block decision."""
    return REVIEWER.sign_record(
        {
            "record_type": "override",
            "transaction_id": transaction_id,
            "original_decision": original_decision,
            "new_decision": new_decision,
            "reviewer_name": reviewer_name,
            "justification": justification,
        }
    )


def sign_pipeline_decision(
    transaction_id: str,
    fraud_score: float,
    detect_decision: str,
    mandate_allowed: bool,
    violated_mandate_rules: list,
    final_decision: str,
    reasons: list,
    caller_id: str = None,
    policy_id: str = None,
    policy_version: str = None,
    matched_rule_id: str = None,
) -> dict:
    """AUTHORITY signs the pipeline's combined decision: detect layer
    score/decision AND mandate layer result, folded into one final
    decision. Neither the detector nor the mandate checker can make a
    decision final on their own; only this signature does.

    caller_id identifies which system or person requested this decision
    be evaluated (see sign/src/caller_auth.py). It is optional and
    defaults to None for backward compatibility with callers that don't
    pass one; when present it is embedded INSIDE the signed envelope
    (not a sibling field), so it is just as tamper evident as
    final_decision itself, an attacker cannot silently reattribute a
    decision to a different caller after signing.

    policy_id/policy_version/matched_rule_id identify which policy
    document (see policy/src/policy_engine.py) and which of its rules
    produced final_decision. Optional and default to None for the same
    backward compatibility reason as caller_id; when present they are
    embedded inside the signed envelope, so a decision can't be silently
    reattributed to a different policy after the fact either."""
    return AUTHORITY.sign_record(
        {
            "record_type": "pipeline_decision",
            "transaction_id": transaction_id,
            "fraud_score": round(float(fraud_score), 4),
            "detect_decision": detect_decision,
            "mandate_allowed": mandate_allowed,
            "violated_mandate_rules": violated_mandate_rules,
            "final_decision": final_decision,
            "reasons": reasons,
            "caller_id": caller_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "matched_rule_id": matched_rule_id,
        }
    )
