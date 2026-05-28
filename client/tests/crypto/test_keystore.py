"""Tests for local key storage and TOFU pinning (crypto/keystore.py)."""
import pytest
from crypto.keystore import Keystore

PASSWORD = "TestKeystorePass99!"
WRONG_PASSWORD = "WrongPassword000!"


@pytest.fixture
def fresh_keystore(tmp_path):
    path = str(tmp_path / "keystore.json")
    ks = Keystore(path=path)
    ks.create(PASSWORD)
    return ks


class TestCreate:

    def test_create_writes_file(self, tmp_path):
        path = str(tmp_path / "keystore.json")
        ks = Keystore(path=path)
        ks.create(PASSWORD)
        assert ks.exists()

    def test_create_twice_raises(self, fresh_keystore):
        with pytest.raises(FileExistsError):
            fresh_keystore.create(PASSWORD)

    def test_kek_cached_after_create(self, fresh_keystore):
        assert fresh_keystore._kek is not None
        assert len(fresh_keystore._kek) == 32


class TestUnlock:

    def test_unlock_correct_password_succeeds(self, fresh_keystore):
        ks = Keystore(path=fresh_keystore.path)
        ks.unlock(PASSWORD)  # must not raise
        assert ks._kek is not None

    def test_kek_is_deterministic(self, fresh_keystore):
        ks1 = Keystore(path=fresh_keystore.path)
        ks1.unlock(PASSWORD)
        ks2 = Keystore(path=fresh_keystore.path)
        ks2.unlock(PASSWORD)
        assert ks1._kek == ks2._kek

    def test_different_passwords_give_different_kek(self, fresh_keystore):
        ks1 = Keystore(path=fresh_keystore.path)
        ks1.unlock(PASSWORD)
        ks2 = Keystore(path=fresh_keystore.path)
        ks2.unlock(WRONG_PASSWORD)
        assert ks1._kek != ks2._kek


class TestPlanned:
    """These methods are not yet implemented — verify they raise NotImplementedError."""

    def test_private_keys_not_implemented(self, fresh_keystore):
        with pytest.raises(NotImplementedError):
            fresh_keystore.private_keys()

    def test_pin_peer_key_not_implemented(self, fresh_keystore):
        with pytest.raises(NotImplementedError):
            fresh_keystore.pin_peer_key("user-123", "x25519", "somepub")

    def test_pinned_peer_key_not_implemented(self, fresh_keystore):
        with pytest.raises(NotImplementedError):
            fresh_keystore.pinned_peer_key("user-123", "x25519")
