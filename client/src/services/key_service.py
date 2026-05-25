"""Key orchestration — publish own key, fetch + pin peer keys, reconcile.

PLANNED. Implements TOFU pinning and reconciliation against the server's
append-only rotation history (README *TOFU Key Pinning*).
"""

from __future__ import annotations

from typing import Optional

from api.keys import KeyAPI
from crypto.keystore import Keystore
from session import Session


class KeyService:
    def __init__(self, api: Optional[KeyAPI] = None,
                 keystore: Optional[Keystore] = None,
                 session: Optional[Session] = None):
        self.session = session or Session()
        self.api = api or KeyAPI(self.session)
        self.keystore = keystore or Keystore()

    def publish_own_keys(self):
        """Publish this user's X25519 + Ed25519 public keys."""
        raise NotImplementedError("key publishing not yet implemented")

    def fetch_and_pin(self, user_id: str):
        """Fetch a peer's key; pin on first contact (TOFU)."""
        raise NotImplementedError("TOFU pinning not yet implemented")

    def reconcile(self, user_id: str, key_type: str) -> bool:
        """Compare the server's current key against the pin.

        Returns ``True`` if the key is unchanged or a legitimate rotation
        present in history; ``False`` if it may be a substitution attack.
        """
        raise NotImplementedError("key reconciliation not yet implemented")
