/**
 * Repository layer — isolates raw SQL from business logic.
 * Services never touch the database directly; they go through repositories.
 * This makes it possible to swap MySQL for another store without changing services.
 */

class UserRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async create({ userId, username, passwordHash }) {
    const sql = `
      INSERT INTO users (user_id, username, password_hash, created_at)
      VALUES (?, ?, ?, NOW())
    `;
    await this._pool.execute(sql, [userId, username, passwordHash]);
  }

  async findById(userId) {
    const [rows] = await this._pool.execute(
      'SELECT user_id, username, password_hash, created_at FROM users WHERE user_id = ?',
      [userId]
    );
    return rows[0] || null;
  }

  async findByUsername(username) {
    const [rows] = await this._pool.execute(
      'SELECT user_id, username, password_hash, created_at FROM users WHERE username = ?',
      [username]
    );
    return rows[0] || null;
  }

  async listAll() {
    const [rows] = await this._pool.execute(
      'SELECT user_id, username, created_at FROM users ORDER BY username'
    );
    return rows;
  }

  async updatePassword(userId, passwordHash) {
    await this._pool.execute(
      'UPDATE users SET password_hash = ? WHERE user_id = ?',
      [passwordHash, userId]
    );
  }

  async deleteById(userId) {
    await this._pool.execute('DELETE FROM users WHERE user_id = ?', [userId]);
  }
}

module.exports = UserRepository;