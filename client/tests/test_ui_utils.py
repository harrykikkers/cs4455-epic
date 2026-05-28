"""Unit tests for ui.utils._write_cache — the local indexer cache.

Decrypted plaintext and internal UI flags must never reach the on-disk cache:
the C++ ``zebra-store`` indexer only needs the ciphertext envelope, and cleartext
belongs solely in the KEK-encrypted keystore cache. The source dicts must also be
left untouched so in-session display still has the plaintext.
"""
import json

import pytest

import ui.utils as utils


@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / "messages.json"
    monkeypatch.setattr(utils, "_CACHE_FILE", path)
    return path


def test_strips_plaintext_and_internal_flags(cache_file):
    inbox = [{
        "messageId": "m1", "senderId": "alice", "ciphertext": "CT", "nonce": "N",
        "createdAt": "2026-01-01", "plaintext": "TOPSECRET",
        "_mine": False, "_key_warning": True,
    }]
    sent = [{
        "messageId": "m2", "recipientId": "bob", "ciphertext": "CT2",
        "plaintext": "ALSO SECRET", "_mine": True, "_forwarded_to": [{"u": "x"}],
    }]

    utils._write_cache(inbox, sent)

    blob = cache_file.read_text()
    assert "TOPSECRET" not in blob and "ALSO SECRET" not in blob

    written = json.loads(blob)
    for m in written:
        assert "plaintext" not in m
        assert not any(k.startswith("_") for k in m)
    # Metadata the indexer needs survives.
    assert {m["messageId"] for m in written} == {"m1", "m2"}
    assert written[0]["ciphertext"] == "CT"


def test_does_not_mutate_source_dicts(cache_file):
    inbox = [{"messageId": "m1", "ciphertext": "CT",
              "plaintext": "SECRET", "_mine": False}]

    utils._write_cache(inbox, [])

    # Originals keep their plaintext / flags for in-session display.
    assert inbox[0]["plaintext"] == "SECRET"
    assert inbox[0]["_mine"] is False
