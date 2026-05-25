"""HTTP client — one module per route group, all over the base client."""

from .client import BaseClient, HealthAPI
from .auth import AuthAPI
from .messages import MessageAPI
from .keys import KeyAPI

__all__ = ["BaseClient", "HealthAPI", "AuthAPI", "MessageAPI", "KeyAPI"]
