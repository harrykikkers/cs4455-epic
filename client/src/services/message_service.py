"""Message orchestration — send / receive / forward / revoke / delete.

Crypto-dependent actions (send, receive, forward) run the full pipeline from
README *Cryptographic Protocol*: static ECDH + HKDF + AES-256-GCM + Ed25519.
Read/state actions delegate to :class:`~api.messages.MessageAPI`.
"""

from __future__ import annotations

import base64
from typing import Optional

from api.messages import MessageAPI
from crypto.keystore import Keystore
from crypto.messaging import open_message, seal
from services.key_service import KeyService
from session import Session


class MessageService:
    def __init__(self, api: Optional[MessageAPI] = None,
                 session: Optional[Session] = None,
                 keystore: Optional[Keystore] = None,
                 key_service: Optional[KeyService] = None):
        self.session = session or Session()
        self.api = api or MessageAPI(self.session)
        self.keystore = keystore or Keystore()
        self.key_svc = key_service or KeyService(
            session=self.session, keystore=self.keystore)

    # ── read-only ────────────────────────────────────────────────────────

    def inbox(self):
        return self.api.inbox()

    def sent(self):
        return self.api.sent()

    # ── crypto actions ───────────────────────────────────────────────────

    def send(self, recipient_id: str, plaintext: str) -> tuple[dict, bool]:
        """Encrypt ``plaintext`` for ``recipient_id`` and POST it.

        Full pipeline: TOFU fetch → static ECDH + HKDF → AES-256-GCM (with
        replay-protected AAD) → Ed25519 sign → keccak256 digest.

        Returns ``(response_data, changed)`` where ``changed`` is True if the
        recipient's server key differs from the local TOFU pin.
        """
        pinned, changed = self.key_svc.fetch_and_pin(recipient_id)
        if "x25519" not in pinned:
            raise RuntimeError("Recipient has no X25519 key on server.")

        priv = self.keystore.private_keys()
        seq_no = self.keystore.next_send_seq(recipient_id)

        fields = seal(
            plaintext=plaintext,
            sender_id=self.session.user_id,
            recipient_id=recipient_id,
            seq_no=seq_no,
            my_x_priv=priv["x25519"],
            my_ed_priv=priv["ed25519"],
            peer_x_pub=base64.b64decode(pinned["x25519"]),
        ) # seal returns a dict, it does all the crypto and returns the fields needed 

        resp = self.api.send(
            recipient_id=recipient_id,
            ciphertext=fields["ciphertext"],
            nonce=fields["nonce"],
            signature=fields["signature"],
            seq_no=fields["seqNo"],
            digest=fields["digest"],
        )
        return resp, changed

    def receive(self, message: dict,
                pinned: Optional[dict] = None,
                changed: bool = False,
                enforce_replay: bool = True) -> tuple[str, bool]:
        """Verify and decrypt a received message; return ``(plaintext, changed)``.

        Four checks in order: Ed25519 signature → replay counter → static ECDH
        + HKDF → AES-256-GCM decrypt. Plaintext is returned only after all four
        pass. Raises :class:`~crypto.messaging.SignatureError`,
        :class:`~crypto.messaging.ReplayError`, or ``InvalidTag`` on failure.
        ``changed`` is True if the sender's server key differs from the TOFU pin.

        Pass ``pinned`` + ``changed`` to skip the internal key fetch (avoids a
        redundant network round-trip when the caller already has the keys).

        ``enforce_replay=False`` re-decrypts an already-accepted message for
        re-display only (e.g. the plaintext cache was lost): it skips the replay
        gate *and* does not advance the stored counter, so replay protection for
        genuinely new messages is untouched. Signature + AEAD are still enforced.
        """
        sender_id = message.get("senderId") or message.get("sender_id", "")
        recipient_id = self.session.user_id

        if pinned is None:
            pinned, changed = self.key_svc.fetch_and_pin(sender_id)
        if "x25519" not in pinned or "ed25519" not in pinned:
            raise RuntimeError("Sender has no keys on server.")

        priv = self.keystore.private_keys()
        last_seq = self.keystore.last_recv_seq(sender_id)

        plaintext, seq_no = open_message(
            fields=message,
            sender_id=sender_id,
            recipient_id=recipient_id,
            my_x_priv=priv["x25519"],
            peer_x_pub=base64.b64decode(pinned["x25519"]),
            peer_ed_pub=base64.b64decode(pinned["ed25519"]),
            last_seq=last_seq,
            enforce_replay=enforce_replay,
        )

        # Only advance the counter on the accept path; re-display must not
        # regress it (seq_no here is an already-seen, older value).
        if enforce_replay:
            self.keystore.set_recv_seq(sender_id, seq_no)
        return plaintext, changed

    def decrypt_own(self, message: dict, pinned: Optional[dict] = None) -> str:
        """Decrypt a message *this* user sent, for local re-display only.

        Our own sent ciphertext is encrypted to the recipient, but static ECDH
        is symmetric: the sender re-derives the same message key from its own
        X25519 private key and the recipient's pinned X25519 public key. The
        signature was produced by us, so it verifies against our *own* Ed25519
        public key (we are the sender). Returns the plaintext.

        Display-only path: it passes ``enforce_replay=False`` and never advances
        any counter. The replay counter tracks inbound seqs per *sender*; our
        own sends are outbound and don't belong to it — this is why sent
        messages are normally served from the plaintext cache rather than
        re-decrypted. Used only as a fallback when that cache misses (e.g. a
        message sent from another session/device, or after the cache was reset).

        Raises if the recipient rotated their X25519 key after the send (the
        original public key is gone, so the key can't be re-derived) or on any
        signature/AEAD failure — callers fall back to the ``[sent]`` placeholder.
        """
        recipient_id = message.get("recipientId") or message.get("recipient_id", "")
        if pinned is None:
            pinned, _ = self.key_svc.fetch_and_pin(recipient_id)
        if "x25519" not in pinned:
            raise RuntimeError("Recipient has no X25519 key on server.")

        priv = self.keystore.private_keys()
        my_ed_pub = base64.b64decode(self.keystore.public_keys()["ed25519"])

        plaintext, _ = open_message(
            fields=message,
            sender_id=self.session.user_id,
            recipient_id=recipient_id,
            my_x_priv=priv["x25519"],
            peer_x_pub=base64.b64decode(pinned["x25519"]),
            peer_ed_pub=my_ed_pub,
            last_seq=None,
            enforce_replay=False,
        )
        return plaintext

    def forward(self, message_id: str, recipient_id: str, plaintext: str) -> tuple[dict, bool]:
        """Re-encrypt ``plaintext`` under ``recipient_id``'s key and forward it.

        A forward is the forwarder sending the already-decrypted plaintext to a
        new recipient — sealed identically to a direct send so the recipient's
        client handles it the same way. Returns ``(response_data, changed)``.
        """
        pinned, changed = self.key_svc.fetch_and_pin(recipient_id)
        if "x25519" not in pinned:
            raise RuntimeError("Recipient has no X25519 key on server.")

        priv = self.keystore.private_keys()
        seq_no = self.keystore.next_send_seq(recipient_id)

        fields = seal(
            plaintext=plaintext,
            sender_id=self.session.user_id,
            recipient_id=recipient_id,
            seq_no=seq_no,
            my_x_priv=priv["x25519"],
            my_ed_priv=priv["ed25519"],
            peer_x_pub=base64.b64decode(pinned["x25519"]),
        )

        resp = self.api.forward(
            message_id=message_id,
            recipient_id=recipient_id,
            ciphertext=fields["ciphertext"],
            nonce=fields["nonce"],
            signature=fields["signature"],
            seq_no=fields["seqNo"],
            digest=fields["digest"],
        )
        return resp, changed

    # ── state actions ────────────────────────────────────────────────────

    def revoke(self, message_id: str, user_id: str):
        return self.api.revoke(message_id, user_id)

    def delete(self, message_id: str):
        return self.api.delete(message_id)
