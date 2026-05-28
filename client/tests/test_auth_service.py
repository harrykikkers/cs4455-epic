"""Unit tests for AuthService.change_password (services/auth_service.py).

Verifies the client sends the Argon2id auth-hash (never the cleartext password)
and re-wraps the local keystore under the new password after the server accepts.
"""
from unittest.mock import MagicMock

import pytest

from crypto.kdf import derive_auth_hash
from services.auth_service import AuthService
from session import Session

OLD = "old-cleartext-pw-123"
NEW = "new-cleartext-pw-456"


@pytest.fixture
def svc():
    api = MagicMock()
    session = Session()
    session.set("tok", "uid", "alice")
    return AuthService(api=api, session=session), api


def test_sends_auth_hashes_not_cleartext(svc):
    service, api = svc
    service.change_password(OLD, NEW)

    api.change_password.assert_called_once_with(
        derive_auth_hash(OLD, "alice"),
        derive_auth_hash(NEW, "alice"),
    )
    # The cleartext password must never be what crosses the wire.
    sent = api.change_password.call_args.args
    assert OLD not in sent and NEW not in sent


def test_rewraps_keystore_with_cleartext_when_provided(svc):
    service, api = svc
    ks = MagicMock()
    service.change_password(OLD, NEW, keystore=ks)
    # The keystore re-wrap needs the CLEARTEXT (KEK derivation), unlike the server.
    ks.change_password.assert_called_once_with(OLD, NEW)


def test_server_call_precedes_keystore_rewrap(svc):
    service, api = svc
    ks = MagicMock()
    calls = []
    api.change_password.side_effect = lambda *a: calls.append("server")
    ks.change_password.side_effect = lambda *a: calls.append("keystore")
    service.change_password(OLD, NEW, keystore=ks)
    assert calls == ["server", "keystore"]


def test_no_keystore_still_changes_on_server(svc):
    service, api = svc
    service.change_password(OLD, NEW)  # keystore omitted
    assert api.change_password.called
