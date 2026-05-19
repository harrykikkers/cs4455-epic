/**
 * Repository layer — isolates raw SQL from business logic.
 * Services never touch the database directly; they go through repositories.
 * This makes it possible to swap MySQL for another store without changing services.
 */
class UserRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async create({ id, username, email, passwordHash }) {
    const sql = `
      INSERT INTO users (id, username, email, password_hash, created_at)
      VALUES (?, ?, ?, ?, NOW())
    `;
    await this._pool.execute(sql, [id, username, email, passwordHash]);
  }

  async findById(id) {
    const [rows] = await this._pool.execute(
      'SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?',
      [id]
    );
    return rows[0] || null;
  }

  async findByUsername(username) {
    const [rows] = await this._pool.execute(
      'SELECT id, username, email, password_hash, created_at FROM users WHERE username = ?',
      [username]
    );
    return rows[0] || null;
  }

  async findByEmail(email) {
    const [rows] = await this._pool.execute(
      'SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?',
      [email]
    );
    return rows[0] || null;
  }

  async listAll() {
    const [rows] = await this._pool.execute(
      'SELECT id, username, created_at FROM users ORDER BY username'
    );
    return rows;
  }

  async deleteById(id) {
    await this._pool.execute('DELETE FROM users WHERE id = ?', [id]);
  }
}

module.exports = UserRepository;
