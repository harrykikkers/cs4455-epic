"""Base HTTP client.

Owns the ``requests`` session, attaches auth headers from the
:class:`~secure_messenger_client.session.Session`, enforces the configured
timeout/TLS settings, and maps status codes onto the exception hierarchy in
:mod:`secure_messenger_client.errors`. Route-group wrappers (``auth``,
``messages``, ``keys``) build on this and expose one method per endpoint.

Note: the GUI still calls ``requests`` directly today — wiring it through
this client (and the service layer) is the next migration step.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

import config
from errors import NetworkError, exception_for_status
from session import Session


class BaseClient:
    def __init__(self, session: Optional[Session] = None,
                 base_url: Optional[str] = None):
        self.session = session or Session()
        self.base_url = (base_url or config.BASE_URL).rstrip("/")
        self._http = requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = {**self.session.auth_header(), **kwargs.pop("headers", {})}
        try:
            resp = self._http.request(
                method, url,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
                verify=config.VERIFY_SSL,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc

        if not resp.ok:
            raise exception_for_status(resp.status_code)(self._error_message(resp))

        if resp.content:
            return resp.json()
        return None

    @staticmethod
    def _error_message(resp: requests.Response) -> str:
        try:
            return resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            return resp.text or f"HTTP {resp.status_code}"

    def _get(self, path: str, **kw: Any) -> Any:
        return self._request("GET", path, **kw)

    def _post(self, path: str, **kw: Any) -> Any:
        return self._request("POST", path, **kw)

    def _put(self, path: str, **kw: Any) -> Any:
        return self._request("PUT", path, **kw)

    def _delete(self, path: str, **kw: Any) -> Any:
        return self._request("DELETE", path, **kw)
