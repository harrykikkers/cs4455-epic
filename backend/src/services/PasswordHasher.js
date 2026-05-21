const argon2 = require('argon2');
const config = require('../config');

/**
 * PasswordHasher — Argon2id wrapper used by AuthService for registration,
 * login, and password change.
 *
 * Algorithm choice (argon2id), OWASP's current recommendation for memory-
 * hard password hashing. Parameters (memoryCost, timeCost, parallelism) OWASP recommended used.
 */

class PasswordHasher {
  constructor() {
    this.options = {
      type: argon2.argon2id,
      memoryCost: config.argon2.memoryCost,
      timeCost: config.argon2.timeCost,
      parallelism: config.argon2.parallelism,
    };
  }

  async hash(password) {
    return argon2.hash(password, this.options);
  }

  async verify(password, hash) {
    return argon2.verify(hash, password);
  }
}

module.exports = PasswordHasher;
