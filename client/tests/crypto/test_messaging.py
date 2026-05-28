"""Tests for the static-ECDH message protocol (crypto/messaging.py).

Security / contract properties verified:
- Round-trip: seal then open recovers the original plaintext and seq_no.
- seal() output shape: exactly {ciphertext, nonce, signature, seqNo, digest},
  no "enc"; base64 strings; nonce base64 length 16; digest is 0x + 64 hex.
- message_key is symmetric across the (sender, recipient) keypair and 32 bytes.
- First message accepted when last_seq is None.
- Replay: last_seq >= seq_no raises ReplayError; one-below is accepted.
- Tampering ciphertext / nonce / signature → SignatureError (signature covers all).
- Metadata/AAD tamper (seqNo, sender_id, recipient_id) → SignatureError.
- Wrong recipient X25519 key → InvalidTag (signature still valid; decrypt fails).
- Wrong sender Ed25519 verify key → SignatureError.
- Check ordering: replay + bad signature raises SignatureError (signature first).
"""
import base64
import re

import pytest
from cryptography.exceptions import InvalidTag

from crypto.messaging import (
    ReplayError,
    SignatureError,
    build_aad,
    message_key,
    open_message,
    seal,
)
from crypto.signing import generate_keypair

SENDER_ID = "alice-id"
RECIPIENT_ID = "bob-id"
PLAINTEXT = "hello bob, this is alice"
DIGEST_RE = re.compile(r"^0x[0-9a-f]{64}$")


def _flip_b64_byte(b64_str, index=0):
    """Decode a base64 field, flip one byte, and re-encode."""
    raw = bytearray(base64.b64decode(b64_str))
    raw[index] ^= 0xFF
    return base64.b64encode(bytes(raw)).decode("ascii")


@pytest.fixture
def ed_keypair():
    """Sender's Ed25519 signing keypair (priv, pub)."""
    return generate_keypair()


@pytest.fixture
def ed_keypair_b():
    """An independent Ed25519 keypair (a wrong/imposter signer)."""
    return generate_keypair()


@pytest.fixture
def sealed(x25519_keypair, x25519_keypair_b, ed_keypair):
    """A sealed message from sender (keypair) to recipient (keypair_b)."""
    sender_x_priv, _ = x25519_keypair
    _, recipient_x_pub = x25519_keypair_b
    ed_priv, _ = ed_keypair
    fields = seal(
        plaintext=PLAINTEXT,
        sender_id=SENDER_ID,
        recipient_id=RECIPIENT_ID,
        seq_no=5,
        my_x_priv=sender_x_priv,
        my_ed_priv=ed_priv,
        peer_x_pub=recipient_x_pub,
    )
    return fields


def _open(fields, x25519_keypair, x25519_keypair_b, ed_keypair, **overrides):
    """Open `fields` from the recipient's side with optional kwarg overrides."""
    sender_x_priv, sender_x_pub = x25519_keypair
    recipient_x_priv, _ = x25519_keypair_b
    _, ed_pub = ed_keypair
    kwargs = dict(
        fields=fields,
        sender_id=SENDER_ID,
        recipient_id=RECIPIENT_ID,
        my_x_priv=recipient_x_priv,
        peer_x_pub=sender_x_pub,
        peer_ed_pub=ed_pub,
        last_seq=None,
    )
    kwargs.update(overrides)
    return open_message(**kwargs)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_round_trip(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    plaintext, seq_no = _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair)
    assert plaintext == PLAINTEXT
    assert seq_no == 5


# ---------------------------------------------------------------------------
# seal() output shape
# ---------------------------------------------------------------------------

def test_seal_has_exactly_five_keys_no_enc(sealed):
    assert set(sealed.keys()) == {"ciphertext", "nonce", "signature", "seqNo", "digest"}
    assert "enc" not in sealed


def test_seal_field_types(sealed):
    assert isinstance(sealed["ciphertext"], str)
    assert isinstance(sealed["nonce"], str)
    assert isinstance(sealed["signature"], str)
    assert isinstance(sealed["seqNo"], int)
    assert sealed["seqNo"] == 5


def test_seal_nonce_base64_length(sealed):
    # 12-byte nonce → 16 base64 characters.
    assert len(sealed["nonce"]) == 16


def test_seal_digest_format(sealed):
    assert DIGEST_RE.match(sealed["digest"])


# ---------------------------------------------------------------------------
# message_key — symmetry and length
# ---------------------------------------------------------------------------

