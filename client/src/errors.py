"""Custom exception hierarchy for the client.

The base HTTP client (:mod:`secure_messenger_client.api.client`) maps server
status codes onto these exceptions; the UI catches the base
:class:`ClientError` and shows a friendly message in the status bar.
"""

from __future__ import annotations


class ClientError(Exception):
    """Base class for all client-side errors."""


class ValidationError(ClientError):
    """400 — malformed request or failed input validation."""


class AuthenticationError(ClientError):
    """401 — missing, invalid, or expired credentials."""


class AuthorizationError(ClientError):
    """403 — authenticated but not permitted."""


class NotFoundError(ClientError):
    """404 — resource does not exist."""


class ConflictError(ClientError):
    """409 — duplicate resource (username taken, duplicate seq_no, ...)."""


class RateLimitError(ClientError):
    """429 — rate limit exceeded."""


class ServerError(ClientError):
    """5xx — backend failure."""


class NetworkError(ClientError):
    """Transport-level failure (timeout, DNS, refused connection)."""


_STATUS_EXCEPTIONS: dict[int, type[ClientError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: AuthorizationError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}


def exception_for_status(status_code: int) -> type[ClientError]:
    """Return the exception class that maps to an HTTP status code."""
    if status_code in _STATUS_EXCEPTIONS:
        return _STATUS_EXCEPTIONS[status_code]
    if status_code >= 500:
        return ServerError
    return ClientError
