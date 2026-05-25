"""Authentication orchestration — register, login, password change.

Composes :class:`~secure_messenger_client.api.auth.AuthAPI` with the crypto
layer (key generation, KEK derivation) and the keystore. The network parts
are wired up; the crypto parts are flagged with TODOs.
"""

from __future__ import annotations

from typing import Optional

from api.auth import AuthAPI
from session import Session


class AuthService:
    def __init__(self, api: Optional[AuthAPI] = None,
                 session: Optional[Session] = None):
        self.session = session or Session()
        self.api = api or AuthAPI(self.session)

    def login(self, username: str, password: str) -> None:
        """Authenticate and populate the session.

        TODO: unlock the local keystore with a KEK derived from
        ``password`` (``crypto.kdf.derive_kek``) so private keys are
        available for the session.
        """
        data = self.api.login(username, password)["data"]
        self.session.set(data["token"], data["user"]["userId"],
                         data["user"]["username"])

    def register(self, username: str, password: str):
        """Register a new account.

        TODO: generate X25519 + Ed25519 keypairs, encrypt the private keys
        under the KEK into the keystore, and publish the public keys via
        ``KeyService``.
        """
        return self.api.register(username, password)

    def change_password(self, current: str, new: str):
        """Change the account password.

        TODO: re-encrypt the keystore under a KEK derived from ``new``.
        """
        return self.api.change_password(current, new)
