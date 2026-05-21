/**
 * A fake mysql2 pool for tests. Only pool.execute() and pool.getConnection()
 * are implemented — these are the only surfaces of mysql2 that the project's
 * repositories touch. Everything that calls into them (UserRepository,
 * KeyRepository) runs its real body from src/repositories/.
 *
 * Storage is in-memory. The dispatcher matches on the SQL string that the
 * real repositories emit, so adding or changing a query in a repository
 * will require adding a matching branch here.
 *
 * Connections returned by getConnection() share the same underlying store
 * but snapshot it on beginTransaction() so rollback() restores the prior
 * state — this lets the KeyRepository.publishKey transaction be exercised
 * end-to-end, including failure paths.
 */
function makeFakePool() {
  const users = new Map(); // user_id -> row
  const publicKeys = new Map(); // `${user_id}|${key_type}` -> row
  const publicKeyHistory = []; // append-only

  function findByUsername(username) {
    for (const row of users.values()) {
      if (row.username === username) return row;
    }
    return undefined;
  }

  async function execute(sql, params = []) {
    const normalised = sql.replace(/\s+/g, ' ').trim();

    // ===== users =====

    // INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, NOW())
    if (/^INSERT INTO users/i.test(normalised)) {
      const [userId, username, passwordHash] = params;
      if (findByUsername(username)) {
        const err = new Error("Duplicate entry for key 'users.username'");
        err.code = 'ER_DUP_ENTRY';
        throw err;
      }
      const now = new Date();
      users.set(userId, {
        user_id: userId,
        username,
        password_hash: passwordHash,
        password_changed_at: now,
        created_at: now,
      });
      return [{ affectedRows: 1 }, []];
    }

    // SELECT ... FROM users WHERE user_id = ?
    if (/^SELECT .* FROM users WHERE user_id = \?/i.test(normalised)) {
      const [userId] = params;
      const row = users.get(userId);
      return [row ? [row] : [], []];
    }

    // SELECT ... FROM users WHERE username = ?
    if (/^SELECT .* FROM users WHERE username = \?/i.test(normalised)) {
      const [username] = params;
      const row = findByUsername(username);
      return [row ? [row] : [], []];
    }

    // SELECT user_id, username, created_at FROM users ORDER BY username
    if (/^SELECT .* FROM users ORDER BY username/i.test(normalised)) {
      const rows = [...users.values()]
        .map(({ user_id, username, created_at }) => ({ user_id, username, created_at }))
        .sort((a, b) => a.username.localeCompare(b.username));
      return [rows, []];
    }

    // UPDATE users SET password_hash = ?, password_changed_at = NOW() WHERE user_id = ?
    if (/^UPDATE users SET password_hash/i.test(normalised)) {
      const [passwordHash, userId] = params;
      const row = users.get(userId);
      if (row) {
        row.password_hash = passwordHash;
        row.password_changed_at = new Date();
      }
      return [{ affectedRows: row ? 1 : 0 }, []];
    }

    // DELETE FROM users WHERE user_id = ?
    if (/^DELETE FROM users WHERE user_id = \?/i.test(normalised)) {
      const [userId] = params;
      const existed = users.delete(userId);
      return [{ affectedRows: existed ? 1 : 0 }, []];
    }

    // ===== public_keys (directory listing) =====

    // SELECT pk.user_id, pk.public_key, pk.key_type, pk.version, u.username
    //   FROM public_keys pk JOIN users u ON u.user_id = pk.user_id
    if (/^SELECT .* FROM public_keys pk JOIN users u/i.test(normalised)) {
      const rows = [];
      for (const r of publicKeys.values()) {
        const u = users.get(r.user_id);
        if (!u) continue; // FK in prod; defensive here
        rows.push({
          user_id: r.user_id,
          public_key: r.public_key,
          key_type: r.key_type,
          version: r.version,
          username: u.username,
        });
      }
      return [rows, []];
    }

    // ===== public_keys (per-user lookups) =====
    //
    // Two variants share the same WHERE clause:
    //   - publishKey()'s SELECT ... FOR UPDATE
    //   - getPublicKeyByType()'s plain SELECT
    // FOR UPDATE is a no-op in this single-threaded fake.
    //
    // Rows are cloned on the way out — real mysql2 deserialises a fresh
    // object per query, so the repo can hold an old snapshot in `current`
    // even after a later UPDATE writes the row. Returning live references
    // would silently mutate `current` underneath the repo.
    if (/^SELECT .* FROM public_keys WHERE user_id = \? AND key_type = \?( FOR UPDATE)?$/i.test(normalised)) {
      const [userId, keyType] = params;
      const row = publicKeys.get(`${userId}|${keyType}`);
      return [row ? [{ ...row }] : [], []];
    }

    // SELECT ... FROM public_keys WHERE user_id = ?
    if (/^SELECT .* FROM public_keys WHERE user_id = \?$/i.test(normalised)) {
      const [userId] = params;
      const rows = [...publicKeys.values()]
        .filter((r) => r.user_id === userId)
        .map((r) => ({ ...r }));
      return [rows, []];
    }

    // INSERT INTO public_keys (id, user_id, public_key, key_type, version) VALUES (?, ?, ?, ?, 1)
    if (/^INSERT INTO public_keys/i.test(normalised)) {
      const [id, userId, publicKey, keyType] = params;
      const compositeKey = `${userId}|${keyType}`;
      if (publicKeys.has(compositeKey)) {
        const err = new Error("Duplicate entry for key 'public_keys.uniq_user_keytype'");
        err.code = 'ER_DUP_ENTRY';
        throw err;
      }
      publicKeys.set(compositeKey, {
        id,
        user_id: userId,
        public_key: publicKey,
        key_type: keyType,
        version: 1,
        created_at: new Date(),
        rotated_at: null,
      });
      return [{ affectedRows: 1 }, []];
    }

    // UPDATE public_keys SET public_key = ?, version = ?, rotated_at = NOW(), created_at = NOW()
    //   WHERE user_id = ? AND key_type = ?
    if (/^UPDATE public_keys SET public_key/i.test(normalised)) {
      const [publicKey, version, userId, keyType] = params;
      const row = publicKeys.get(`${userId}|${keyType}`);
      if (row) {
        const now = new Date();
        row.public_key = publicKey;
        row.version = version;
        row.rotated_at = now;
        row.created_at = now;
      }
      return [{ affectedRows: row ? 1 : 0 }, []];
    }

    // ===== public_key_history =====

    // INSERT INTO public_key_history (id, user_id, public_key, key_type, version, pinned_at) VALUES ...
    if (/^INSERT INTO public_key_history/i.test(normalised)) {
      const [id, userId, publicKey, keyType, version, pinnedAt] = params;
      publicKeyHistory.push({
        id,
        user_id: userId,
        public_key: publicKey,
        key_type: keyType,
        version,
        pinned_at: pinnedAt,
        rotated_at: new Date(),
      });
      return [{ affectedRows: 1 }, []];
    }

    // SELECT ... FROM public_key_history WHERE user_id = ? AND key_type = ? ORDER BY version ASC
    if (/^SELECT .* FROM public_key_history WHERE user_id = \? AND key_type = \?/i.test(normalised)) {
      const [userId, keyType] = params;
      const rows = publicKeyHistory
        .filter((r) => r.user_id === userId && r.key_type === keyType)
        .sort((a, b) => a.version - b.version)
        .map((r) => ({ ...r }));
      return [rows, []];
    }

    throw new Error(`fakePool: no route matched SQL: ${normalised}`);
  }

  function getConnection() {
    // Snapshot the mutable stores on beginTransaction so rollback() can
    // restore them. Rows are plain objects, so a shallow clone is sufficient.
    let snapshot = null;

    function snapshotStores() {
      return {
        publicKeys: new Map([...publicKeys].map(([k, v]) => [k, { ...v }])),
        publicKeyHistory: publicKeyHistory.map((r) => ({ ...r })),
      };
    }

    function restoreStores(s) {
      publicKeys.clear();
      for (const [k, v] of s.publicKeys) publicKeys.set(k, v);
      publicKeyHistory.length = 0;
      publicKeyHistory.push(...s.publicKeyHistory);
    }

    return {
      execute,
      async beginTransaction() {
        snapshot = snapshotStores();
      },
      async commit() {
        snapshot = null;
      },
      async rollback() {
        if (snapshot) {
          restoreStores(snapshot);
          snapshot = null;
        }
      },
      release() {},
    };
  }

  return {
    execute,
    getConnection,
    // Test-only escape hatch: rewrite password_changed_at to a chosen
    // instant so JWT-invalidation tests don't have to sleep across a
    // second boundary to trigger the comparison.
    _setPasswordChangedAt(userId, date) {
      const row = users.get(userId);
      if (row) row.password_changed_at = date;
    },
    _store: users,
    _publicKeysStore: publicKeys,
    _publicKeyHistoryStore: publicKeyHistory,
  };
}

module.exports = { makeFakePool };
