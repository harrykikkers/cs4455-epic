/**
 * Public-key storage with TOFU (Trust On First Use) semantics.
 *
 * The first key a user publishes for a given key_type is pinned. Subsequent
 * publishes are surfaced to the service layer as either "unchanged" or
 * "rotation" — never silently overwritten — so the client can warn the user
 * and require explicit acknowledgement (analogous to SSH known_hosts).
 *
 * Every prior key is preserved in public_key_history; a compromised server
 * cannot substitute a user's key without leaving an audit trail clients can
 * inspect via GET /api/keys/:userId/history.
 */

const { randomUUID } = require('crypto');

class KeyRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async findCurrent(userId, keyType) {
    const [rows] = await this._pool.execute(
      `SELECT id, public_key, key_type, version, created_at, rotated_at
       FROM public_keys
       WHERE user_id = ? AND key_type = ?`,
      [userId, keyType]
    );
    return rows[0] || null;
  }

  async insertFirst({ userId, publicKey, keyType }) {
    const id = randomUUID();
    await this._pool.execute(
      `INSERT INTO public_keys (id, user_id, public_key, key_type, version)
       VALUES (?, ?, ?, ?, 1)`,
      [id, userId, publicKey, keyType]
    );
    return { id, version: 1 };
  }

  /**
   * Atomic rotation: archive the current row into public_key_history, then
   * overwrite the live row with the new key and a bumped version. Both
   * statements share a single connection in a transaction so a crash
   * between them cannot leave history out of sync with the live key.
   */
  async rotate({ userId, keyType, current, newPublicKey }) {
    const conn = await this._pool.getConnection();
    try {
      await conn.beginTransaction();

      await conn.execute(
        `INSERT INTO public_key_history
           (id, user_id, public_key, key_type, version, pinned_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
        [randomUUID(), userId, current.public_key, keyType, current.version, current.created_at]
      );

      const newVersion = current.version + 1;
      await conn.execute(
        `UPDATE public_keys
         SET public_key = ?, version = ?, rotated_at = NOW(), created_at = NOW()
         WHERE user_id = ? AND key_type = ?`,
        [newPublicKey, newVersion, userId, keyType]
      );

      await conn.commit();
      return { version: newVersion };
    } catch (err) {
      await conn.rollback();
      throw err;
    } finally {
      conn.release();
    }
  }

  async getPublicKeys(userId) {
    const [rows] = await this._pool.execute(
      `SELECT public_key, key_type, version, created_at, rotated_at
       FROM public_keys WHERE user_id = ?`,
      [userId]
    );
    return rows;
  }

  async getPublicKeyByType(userId, keyType) {
    const [rows] = await this._pool.execute(
      `SELECT public_key, key_type, version, created_at, rotated_at
       FROM public_keys WHERE user_id = ? AND key_type = ?`,
      [userId, keyType]
    );
    return rows[0] || null;
  }

  async getAllPublicKeys() {
    const [rows] = await this._pool.execute(
      `SELECT pk.user_id, pk.public_key, pk.key_type, pk.version, u.username
       FROM public_keys pk
       JOIN users u ON u.user_id = pk.user_id`
    );
    return rows;
  }

  async getHistory(userId, keyType) {
    const [rows] = await this._pool.execute(
      `SELECT public_key, key_type, version, pinned_at, rotated_at
       FROM public_key_history
       WHERE user_id = ? AND key_type = ?
       ORDER BY version ASC`,
      [userId, keyType]
    );
    return rows;
  }
}

module.exports = KeyRepository;
