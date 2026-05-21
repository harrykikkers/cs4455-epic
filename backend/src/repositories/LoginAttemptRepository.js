const { randomUUID } = require('crypto');

/**
 * Records every login attempt — success or failure — keyed by user_id.
 * AuthService uses countRecentFailures() to enforce a per-user lockout
 * after too many failures inside a sliding window.
 *
 * The schema also indexes by ip_address so a future IP-based throttle can
 * be layered on top without migrating data.
 */
class LoginAttemptRepository {
  constructor(pool) {
    this._pool = pool;
  }

  async record({ userId, ipAddress, success }) {
    await this._pool.execute(
      `INSERT INTO login_attempts (id, user_id, ip_address, success, attempted_at)
       VALUES (?, ?, ?, ?, NOW())`,
      [randomUUID(), userId, ipAddress, success ? 1 : 0]
    );
  }

  /**
   * Count failed attempts for a user inside the trailing `windowMs`
   * milliseconds. A successful login since the last failure does NOT
   * reset the counter on its own — the caller decides whether to gate
   * on raw failures or only failures-since-last-success.
   */
  async countRecentFailures(userId, windowMs) {
    const [rows] = await this._pool.execute(
      `SELECT COUNT(*) AS n
       FROM login_attempts
       WHERE user_id = ?
         AND success = 0
         AND attempted_at >= NOW() - INTERVAL ? SECOND`,
      [userId, Math.ceil(windowMs / 1000)]
    );
    return Number(rows[0]?.n || 0);
  }

  /**
   * Clear the failure streak after a successful auth. Implemented as a
   * targeted delete rather than a flag flip so the table stays a clean
   * audit log of "what's still relevant for lockout".
   */
  async clearFailures(userId) {
    await this._pool.execute(
      'DELETE FROM login_attempts WHERE user_id = ? AND success = 0',
      [userId]
    );
  }
}

module.exports = LoginAttemptRepository;
