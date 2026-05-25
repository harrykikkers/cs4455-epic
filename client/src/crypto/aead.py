"""AES-256-GCM authenticated encryption (``cryptography``).

PLANNED. The AAD binds a per-recipient monotonic sequence number into the
GCM tag for replay protection (README step 6). The nonce is random — each
derived key is used exactly once.
"""

from __future__ import annotations


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Return ``(nonce, ciphertext)`` (ciphertext includes the GCM tag)."""
    raise NotImplementedError("AES-256-GCM encryption not yet implemented")


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Return the plaintext, raising on tag/AAD mismatch."""
    raise NotImplementedError("AES-256-GCM decryption not yet implemented")
