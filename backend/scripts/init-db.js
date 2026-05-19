/**
 * Run once to create the database tables:
 *   node scripts/init-db.js
 *
 * Uses parameterised DDL — no user input in these queries.
 */
const { getPool } = require('../src/config/database');
const logger = require('../src/utils/logger').child({ component: 'init' });

const TABLES = [
  `CREATE TABLE IF NOT EXISTS users (
    id CHAR(36) PRIMARY KEY,
    username VARCHAR(30) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_username (username),
    INDEX idx_email (email)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`,

  `CREATE TABLE IF NOT EXISTS public_keys (
    user_id CHAR(36) PRIMARY KEY,
    public_key TEXT NOT NULL,
    key_type VARCHAR(20) NOT NULL DEFAULT 'x25519',
    created_at DATETIME NOT NULL,
    rotated_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`,

  `CREATE TABLE IF NOT EXISTS messages (
    id CHAR(36) PRIMARY KEY,
    sender_id CHAR(36) NOT NULL,
    recipient_id CHAR(36) NOT NULL,
    ciphertext MEDIUMTEXT NOT NULL,
    nonce VARCHAR(255) NOT NULL,
    sender_public_key TEXT NOT NULL,
    tx_hash VARCHAR(66) NULL,
    created_at DATETIME NOT NULL,
    deleted_at DATETIME NULL,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_recipient (recipient_id, deleted_at, created_at),
    INDEX idx_sender (sender_id, deleted_at, created_at)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`,

  `CREATE TABLE IF NOT EXISTS message_shares (
    id CHAR(36) PRIMARY KEY,
    message_id CHAR(36) NOT NULL,
    shared_by_id CHAR(36) NOT NULL,
    shared_with_id CHAR(36) NOT NULL,
    ciphertext MEDIUMTEXT NOT NULL,
    nonce VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (shared_by_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (shared_with_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_share_lookup (message_id, shared_with_id, revoked_at)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`,
];

async function init() {
  const pool = getPool();
  try {
    for (const sql of TABLES) {
      await pool.execute(sql);
    }
    logger.info('Database tables created successfully');
  } catch (err) {
    logger.error('Database initialisation failed:', err);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

init();
