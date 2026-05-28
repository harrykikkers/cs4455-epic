"""Unit tests for crypto.kdf — HKDF-Expand message keys + Argon2id KEK."""

import os

import pytest

from crypto.kdf import (
    _auth_salt,
    derive_auth_hash,
    derive_kek,
    derive_message_key,
)


# --- derive_kek (Argon2id -> HKDF-Expand) --------------------------------


def test_derive_kek_is_deterministic():
    salt = os.urandom(16)
    assert derive_kek("hunter2", salt) == derive_kek("hunter2", salt)


def test_derive_kek_returns_32_bytes_by_default():
    kek = derive_kek("hunter2", os.urandom(16))
    assert isinstance(kek, bytes)
    assert len(kek) == 32


def test_derive_kek_respects_length_argument():
    assert len(derive_kek("pw", os.urandom(16), length=64)) == 64


def test_derive_kek_differs_with_salt():
    assert derive_kek("pw", os.urandom(16)) != derive_kek("pw", os.urandom(16))


def test_derive_kek_differs_with_password():
    salt = os.urandom(16)
    assert derive_kek("password-a", salt) != derive_kek("password-b", salt)


# --- derive_message_key (HKDF-Expand) ------------------------------------


def test_derive_message_key_is_deterministic():
    secret = os.urandom(32)
    assert derive_message_key(secret, b"info") == derive_message_key(secret, b"info")


def test_derive_message_key_returns_requested_length():
    key = derive_message_key(os.urandom(32), b"info")
    assert isinstance(key, bytes)
    assert len(key) == 32
    assert len(derive_message_key(os.urandom(32), b"info", length=16)) == 16


def test_derive_message_key_is_domain_separated_by_info():
    secret = os.urandom(32)
    assert derive_message_key(secret, b"info-a") != derive_message_key(secret, b"info-b")


def test_derive_message_key_differs_with_secret():
    assert derive_message_key(os.urandom(32), b"info") != derive_message_key(
        os.urandom(32), b"info"
    )


# --- derive_auth_hash (client-side auth pre-hash) ------------------------


def test_derive_auth_hash_is_deterministic():
    assert derive_auth_hash("hunter2", "alice") == derive_auth_hash("hunter2", "alice")


def test_derive_auth_hash_returns_hex_string():
    h = derive_auth_hash("hunter2", "alice")
    assert isinstance(h, str)
    assert len(h) == 64  # 32 bytes hex-encoded
    bytes.fromhex(h)  # must be valid hex


def test_derive_auth_hash_respects_length_argument():
    assert len(derive_auth_hash("pw", "alice", length=16)) == 32  # 16 bytes -> 32 hex


def test_derive_auth_hash_differs_with_password():
    assert derive_auth_hash("password-a", "alice") != derive_auth_hash(
        "password-b", "alice"
    )


def test_derive_auth_hash_differs_with_username():
    assert derive_auth_hash("pw", "alice") != derive_auth_hash("pw", "bob")


def test_derive_auth_hash_username_is_normalised():
    # Salt is strip+lowercase on the username so login is robust to casing.
    assert derive_auth_hash("pw", "Alice") == derive_auth_hash("pw", " alice ")


def test_derive_auth_hash_domain_separated_from_kek():
    # Even given the identical Argon2id input (same password + salt), the auth
    # hash must differ from the KEK so the value sent to the server can never
    # coincide with the local key-encryption key.
    salt = _auth_salt("alice")
    auth = bytes.fromhex(derive_auth_hash("pw", "alice"))
    assert auth != derive_kek("pw", salt)
