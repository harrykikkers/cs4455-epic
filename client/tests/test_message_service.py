"""Unit tests for MessageService.decrypt_own — the sender-side
decrypt-on-cache-miss fallback.

Verifies the service wiring (camelCase field names, base64 key encodings, the
"verify against our own Ed25519 key" detail) recovers the plaintext of a message
*this* user sent, using static-ECDH symmetry. This is what makes own sent
messages display as their real text instead of the ``[sent]`` placeholder when
the local plaintext cache misses.
"""
import base64
from unittest.mock import MagicMock

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

from crypto.messaging import seal
from crypto.signing import generate_keypair
from services.message_service import MessageService


def _x25519():
    priv = X25519PrivateKey.generate()
    return (
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()),
        priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
    )


def _b64(b):
    return base64.b64encode(b).decode("ascii")


def _make_service_and_message():
    sender_x_priv, sender_x_pub = _x25519()
    _, recip_x_pub = _x25519()
    ed_priv, ed_pub = generate_keypair()

    # Seal a message as sender → recipient (what the backend stores & returns).
    fields = seal(
        plaintext="secret to self-read",
        sender_id="me-id",
        recipient_id="rid",
        seq_no=9,
        my_x_priv=sender_x_priv,
        my_ed_priv=ed_priv,
        peer_x_pub=recip_x_pub,
    )
    sent_msg = {  # shaped like the backend "sent" DTO (camelCase)
        "messageId": "m1",
        "recipientId": "rid",
        "ciphertext": fields["ciphertext"],
        "nonce": fields["nonce"],
        "signature": fields["signature"],
        "seqNo": fields["seqNo"],
    }

    keystore = MagicMock()
    keystore.private_keys.return_value = {"x25519": sender_x_priv, "ed25519": ed_priv}
    keystore.public_keys.return_value = {
        "x25519": _b64(sender_x_pub), "ed25519": _b64(ed_pub)}
    session = MagicMock()
    session.user_id = "me-id"
    key_svc = MagicMock()
    key_svc.fetch_and_pin.return_value = ({"x25519": _b64(recip_x_pub)}, False)

    svc = MessageService(api=MagicMock(), session=session,
                         keystore=keystore, key_service=key_svc)
    return svc, sent_msg, key_svc, _b64(recip_x_pub)


def test_decrypt_own_recovers_sent_plaintext():
    svc, sent_msg, key_svc, _ = _make_service_and_message()
    assert svc.decrypt_own(sent_msg) == "secret to self-read"
    key_svc.fetch_and_pin.assert_called_once_with("rid")


def test_decrypt_own_uses_supplied_pinned_without_fetch():
    svc, sent_msg, key_svc, recip_x_pub_b64 = _make_service_and_message()
    out = svc.decrypt_own(sent_msg, pinned={"x25519": recip_x_pub_b64})
    assert out == "secret to self-read"
    key_svc.fetch_and_pin.assert_not_called()


def test_decrypt_own_rejects_tampered_ciphertext():
    import pytest
    from crypto.messaging import SignatureError

    svc, sent_msg, _, _ = _make_service_and_message()
    raw = bytearray(base64.b64decode(sent_msg["ciphertext"]))
    raw[0] ^= 0xFF
    sent_msg["ciphertext"] = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(SignatureError):
        svc.decrypt_own(sent_msg)
