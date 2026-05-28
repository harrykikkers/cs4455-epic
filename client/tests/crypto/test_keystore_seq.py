"""Tests for per-peer sequence counters in the keystore (crypto/keystore.py).

Properties verified:
- next_send_seq returns 1, 2, 3 ... monotonically for the same recipient.
- Send counters are independent per recipient.
- last_recv_seq is None until set, then returns what set_recv_seq stored.
- Both send and receive counters persist across new Keystore instances.
"""
import pytest
from crypto.keystore import Keystore

PASSWORD = "TestKeystorePass99!"


@pytest.fixture
def keystore_path(tmp_path):
    path = str(tmp_path / "keystore.json")
    Keystore(path=path).create(PASSWORD)
    return path


@pytest.fixture
def keystore(keystore_path):
    return Keystore(path=keystore_path)


class TestSequenceCounters:

    def test_next_send_seq_is_monotonic(self, keystore):
        assert keystore.next_send_seq("bob") == 1
        assert keystore.next_send_seq("bob") == 2
        assert keystore.next_send_seq("bob") == 3

    def test_send_counters_independent_per_recipient(self, keystore):
        assert keystore.next_send_seq("bob") == 1
        assert keystore.next_send_seq("carol") == 1
        assert keystore.next_send_seq("bob") == 2
        assert keystore.next_send_seq("carol") == 2
        assert keystore.next_send_seq("bob") == 3

    def test_last_recv_seq_none_initially(self, keystore):
        assert keystore.last_recv_seq("alice") is None

    def test_set_recv_seq_round_trip(self, keystore):
        keystore.set_recv_seq("alice", 7)
        assert keystore.last_recv_seq("alice") == 7

    def test_set_recv_seq_overwrites(self, keystore):
        keystore.set_recv_seq("alice", 7)
        keystore.set_recv_seq("alice", 12)
        assert keystore.last_recv_seq("alice") == 12

    def test_recv_counters_independent_per_sender(self, keystore):
        keystore.set_recv_seq("alice", 3)
        keystore.set_recv_seq("dave", 9)
        assert keystore.last_recv_seq("alice") == 3
        assert keystore.last_recv_seq("dave") == 9

    def test_send_seq_persists_across_instances(self, keystore_path):
        ks1 = Keystore(path=keystore_path)
        assert ks1.next_send_seq("bob") == 1
        assert ks1.next_send_seq("bob") == 2
        ks2 = Keystore(path=keystore_path)
        assert ks2.next_send_seq("bob") == 3

    def test_recv_seq_persists_across_instances(self, keystore_path):
        Keystore(path=keystore_path).set_recv_seq("alice", 42)
        ks2 = Keystore(path=keystore_path)
        assert ks2.last_recv_seq("alice") == 42


NEW_PASSWORD = "BrandNewKeystorePass42!"


class TestChangePassword:

    def test_old_password_no_longer_unlocks(self, keystore_path):
        Keystore(path=keystore_path).change_password(PASSWORD, NEW_PASSWORD)
        with pytest.raises(Exception):
            Keystore(path=keystore_path).unlock(PASSWORD)

    def test_new_password_unlocks(self, keystore_path):
        Keystore(path=keystore_path).change_password(PASSWORD, NEW_PASSWORD)
        # Must not raise — the new password's KEK now wraps the keys.
        Keystore(path=keystore_path).unlock(NEW_PASSWORD)

    def test_public_keys_unchanged(self, keystore_path):
        ks = Keystore(path=keystore_path)
        before = ks.public_keys()
        ks.change_password(PASSWORD, NEW_PASSWORD)
        assert Keystore(path=keystore_path).public_keys() == before

    def test_private_keys_recovered_identically(self, keystore_path):
        ks_before = Keystore(path=keystore_path)
        ks_before.unlock(PASSWORD)
        priv_before = dict(ks_before.private_keys())

        Keystore(path=keystore_path).change_password(PASSWORD, NEW_PASSWORD)

        ks_after = Keystore(path=keystore_path)
        ks_after.unlock(NEW_PASSWORD)
        assert ks_after.private_keys() == priv_before

    def test_in_memory_session_keeps_working(self, keystore_path):
        # change_password updates the in-memory keys so the unlocked session
        # keeps working without a re-unlock.
        ks = Keystore(path=keystore_path)
        ks.unlock(PASSWORD)
        priv_before = dict(ks.private_keys())
        ks.change_password(PASSWORD, NEW_PASSWORD)
        assert ks.private_keys() == priv_before

    def test_wrong_old_password_raises(self, keystore_path):
        with pytest.raises(Exception):
            Keystore(path=keystore_path).change_password("WrongOldPass!!", NEW_PASSWORD)


class TestMessageCache:
    """The KEK-encrypted plaintext cache that survives a restart."""

    def _unlocked(self, path, password=PASSWORD):
        ks = Keystore(path=path)
        ks.unlock(password)
        return ks

    def test_round_trip(self, keystore_path):
        ks = self._unlocked(keystore_path)
        ks.save_message_cache({"m1": "hello", "m2": "world"})
        assert ks.load_message_cache() == {"m1": "hello", "m2": "world"}

    def test_persists_across_instances(self, keystore_path):
        self._unlocked(keystore_path).save_message_cache({"m1": "hi"})
        assert self._unlocked(keystore_path).load_message_cache() == {"m1": "hi"}

    def test_missing_cache_returns_empty(self, keystore_path):
        assert self._unlocked(keystore_path).load_message_cache() == {}

    def test_locked_keystore_returns_empty(self, keystore_path):
        # A fresh, un-unlocked instance has no KEK → cannot read the cache.
        self._unlocked(keystore_path).save_message_cache({"m1": "hi"})
        assert Keystore(path=keystore_path).load_message_cache() == {}

    def test_locked_keystore_save_is_noop(self, keystore_path):
        Keystore(path=keystore_path).save_message_cache({"m1": "hi"})  # no KEK
        assert self._unlocked(keystore_path).load_message_cache() == {}

    def test_cache_file_is_encrypted_at_rest(self, keystore_path):
        import pathlib
        ks = self._unlocked(keystore_path)
        ks.save_message_cache({"m1": "TOPSECRETPLAINTEXT"})
        raw = pathlib.Path(ks._cache_path()).read_text()
        assert "TOPSECRETPLAINTEXT" not in raw

    def test_survives_password_change(self, keystore_path):
        # change_password re-wraps the cache under the new KEK, so prior
        # plaintext stays readable (the replay counters persist regardless).
        self._unlocked(keystore_path).save_message_cache({"m1": "secret"})
        Keystore(path=keystore_path).change_password(PASSWORD, NEW_PASSWORD)
        ks = Keystore(path=keystore_path)
        ks.unlock(NEW_PASSWORD)
        assert ks.load_message_cache() == {"m1": "secret"}
