"""Authentication orchestration — register, login, password change.

Composes :class:`~secure_messenger_client.api.auth.AuthAPI` with the crypto
layer (key generation, KEK derivation) and the keystore. The network parts
are wired up; the crypto parts are flagged with TODOs.
"""

from __future__ import annotations

from typing import Optional

from api.auth import AuthAPI
from crypto.kdf import derive_auth_hash
from session import Session


class AuthService:
    def __init__(self, api: Optional[AuthAPI] = None,
                 session: Optional[Session] = None):
        self.session = session or Session()
        self.api = api or AuthAPI(self.session)

    def login(self, username: str, password: str) -> None:
        """Authenticate and populate the session.

        Sends the Argon2id pre-hash of the password (``derive_auth_hash``)
        rather than the cleartext, so the server never sees the plaintext.

        TODO: unlock the local keystore with a KEK derived from the
        *cleartext* ``password`` (``crypto.kdf.derive_kek``) — not the auth
        hash — so private keys are available for the session.
        """
        data = self.api.login(username, derive_auth_hash(password, username))["data"]
        self.session.set(data["token"], data["user"]["userId"],
                         data["user"]["username"])

    def register(self, username: str, password: str):
        """Register a new account.

        Sends the Argon2id pre-hash of the password (``derive_auth_hash``);
        the server salts and re-hashes it before storage.

        TODO: generate X25519 + Ed25519 keypairs, encrypt the private keys
        under a KEK derived from the *cleartext* ``password`` into the
        keystore, and publish the public keys via ``KeyService``.
        """
        return self.api.register(username, derive_auth_hash(password, username))

    def change_password(self, current: str, new: str):
        """Change the account password.

        Both the current and new passwords are pre-hashed
        (``derive_auth_hash``) with the logged-in user's username before being
        sent.

        TODO: re-encrypt the keystore under a KEK derived from the cleartext
        ``new`` password.
        """
        username = self.session.username
        return self.api.change_password(
            derive_auth_hash(current, username),
            derive_auth_hash(new, username),
        )
