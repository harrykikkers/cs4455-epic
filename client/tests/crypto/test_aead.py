"""Tests for AES-256-GCM authenticated encryption (crypto/aead.py).

Security properties verified:
- Correct plaintext recovered after encrypt→decrypt
- Wrong key, tampered ciphertext, wrong AAD, wrong nonce all raise
- Nonce is 12 bytes and freshly random on every call
- Key must be exactly 32 bytes
"""
import os
import pytest
from crypto.aead import encrypt, decrypt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flip_bit(data: bytes, index: int = 0) -> bytes:
    return bytes([data[index] ^ 0xFF]) + data[index + 1:]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_roundtrip(aes_key):
    nonce, ct = encrypt(aes_key, b"hello world", b"aad-data")
    assert decrypt(aes_key, nonce, ct, b"aad-data") == b"hello world"


def test_roundtrip_empty_plaintext(aes_key):
    nonce, ct = encrypt(aes_key, b"", b"aad")
    assert decrypt(aes_key, nonce, ct, b"aad") == b""


def test_roundtrip_empty_aad(aes_key):
    nonce, ct = encrypt(aes_key, b"message", b"")
    assert decrypt(aes_key, nonce, ct, b"") == b"message"


def test_roundtrip_long_plaintext(aes_key):
    plaintext = os.urandom(10_000)
    nonce, ct = encrypt(aes_key, plaintext, b"aad")
    assert decrypt(aes_key, nonce, ct, b"aad") == plaintext


# ---------------------------------------------------------------------------
# Nonce properties
# ---------------------------------------------------------------------------

def test_nonce_is_12_bytes(aes_key):
    nonce, _ = encrypt(aes_key, b"msg", b"aad")
    assert len(nonce) == 12


def test_nonces_are_unique_across_calls(aes_key):
    nonces = {encrypt(aes_key, b"msg", b"aad")[0] for _ in range(20)}
    assert len(nonces) == 20  # all 20 nonces must be distinct


# ---------------------------------------------------------------------------
# Tamper detection — wrong key
# ---------------------------------------------------------------------------

def test_wrong_key_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"aad")
    with pytest.raises(Exception):
        decrypt(os.urandom(32), nonce, ct, b"aad")


# ---------------------------------------------------------------------------
# Tamper detection — ciphertext integrity
# ---------------------------------------------------------------------------

def test_tampered_ciphertext_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"aad")
    with pytest.raises(Exception):
        decrypt(aes_key, nonce, _flip_bit(ct), b"aad")


def test_truncated_ciphertext_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"aad")
    with pytest.raises(Exception):
        decrypt(aes_key, nonce, ct[:-1], b"aad")


# ---------------------------------------------------------------------------
# Tamper detection — AAD integrity
# ---------------------------------------------------------------------------

def test_wrong_aad_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"correct-aad")
    with pytest.raises(Exception):
        decrypt(aes_key, nonce, ct, b"wrong-aad")


def test_empty_aad_vs_nonempty_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"aad")
    with pytest.raises(Exception):
        decrypt(aes_key, nonce, ct, b"")


# ---------------------------------------------------------------------------
# Tamper detection — nonce
# ---------------------------------------------------------------------------

def test_wrong_nonce_raises(aes_key):
    nonce, ct = encrypt(aes_key, b"secret", b"aad")
    with pytest.raises(Exception):
        decrypt(aes_key, _flip_bit(nonce), ct, b"aad")


# ---------------------------------------------------------------------------
# Key size enforcement
# ---------------------------------------------------------------------------

def test_key_too_short_raises():
    with pytest.raises(Exception):
        encrypt(b"tooshort", b"msg", b"aad")


def test_key_too_long_raises():
    with pytest.raises(Exception):
        encrypt(os.urandom(64), b"msg", b"aad")
