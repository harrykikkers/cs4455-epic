"""Message DTO.

``plaintext`` is populated only after a message is verified and decrypted
locally; on the wire the client only ever holds ciphertext + metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    message_id: str
    sender_id: str
    sender_username: str
    recipient_id: str
    recipient_username: str
    created_at: str
    chain_status: str = "pending"
    plaintext: Optional[str] = None
    mine: bool = False
