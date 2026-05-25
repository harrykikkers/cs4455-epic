"""Public-key DTO (key directory + rotation history entries)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PublicKey:
    user_id: str
    key_type: str          # "x25519" | "ed25519"
    public_key: str        # base64 / hex encoded
    created_at: Optional[str] = None
