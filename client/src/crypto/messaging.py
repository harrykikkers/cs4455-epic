"""Message-layer cryptographic protocol — static ECDH + HKDF + AES-256-GCM + Ed25519.

Implements the Alice→Bob pipeline (README *Cryptographic Protocol*, steps 3–8):

  3. Static ECDH:   dh_out = X25519(sender_x25519_sk, recipient_x25519_pk)
  4. HKDF-Expand:   key = HKDF(dh_out, info="zebra-msg-v1")  → 32-byte AES key
  5. AES-256-GCM:   fresh 12-byte nonce; AAD = sender_id ‖ recipient_id ‖ seq_no
  6. Ed25519 sign:  over sender_id ‖ recipient_id ‖ seq_no ‖ ciphertext ‖ nonce
  7. keccak256(plaintext) digest for on-chain anchoring

On receive (step 8) the four checks run IN ORDER: signature → replay → ECDH/HKDF
→ AEAD decrypt. Plaintext is returned only after all four pass.

The message key is *static* per (sender, recipient) pair — the same key encrypts
every Alice→Bob message. AES-GCM stays secure under this key reuse only because
each message draws a random 96-bit nonce from the OS CSPRNG (see crypto.aead):
the nonce is not "used once" in a counter sense, but the 96-bit space is large
enough that a collision is improbable over a pair's realistic message volume.
A repeated (key, nonce) pair would be catastrophic.

There is deliberately no per-message public key on the wire: the recipient already
holds the sender's pinned X25519 key (TOFU), so static ECDH needs nothing extra.
"""

from __future__ import annotations

import base64
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)

from crypto.aead import decrypt as aead_decrypt, encrypt as aead_encrypt
from crypto.digest import keccak256_hex
from crypto.kdf import derive_message_key
from crypto.signing import sign as ed_sign, verify as ed_verify

# Domain-separated HKDF info for the message key (step 4). Distinct from the
# keystore KEK info ("local-key-encrypt-v1") and the auth info ("server-auth-v1")
# so the same key material can never collide across purposes.
_MSG_INFO = b"zebra-msg-v1"


class SignatureError(Exception):
    """Ed25519 signature did not verify against the sender's pinned key."""


class ReplayError(Exception):
    """seq_no was not strictly greater than the last-seen counter for this sender."""


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def message_key(my_x_priv: bytes, peer_x_pub: bytes) -> bytes:
    """Static ECDH + HKDF-Expand → 32-byte AES-256-GCM key (steps 3–4).

    Symmetric by construction: X25519(a_sk, b_pk) == X25519(b_sk, a_pk), so the
    sender and recipient derive an identical key from their long-term keys alone.
    """
    priv = X25519PrivateKey.from_private_bytes(my_x_priv)
    pub = X25519PublicKey.from_public_bytes(peer_x_pub)
    dh_out = priv.exchange(pub)
    return derive_message_key(dh_out, _MSG_INFO)


def build_aad(sender_id: str, recipient_id: str, seq_no: int) -> bytes:
    """AAD bound into the GCM tag (step 5): sender_id ‖ recipient_id ‖ seq_no.

    Tampering with sender, recipient, or sequence number is detected on decrypt
    because the tag covers these bytes. '|' is an unambiguous delimiter — UUIDs
    and decimal integers never contain it.
    """
    return f"{sender_id}|{recipient_id}|{seq_no}".encode("utf-8")


def signed_payload(sender_id: str, recipient_id: str, seq_no: int,
                   ciphertext: bytes, nonce: bytes) -> bytes:
    """Bytes the sender signs (step 6): metadata ‖ ciphertext ‖ nonce.

    The verifier rebuilds this verbatim from the same fields and never parses it,
    so raw ciphertext/nonce bytes that happen to contain the delimiter are
    harmless — the comparison is over the whole signature, not split fields.
    """
    return (
        f"{sender_id}|{recipient_id}|{seq_no}|".encode("utf-8")
        + ciphertext
        + b"|"
        + nonce
    )


def seal(*, plaintext: str, sender_id: str, recipient_id: str, seq_no: int,
         my_x_priv: bytes, my_ed_priv: bytes, peer_x_pub: bytes) -> dict:
    """Encrypt + sign a message for transmission (steps 3–7).

    Returns the JSON-ready field dict for ``MessageAPI.send`` — every binary
    field base64-encoded, ``seqNo`` an int, ``digest`` 0x-hex. No public key is
    included: static ECDH derives the key from the recipient's pinned X25519 key.
    """
    plaintext_bytes = plaintext.encode("utf-8")
    key = message_key(my_x_priv, peer_x_pub)
    aad = build_aad(sender_id, recipient_id, seq_no)
    nonce, ciphertext = aead_encrypt(key, plaintext_bytes, aad)
    signature = ed_sign(
        signed_payload(sender_id, recipient_id, seq_no, ciphertext, nonce),
        my_ed_priv,
    )
    return {
        "ciphertext": _b64e(ciphertext),
        "nonce": _b64e(nonce),
        "signature": _b64e(signature),
        "seqNo": seq_no,
        "digest": keccak256_hex(plaintext_bytes),
    }


def open_message(*, fields: dict, sender_id: str, recipient_id: str,
                 my_x_priv: bytes, peer_x_pub: bytes, peer_ed_pub: bytes,
                 last_seq: Optional[int],
                 enforce_replay: bool = True) -> tuple[str, int]:
    """Verify, replay-check, and decrypt a received message (step 8).

    Four checks, IN ORDER:
      1. Ed25519 signature against the sender's pinned public key.
      2. seq_no strictly greater than ``last_seq`` (None = first message, accept).
      3. static ECDH + HKDF to recover the message key.
      4. AES-256-GCM decrypt with the reconstructed AAD (raises InvalidTag on tamper).

    Returns ``(plaintext, seq_no)``. Raises :class:`SignatureError`,
    :class:`ReplayError`, or ``cryptography.exceptions.InvalidTag``. The plaintext
    is produced only if every check passes.

    ``enforce_replay`` gates check (2). It must stay ``True`` when *accepting* a
    new message. Pass ``False`` only to re-decrypt a message we already accepted
    (its seq_no is already recorded) purely for re-display — e.g. when the local
    plaintext cache was lost. Signature + AEAD integrity are still enforced, so
    this never weakens authenticity; it only skips the monotonic-ordering gate
    that exists to reject *new* duplicates, not to forbid re-reading old ones.
    """
    ciphertext = _b64d(fields["ciphertext"])
    nonce = _b64d(fields["nonce"])
    signature = _b64d(fields["signature"])
    seq_no = int(fields["seqNo"])

    # (1) authenticity — verify before touching the ciphertext at all
    payload = signed_payload(sender_id, recipient_id, seq_no, ciphertext, nonce)
    if not ed_verify(payload, signature, peer_ed_pub):
        raise SignatureError("Ed25519 signature verification failed")

    # (2) replay / ordering — strictly greater than the last accepted seq_no
    if enforce_replay and last_seq is not None and seq_no <= last_seq:
        raise ReplayError(f"seq_no {seq_no} is not greater than last-seen {last_seq}")

    # (3) static ECDH + HKDF → message key
    key = message_key(my_x_priv, peer_x_pub)

    # (4) AEAD decrypt with the reconstructed AAD
    aad = build_aad(sender_id, recipient_id, seq_no)
    plaintext = aead_decrypt(key, nonce, ciphertext, aad)
    return plaintext.decode("utf-8"), seq_no
