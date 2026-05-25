"""Message orchestration — send / receive / forward / revoke / delete.

Read/state actions delegate to :class:`~secure_messenger_client.api.messages.MessageAPI`;
the crypto-dependent actions (send, receive-decrypt, forward) are PLANNED —
they will run the pipeline in the README *Cryptographic Protocol*.
"""

from __future__ import annotations

from typing import Optional

from api.messages import MessageAPI
from session import Session


class MessageService:
    def __init__(self, api: Optional[MessageAPI] = None,
                 session: Optional[Session] = None):
        self.session = session or Session()
        self.api = api or MessageAPI(self.session)

    def inbox(self):
        return self.api.inbox()

    def sent(self):
        return self.api.sent()

    def send(self, recipient_id: str, plaintext: str):
        """Encrypt ``plaintext`` for the recipient and POST it.

        TODO: HPKE encapsulate → HKDF → AES-GCM (with replay-protected AAD)
        → Ed25519 sign → keccak digest, then ``MessageAPI.send(...)``.
        """
        raise NotImplementedError("message encryption not yet implemented")

    def receive(self, message_id: str) -> str:
        """Fetch, verify, and decrypt a message; return the plaintext.

        TODO: verify signature → check replay → HPKE decapsulate → HKDF →
        AES-GCM decrypt (README step 10).
        """
        raise NotImplementedError("message decryption not yet implemented")

    def forward(self, message_id: str, recipient_id: str):
        """Re-encrypt a message under a new recipient and forward it.

        TODO: decrypt locally, re-encrypt for ``recipient_id``, then
        ``MessageAPI.forward(...)``.
        """
        raise NotImplementedError("re-encryption for forwarding not yet implemented")

    def revoke(self, message_id: str, user_id: str):
        return self.api.revoke(message_id, user_id)

    def delete(self, message_id: str):
        return self.api.delete(message_id)
