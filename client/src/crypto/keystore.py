"""Local private-key storage + KEK + pinned peer keys.

PLANNED. Stores the user's X25519 decapsulation key and Ed25519 signing
key in ``KEYSTORE_PATH`` as JSON, encrypted under a KEK derived from the
password (see :func:`secure_messenger_client.crypto.kdf.derive_kek`). Also
holds TOFU-pinned peer public keys for reconciliation against the server's
rotation history (README *TOFU Key Pinning*).
"""

from __future__ import annotations

from typing import Optional

import config


class Keystore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.KEYSTORE_PATH
        self._kek: Optional[bytes] = None

    def unlock(self, password: str) -> None:
        """Derive the KEK and decrypt the stored private keys into memory."""
        raise NotImplementedError("keystore unlock not yet implemented")

    def private_keys(self) -> dict:
        """Return the decrypted X25519 + Ed25519 private keys."""
        raise NotImplementedError("keystore access not yet implemented")

    def pin_peer_key(self, user_id: str, key_type: str, public_key: str) -> None:
        """Record a peer's public key on first contact (TOFU)."""
        raise NotImplementedError("peer-key pinning not yet implemented")

    def pinned_peer_key(self, user_id: str, key_type: str) -> Optional[str]:
        """Return the pinned public key for a peer, or ``None`` if unseen."""
        raise NotImplementedError("peer-key lookup not yet implemented")
