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
  const messages = new Map(); // message_id -> row
  const messageShares = []; // share rows (append-only; revoked_at flips in place)
  const blockchainRecords = []; // chain rows

  function findByUsername(username) {
    for (const row of users.values()) {
      if (row.username === username) return row;
    }
    return undefined;
  }

  // LIMIT/OFFSET are interpolated into the SQL string by MessageRepository
  // (mysql2 rejects them as bound params), so we parse them back out here.
  function limitOffset(sql, rows) {
    const m = sql.match(/LIMIT (\d+) OFFSET (\d+)/i);
    if (!m) return rows;
    const lim = Number.parseInt(m[1], 10);
    const off = Number.parseInt(m[2], 10);
    return rows.slice(off, off + lim);
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

    // ===== messages =====

    // INSERT INTO messages (...) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())
    if (/^INSERT INTO messages/i.test(normalised)) {
      const [messageId, senderId, recipientId, ciphertext, nonce, signature, seqNo, digestHash] = params;
      // Unique (recipient_id, nonce) — the server-side replay backstop.
      for (const row of messages.values()) {
        if (row.recipient_id === recipientId && row.nonce === nonce) {
          const err = new Error("Duplicate entry for key 'messages.uniq_recipient_nonce'");
          err.code = 'ER_DUP_ENTRY';
          throw err;
        }
      }
      messages.set(messageId, {
        message_id: messageId,
        sender_id: senderId,
        recipient_id: recipientId,
        ciphertext,
        nonce,
        signature,
        seq_no: seqNo,
        digest_hash: digestHash,
        chain_status: 'pending', // DDL default
        created_at: new Date(),
        deleted_at: null,
      });
      return [{ affectedRows: 1 }, []];
    }

    // findById: SELECT m.*, u.username AS sender_username FROM messages m JOIN users u ...
    //           WHERE m.message_id = ? AND m.deleted_at IS NULL
    if (/^SELECT m\.\*, u\.username AS sender_username FROM messages m/i.test(normalised)) {
      const [messageId] = params;
      const row = messages.get(messageId);
      if (!row || row.deleted_at !== null) return [[], []];
      const u = users.get(row.sender_id);
      return [[{ ...row, sender_username: u ? u.username : null }], []];
    }

    // findByRecipient: SELECT m.message_id, m.sender_id, m.ciphertext ... WHERE m.recipient_id = ?
    if (/^SELECT m\.message_id, m\.sender_id, m\.ciphertext/i.test(normalised)) {
      const [recipientId] = params;
      const rows = [...messages.values()]
        .filter((r) => r.recipient_id === recipientId && r.deleted_at === null)
        .sort((a, b) => b.created_at - a.created_at)
        .map((r) => {
          const u = users.get(r.sender_id);
          return {
            message_id: r.message_id, sender_id: r.sender_id, ciphertext: r.ciphertext,
            nonce: r.nonce, signature: r.signature, seq_no: r.seq_no,
            digest_hash: r.digest_hash, chain_status: r.chain_status,
            created_at: r.created_at, sender_username: u ? u.username : null,
          };
        });
      return [limitOffset(normalised, rows), []];
    }

    // findBySender: SELECT m.message_id, m.recipient_id, m.ciphertext ... WHERE m.sender_id = ?
    if (/^SELECT m\.message_id, m\.recipient_id, m\.ciphertext/i.test(normalised)) {
      const [senderId] = params;
      const rows = [...messages.values()]
        .filter((r) => r.sender_id === senderId && r.deleted_at === null)
        .sort((a, b) => b.created_at - a.created_at)
        .map((r) => {
          const u = users.get(r.recipient_id);
          return {
            message_id: r.message_id, recipient_id: r.recipient_id, ciphertext: r.ciphertext,
            nonce: r.nonce, signature: r.signature, seq_no: r.seq_no,
            digest_hash: r.digest_hash, chain_status: r.chain_status,
            created_at: r.created_at, recipient_username: u ? u.username : null,
          };
        });
      return [limitOffset(normalised, rows), []];
    }

    // softDelete: UPDATE messages SET deleted_at = NOW() WHERE message_id = ?
    //             AND (sender_id = ? OR recipient_id = ?) AND deleted_at IS NULL
    if (/^UPDATE messages SET deleted_at = NOW\(\)/i.test(normalised)) {
      const [messageId, userId, userId2] = params;
      const row = messages.get(messageId);
      const owns = row && (row.sender_id === userId || row.recipient_id === userId2);
      if (row && owns && row.deleted_at === null) {
        row.deleted_at = new Date();
        return [{ affectedRows: 1 }, []];
      }
      return [{ affectedRows: 0 }, []];
    }

    // markChainFailed / recordChainEntry: UPDATE messages SET chain_status = ? WHERE message_id = ?
    if (/^UPDATE messages SET chain_status = \? WHERE message_id = \?$/i.test(normalised)) {
      const [chainStatus, messageId] = params;
      const row = messages.get(messageId);
      if (row) row.chain_status = chainStatus;
      return [{ affectedRows: row ? 1 : 0 }, []];
    }

    // ===== message_shares =====

    // INSERT INTO message_shares (...) VALUES (...)
    if (/^INSERT INTO message_shares/i.test(normalised)) {
      const [id, messageId, sharedById, sharedWithId, ciphertext, nonce, signature, seqNo, digestHash] = params;
      // Unique (shared_with_id, nonce) — replay backstop on forwards.
      if (messageShares.some((s) => s.shared_with_id === sharedWithId && s.nonce === nonce)) {
        const err = new Error("Duplicate entry for key 'message_shares.uniq_sharedwith_nonce'");
        err.code = 'ER_DUP_ENTRY';
        throw err;
      }
      messageShares.push({
        id,
        message_id: messageId,
        shared_by_id: sharedById,
        shared_with_id: sharedWithId,
        ciphertext,
        nonce,
        signature,
        seq_no: seqNo,
        digest_hash: digestHash,
        created_at: new Date(),
        revoked_at: null,
      });
      return [{ affectedRows: 1 }, []];
    }

    // findSharedWith: SELECT ms.*, u.username FROM message_shares ms ...
    //                 WHERE ms.message_id = ? AND ms.revoked_at IS NULL
    if (/^SELECT ms\.\*, u\.username FROM message_shares ms/i.test(normalised)) {
      const [messageId] = params;
      const rows = messageShares
        .filter((s) => s.message_id === messageId && s.revoked_at === null)
        .map((s) => {
          const u = users.get(s.shared_with_id);
          return { ...s, username: u ? u.username : null };
        });
      return [rows, []];
    }

    // findSharedWithUser: SELECT ms.id AS share_id, ms.message_id, ms.shared_by_id AS sender_id ...
    //                     WHERE ms.shared_with_id = ? AND revoked_at IS NULL AND om.deleted_at IS NULL
    if (/^SELECT ms\.id AS share_id, ms\.message_id, ms\.shared_by_id AS sender_id/i.test(normalised)) {
      const [userId] = params;
      const rows = messageShares
        .filter((s) => s.shared_with_id === userId && s.revoked_at === null)
        .filter((s) => { const om = messages.get(s.message_id); return om && om.deleted_at === null; })
        .sort((a, b) => b.created_at - a.created_at)
        .map((s) => {
          const u = users.get(s.shared_by_id);
          const om = messages.get(s.message_id);
          return {
            share_id: s.id, message_id: s.message_id, sender_id: s.shared_by_id,
            ciphertext: s.ciphertext, nonce: s.nonce, signature: s.signature,
            seq_no: s.seq_no, digest_hash: s.digest_hash, created_at: s.created_at,
            sender_username: u ? u.username : null, chain_status: om ? om.chain_status : null,
          };
        });
      return [limitOffset(normalised, rows), []];
    }

    // findSharedByUser: SELECT ms.id AS share_id, ms.message_id, ms.shared_with_id AS recipient_id ...
    //                   WHERE ms.shared_by_id = ? AND revoked_at IS NULL AND om.deleted_at IS NULL
    if (/^SELECT ms\.id AS share_id, ms\.message_id, ms\.shared_with_id AS recipient_id/i.test(normalised)) {
      const [userId] = params;
      const rows = messageShares
        .filter((s) => s.shared_by_id === userId && s.revoked_at === null)
        .filter((s) => { const om = messages.get(s.message_id); return om && om.deleted_at === null; })
        .sort((a, b) => b.created_at - a.created_at)
        .map((s) => {
          const u = users.get(s.shared_with_id);
          const om = messages.get(s.message_id);
          return {
            share_id: s.id, message_id: s.message_id, recipient_id: s.shared_with_id,
            ciphertext: s.ciphertext, nonce: s.nonce, signature: s.signature,
            seq_no: s.seq_no, digest_hash: s.digest_hash, created_at: s.created_at,
            recipient_username: u ? u.username : null, chain_status: om ? om.chain_status : null,
          };
        });
      return [limitOffset(normalised, rows), []];
    }

    // softDeleteShare: UPDATE message_shares SET revoked_at = NOW()
    //                  WHERE id = ? AND shared_by_id = ? AND revoked_at IS NULL
    // Must precede the generic revokeShare matcher below — both start with the
    // same SET clause, but this one is scoped to the share id + forwarder.
    if (/^UPDATE message_shares SET revoked_at = NOW\(\) WHERE id = \?/i.test(normalised)) {
      const [shareId, sharedById] = params;
      const s = messageShares.find((x) => x.id === shareId && x.shared_by_id === sharedById && x.revoked_at === null);
      if (s) {
        s.revoked_at = new Date();
        return [{ affectedRows: 1 }, []];
      }
      return [{ affectedRows: 0 }, []];
    }

    // revokeShare: UPDATE message_shares SET revoked_at = NOW() WHERE message_id = ? AND shared_with_id = ?
    if (/^UPDATE message_shares SET revoked_at = NOW\(\)/i.test(normalised)) {
      const [messageId, sharedWithId] = params;
      let affected = 0;
      for (const s of messageShares) {
        if (s.message_id === messageId && s.shared_with_id === sharedWithId && s.revoked_at === null) {
          s.revoked_at = new Date();
          affected += 1;
        }
      }
      return [{ affectedRows: affected }, []];
    }

    // ===== blockchain_records =====

    // INSERT INTO blockchain_records (id, message_id, tx_hash, digest_hash) VALUES (?, ?, ?, ?)
    if (/^INSERT INTO blockchain_records/i.test(normalised)) {
      const [id, messageId, txHash, digestHash] = params;
      if (blockchainRecords.some((r) => r.tx_hash === txHash)) {
        const err = new Error("Duplicate entry for key 'blockchain_records.tx_hash'");
        err.code = 'ER_DUP_ENTRY';
        throw err;
      }
      blockchainRecords.push({
        id, message_id: messageId, tx_hash: txHash, digest_hash: digestHash, created_at: new Date(),
      });
      return [{ affectedRows: 1 }, []];
    }

    // findChainRecord: SELECT id, tx_hash, digest_hash, created_at FROM blockchain_records
    //                  WHERE message_id = ? ORDER BY created_at DESC LIMIT 1
    if (/^SELECT id, tx_hash, digest_hash, created_at FROM blockchain_records/i.test(normalised)) {
      const [messageId] = params;
      const rows = blockchainRecords
        .filter((r) => r.message_id === messageId)
        .sort((a, b) => b.created_at - a.created_at)
        .map((r) => ({ ...r }));
      return [rows.length ? [rows[0]] : [], []];
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
        messages: new Map([...messages].map(([k, v]) => [k, { ...v }])),
        messageShares: messageShares.map((r) => ({ ...r })),
        blockchainRecords: blockchainRecords.map((r) => ({ ...r })),
      };
    }

    function restoreStores(s) {
      publicKeys.clear();
      for (const [k, v] of s.publicKeys) publicKeys.set(k, v);
      publicKeyHistory.length = 0;
      publicKeyHistory.push(...s.publicKeyHistory);
      messages.clear();
      for (const [k, v] of s.messages) messages.set(k, v);
      messageShares.length = 0;
      messageShares.push(...s.messageShares);
      blockchainRecords.length = 0;
      blockchainRecords.push(...s.blockchainRecords);
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
    _messagesStore: messages,
    _messageSharesStore: messageShares,
    _blockchainRecordsStore: blockchainRecords,
  };
}

module.exports = { makeFakePool };
