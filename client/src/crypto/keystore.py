"""Local private-key storage + KEK + pinned peer keys.

Stores the user's X25519 decapsulation key and Ed25519 signing key in
``KEYSTORE_PATH`` as JSON, encrypted under a KEK derived from the password
(see :func:`crypto.kdf.derive_kek`). The KDF salt is generated once when the
keystore is first created and persisted alongside the ciphertext, so every
later unlock re-derives the identical KEK from the same password. Also holds
TOFU-pinned peer public keys for reconciliation against the server's rotation
history (README *TOFU Key Pinning*).

Salt generation, KEK derivation, private-key encryption (``crypto.aead``),
and TOFU peer-key pinning are all implemented here.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Optional

import config
from crypto.aead import decrypt, encrypt
from crypto.kdf import derive_kek
from crypto.signing import generate_keypair as _ed25519_keypair
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

_AAD = b"zebra-keystore-v1"
_b64e = lambda b: base64.b64encode(b).decode("ascii")

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
        self._keys: Optional[dict] = None

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

        x_priv = X25519PrivateKey.generate()
        x_priv_bytes = x_priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        x_pub_bytes  = x_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ed_priv_bytes, ed_pub_bytes = _ed25519_keypair()

        nonce, ciphertext = encrypt(self._kek, x_priv_bytes + ed_priv_bytes, _AAD)

        self._save(
            {
                "version":    _FORMAT_VERSION,
                "salt":       _b64e(salt),
                "nonce":      _b64e(nonce),
                "ciphertext": _b64e(ciphertext),
                "pub_x25519": _b64e(x_pub_bytes),
                "pub_ed25519": _b64e(ed_pub_bytes),
                "peers":      {},
            }
        )

    def unlock(self, password: str) -> None:
        """Derive the KEK from the persisted salt into memory."""
        data = self._load()
        salt = base64.b64decode(data["salt"])
        self._kek = derive_kek(password, salt)
        plaintext = decrypt(self._kek, base64.b64decode(data["nonce"]),
                            base64.b64decode(data["ciphertext"]), _AAD)
        self._keys = {"x25519": plaintext[:32], "ed25519": plaintext[32:64]}

    def private_keys(self) -> dict:
        """Return the decrypted X25519 + Ed25519 private keys."""
        if self._keys is None:
            raise RuntimeError("Keystore is locked — call unlock() first")
        return self._keys

    def pin_peer_key(self, user_id: str, key_type: str, public_key: str) -> None:
        """Record a peer's public key on first contact (TOFU)."""
        data = self._load()
        data.setdefault("peers", {}).setdefault(user_id, {})[key_type] = public_key
        self._save(data)

    def pinned_peer_key(self, user_id: str, key_type: str) -> Optional[str]:
        """Return the pinned public key for a peer, or ``None`` if unseen."""
        data = self._load()
        return data.get("peers", {}).get(user_id, {}).get(key_type)

    def public_keys(self) -> dict:
        """Return the base64-encoded public keys (no password needed)."""
        data = self._load()
        return {"x25519": data["pub_x25519"], "ed25519": data["pub_ed25519"]}

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
