const KeyService = require('../../src/services/KeyService');
const KeyRepository = require('../../src/repositories/KeyRepository');
const { ConflictError, NotFoundError } = require('../../src/utils/errors');
const { makeFakePool } = require('../helpers/fakePool');

/**
 * Every test below wires KeyService with:
 *   - the real KeyRepository class (src/repositories/KeyRepository.js)
 *   - fake mysql2 pool whose only job is to back the repo with an
 *     in-memory store (tests/helpers/fakePool.js)
 *
 * Nothing in src/ is stubbed — the service runs its real flows: real TOFU
 * decision tree, real transactional publish through the production
 * repository code (the fake pool routes pool.execute + getConnection).
 */

function build() {
  const pool = makeFakePool();
  const keyRepo = new KeyRepository(pool);
  const svc = new KeyService(keyRepo);
  return { pool, svc };
}

// Seed a user row directly so the listPublicKeys JOIN has a counterpart.
// Bypasses AuthService to keep these tests focused on the key flow.
function seedUser(pool, userId, username) {
  pool._store.set(userId, {
    user_id: userId,
    username,
    password_hash: 'unused',
    password_changed_at: new Date(),
    created_at: new Date(),
  });
}

describe('KeyService', () => {
  describe('publishKey', () => {
    test('pins the first key for a user/keyType', async () => {
      const { svc } = build();

      const result = await svc.publishKey({
        userId: 'user-1',
        publicKey: 'alice-key-v1',
        keyType: 'x25519',
      });

      expect(result).toEqual({ status: 'pinned', version: 1 });

      const stored = await svc.getPublicKeyByType('user-1', 'x25519');
      expect(stored.publicKey).toBe('alice-key-v1');
      expect(stored.version).toBe(1);
    });

    test('treats publishing the same key as idempotent', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'same-key',
        keyType: 'x25519',
      });

      const result = await svc.publishKey({
        userId: 'user-1',
        publicKey: 'same-key',
        keyType: 'x25519',
      });

      expect(result).toEqual({ status: 'unchanged', version: 1 });
    });

    test('rejects rotation without acknowledgement and leaves the pinned key intact', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'old-key',
        keyType: 'x25519',
      });

      await expect(
        svc.publishKey({
          userId: 'user-1',
          publicKey: 'new-key',
          keyType: 'x25519',
        })
      ).rejects.toBeInstanceOf(ConflictError);

      // Pinned key must NOT be overwritten by a rejected rotation, and no
      // history row should have been written either.
      const current = await svc.getPublicKeyByType('user-1', 'x25519');
      expect(current.publicKey).toBe('old-key');
      expect(current.version).toBe(1);

      const history = await svc.getKeyHistory('user-1', 'x25519');
      expect(history).toEqual([]);
    });

    test('treats explicit acknowledgeRotation=false the same as omitting it', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'old-key',
        keyType: 'x25519',
      });

      await expect(
        svc.publishKey({
          userId: 'user-1',
          publicKey: 'new-key',
          keyType: 'x25519',
          acknowledgeRotation: false,
        })
      ).rejects.toBeInstanceOf(ConflictError);
    });

    test('rotates the key when acknowledgement=true and archives the previous key', async () => {
      const { svc } = build();

      // Capture the original creation time so we can verify it is preserved
      // as pinned_at in the history row.
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'key-v1',
        keyType: 'x25519',
      });
      const originalPinnedAt = (await svc.getPublicKeyByType('user-1', 'x25519')).createdAt;

      const result = await svc.publishKey({
        userId: 'user-1',
        publicKey: 'key-v2',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });

      expect(result).toEqual({
        status: 'rotated',
        version: 2,
        previousVersion: 1,
      });

      const current = await svc.getPublicKeyByType('user-1', 'x25519');
      expect(current.publicKey).toBe('key-v2');
      expect(current.version).toBe(2);
      expect(current.rotatedAt).toBeInstanceOf(Date);

      const history = await svc.getKeyHistory('user-1', 'x25519');
      expect(history).toHaveLength(1);
      expect(history[0]).toMatchObject({
        publicKey: 'key-v1',
        keyType: 'x25519',
        version: 1,
        // The audit trail is only useful if pinned_at survives — it is what
        // a client uses to reconcile "when was this key first trusted?".
        pinnedAt: originalPinnedAt,
      });
      expect(history[0].rotatedAt).toBeInstanceOf(Date);
    });

    test('keeps key types isolated within a single user', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'signing-key',
        keyType: 'ed25519',
      });

      // Publishing under a different keyType is a fresh pin, not a rotation.
      const result = await svc.publishKey({
        userId: 'user-1',
        publicKey: 'kem-key',
        keyType: 'x25519',
      });

      expect(result).toEqual({ status: 'pinned', version: 1 });

      const both = await svc.getPublicKeys('user-1');
      expect(both.map((k) => k.keyType).sort()).toEqual(['ed25519', 'x25519']);
    });

    test('increments versions monotonically across multiple rotations', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v1',
        keyType: 'x25519',
      });

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v2',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });

      const result = await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v3',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });

      expect(result).toEqual({
        status: 'rotated',
        version: 3,
        previousVersion: 2,
      });

      const current = await svc.getPublicKeyByType('user-1', 'x25519');
      expect(current.version).toBe(3);
      expect(current.publicKey).toBe('v3');

      const history = await svc.getKeyHistory('user-1', 'x25519');
      expect(history.map((h) => h.publicKey)).toEqual(['v1', 'v2']);
      expect(history.map((h) => h.version)).toEqual([1, 2]);
    });
  });

  describe('getPublicKeys', () => {
    test('returns all current public keys for a user', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'sig-key',
        keyType: 'ed25519',
      });
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'kem-key',
        keyType: 'x25519',
      });

      const keys = await svc.getPublicKeys('user-1');

      expect(keys).toHaveLength(2);
      expect(keys.map((k) => k.keyType).sort()).toEqual(['ed25519', 'x25519']);
    });

    test('throws NotFoundError when user has no keys', async () => {
      const { svc } = build();

      await expect(svc.getPublicKeys('ghost')).rejects.toBeInstanceOf(NotFoundError);
    });
  });

  describe('getPublicKeyByType', () => {
    test('returns a specific key type', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'kem-key',
        keyType: 'x25519',
      });

      const key = await svc.getPublicKeyByType('user-1', 'x25519');
      expect(key.publicKey).toBe('kem-key');
      expect(key.keyType).toBe('x25519');
    });

    test('throws NotFoundError when the requested key type does not exist for the user', async () => {
      const { svc } = build();

      // Pin one type, then ask for a different one.
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'sig-key',
        keyType: 'ed25519',
      });

      await expect(
        svc.getPublicKeyByType('user-1', 'x25519')
      ).rejects.toBeInstanceOf(NotFoundError);
    });
  });

  describe('listPublicKeys', () => {
    test('returns every users key joined with their username', async () => {
      const { pool, svc } = build();
      seedUser(pool, 'user-1', 'alice');
      seedUser(pool, 'user-2', 'bob');

      await svc.publishKey({ userId: 'user-1', publicKey: 'alice-sig', keyType: 'ed25519' });
      await svc.publishKey({ userId: 'user-1', publicKey: 'alice-kem', keyType: 'x25519' });
      await svc.publishKey({ userId: 'user-2', publicKey: 'bob-sig', keyType: 'ed25519' });

      const directory = await svc.listPublicKeys();

      expect(directory).toHaveLength(3);
      expect(directory.map((r) => `${r.username}:${r.keyType}`).sort()).toEqual([
        'alice:ed25519',
        'alice:x25519',
        'bob:ed25519',
      ]);
    });

    test('returns an empty array when no keys are published', async () => {
      const { svc } = build();
      const directory = await svc.listPublicKeys();
      expect(directory).toEqual([]);
    });
  });

  describe('getKeyHistory', () => {
    test('returns an empty array before any rotation (history is legitimately empty)', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v1',
        keyType: 'x25519',
      });

      const history = await svc.getKeyHistory('user-1', 'x25519');
      expect(history).toEqual([]);
    });

    test('returns history ordered by ascending version across multiple rotations', async () => {
      const { svc } = build();

      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v1',
        keyType: 'x25519',
      });
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v2',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v3',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });
      await svc.publishKey({
        userId: 'user-1',
        publicKey: 'v4',
        keyType: 'x25519',
        acknowledgeRotation: true,
      });

      const history = await svc.getKeyHistory('user-1', 'x25519');
      expect(history.map((h) => h.publicKey)).toEqual(['v1', 'v2', 'v3']);
      expect(history.map((h) => h.version)).toEqual([1, 2, 3]);
    });

    test('returns an empty array for an unknown user/keyType pair', async () => {
      const { svc } = build();
      const history = await svc.getKeyHistory('ghost', 'x25519');
      expect(history).toEqual([]);
    });
  });
});
