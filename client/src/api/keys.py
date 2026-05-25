"""Wrappers for /api/keys/* endpoints.

Payload field names are best-effort until the key-publish flow is built
client-side (the GUI does not exercise these yet); adjust to match the
backend contract when wiring up ``KeyService``.
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

    def list_all(self) -> Any:
        """GET /api/keys — directory of all users' keys."""
        return self._get("/api/keys")

    def get(self, user_id: str) -> Any:
        """GET /api/keys/:user_id — a single user's current key."""
        return self._get(f"/api/keys/{user_id}")

    def history(self, user_id: str, key_type: str) -> Any:
        """GET /api/keys/:user_id/history/:key_type — append-only rotation log."""
        return self._get(f"/api/keys/{user_id}/history/{key_type}")
