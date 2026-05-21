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

  /**
   * Atomic publish: SELECT ... FOR UPDATE serialises concurrent publishes
   * for the same (user_id, key_type), so two requests can't both observe
   * "no current key" and double-insert, nor both observe the same current
   * version and double-rotate (which would leave two history rows at the
   * same version and corrupt the audit trail).
   *
   * Returns one of:
   *   { status: 'pinned',            version }
   *   { status: 'unchanged',         version }
   *   { status: 'rotation_required', currentVersion }
   *   { status: 'rotated',           version, previousVersion }
   *
   * The 'rotation_required' branch is data, not an error — the service
   * decides whether to surface it as a 409, log it, etc.
   */
  async publishKey({ userId, publicKey, keyType, acknowledgeRotation }) {
    const conn = await this._pool.getConnection();
    try {
      await conn.beginTransaction();

      const [rows] = await conn.execute(
        `SELECT public_key, version, created_at
         FROM public_keys
         WHERE user_id = ? AND key_type = ?
         FOR UPDATE`,
        [userId, keyType]
      );
      const current = rows[0] || null;

      if (!current) {
        await conn.execute(
          `INSERT INTO public_keys (id, user_id, public_key, key_type, version)
           VALUES (?, ?, ?, ?, 1)`,
          [randomUUID(), userId, publicKey, keyType]
        );
        await conn.commit();
        return { status: 'pinned', version: 1 };
      }

      if (current.public_key === publicKey) {
        await conn.commit();
        return { status: 'unchanged', version: current.version };
      }

      if (!acknowledgeRotation) {
        await conn.commit();
        return { status: 'rotation_required', currentVersion: current.version };
      }

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
        [publicKey, newVersion, userId, keyType]
      );

      await conn.commit();
      return { status: 'rotated', version: newVersion, previousVersion: current.version };
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
