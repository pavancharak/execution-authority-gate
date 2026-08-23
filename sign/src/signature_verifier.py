"""
Independent signature verification — deliberately separate from
authority_signer.py.

Verification here uses ONLY the public key files on disk (tokens/*.pem).
It never touches a private key, so anything that can import this module
(the pipeline, a test, a judge's own script) can check a signed record's
authenticity without being able to forge one.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from authority_signer import _canonical, TOKENS_DIR


def verify_record(record: dict, signer_name: str) -> bool:
    """Verify a signed record using ONLY the public key file on disk —
    exactly what a judge would do, with no access to any private key."""
    pub_path = TOKENS_DIR / f"{signer_name}_public_key.pem"
    if not pub_path.exists():
        return False
    public_key: Ed25519PublicKey = serialization.load_pem_public_key(pub_path.read_bytes())

    record = dict(record)
    signature_hex = record.pop("signature", None)
    if signature_hex is None:
        return False
    try:
        public_key.verify(bytes.fromhex(signature_hex), _canonical(record))
        return True
    except InvalidSignature:
        return False
