"""Authentication orchestration — register, login, password change.

Composes :class:`~api.auth.AuthAPI` with the crypto layer (keystore key
generation + KEK unlock) and :class:`~services.key_service.KeyService`. This is
the single code path for auth: register generates the local keystore, login
unlocks it and publishes the public keys. The UI frames call these methods
rather than talking to the server directly.
"""

from __future__ import annotations

import os
from typing import Optional

from api.auth import AuthAPI
from crypto.kdf import derive_auth_hash
from crypto.keystore import Keystore
from services.key_service import KeyService
from session import Session


class AuthService:
    def __init__(self, api: Optional[AuthAPI] = None,
                 session: Optional[Session] = None,
                 keystore: Optional[Keystore] = None,
                 key_service: Optional[KeyService] = None):
        self.session = session or Session()
        self.api = api or AuthAPI(self.session)
        self.keystore = keystore or Keystore()
        self.key_svc = key_service or KeyService(
            session=self.session, keystore=self.keystore)

    def login(self, username: str, password: str) -> dict:
        """Authenticate, unlock the local keystore, and publish public keys.

        The password is used two independent, domain-separated ways: the
        Argon2id pre-hash (``derive_auth_hash``) is sent to the server as the
        credential, while the *cleartext* password derives the local KEK that
        unlocks the keystore — the cleartext never leaves the device.

        On first login the keystore is created (this happens at register, so the
        create path here is only a fallback). Once unlocked, the X25519 +
        Ed25519 public keys are published so peers can reach this user. Returns
        the server ``data`` block (token + user) and leaves it on ``self.session``.
        """
        data = self.api.login(username, derive_auth_hash(password, username))["data"]
        self.session.set(data["token"], data["user"]["userId"],
                         data["user"]["username"])

        if self.keystore.exists():
            self.keystore.unlock(password)
        else:
            self.keystore.create(password)
            self.keystore.unlock(password)

        self.key_svc.publish_own_keys()
        return data

    def register(self, username: str, password: str):
        """Register a new account and generate the local keystore.

        Sends the Argon2id pre-hash (``derive_auth_hash``); the server salts and
        re-hashes it before storage. On success, generates the X25519 + Ed25519
        keypairs and stores the private keys encrypted under a KEK derived from
        the *cleartext* password. Public keys are published later, at first
        login, which is where the JWT needed to authenticate ``POST /api/keys``
        first becomes available.

        A pre-existing keystore at the configured path is replaced — registering
        a new account starts a fresh local identity on this machine.
        """
        resp = self.api.register(username, derive_auth_hash(password, username))
        if self.keystore.exists():
            os.remove(self.keystore.path)
        self.keystore.create(password)
        return resp

    def change_password(self, current: str, new: str, keystore=None):
        """Change the account password.

        Both the current and new passwords are pre-hashed
        (``derive_auth_hash``) with the logged-in user's username before being
        sent. After the server accepts the change, if a ``keystore`` is provided
        its private keys are re-wrapped under a KEK derived from the *cleartext*
        ``new`` password (``Keystore.change_password``), so the user is not
        locked out of their own keys. The server call is authoritative and runs
        first; the local re-wrap follows only on success.
        """
        username = self.session.username
        result = self.api.change_password(
            derive_auth_hash(current, username),
            derive_auth_hash(new, username),
        )
        if keystore is not None:
            keystore.change_password(current, new)
        return result