def test_message_key_symmetric(x25519_keypair, x25519_keypair_b):
    a_priv, a_pub = x25519_keypair
    b_priv, b_pub = x25519_keypair_b
    assert message_key(a_priv, b_pub) == message_key(b_priv, a_pub)


def test_message_key_length(x25519_keypair, x25519_keypair_b):
    a_priv, _ = x25519_keypair
    _, b_pub = x25519_keypair_b
    assert len(message_key(a_priv, b_pub)) == 32


# ---------------------------------------------------------------------------
# Replay / ordering
# ---------------------------------------------------------------------------

def test_first_message_accepted_with_none(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    plaintext, seq_no = _open(
        sealed, x25519_keypair, x25519_keypair_b, ed_keypair, last_seq=None
    )
    assert plaintext == PLAINTEXT
    assert seq_no == 5


def test_replay_equal_seq_raises(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    with pytest.raises(ReplayError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair, last_seq=5)


def test_replay_higher_last_seq_raises(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    with pytest.raises(ReplayError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair, last_seq=6)


def test_one_below_seq_accepted(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    plaintext, seq_no = _open(
        sealed, x25519_keypair, x25519_keypair_b, ed_keypair, last_seq=4
    )
    assert plaintext == PLAINTEXT
    assert seq_no == 5


# ---------------------------------------------------------------------------
# Ciphertext / nonce / signature tamper → SignatureError
# ---------------------------------------------------------------------------

def test_tampered_ciphertext_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    sealed["ciphertext"] = _flip_b64_byte(sealed["ciphertext"])
    with pytest.raises(SignatureError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair)


def test_tampered_nonce_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    sealed["nonce"] = _flip_b64_byte(sealed["nonce"])
    with pytest.raises(SignatureError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair)


def test_tampered_signature_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    sealed["signature"] = _flip_b64_byte(sealed["signature"])
    with pytest.raises(SignatureError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair)


# ---------------------------------------------------------------------------
# Metadata / AAD tamper → SignatureError (signature covers these fields)
# ---------------------------------------------------------------------------

def test_tampered_seqno_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    sealed["seqNo"] = 99
    with pytest.raises(SignatureError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair)


def test_wrong_sender_id_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    with pytest.raises(SignatureError):
        _open(
            sealed, x25519_keypair, x25519_keypair_b, ed_keypair,
            sender_id="not-alice",
        )


def test_wrong_recipient_id_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    with pytest.raises(SignatureError):
        _open(
            sealed, x25519_keypair, x25519_keypair_b, ed_keypair,
            recipient_id="not-bob",
        )


# ---------------------------------------------------------------------------
# Wrong keys
# ---------------------------------------------------------------------------

def test_wrong_recipient_x25519_key_raises_invalid_tag(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    # Signature does not depend on the recipient X25519 key, so it still
    # verifies; the ECDH-derived AES key is wrong, so decryption fails.
    wrong_x_priv, _ = generate_keypair_x()
    with pytest.raises(InvalidTag):
        _open(
            sealed, x25519_keypair, x25519_keypair_b, ed_keypair,
            my_x_priv=wrong_x_priv,
        )


def test_wrong_sender_ed25519_key_raises_signature_error(sealed, x25519_keypair, x25519_keypair_b, ed_keypair, ed_keypair_b):
    _, wrong_ed_pub = ed_keypair_b
    with pytest.raises(SignatureError):
        _open(
            sealed, x25519_keypair, x25519_keypair_b, ed_keypair,
            peer_ed_pub=wrong_ed_pub,
        )


# ---------------------------------------------------------------------------
# Check ordering — signature is verified before the replay check
# ---------------------------------------------------------------------------

def test_signature_checked_before_replay(sealed, x25519_keypair, x25519_keypair_b, ed_keypair):
    # Message is BOTH a replay (last_seq >= seq_no) AND has a bad signature.
    # Signature is check (1), so SignatureError wins over ReplayError.
    sealed["signature"] = _flip_b64_byte(sealed["signature"])
    with pytest.raises(SignatureError):
        _open(sealed, x25519_keypair, x25519_keypair_b, ed_keypair, last_seq=10)


# ---------------------------------------------------------------------------
# AAD helper sanity
# ---------------------------------------------------------------------------

def test_build_aad_format():
    assert build_aad("a", "b", 7) == b"a|b|7"


def generate_keypair_x():
    """Helper: a fresh raw-bytes X25519 keypair (priv, pub)."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )
    priv = X25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv_bytes, pub_bytes
