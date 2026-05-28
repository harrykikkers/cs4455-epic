"""Tests for HPKE encapsulation / decapsulation (crypto/hpke.py).

Security properties verified:
- Sender and recipient derive the same shared secret
- Wrong private key gives a different (useless) shared secret
- Each encapsulate() call produces a fresh enc (ephemeral keypair)
- Shared secret is 32 bytes
- enc is non-empty bytes
"""
import pytest
from crypto.hpke import encapsulate, decapsulate


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_shared_secret_roundtrip(x25519_keypair):
    priv, pub = x25519_keypair
    enc, secret_sender = encapsulate(pub)
    secret_recipient = decapsulate(enc, priv)
    assert secret_sender == secret_recipient


def test_roundtrip_produces_32_byte_secret(x25519_keypair):
    priv, pub = x25519_keypair
    enc, secret = encapsulate(pub)
    assert len(secret) == 32
    assert len(decapsulate(enc, priv)) == 32


# ---------------------------------------------------------------------------
# Ephemeral keypair — enc must be fresh each call
# ---------------------------------------------------------------------------

def test_enc_is_unique_per_call(x25519_keypair):
    _, pub = x25519_keypair
    enc_values = {encapsulate(pub)[0] for _ in range(10)}
    assert len(enc_values) == 10


def test_enc_is_bytes(x25519_keypair):
    _, pub = x25519_keypair
    enc, secret = encapsulate(pub)
    assert isinstance(enc, bytes) and len(enc) > 0
    assert isinstance(secret, bytes)


# ---------------------------------------------------------------------------
# Wrong private key → different secret (not the same as sender's)
# ---------------------------------------------------------------------------

def test_wrong_private_key_gives_different_secret(x25519_keypair, x25519_keypair_b):
    _, pub = x25519_keypair
    priv_b, _ = x25519_keypair_b  # completely unrelated key
    enc, secret_sender = encapsulate(pub)
    secret_wrong = decapsulate(enc, priv_b)
    assert secret_wrong != secret_sender


# ---------------------------------------------------------------------------
# Two independent sends produce independent secrets
# ---------------------------------------------------------------------------

def test_two_sends_independent_secrets(x25519_keypair):
    priv, pub = x25519_keypair
    enc1, secret1 = encapsulate(pub)
    enc2, secret2 = encapsulate(pub)
    assert secret1 != secret2  # ephemeral → different shared secret each time
