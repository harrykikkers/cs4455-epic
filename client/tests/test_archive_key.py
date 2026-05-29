"""Unit tests for the C++ message-store archive key derivation.

These do not need the C++ binary or a backend — they exercise only the
key-derivation helpers added to ``crypto.keystore.Keystore``.
"""

import os

from crypto.keystore import Keystore


def _ks_with_kek(tmp_path):
    ks = Keystore(path=os.path.join(str(tmp_path), "keystore.json"))
    ks._kek = b"\x01" * 32
    return ks


def test_archive_key_hex_format(tmp_path):
    ks = _ks_with_kek(tmp_path)
    hex_key = ks.archive_key_hex()
    assert len(hex_key) == 64
    assert all(c in "0123456789abcdef" for c in hex_key)


def test_archive_key_deterministic(tmp_path):
    ks = _ks_with_kek(tmp_path)
    assert ks.archive_key_hex() == ks.archive_key_hex()
    assert ks.archive_key() == ks.archive_key()


def test_archive_key_domain_separated_from_kek(tmp_path):
    ks = _ks_with_kek(tmp_path)
    assert ks.archive_key() != ks._kek
    assert ks.archive_key_hex() != ks._kek.hex()


def test_archive_key_raises_when_locked(tmp_path):
    ks = Keystore(path=os.path.join(str(tmp_path), "keystore.json"))
    # No _kek set -> locked.
    import pytest
    with pytest.raises(RuntimeError):
        ks.archive_key()
    with pytest.raises(RuntimeError):
        ks.archive_key_hex()


def test_archive_path_is_keystore_sibling(tmp_path):
    p = os.path.join(str(tmp_path), "keystore.json")
    ks = Keystore(path=p)
    assert ks.archive_path() == p + ".archive"
