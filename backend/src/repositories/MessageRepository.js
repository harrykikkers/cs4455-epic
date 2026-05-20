const { ConflictError } = require('../utils/errors');

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
    try {
      await this._pool.execute(sql, [messageId, senderId, recipientId, ciphertext, nonce]);
    } catch (err) {
      // Unique (recipient_id, nonce) — an active attacker replaying a
      // captured ciphertext+nonce hits this. AEAD already prevents the
      // recipient from decrypting a replay, but rejecting at the server
      // also keeps the inbox clean and gives a defensible audit signal.
      if (err.code === 'ER_DUP_ENTRY') {
        throw new ConflictError('Duplicate nonce for this recipient — possible replay');
      }
      throw err;
    }
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
    // mysql2 prepared statements reject non-integer binds for LIMIT/OFFSET,
    // and req.query values arrive as strings when express-validator's .toInt()
    // doesn't fire (e.g. when the param is absent the destructured default
    // is a number, but a caller passing strings would break). Coerce here.
    const lim = Number.parseInt(limit, 10);
    const off = Number.parseInt(offset, 10);
    const [rows] = await this._pool.execute(
      `SELECT m.message_id, m.sender_id, m.ciphertext, m.nonce,
              m.created_at, u.username AS sender_username
       FROM messages m
       JOIN users u ON u.user_id = m.sender_id
       WHERE m.recipient_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [recipientId, lim, off]
    );
    return rows;
  }

  async findBySender(senderId, { limit = 50, offset = 0 } = {}) {
    const lim = Number.parseInt(limit, 10);
    const off = Number.parseInt(offset, 10);
    const [rows] = await this._pool.execute(
      `SELECT m.message_id, m.recipient_id, m.ciphertext, m.nonce,
              m.created_at, u.username AS recipient_username
       FROM messages m
       JOIN users u ON u.user_id = m.recipient_id
       WHERE m.sender_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC
       LIMIT ? OFFSET ?`,
      [senderId, lim, off]
    );
    return rows;
  }

  async softDelete(messageId, userId) {
    const [result] = await this._pool.execute(
      'UPDATE messages SET deleted_at = NOW() WHERE message_id = ? AND (sender_id = ? OR recipient_id = ?) AND deleted_at IS NULL',
      [messageId, userId, userId]
    );
    return result.affectedRows;
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
    try {
      await this._pool.execute(sql, [id, messageId, sharedById, sharedWithId, ciphertext, nonce]);
    } catch (err) {
      if (err.code === 'ER_DUP_ENTRY') {
        throw new ConflictError('Duplicate nonce for this share recipient — possible replay');
      }
      throw err;
    }
  }

  async revokeShare(messageId, sharedWithId) {
    await this._pool.execute(
      'UPDATE message_shares SET revoked_at = NOW() WHERE message_id = ? AND shared_with_id = ?',
      [messageId, sharedWithId]
    );
  }
}

module.exports = MessageRepository;