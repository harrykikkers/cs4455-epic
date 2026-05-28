"""DHKEM(X25519) key encapsulation — sender encrypts a shared secret to a recipient.

This is the key establishment layer (RFC 9180 §4, DHKEM).  The full
HPKE Mode_Auth sender-authentication is provided at the message layer via
an Ed25519 signature over the ciphertext (see signing.py).

How it works:
  Sender:
    1. Generate a fresh ephemeral X25519 keypair.
    2. Perform ECDH: ephemeral_priv × recipient_pub → raw DH output.
    3. Derive the shared secret via HKDF so the output is uniformly random.
    4. Send ``enc`` (the ephemeral public key) alongside the ciphertext.

  Recipient:
    1. Perform ECDH: recipient_priv × enc (ephemeral pub) → same DH output.
    2. Derive the same shared secret via the same HKDF call.

Known limitation: no forward secrecy.  If the recipient's long-term
X25519 private key is ever compromised, all past ciphertexts become
decryptable because the attacker can recompute every DH output from the
stored ``enc`` values.  This is a deliberate design trade-off.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from crypto.kdf import derive_message_key

_INFO = b"zebra-hpke-v1"


def encapsulate(recipient_x25519_pub: bytes) -> tuple[bytes, bytes]:
    """Encapsulate a shared secret to ``recipient_x25519_pub``.

    Returns ``(enc, shared_secret)`` where ``enc`` is the 32-byte ephemeral
    public key to transmit with the message.
    """
    eph_priv = X25519PrivateKey.generate()
    enc = eph_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    rec_pub = X25519PublicKey.from_public_bytes(recipient_x25519_pub)
    dh_out = eph_priv.exchange(rec_pub)

    shared_secret = derive_message_key(dh_out, _INFO)
    return enc, shared_secret


def decapsulate(enc: bytes, recipient_x25519_priv: bytes) -> bytes:
    """Recover the shared secret from ``enc`` using the recipient's private key."""
    eph_pub = X25519PublicKey.from_public_bytes(enc)
    rec_priv = X25519PrivateKey.from_private_bytes(recipient_x25519_priv)
    dh_out = rec_priv.exchange(eph_pub)

    return derive_message_key(dh_out, _INFO)
