"""In-memory session state — JWT and current-user info between calls.

Shared by the service layer; mutations are guarded by a lock so background
worker threads (network/crypto) can read and update it safely.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    token: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def is_authenticated(self) -> bool:
        return self.token is not None

    def set(self, token: str, user_id: str, username: str) -> None:
        with self._lock:
            self.token = token
            self.user_id = user_id
            self.username = username

    def clear(self) -> None:
        with self._lock:
            self.token = None
            self.user_id = None
            self.username = None

    def auth_header(self) -> dict[str, str]:
        with self._lock:
            if not self.token:
                return {}
            return {"Authorization": f"Bearer {self.token}"}
