/**
 * A fake mysql2 pool for tests. Only pool.execute() is implemented — and
 * that is the only function in the test path that does NOT come from the
 * project's own source. Everything that calls into it (UserRepository.create,
 * findByUsername, updatePassword, etc.) runs its real body from
 * src/repositories/UserRepository.js.
 *
 * Storage is an in-memory Map. The function dispatches on the SQL string
 * that the real UserRepository emits, so adding/changing a query in the
 * repository will require adding a matching branch here.
 */
function makeFakePool() {
  const users = new Map(); // user_id -> row

  function findByUsername(username) {
    for (const row of users.values()) {
      if (row.username === username) return row;
    }
    return undefined;
  }

  async function execute(sql, params = []) {
    const normalised = sql.replace(/\s+/g, ' ').trim();

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

    throw new Error(`fakePool: no route matched SQL: ${normalised}`);
  }

  return {
    execute,
    // Test-only escape hatch: rewrite password_changed_at to a chosen
    // instant so JWT-invalidation tests don't have to sleep across a
    // second boundary to trigger the comparison.
    _setPasswordChangedAt(userId, date) {
      const row = users.get(userId);
      if (row) row.password_changed_at = date;
    },
    _store: users,
  };
}

module.exports = { makeFakePool };
