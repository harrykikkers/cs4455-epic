/**
 * Stores public keys for TOFU (Trust On First Use) key management.
 * When a user first registers, their public key is pinned.
 * Subsequent key changes require explicit acknowledgement.
 */
class KeyRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async storePublicKey({ userId, publicKey, keyType }) {
    const sql = `
      INSERT INTO public_keys (user_id, public_key, key_type, created_at)
      VALUES (?, ?, ?, NOW())
      ON DUPLICATE KEY UPDATE
        public_key = VALUES(public_key),
        rotated_at = NOW()
    `;
    await this._pool.execute(sql, [userId, publicKey, keyType]);
  }

  async getPublicKey(userId) {
    const [rows] = await this._pool.execute(
      'SELECT public_key, key_type, created_at, rotated_at FROM public_keys WHERE user_id = ?',
      [userId]
    );
    return rows[0] || null;
  }

  async getAllPublicKeys() {
    const [rows] = await this._pool.execute(
      `SELECT pk.user_id, pk.public_key, pk.key_type, u.username
       FROM public_keys pk
       JOIN users u ON u.id = pk.user_id`
    );
    return rows;
  }
}

module.exports = KeyRepository;
