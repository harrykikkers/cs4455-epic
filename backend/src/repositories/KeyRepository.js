/**
 * Stores public keys for TOFU (Trust On First Use) key management.
 * When a user first registers, their public key is pinned.
 * Subsequent key changes require explicit acknowledgement.
 */

const { randomUUID } = require('crypto');

class KeyRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async storePublicKey({ userId, publicKey, keyType }) {
    // Check if this key type already exists for the user
    const [existing] = await this._pool.execute(
      'SELECT id FROM public_keys WHERE user_id = ? AND key_type = ?',
      [userId, keyType]
    );

    if (existing.length > 0) {
      await this._pool.execute(
        'UPDATE public_keys SET public_key = ?, rotated_at = NOW() WHERE user_id = ? AND key_type = ?',
        [publicKey, userId, keyType]
      );
    } else {
      const id = randomUUID();
      await this._pool.execute(
        'INSERT INTO public_keys (id, user_id, public_key, key_type) VALUES (?, ?, ?, ?)',
        [id, userId, publicKey, keyType]
      );
    }
  }

  async getPublicKeys(userId) {
    const [rows] = await this._pool.execute(
      'SELECT public_key, key_type, created_at, rotated_at FROM public_keys WHERE user_id = ?',
      [userId]
    );
    return rows;
  }

  async getPublicKeyByType(userId, keyType) {
    const [rows] = await this._pool.execute(
      'SELECT public_key, key_type, created_at, rotated_at FROM public_keys WHERE user_id = ? AND key_type = ?',
      [userId, keyType]
    );
    return rows[0] || null;
  }

  async getAllPublicKeys() {
    const [rows] = await this._pool.execute(
      `SELECT pk.user_id, pk.public_key, pk.key_type, u.username
       FROM public_keys pk
       JOIN users u ON u.user_id = pk.user_id`
    );
    return rows;
  }
}

module.exports = KeyRepository;