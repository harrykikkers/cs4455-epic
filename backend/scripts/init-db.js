/**
 * Run once to create the database tables:
 *   node scripts/init-db.js
 *
 * Uses parameterised DDL — no user input in these queries.
 */
require('dotenv').config();
const mysql = require('mysql2/promise');

async function init() {
  const pool = mysql.createPool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
  });

  const tables = [
    `CREATE TABLE IF NOT EXISTS users (
      user_id CHAR(36) PRIMARY KEY,
      username VARCHAR(30) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      password_changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`,

    `CREATE TABLE IF NOT EXISTS public_keys (
      id CHAR(36) PRIMARY KEY,
      user_id CHAR(36) NOT NULL,
      public_key TEXT NOT NULL,
      key_type ENUM('x25519', 'ed25519') NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      rotated_at DATETIME NULL,
      FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
      INDEX idx_user_key (user_id, key_type)
    )`,

    `CREATE TABLE IF NOT EXISTS messages (
      message_id CHAR(36) PRIMARY KEY,
      sender_id CHAR(36) NOT NULL,
      recipient_id CHAR(36) NOT NULL,
      ciphertext TEXT NOT NULL,
      nonce VARCHAR(255) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      deleted_at DATETIME NULL,
      FOREIGN KEY (sender_id) REFERENCES users(user_id),
      FOREIGN KEY (recipient_id) REFERENCES users(user_id),
      INDEX idx_recipient (recipient_id, deleted_at, created_at),
      INDEX idx_sender (sender_id, deleted_at, created_at)
    )`,

    `CREATE TABLE IF NOT EXISTS message_shares (
      id CHAR(36) PRIMARY KEY,
      message_id CHAR(36) NOT NULL,
      shared_by_id CHAR(36) NOT NULL,
      shared_with_id CHAR(36) NOT NULL,
      ciphertext TEXT NOT NULL,
      nonce VARCHAR(255) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      revoked_at DATETIME NULL,
      FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
      FOREIGN KEY (shared_by_id) REFERENCES users(user_id),
      FOREIGN KEY (shared_with_id) REFERENCES users(user_id),
      INDEX idx_share_lookup (message_id, shared_with_id, revoked_at)
    )`,

    `CREATE TABLE IF NOT EXISTS blockchain_records (
      id CHAR(36) PRIMARY KEY,
      message_id CHAR(36) NOT NULL,
      tx_hash VARCHAR(66) NOT NULL UNIQUE,
      digest_hash VARCHAR(66) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
    )`,
  ];

  for (const sql of tables) {
    await pool.execute(sql);
  }

  // Backward-compatible migration: add password_changed_at to existing
  // users tables. MySQL 8 lacks ADD COLUMN IF NOT EXISTS, so we swallow
  // the duplicate-field error and rethrow anything else.
  try {
    await pool.execute(
      `ALTER TABLE users
         ADD COLUMN password_changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
         AFTER password_hash`
    );
    console.log('Added users.password_changed_at');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  console.log('Tables created');
  await pool.end();
}

init().catch(console.error);