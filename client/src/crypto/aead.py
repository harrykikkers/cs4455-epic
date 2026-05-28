"""AES-256-GCM authenticated encryption (``cryptography`` library).

AES-256-GCM is an AEAD scheme: it encrypts AND authenticates in one step.
Any tampering with the ciphertext, nonce, or AAD causes decryption to raise
— the server cannot modify the message without the recipient detecting it.

Nonce: 12 bytes, generated fresh from the OS CSPRNG for every encrypt call.
Key:   exactly 32 bytes (256 bits).
AAD:   additional authenticated data — bound into the tag but not encrypted
       (used to authenticate metadata like sequence numbers).
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Encrypt and authenticate ``plaintext``.

    Returns ``(nonce, ciphertext)`` where ciphertext includes the 16-byte
    GCM authentication tag appended by the library.
    """
    if len(key) != 32:
        raise ValueError(f"Key must be 32 bytes, got {len(key)}")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Decrypt and verify.  Raises ``InvalidTag`` if anything was tampered with."""
    if len(key) != 32:
        raise ValueError(f"Key must be 32 bytes, got {len(key)}")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)
