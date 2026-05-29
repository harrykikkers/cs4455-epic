"""Key orchestration — publish own key, fetch + pin peer keys, reconcile.

Implements TOFU pinning and reconciliation against the server's append-only
rotation history (README *TOFU Key Pinning*).
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

    def publish_own_keys(self) -> None:
        """Publish this user's X25519 + Ed25519 public keys to the server."""
        pub = self.keystore.public_keys()
        for key_type in ("x25519", "ed25519"):
            self.api.publish(pub[key_type], key_type, acknowledge_rotation=True)

    def fetch_and_pin(self, user_id: str) -> tuple[dict, bool]:
        """Fetch a peer's keys and TOFU-pin them on first contact.

        Returns ``(keys, changed)`` where ``keys`` is a dict of
        ``{key_type: base64_public_key}`` and ``changed`` is True if the
        server's current key differs from the locally pinned one (possible key
        rotation or substitution — the caller should surface a key-change
        warning). On first contact the keys are pinned and ``changed`` is
        False. On subsequent calls the pinned key is returned so callers always
        use the key we committed to, not whatever the server currently claims.
        """
        resp = self.api.get(user_id)
        data = resp.get("data", [])
        result = {}
        changed = False
        for kt in ("x25519", "ed25519"):
            pub = next((k["publicKey"] for k in data if k["keyType"] == kt), None)
            if pub is None:
                continue
            pinned = self.keystore.pinned_peer_key(user_id, kt)
            if pinned is None:
                self.keystore.pin_peer_key(user_id, kt, pub)
                result[kt] = pub
            elif pinned != pub:
                changed = True
                result[kt] = pinned  # keep the pinned key (secure TOFU)
            else:
                result[kt] = pinned
        return result, changed

    def reconcile(self, user_id: str, key_type: str) -> bool:
        """Compare the server's current key against the TOFU pin.

        Returns ``True`` if the key is unchanged or the change is a legitimate
        rotation present in the server's append-only history. Returns ``False``
        if the current key differs from the pin and is absent from history —
        indicating a possible key-substitution attack.
        """
        resp = self.api.get(user_id)
        server_keys = resp.get("data", [])
        current = next(
            (k["publicKey"] for k in server_keys if k["keyType"] == key_type),
            None,
        )
        pinned = self.keystore.pinned_peer_key(user_id, key_type)

        if pinned is None or current == pinned:
            return True

        try:
            hist = self.api.history(user_id, key_type)
            history_keys = {h["publicKey"] for h in hist.get("data", [])}
            return pinned in history_keys
        except Exception:
            return False
