"""Wrappers for /api/keys/* endpoints.

Driven by :class:`~services.key_service.KeyService`: ``AuthService.login``
publishes the user's public keys via ``publish`` on every login, and the
message pipeline fetches + pins peer keys via ``get`` / ``history``.
"""

from __future__ import annotations

from typing import Any

from .client import BaseClient


class KeyAPI(BaseClient):
    def publish(self, public_key: str, key_type: str,
                acknowledge_rotation: bool = False) -> Any:
        """POST /api/keys — publish own public key."""
        return self._post("/api/keys", json={
            "publicKey": public_key,
            "keyType": key_type,
            "acknowledgeRotation": acknowledge_rotation,
        })

    def get(self, user_id: str) -> Any:
        """GET /api/keys/:user_id — a single user's current key."""
        return self._get(f"/api/keys/{user_id}")

    def history(self, user_id: str, key_type: str) -> Any:
        """GET /api/keys/:user_id/history/:key_type — append-only rotation log."""
        return self._get(f"/api/keys/{user_id}/history/{key_type}")
