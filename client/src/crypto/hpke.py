"""HPKE Mode_Base seal / open — DHKEM(X25519, HKDF-SHA256), RFC 9180.

PLANNED — wraps ``pyhpke``. See README *Cryptographic Protocol* steps 3-4
(sender: ephemeral keygen + encapsulate) and step 10 (recipient:
decapsulate).
"""

from __future__ import annotations


def encapsulate(recipient_x25519_pub: bytes) -> tuple[bytes, bytes]:
    """Generate a fresh ephemeral keypair and encapsulate to the recipient.

    Returns ``(enc, shared_secret)`` where ``enc`` is the encapsulated key
    transmitted alongside the ciphertext. The ephemeral private key must be
    erased immediately after use (forward secrecy).
    """
    raise NotImplementedError("HPKE encapsulation not yet implemented")


def decapsulate(enc: bytes, recipient_x25519_priv: bytes) -> bytes:
    """Recover the shared secret from an encapsulated key."""
    raise NotImplementedError("HPKE decapsulation not yet implemented")
