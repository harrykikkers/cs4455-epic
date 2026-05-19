class MessageRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async create({ messageId, senderId, recipientId, ciphertext, nonce }) {
    const sql = `
      INSERT INTO messages
        (message_id, sender_id, recipient_id, ciphertext, nonce, created_at)
      VALUES (?, ?, ?, ?, ?, NOW())
    `;
    await this._pool.execute(sql, [messageId, senderId, recipientId, ciphertext, nonce]);
  }

  async findById(messageId) {
    const [rows] = await this._pool.execute(
      `SELECT m.*, u.username AS sender_username
       FROM messages m
       JOIN users u ON u.user_id = m.sender_id
       WHERE m.message_id = ? AND m.deleted_at IS NULL`,
      [messageId]
    );
    return rows[0] || null;
  }

  async findByRecipient(recipientId, { limit = 50, offset = 0 } = {}) {
    const [rows] = await this._pool.execute(
      `SELECT m.message_id, m.sender_id, m.ciphertext, m.nonce,
              m.created_at, u.username AS sender_username
       FROM messages m
       JOIN users u ON u.user_id = m.sender_id
       WHERE m.recipient_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [recipientId, limit, offset]
    );
    return rows;
  }

  async findBySender(senderId, { limit = 50, offset = 0 } = {}) {
    const [rows] = await this._pool.execute(
      `SELECT m.message_id, m.recipient_id, m.ciphertext, m.nonce,
              m.created_at, u.username AS recipient_username
       FROM messages m
       JOIN users u ON u.user_id = m.recipient_id
       WHERE m.sender_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [senderId, limit, offset]
    );
    return rows;
  }

  async softDelete(messageId, userId) {
    await this._pool.execute(
      'UPDATE messages SET deleted_at = NOW() WHERE message_id = ? AND (sender_id = ? OR recipient_id = ?) AND deleted_at IS NULL',
      [messageId, userId, userId]
    );
  }

  async findSharedWith(messageId) {
    const [rows] = await this._pool.execute(
      `SELECT ms.*, u.username
       FROM message_shares ms
       JOIN users u ON u.user_id = ms.shared_with_id
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
}

module.exports = MessageRepository;