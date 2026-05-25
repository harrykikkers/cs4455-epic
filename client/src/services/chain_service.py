"""Chain orchestration — fetch the on-chain anchor proof for a message.

The client never reads Sepolia directly; it asks the server for the
recorded ``tx_hash`` and hands it (plus the locally computed digest) to the
standalone verification page. See README *Blockchain Verification*.
"""

from __future__ import annotations

from typing import Optional

from api.messages import MessageAPI
from session import Session


class ChainService:
    def __init__(self, api: Optional[MessageAPI] = None,
                 session: Optional[Session] = None):
        self.session = session or Session()
        self.api = api or MessageAPI(self.session)

    def proof(self, message_id: str):
        """Return ``{ digest_hash, chain_status, tx_hash, recorded_at }``."""
        return self.api.chain(message_id)
