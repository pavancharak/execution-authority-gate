"""
Caller authentication and permission scoping.

EAG-AUDIT-GAPS.md section 4 found no caller authentication anywhere in
this repo: every signed decision's `signer` field is hardcoded to
"authority", and there is no concept of who (which system, which
person) asked for a decision, or what they're allowed to do with it.

This module fixes that with a small token, with no dependencies, that
works like a JWT: a caller identity (caller_id, scoped permissions,
rate limit, expiry) is signed with HMAC SHA256 using a secret held
only by this authority.
Anyone holding a valid token can prove which caller they are; nobody
can mint a token for a caller they aren't, or grant themselves a
permission they weren't issued.

This is deliberately NOT the same trust boundary as sign/src/authority_signer.py's
Ed25519 keys, which sign the *content* of a decision so anyone with the
public key can verify it was untampered. Caller tokens answer a
different question: "is this caller who they claim to be, and what are
they allowed to do with a decision, once it exists." Mixing the two
would let a caller's own key double as the key that signs decisions,
which is exactly the kind of self authorization EAG-AUDIT-GAPS.md section 4
flags as absent (a caller should never be able to also be the
authority).
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent  # sign/
KEYS_DIR = ROOT / "tokens" / "keys"
KEYS_DIR.mkdir(parents=True, exist_ok=True)
SECRET_PATH = KEYS_DIR / "caller_auth_secret.key"

DEFAULT_TTL_SECONDS = 3600

# Decision types a caller may be granted permission to execute. "READ" is
# not a decision type but a standing permission to read/list decisions
# without executing any of them.
DECISION_TYPES = ("ALLOW", "FLAG", "BLOCK")


@dataclass
class CallerIdentity:
    caller_id: str
    permissions: list
    rate_limit: int
    expires_at: float
    issued_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "caller_id": self.caller_id,
            "permissions": list(self.permissions),
            "rate_limit": self.rate_limit,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


# Predefined callers and what they're allowed to execute. A caller not
# listed here cannot be issued a token at all (see
# CallerAuthenticator.create_token). "READ" grants read only access to
# the decisions and audit trail but never lets a caller execute anything.
PREDEFINED_CALLERS = {
    "payment-processor": {
        "permissions": ["ALLOW", "FLAG"],  # cannot execute BLOCK: a payment
        # processor settles or steps up; it does not get to unilaterally
        # deny a transaction the authority didn't already deny.
        "rate_limit": 1000,
    },
    "fraud-analyst": {
        "permissions": ["ALLOW", "FLAG", "BLOCK"],  # full execution access,
        # a human with review authority over all three outcomes.
        "rate_limit": 200,
    },
    "audit-system": {
        "permissions": ["READ"],  # read only: can list or inspect decisions,
        # can never execute one.
        "rate_limit": 5000,
    },
}


def _load_or_create_secret() -> bytes:
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    import secrets

    key = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(key)
    return key


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class CallerAuthenticator:
    """Issues and verifies caller tokens signed with HMAC. The secret never
    leaves this class (or the file it's persisted to); a token proves
    only that whoever produced it had access to that secret at issuance
    time, i.e. this authenticator, or another instance pointed at the
    same secret file."""

    def __init__(self, secret: Optional[bytes] = None, registry: Optional[dict] = None):
        self._secret = secret if secret is not None else _load_or_create_secret()
        self._registry = dict(registry) if registry is not None else dict(PREDEFINED_CALLERS)

    def register_caller(self, caller_id: str, permissions: list, rate_limit: int = 100):
        """Register a caller beyond the predefined list. Kept separate
        from PREDEFINED_CALLERS so tests and future dynamic registration
        don't mutate shared module state."""
        self._registry[caller_id] = {"permissions": list(permissions), "rate_limit": rate_limit}

    def _sign(self, payload_b64: str) -> str:
        digest = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
        return digest

    def create_token(self, caller_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
        """Issue a signed token for a known caller. Raises KeyError for
        any caller_id not in the registry: this authenticator will not
        mint a token for an identity it doesn't recognize."""
        if caller_id not in self._registry:
            raise KeyError(f"unknown caller_id: {caller_id!r}")

        entry = self._registry[caller_id]
        now = time.time()
        payload = {
            "caller_id": caller_id,
            "permissions": entry["permissions"],
            "rate_limit": entry["rate_limit"],
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        }
        payload_b64 = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = self._sign(payload_b64)
        return f"{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Optional[CallerIdentity]:
        """Return a CallerIdentity if the token's signature is valid and
        it has not expired, else None. Never raises on malformed input;
        an untrusted string supplied by the caller should never crash
        the verifier."""
        if not token or "." not in token:
            return None
        payload_b64, _, signature = token.rpartition(".")
        if not payload_b64 or not signature:
            return None

        expected = self._sign(payload_b64)
        if not hmac.compare_digest(expected, signature):
            return None

        try:
            payload = json.loads(_b64decode(payload_b64))
        except (ValueError, UnicodeDecodeError):
            return None

        identity = CallerIdentity(
            caller_id=payload["caller_id"],
            permissions=payload["permissions"],
            rate_limit=payload["rate_limit"],
            expires_at=payload["expires_at"],
            issued_at=payload["issued_at"],
        )
        if identity.is_expired():
            return None
        return identity

    def can_execute(self, caller: CallerIdentity, decision_type: str) -> bool:
        """Whether this caller may execute a decision of this type
        (ALLOW/FLAG/BLOCK). A caller with only READ permission can never
        execute anything, regardless of decision_type."""
        if caller is None or caller.is_expired():
            return False
        return decision_type in caller.permissions


# Module level authenticator shared by the pipeline and web layers, the
# same pattern authority_signer.py uses for AUTHORITY/REVIEWER.
AUTHENTICATOR = CallerAuthenticator()
