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
# Domain-separated AAD for the decrypted-message cache so its ciphertext can
# never be confused with the key blob even though both are wrapped under the KEK.
_CACHE_AAD = b"zebra-msgcache-v1"
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

    def change_password(self, old_password: str, new_password: str) -> None:
        """Re-wrap the stored private keys under a KEK derived from new_password.

        Decrypts with the old password's KEK (which also verifies old_password),
        then re-encrypts the same private-key blob under the new password's KEK
        with a fresh nonce. The KDF salt is unchanged — it is random per keystore,
        not password-derived, so it need not rotate. Updates the in-memory KEK and
        keys so the unlocked session keeps working.
        """
        data = self._load()
        salt = base64.b64decode(data["salt"])
        old_kek = derive_kek(old_password, salt)
        # Decrypt under the old KEK — raises InvalidTag on a wrong old password,
        # which we let propagate so the caller can surface the failure.
        plaintext = decrypt(old_kek, base64.b64decode(data["nonce"]),
                            base64.b64decode(data["ciphertext"]), _AAD)
        new_kek = derive_kek(new_password, salt)
        nonce, ciphertext = encrypt(new_kek, plaintext, _AAD)
        data["nonce"] = _b64e(nonce)
        data["ciphertext"] = _b64e(ciphertext)
        self._save(data)
        self._kek = new_kek
        self._keys = {"x25519": plaintext[:32], "ed25519": plaintext[32:64]}
        # Re-wrap the decrypted-message cache under the new KEK too. The replay
        # seq counters persist across the change, so if the cache stayed under
        # the old KEK it would become unreadable and already-seen messages could
        # no longer be re-decrypted (the replay check would reject them).
        cache = self._decrypt_cache(old_kek)
        if cache:
            self.save_message_cache(cache)

    def pin_peer_key(self, user_id: str, key_type: str, public_key: str) -> None:
        """Record a peer's public key on first contact (TOFU)."""
        data = self._load()
        data.setdefault("peers", {}).setdefault(user_id, {})[key_type] = public_key
        self._save(data)

    def pinned_peer_key(self, user_id: str, key_type: str) -> Optional[str]:
        """Return the pinned public key for a peer, or ``None`` if unseen."""
        data = self._load()
        return data.get("peers", {}).get(user_id, {}).get(key_type)

    # --- per-peer sequence counters (replay protection) ------------------

    def next_send_seq(self, recipient_id: str) -> int:
        """Return (and persist) the next monotonic send counter for ``recipient_id``.

        The message key is static per (sender, recipient) pair, so the sequence
        number is what lets the recipient detect replays and reordering. Counters
        are persisted so they keep climbing across restarts. Starts at 1.
        """
        data = self._load()
        seqs = data.setdefault("seq_send", {})
        nxt = int(seqs.get(recipient_id, 0)) + 1
        seqs[recipient_id] = nxt
        self._save(data)
        return nxt

    def last_recv_seq(self, sender_id: str) -> Optional[int]:
        """Highest accepted sequence number from ``sender_id``, or ``None`` if unseen."""
        data = self._load()
        v = data.get("seq_recv", {}).get(sender_id)
        return int(v) if v is not None else None

    def set_recv_seq(self, sender_id: str, seq_no: int) -> None:
        """Record the highest accepted sequence number seen from ``sender_id``."""
        data = self._load()
        data.setdefault("seq_recv", {})[sender_id] = int(seq_no)
        self._save(data)

    def public_keys(self) -> dict:
        """Return the base64-encoded public keys (no password needed)."""
        data = self._load()
        return {"x25519": data["pub_x25519"], "ed25519": data["pub_ed25519"]}

    # --- decrypted-message cache -----------------------------------------

    def _cache_path(self) -> str:
        """Path of the encrypted plaintext cache (a sibling of the keystore)."""
        return self.path + ".msgcache"

    def _decrypt_cache(self, kek: Optional[bytes]) -> dict:
        """Decrypt the ``{messageId: plaintext}`` cache under ``kek``.

        Returns ``{}`` if there is no KEK, no cache file, or the file cannot be
        decrypted (e.g. it was written under a different password). The cache is
        only a display convenience — a miss just means messages are re-decrypted
        live on the next poll.
        """
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
        """Return the persisted ``{messageId: plaintext}`` cache for this session.

        Decrypted under the in-memory KEK, so the keystore must be unlocked.
        Seeding the in-memory cache from this on startup lets already-read
        messages display after a restart WITHOUT re-running the replay check:
        the per-sender seq counters persist, so a live re-decrypt of an old
        message would otherwise be rejected as a replay.
        """
        return self._decrypt_cache(self._kek)

    def save_message_cache(self, cache: dict) -> None:
        """Encrypt and persist the ``{messageId: plaintext}`` cache under the KEK.

        No-op while the keystore is locked. Written atomically with owner-only
        permissions like the keystore itself — it holds decrypted plaintext, so
        it must never be left world-readable nor persisted in the clear.
        """
        if self._kek is None:
            return
        payload = json.dumps(cache).encode("utf-8")
        nonce, ciphertext = encrypt(self._kek, payload, _CACHE_AAD)
        self._write_json_secure(self._cache_path(), {
            "version": _FORMAT_VERSION,
            "nonce": _b64e(nonce),
            "ciphertext": _b64e(ciphertext),
        })

    # --- persistence -----------------------------------------------------

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
        # Atomic, owner-only write: these files hold key material / decrypted
        # plaintext, so they must never be group/world readable nor left
        # half-written on a crash. The temp name is unique per write so two
        # concurrent writers (e.g. a poll persisting the message cache while a
        # send bumps a seq counter) cannot clobber each other's temp file.
        tmp = f"{path}.{os.getpid()}.{base64.urlsafe_b64encode(os.urandom(6)).decode('ascii')}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except BaseException:
            os.unlink(tmp)
            raise
        os.replace(tmp, path)
