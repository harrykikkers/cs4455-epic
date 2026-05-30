"""Wrappers for /api/auth/* endpoints."""

from __future__ import annotations

from typing import Any

from .client import BaseClient


class AuthAPI(BaseClient):
    def register(self, username: str, password: str) -> Any:
        """POST /api/auth/register — returns ``{ user_id }``."""
        return self._post("/api/auth/register",
                          json={"username": username, "password": password})

    def login(self, username: str, password: str) -> Any:
        """POST /api/auth/login — returns token + user; caller stores it."""
        return self._post("/api/auth/login",
                          json={"username": username, "password": password})

    def change_password(self, current: str, new: str) -> Any:
        """PUT /api/auth/password — requires an authenticated session."""
        return self._put("/api/auth/password",
                         json={"currentPassword": current, "newPassword": new})

    def get_user(self, username: str) -> Any:
        """GET /api/auth/user?username=… — look up a user by username.

        Used to resolve a recipient (New Chat / Forward) to a user id. Raises
        ``NotFoundError`` (404) if no such user exists.
        """
        return self._get("/api/auth/user", params={"username": username})
