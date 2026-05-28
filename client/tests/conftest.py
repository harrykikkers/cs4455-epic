"""Shared fixtures for the client unit suite.

These tests exercise the client's own code in isolation — no running
backend. Network-touching layers (``api``/``services``) are driven with the
``responses`` library or injected fakes; filesystem-touching code uses
pytest's ``tmp_path``.
"""

import pytest

from session import Session


@pytest.fixture
def keystore_path(tmp_path):
    """Path to a keystore file inside an isolated temp dir (not yet created)."""
    return str(tmp_path / "keystore.json")


@pytest.fixture
def session():
    """A fresh, unauthenticated session."""
    return Session()
