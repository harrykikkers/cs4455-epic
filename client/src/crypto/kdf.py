"""Key derivation — HKDF-SHA256 + Argon2id (``cryptography`` / ``argon2-cffi``).

PLANNED. Two distinct derivations:

* ``derive_message_key`` — HKDF-Expand over the HPKE shared secret with a
  domain-separated ``info`` string (README step 5).
* ``derive_kek`` — Argon2id over the user's password to produce the local
  key-encryption key for the keystore (README *Key Storage at Rest*). This
  is separate from the server-side password hash.
"""

from __future__ import annotations


def derive_message_key(shared_secret: bytes, info: bytes, length: int = 32) -> bytes:
    raise NotImplementedError("HKDF message-key derivation not yet implemented")


def derive_kek(password: str, salt: bytes, *, length: int = 32) -> bytes:
    raise NotImplementedError("Argon2id KEK derivation not yet implemented")
