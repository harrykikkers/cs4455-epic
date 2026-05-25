"""Wrappers for /api/messages/* endpoints.

All crypto fields (``enc``, ``ciphertext``, ``nonce``, ``signature``,
``digest``) are produced by the crypto layer and passed in as-is — this
module knows nothing about encryption.
"""

from __future__ import annotations

from typing import Any

from .client import BaseClient


class MessageAPI(BaseClient):
    def send(self, recipient_id: str, enc: str, ciphertext: str, nonce: str,
             signature: str, seq_no: int, digest: str) -> Any:
        """POST /api/messages."""
        return self._post("/api/messages", json={
            "recipientId": recipient_id,
            "enc": enc,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "signature": signature,
            "seqNo": seq_no,
            "digest": digest,
        })

    def inbox(self) -> Any:
        """GET /api/messages/inbox."""
        return self._get("/api/messages/inbox")

    def sent(self) -> Any:
        """GET /api/messages/sent."""
        return self._get("/api/messages/sent")

    def get(self, message_id: str) -> Any:
        """GET /api/messages/:id."""
        return self._get(f"/api/messages/{message_id}")

    def chain(self, message_id: str) -> Any:
        """GET /api/messages/:id/chain — blockchain anchor proof."""
        return self._get(f"/api/messages/{message_id}/chain")

    def forward(self, message_id: str, recipient_id: str, enc: str,
                ciphertext: str, nonce: str) -> Any:
        """POST /api/messages/:id/forward — re-encrypted for a new recipient."""
        return self._post(f"/api/messages/{message_id}/forward", json={
            "recipientId": recipient_id,
            "enc": enc,
            "ciphertext": ciphertext,
            "nonce": nonce,
        })

    def revoke(self, message_id: str, user_id: str) -> Any:
        """POST /api/messages/:id/revoke — revoke a user's shared access.

        ``user_id`` is the share recipient to revoke; the backend requires it
        in the body (``{ userId }``) since a message can be shared with many.
        """
        return self._post(f"/api/messages/{message_id}/revoke",
                          json={"userId": user_id})

    def delete(self, message_id: str) -> Any:
        """DELETE /api/messages/:id — soft delete."""
        return self._delete(f"/api/messages/{message_id}")
