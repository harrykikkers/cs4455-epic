"""Tests for Ed25519 sign / verify (crypto/signing.py).

Security properties verified:
- generate_keypair returns correct raw byte lengths (32 bytes each)
- sign → verify round-trip passes
- Tampered payload, tampered signature, and wrong public key all fail
- Two different keypairs produce independently valid sign/verify pairs
"""
import os
import pytest
from crypto.signing import generate_keypair, sign, verify


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def test_keypair_lengths():
    priv, pub = generate_keypair()
    assert len(priv) == 32
    assert len(pub) == 32


def test_keypairs_are_unique():
    pairs = [generate_keypair() for _ in range(5)]
    privs = [p for p, _ in pairs]
    pubs = [q for _, q in pairs]
    assert len(set(privs)) == 5
    assert len(set(pubs)) == 5


# ---------------------------------------------------------------------------
# Sign / verify round-trip
# ---------------------------------------------------------------------------

def test_sign_verify_roundtrip():
    priv, pub = generate_keypair()
    payload = b"sender-id|recipient-id|seq=0|ciphertext"
    sig = sign(payload, priv)
    assert verify(payload, sig, pub) is True


def test_signature_is_64_bytes():
    priv, _ = generate_keypair()
    sig = sign(b"payload", priv)
    assert len(sig) == 64


def test_sign_empty_payload():
    priv, pub = generate_keypair()
    sig = sign(b"", priv)
    assert verify(b"", sig, pub) is True


def test_sign_large_payload():
    priv, pub = generate_keypair()
    payload = os.urandom(10_000)
    sig = sign(payload, priv)
    assert verify(payload, sig, pub) is True


# ---------------------------------------------------------------------------
# Tamper detection — payload
# ---------------------------------------------------------------------------

def test_tampered_payload_fails():
    priv, pub = generate_keypair()
    payload = b"original message"
    sig = sign(payload, priv)
    assert verify(b"modified message", sig, pub) is False


def test_extra_byte_in_payload_fails():
    priv, pub = generate_keypair()
    payload = b"message"
    sig = sign(payload, priv)
    assert verify(payload + b"\x00", sig, pub) is False


# ---------------------------------------------------------------------------
# Tamper detection — signature
# ---------------------------------------------------------------------------

def test_tampered_signature_fails():
    priv, pub = generate_keypair()
    payload = b"message"
    sig = sign(payload, priv)
    bad_sig = bytes([sig[0] ^ 0xFF]) + sig[1:]
    assert verify(payload, bad_sig, pub) is False


def test_truncated_signature_raises_or_fails():
    priv, pub = generate_keypair()
    sig = sign(b"message", priv)
    result = None
    try:
        result = verify(b"message", sig[:-1], pub)
    except Exception:
        pass
    # Either raises or returns False — must not return True
    assert result is not True


# ---------------------------------------------------------------------------
# Wrong key
# ---------------------------------------------------------------------------

def test_wrong_public_key_fails():
    priv, _ = generate_keypair()
    _, unrelated_pub = generate_keypair()
    payload = b"message"
    sig = sign(payload, priv)
    assert verify(payload, sig, unrelated_pub) is False


def test_two_keypairs_independent():
    priv_a, pub_a = generate_keypair()
    priv_b, pub_b = generate_keypair()
    payload = b"message"
    sig_a = sign(payload, priv_a)
    sig_b = sign(payload, priv_b)
    assert verify(payload, sig_a, pub_a) is True
    assert verify(payload, sig_b, pub_b) is True
    assert verify(payload, sig_a, pub_b) is False
    assert verify(payload, sig_b, pub_a) is False
