"""Local private-key storage + KEK + pinned peer keys.

Stores the user's X25519 decapsulation key and Ed25519 signing key in
``KEYSTORE_PATH`` as JSON, encrypted under a KEK derived from the password
(see :func:`crypto.kdf.derive_kek`). The KDF salt is generated once when the
keystore is first created and persisted alongside the ciphertext, so every
later unlock re-derives the identical KEK from the same password. Also holds
TOFU-pinned peer public keys for reconciliation against the server's rotation
history (README *TOFU Key Pinning*).

Salt generation and KEK derivation are implemented here; private-key
encryption (``crypto.aead``) and peer pinning remain PLANNED.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Optional

import config
from crypto.kdf import derive_kek

# 128-bit salt — the Argon2 RFC 9106 recommendation. Random per keystore, so
# uniqueness is statistical and needs no coordination or collision checks.
SALT_BYTES = 16

# On-disk format version. Bump when the JSON layout or KDF parameters change
# so an old keystore can be detected (and migrated) rather than silently
# producing a wrong KEK.
_FORMAT_VERSION = 1


def generate_salt() -> bytes:
    """Return a fresh, random 16-byte KDF salt (one per keystore)."""
    return os.urandom(SALT_BYTES)


class Keystore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.KEYSTORE_PATH
        self._kek: Optional[bytes] = None

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def create(self, password: str) -> None:
        """Initialize a new keystore: generate the salt, derive and cache the KEK.

        Generates the one and only salt for this keystore, persists it, and
        keeps the derived KEK in memory for the rest of the session. Raises
        ``FileExistsError`` if a keystore is already present so an accidental
        re-registration cannot overwrite existing private keys.
        """
        if self.exists():
            raise FileExistsError(f"keystore already exists at {self.path}")
        salt = generate_salt()
        self._kek = derive_kek(password, salt)
        self._save(
            {
                "version": _FORMAT_VERSION,
                "salt": base64.b64encode(salt).decode("ascii"),
            }
        )

    def unlock(self, password: str) -> None:
        """Derive the KEK from the persisted salt into memory."""
        data = self._load()
        salt = base64.b64decode(data["salt"])
        self._kek = derive_kek(password, salt)

    def private_keys(self) -> dict:
        """Return the decrypted X25519 + Ed25519 private keys."""
        raise NotImplementedError("keystore access not yet implemented")

    def pin_peer_key(self, user_id: str, key_type: str, public_key: str) -> None:
        """Record a peer's public key on first contact (TOFU)."""
        raise NotImplementedError("peer-key pinning not yet implemented")

    def pinned_peer_key(self, user_id: str, key_type: str) -> Optional[str]:
        """Return the pinned public key for a peer, or ``None`` if unseen."""
        raise NotImplementedError("peer-key lookup not yet implemented")

    # --- persistence -----------------------------------------------------

    def _load(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version")
        if version != _FORMAT_VERSION:
            raise ValueError(f"unsupported keystore format version: {version!r}")
        return data

    def _save(self, data: dict) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # Atomic, owner-only write: the file holds key material, so it must
        # never be group/world readable nor left half-written on a crash.
        tmp = f"{self.path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except BaseException:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)
