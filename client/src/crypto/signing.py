"""Ed25519 sign / verify (``cryptography``).

PLANNED. The signature covers the full payload including the sequence
number; recipients verify before any decryption (README step 7 / step 10).
"""

from __future__ import annotations


def generate_keypair() -> tuple[bytes, bytes]:
    """Return ``(private_key, public_key)`` raw bytes."""
    raise NotImplementedError("Ed25519 key generation not yet implemented")


def sign(payload: bytes, ed25519_priv: bytes) -> bytes:
    raise NotImplementedError("Ed25519 signing not yet implemented")


def verify(payload: bytes, signature: bytes, ed25519_pub: bytes) -> bool:
    raise NotImplementedError("Ed25519 verification not yet implemented")
