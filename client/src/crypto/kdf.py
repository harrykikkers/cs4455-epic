"""Key derivation — HKDF-SHA256 + Argon2id (``cryptography`` / ``argon2-cffi``).

Three derivations, all domain-separated so the same password (or shared
secret) never produces the same bytes for two different purposes:

* ``derive_message_key`` — HKDF-Expand over the static-ECDH shared secret
  (``X25519(my_sk, peer_pk)``) with a domain-separated ``info`` string (README
  step 4). Expand-only with no salt — the X25519 output is already uniform.

* ``derive_kek`` — Argon2id over the user's password to produce the local
  key-encryption key for the keystore (README *Key Storage at Rest*). The KEK
  encrypts the X25519 + Ed25519 private keys at rest and never leaves the
  device.

* ``derive_auth_hash`` — Argon2id over the user's password to produce the
  credential sent to the server for authentication, so the cleartext password
  never leaves the device. The server salts and re-hashes this value with its
  own random salt before storage, so a database leak is not directly
  replayable. It is domain-separated from ``derive_kek`` (different salt and
  ``info``) so the value sent to the server can never coincide with the local
  key-encryption key.
"""

from __future__ import annotations

import hashlib

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand


def _argon2id(password: str, salt: bytes) -> bytes:
    """Argon2id over a password with OWASP-recommended parameters (RFC 9106)."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=2,
        memory_cost=19456,
        parallelism=1,
        hash_len=32,
        type=Type.ID,
    )


def derive_message_key(shared_secret: bytes, info: bytes, length: int = 32) -> bytes:
    """Derive a message key from the static-ECDH shared secret via HKDF-Expand."""
    return HKDFExpand(
        algorithm=hashes.SHA256(),
        length=length,
        info=info,
    ).derive(shared_secret)


def derive_kek(password: str, salt: bytes, *, length: int = 32) -> bytes:
    """Derive the local key-encryption key from the password via Argon2id.

    Runs Argon2id (OWASP-recommended parameters) over the password and feeds
    the raw output into HKDF-Expand for domain separation from any other use
    of the same password material.
    """
    return HKDFExpand(
        algorithm=hashes.SHA256(),
        length=length,
        info=b"local-key-encrypt-v1",
    ).derive(_argon2id(password, salt))


def _auth_salt(username: str) -> bytes:
    """Deterministic per-user salt for the authentication pre-hash.

    Derived from the username rather than randomly, so every login reproduces
    the identical pre-hash. Per-user *random* salting happens server-side,
    where it protects the stored credential; this salt only individualises the
    pre-hash so it is not identical across users who share a password.
    Normalised (strip + lowercase) so the login pre-hash is robust to casing.
    """
    material = b"server-auth-salt-v1|" + username.strip().lower().encode("utf-8")
    return hashlib.sha256(material).digest()[:16]


def derive_auth_hash(password: str, username: str, *, length: int = 32) -> str:
    """Derive the authentication credential the client sends to the server.

    Argon2id over the password with a deterministic per-user salt so the
    cleartext never leaves the device, then HKDF-Expand with a distinct
    ``info`` for domain separation from :func:`derive_kek`. Returned
    hex-encoded for JSON transport; the server salts and hashes this value
    again before storage.
    """
    derived = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=length,
        info=b"server-auth-v1",
    ).derive(_argon2id(password, _auth_salt(username)))
    return derived.hex()
