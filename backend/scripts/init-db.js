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
      version INT NOT NULL DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      rotated_at DATETIME NULL,
      UNIQUE KEY uniq_user_keytype (user_id, key_type),
      FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )`,

    // Append-only audit trail of every prior public key. A compromised server
    // cannot silently swap a user's key without leaving a row here — the
    // client can reconcile its pinned key against this history to detect
    // unauthorised rotation.
    `CREATE TABLE IF NOT EXISTS public_key_history (
      id CHAR(36) PRIMARY KEY,
      user_id CHAR(36) NOT NULL,
      public_key TEXT NOT NULL,
      key_type ENUM('x25519', 'ed25519') NOT NULL,
      version INT NOT NULL,
      pinned_at DATETIME NOT NULL,
      rotated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
      INDEX idx_history_user_key (user_id, key_type, version)
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

  // Add version column to public_keys for TOFU rotation tracking.
  try {
    await pool.execute(
      `ALTER TABLE public_keys
         ADD COLUMN version INT NOT NULL DEFAULT 1
         AFTER key_type`
    );
    console.log('Added public_keys.version');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // Promote the non-unique (user_id, key_type) index to a UNIQUE constraint.
  // INSERT … ON DUPLICATE KEY UPDATE in the repository depends on this.
  try {
    await pool.execute('ALTER TABLE public_keys DROP INDEX idx_user_key');
  } catch (err) {
    if (err.code !== 'ER_CANT_DROP_FIELD_OR_KEY') throw err;
  }
  try {
    await pool.execute(
      'ALTER TABLE public_keys ADD UNIQUE KEY uniq_user_keytype (user_id, key_type)'
    );
    console.log('Added unique constraint on public_keys (user_id, key_type)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME') throw err;
  }

  // Replay protection: a (recipient_id, nonce) pair must be unique. An
  // active attacker replaying a captured ciphertext+nonce will now fail
  // at the DB layer with ER_DUP_ENTRY, which the repository surfaces as
  // 409 CONFLICT. Note: AEAD nonces are required to be unique per key
  // already; this is a server-side belt-and-braces check.
  try {
    await pool.execute(
      'ALTER TABLE messages ADD UNIQUE KEY uniq_recipient_nonce (recipient_id, nonce)'
    );
    console.log('Added unique constraint on messages (recipient_id, nonce)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME' && err.code !== 'ER_DUP_ENTRY') throw err;
  }

  // Same replay protection for re-encrypted forwarded shares.
  try {
    await pool.execute(
      'ALTER TABLE message_shares ADD UNIQUE KEY uniq_sharedwith_nonce (shared_with_id, nonce)'
    );
    console.log('Added unique constraint on message_shares (shared_with_id, nonce)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME' && err.code !== 'ER_DUP_ENTRY') throw err;
  }

  console.log('Tables created');
  await pool.end();
}

init().catch(console.error);