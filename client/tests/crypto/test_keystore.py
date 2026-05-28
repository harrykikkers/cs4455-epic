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


@pytest.fixture
def unlocked_keystore(fresh_keystore):
    fresh_keystore.unlock(PASSWORD)
    return fresh_keystore


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
        ks.unlock(PASSWORD)
        assert ks._kek is not None

    def test_unlock_wrong_password_raises(self, fresh_keystore):
        ks = Keystore(path=fresh_keystore.path)
        with pytest.raises(Exception):
            ks.unlock(WRONG_PASSWORD)

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
        with pytest.raises(Exception):
            ks2.unlock(WRONG_PASSWORD)


class TestPrivateKeys:

    def test_private_keys_raises_before_unlock(self, fresh_keystore):
        with pytest.raises(RuntimeError):
            fresh_keystore.private_keys()

    def test_private_keys_returns_x25519_and_ed25519(self, unlocked_keystore):
        keys = unlocked_keystore.private_keys()
        assert "x25519" in keys and "ed25519" in keys

    def test_private_keys_are_32_bytes(self, unlocked_keystore):
        keys = unlocked_keystore.private_keys()
        assert len(keys["x25519"]) == 32
        assert len(keys["ed25519"]) == 32

    def test_same_password_recovers_same_keys(self, fresh_keystore):
        ks1 = Keystore(path=fresh_keystore.path)
        ks1.unlock(PASSWORD)
        ks2 = Keystore(path=fresh_keystore.path)
        ks2.unlock(PASSWORD)
        assert ks1.private_keys() == ks2.private_keys()

    def test_two_keystores_have_different_keys(self, tmp_path):
        path_a = str(tmp_path / "ks_a.json")
        path_b = str(tmp_path / "ks_b.json")
        Keystore(path=path_a).create(PASSWORD)
        Keystore(path=path_b).create(PASSWORD)
        ks_a = Keystore(path=path_a); ks_a.unlock(PASSWORD)
        ks_b = Keystore(path=path_b); ks_b.unlock(PASSWORD)
        assert ks_a.private_keys()["x25519"] != ks_b.private_keys()["x25519"]


class TestPeerKeyPinning:

    def test_unknown_user_returns_none(self, fresh_keystore):
        assert fresh_keystore.pinned_peer_key("unknown", "x25519") is None

    def test_pin_and_lookup(self, fresh_keystore):
        fresh_keystore.pin_peer_key("user-123", "x25519", "pub-x")
        assert fresh_keystore.pinned_peer_key("user-123", "x25519") == "pub-x"

    def test_x25519_and_ed25519_independent(self, fresh_keystore):
        fresh_keystore.pin_peer_key("user-123", "x25519", "pub-x")
        fresh_keystore.pin_peer_key("user-123", "ed25519", "pub-e")
        assert fresh_keystore.pinned_peer_key("user-123", "x25519") == "pub-x"
        assert fresh_keystore.pinned_peer_key("user-123", "ed25519") == "pub-e"

    def test_pin_persists_across_instances(self, fresh_keystore):
        fresh_keystore.pin_peer_key("user-abc", "x25519", "persistent-pub")
        ks2 = Keystore(path=fresh_keystore.path)
        assert ks2.pinned_peer_key("user-abc", "x25519") == "persistent-pub"

    def test_overwrite_pinned_key(self, fresh_keystore):
        fresh_keystore.pin_peer_key("user-123", "x25519", "old-pub")
        fresh_keystore.pin_peer_key("user-123", "x25519", "new-pub")
        assert fresh_keystore.pinned_peer_key("user-123", "x25519") == "new-pub"
