"""Ed25519 sign / verify (``cryptography`` library).

Ed25519 gives 32-byte keys, 64-byte signatures, and is fast.
Every message is signed by the sender so the recipient can verify
it genuinely came from someone holding that private key (authenticity).
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def generate_keypair() -> tuple[bytes, bytes]:
    """Return ``(private_key_bytes, public_key_bytes)``, each 32 bytes."""
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv_bytes, pub_bytes


def sign(payload: bytes, ed25519_priv: bytes) -> bytes:
    """Sign ``payload`` and return a 64-byte signature."""
    priv = Ed25519PrivateKey.from_private_bytes(ed25519_priv)
    return priv.sign(payload)


def verify(payload: bytes, signature: bytes, ed25519_pub: bytes) -> bool:
    """Return ``True`` if ``signature`` is valid for ``payload``, else ``False``."""
    pub = Ed25519PublicKey.from_public_bytes(ed25519_pub)
    try:
        pub.verify(signature, payload)
        return True
    except Exception:
        return False
