class MessageRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async create({ id, senderId, recipientId, ciphertext, nonce, senderPublicKey, txHash }) {
    const sql = `
      INSERT INTO messages
        (id, sender_id, recipient_id, ciphertext, nonce, sender_public_key, tx_hash, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, NOW())
    `;
    await this._pool.execute(sql, [
      id, senderId, recipientId, ciphertext, nonce, senderPublicKey, txHash,
    ]);
  }

  async findById(id) {
    const [rows] = await this._pool.execute(
      `SELECT m.*, u.username AS sender_username
       FROM messages m
       JOIN users u ON u.id = m.sender_id
       WHERE m.id = ?`,
      [id]
    );
    return rows[0] || null;
  }

  async findByRecipient(recipientId, { limit = 50, offset = 0 } = {}) {
    const [rows] = await this._pool.execute(
      `SELECT m.id, m.sender_id, m.ciphertext, m.nonce, m.sender_public_key,
              m.tx_hash, m.created_at, u.username AS sender_username
       FROM messages m
       JOIN users u ON u.id = m.sender_id
       WHERE m.recipient_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [recipientId, limit, offset]
    );
    return rows;
  }

  async findBySender(senderId, { limit = 50, offset = 0 } = {}) {
    const [rows] = await this._pool.execute(
      `SELECT m.id, m.recipient_id, m.ciphertext, m.nonce,
              m.tx_hash, m.created_at, u.username AS recipient_username
       FROM messages m
       JOIN users u ON u.id = m.recipient_id
       WHERE m.sender_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [senderId, limit, offset]
    );
    return rows;
  }

  async softDelete(id, userId) {
    // Soft delete — marks the message as deleted for audit trail
    await this._pool.execute(
      'UPDATE messages SET deleted_at = NOW() WHERE id = ? AND (sender_id = ? OR recipient_id = ?)',
      [id, userId, userId]
    );
  }

  async findSharedWith(messageId) {
    const [rows] = await this._pool.execute(
      `SELECT ms.*, u.username
       FROM message_shares ms
       JOIN users u ON u.id = ms.shared_with_id
       WHERE ms.message_id = ? AND ms.revoked_at IS NULL`,
      [messageId]
    );
    return rows;
  }

  async createShare({ id, messageId, sharedById, sharedWithId, ciphertext, nonce }) {
    const sql = `
      INSERT INTO message_shares
        (id, message_id, shared_by_id, shared_with_id, ciphertext, nonce, created_at)
      VALUES (?, ?, ?, ?, ?, ?, NOW())
    `;
    await this._pool.execute(sql, [id, messageId, sharedById, sharedWithId, ciphertext, nonce]);
  }

  async revokeShare(messageId, sharedWithId) {
    await this._pool.execute(
      'UPDATE message_shares SET revoked_at = NOW() WHERE message_id = ? AND shared_with_id = ?',
      [messageId, sharedWithId]
    );
  }

  async updateTxHash(messageId, txHash) {
    await this._pool.execute(
      'UPDATE messages SET tx_hash = ? WHERE id = ?',
      [txHash, messageId]
    );
  }
}

module.exports = MessageRepository;
