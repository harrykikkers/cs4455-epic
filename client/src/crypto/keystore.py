"""Local private-key storage, KEK wrapping, TOFU peer-key pinning."""

from __future__ import annotations

import base64
import json
import os
from typing import Optional

import config
from crypto.aead import decrypt, encrypt
from crypto.kdf import derive_kek
from crypto.signing import generate_keypair as _ed25519_keypair
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

# AAD labels — tie each ciphertext to its purpose so blobs can't be mixed up.
_AAD = b"zebra-keystore-v1"
_CACHE_AAD = b"zebra-msgcache-v1"
_ARCHIVE_INFO = b"zebra-msgarchive-v1"

_b64e = lambda b: base64.b64encode(b).decode("ascii")
# Converts raw bytes to a base64 string.
#  JSON can't store raw bytes, only strings.

SALT_BYTES = 16       # 128-bit salt per RFC 9106
_FORMAT_VERSION = 1   # bump to 2 if the JSON layout or KDF params change


def generate_salt() -> bytes:
    return os.urandom(SALT_BYTES)


class Keystore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.KEYSTORE_PATH
        self._kek: Optional[bytes] = None   # None = locked
        self._keys: Optional[dict] = None

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def create(self, password: str) -> None:
        """Create a new keystore: generate keypairs, encrypt under KEK, save."""
        if self.exists():
            raise FileExistsError(f"keystore already exists at {self.path}")
        salt = generate_salt()
        self._kek = derive_kek(password, salt) # kdf.py - derives the key encryption key from the password and salt

        x_priv = X25519PrivateKey.generate()
        x_priv_bytes = x_priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        x_pub_bytes  = x_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ed_priv_bytes, ed_pub_bytes = _ed25519_keypair()

        # Encrypt both private keys as one 64-byte blob under the KEK.
        nonce, ciphertext = encrypt(self._kek, x_priv_bytes + ed_priv_bytes, _AAD)

        self._save(
            {
                "version":    _FORMAT_VERSION,
                "salt":       _b64e(salt),
                "nonce":      _b64e(nonce),
                "ciphertext": _b64e(ciphertext),
                "pub_x25519": _b64e(x_pub_bytes), # public key used for encryption
                "pub_ed25519": _b64e(ed_pub_bytes), # public key used for signing
                "peers":      {},
            }
        )

    def unlock(self, password: str) -> None:
        """Derive the KEK from the stored salt and decrypt private keys into memory."""
        data = self._load()
        salt = base64.b64decode(data["salt"])
        self._kek = derive_kek(password, salt)
        plaintext = decrypt(self._kek, base64.b64decode(data["nonce"]),
                            base64.b64decode(data["ciphertext"]), _AAD)
        # First 32 bytes = X25519 private key, next 32 = Ed25519 private key.
        self._keys = {"x25519": plaintext[:32], "ed25519": plaintext[32:64]}

    def private_keys(self) -> dict:
        if self._keys is None:
            raise RuntimeError("Keystore is locked — call unlock() first")
        return self._keys # called by MessageService when sending or receiving

    def change_password(self, old_password: str, new_password: str) -> None:
        """Re-wrap the private-key blob under a new KEK. Salt is unchanged."""
        data = self._load()
        salt = base64.b64decode(data["salt"])
        old_kek = derive_kek(old_password, salt)
        # Wrong old password → InvalidTag propagates to caller.
        plaintext = decrypt(old_kek, base64.b64decode(data["nonce"]),
                            base64.b64decode(data["ciphertext"]), _AAD)
        new_kek = derive_kek(new_password, salt)
        nonce, ciphertext = encrypt(new_kek, plaintext, _AAD)
        data["nonce"] = _b64e(nonce)
        data["ciphertext"] = _b64e(ciphertext)
        self._save(data)
        self._kek = new_kek
        self._keys = {"x25519": plaintext[:32], "ed25519": plaintext[32:64]}
        cache = self._decrypt_cache(old_kek) # Re-wrap the message cache so it stays readable under the new KEK.
        if cache:
            self.save_message_cache(cache)
        # -- TOFU --
    def pin_peer_key(self, user_id: str, key_type: str, public_key: str) -> None:
        """Store a peer's public key on first contact (TOFU)."""
        data = self._load()
        data.setdefault("peers", {}).setdefault(user_id, {})[key_type] = public_key
        # set default creates the peers dict if it doesnt exist yet
        self._save(data)

    def pinned_peer_key(self, user_id: str, key_type: str) -> Optional[str]:
        """Return the pinned key for a peer, or None if unseen."""
        data = self._load()
        return data.get("peers", {}).get(user_id, {}).get(key_type)
        # --      --

    # --- sequence counters (replay protection) ----------------------------

    def next_send_seq(self, recipient_id: str) -> int:
        """Return and persist the next send counter for this recipient. Starts at 1."""
        data = self._load()
        seqs = data.setdefault("seq_send", {})
        nxt = int(seqs.get(recipient_id, 0)) + 1
        seqs[recipient_id] = nxt
        self._save(data)
        return nxt

    def last_recv_seq(self, sender_id: str) -> Optional[int]:
        """Highest accepted seq_no from this sender, or None if first message."""
        data = self._load()
        v = data.get("seq_recv", {}).get(sender_id)
        return int(v) if v is not None else None

    def set_recv_seq(self, sender_id: str, seq_no: int) -> None:
        data = self._load()
        data.setdefault("seq_recv", {})[sender_id] = int(seq_no)
        self._save(data)

    def public_keys(self) -> dict:
        """Return base64-encoded public keys — no password needed."""
        data = self._load()
        return {"x25519": data["pub_x25519"], "ed25519": data["pub_ed25519"]}

    # --- C++ archive key --------------------------------------------------

    def archive_path(self) -> str:
        return self.path + ".archive"

    def archive_key(self) -> bytes:
        """Derive a 32-byte AES key for the C++ archive via HKDF over the KEK."""
        if self._kek is None:
            raise RuntimeError("Keystore is locked — call unlock() first")
        return HKDFExpand(
            algorithm=hashes.SHA256(),
            length=32,
            info=_ARCHIVE_INFO,
        ).derive(self._kek)

    def archive_key_hex(self) -> str:
        return self.archive_key().hex()

    # --- message plaintext cache ------------------------------------------

    def _cache_path(self) -> str:
        return self.path + ".msgcache"

    def _decrypt_cache(self, kek: Optional[bytes]) -> dict:
        """Decrypt the {messageId: plaintext} cache. Returns {} on any failure."""
        path = self._cache_path()
        if kek is None or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            plaintext = decrypt(kek, base64.b64decode(blob["nonce"]),
                                base64.b64decode(blob["ciphertext"]), _CACHE_AAD)
            return json.loads(plaintext.decode("utf-8"))
        except Exception:
            return {}

    def load_message_cache(self) -> dict:
        """Load the persisted plaintext cache for this session."""
        return self._decrypt_cache(self._kek)

    def save_message_cache(self, cache: dict) -> None:
        """Encrypt and persist {messageId: plaintext} under the KEK."""
        if self._kek is None:
            return
        payload = json.dumps(cache).encode("utf-8")
        nonce, ciphertext = encrypt(self._kek, payload, _CACHE_AAD)
        self._write_json_secure(self._cache_path(), {
            "version": _FORMAT_VERSION,
            "nonce": _b64e(nonce),
            "ciphertext": _b64e(ciphertext),
        })

    # --- persistence ------------------------------------------------------

    def _load(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version")
        if version != _FORMAT_VERSION:
            raise ValueError(f"unsupported keystore format version: {version!r}")
        return data

    def _save(self, data: dict) -> None:
        self._write_json_secure(self.path, data)

    def _write_json_secure(self, path: str, data: dict) -> None:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # Write to a unique temp file then rename atomically — safe against crashes
        # and concurrent writes. 0o600 = owner read/write only.
        tmp = f"{path}.{os.getpid()}.{base64.urlsafe_b64encode(os.urandom(6)).decode('ascii')}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except BaseException:
            os.unlink(tmp)
            raise
        os.replace(tmp, path)
