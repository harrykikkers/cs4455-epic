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

    // Tracks failed login attempts per user for brute-force protection.
    // The auth layer should lock the account or throttle after a
    // configurable threshold (e.g. 5 failures within 15 minutes).
    `CREATE TABLE IF NOT EXISTS login_attempts (
      id CHAR(36) PRIMARY KEY,
      user_id CHAR(36) NOT NULL,
      ip_address VARCHAR(45) NOT NULL,
      attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      success BOOLEAN NOT NULL DEFAULT FALSE,
      FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
      INDEX idx_user_attempts (user_id, attempted_at),
      INDEX idx_ip_attempts (ip_address, attempted_at)
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
    //
    // The UNIQUE constraint on (user_id, key_type, version) prevents a
    // buggy rotation path from inserting duplicate version numbers, which
    // would make the audit trail ambiguous.
    `CREATE TABLE IF NOT EXISTS public_key_history (
      id CHAR(36) PRIMARY KEY,
      user_id CHAR(36) NOT NULL,
      public_key TEXT NOT NULL,
      key_type ENUM('x25519', 'ed25519') NOT NULL,
      version INT NOT NULL,
      pinned_at DATETIME NOT NULL,
      rotated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
      UNIQUE KEY uniq_history_version (user_id, key_type, version),
      INDEX idx_history_user_key (user_id, key_type, version)
    )`,

    // Messaging table.
    //
    // nonce:         Base64-encoded 12-byte AES-256-GCM IV (16 chars base64).
    //                CHAR(16) enforces exact sizing.
    // ciphertext:    Base64-encoded AEAD ciphertext (variable length).
    // signature:     Base64-encoded Ed25519 signature over the signed payload
    //                (sender_id ‖ recipient_id ‖ seq_no ‖ ciphertext ‖ nonce).
    // seq_no:        Monotonically increasing per-recipient sequence number.
    //                The client checks this for replay protection; the server
    //                enforces (recipient_id, nonce) uniqueness as a belt-and-braces
    //                backstop.
    // digest_hash:   Keccak256 hash of the plaintext, supplied by the sender
    //                for blockchain recording. NOT NULL — the client always
    //                computes this before sending.
    // chain_status:  Tracks whether the digest has been written to Sepolia.
    `CREATE TABLE IF NOT EXISTS messages (
      message_id CHAR(36) PRIMARY KEY,
      sender_id CHAR(36) NOT NULL,
      recipient_id CHAR(36) NOT NULL,
      ciphertext TEXT NOT NULL,
      nonce CHAR(16) NOT NULL,
      signature TEXT NOT NULL,
      seq_no BIGINT UNSIGNED NOT NULL,
      digest_hash CHAR(66) NOT NULL,
      chain_status ENUM('pending','recorded','failed') NOT NULL DEFAULT 'pending',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      deleted_at DATETIME NULL,
      FOREIGN KEY (sender_id) REFERENCES users(user_id) ON DELETE CASCADE,
      FOREIGN KEY (recipient_id) REFERENCES users(user_id) ON DELETE CASCADE,
      UNIQUE KEY uniq_recipient_nonce (recipient_id, nonce),
      INDEX idx_recipient (recipient_id, deleted_at, created_at),
      INDEX idx_sender (sender_id, deleted_at, created_at),
      INDEX idx_chain_status (chain_status, created_at)
    )`,

    // Re-encrypted forwarded messages. A forward is a direct message where the
    // forwarder is the sender: the forwarder re-encrypts the plaintext under the
    // new recipient's pinned X25519 key with a fresh nonce, Ed25519-signs it, and
    // draws seq_no from the same per-recipient send counter as direct messages
    // (replay protection). There is no encapsulated key — the protocol is static
    // ECDH, identical to the messages table.
    `CREATE TABLE IF NOT EXISTS message_shares (
      id CHAR(36) PRIMARY KEY,
      message_id CHAR(36) NOT NULL,
      shared_by_id CHAR(36) NOT NULL,
      shared_with_id CHAR(36) NOT NULL,
      ciphertext TEXT NOT NULL,
      nonce CHAR(16) NOT NULL,
      signature TEXT NOT NULL,
      seq_no BIGINT UNSIGNED NOT NULL,
      digest_hash CHAR(66) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      revoked_at DATETIME NULL,
      FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
      FOREIGN KEY (shared_by_id) REFERENCES users(user_id) ON DELETE CASCADE,
      FOREIGN KEY (shared_with_id) REFERENCES users(user_id) ON DELETE CASCADE,
      UNIQUE KEY uniq_sharedwith_nonce (shared_with_id, nonce),
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

  // ---------------------------------------------------------------------------
  // Backward-compatible migrations
  //
  // Each migration swallows the expected "already exists" error so the script
  // is idempotent. Any unexpected error is re-thrown.
  // ---------------------------------------------------------------------------

  // Add password_changed_at to existing users tables.
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

  // --- messages table migrations ---

  // deleted_at (soft-delete support — queries filter with deleted_at IS NULL)
  try {
    await pool.execute(
      `ALTER TABLE messages ADD COLUMN deleted_at DATETIME NULL AFTER created_at`
    );
    console.log('Added messages.deleted_at');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // enc removed — static ECDH replaced per-message ephemeral keys, so there is
  // no encapsulated key to store on the message row anymore.
  try {
    await pool.execute('ALTER TABLE messages DROP COLUMN enc');
    console.log('Dropped messages.enc');
  } catch (err) {
    if (err.code !== 'ER_CANT_DROP_FIELD_OR_KEY') throw err;
  }

  // signature (Ed25519)
  try {
    await pool.execute(
      `ALTER TABLE messages
         ADD COLUMN signature TEXT NOT NULL
         AFTER nonce`
    );
    console.log('Added messages.signature');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // seq_no (replay protection sequence number)
  try {
    await pool.execute(
      `ALTER TABLE messages
         ADD COLUMN seq_no BIGINT UNSIGNED NOT NULL DEFAULT 0
         AFTER signature`
    );
    console.log('Added messages.seq_no');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // digest_hash
  try {
    await pool.execute(
      `ALTER TABLE messages
         ADD COLUMN digest_hash CHAR(66) NOT NULL DEFAULT ''
         AFTER seq_no`
    );
    console.log('Added messages.digest_hash');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // chain_status
  try {
    await pool.execute(
      `ALTER TABLE messages
         ADD COLUMN chain_status ENUM('pending','recorded','failed')
         NOT NULL DEFAULT 'pending'
         AFTER digest_hash`
    );
    console.log('Added messages.chain_status');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  try {
    await pool.execute(
      'ALTER TABLE messages ADD INDEX idx_chain_status (chain_status, created_at)'
    );
    console.log('Added index on messages (chain_status, created_at)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME') throw err;
  }

  // Replay protection: (recipient_id, nonce) uniqueness.
  try {
    await pool.execute(
      'ALTER TABLE messages ADD UNIQUE KEY uniq_recipient_nonce (recipient_id, nonce)'
    );
    console.log('Added unique constraint on messages (recipient_id, nonce)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME' && err.code !== 'ER_DUP_ENTRY') throw err;
  }

  // --- message_shares migrations ---

  // enc removed — static ECDH replaced per-share ephemeral keys, so there is
  // no encapsulated key to store on the share row anymore.
  try {
    await pool.execute('ALTER TABLE message_shares DROP COLUMN enc');
    console.log('Dropped message_shares.enc');
  } catch (err) {
    if (err.code !== 'ER_CANT_DROP_FIELD_OR_KEY') throw err;
  }

  // signature (Ed25519) — forwards are signed exactly like direct messages.
  try {
    await pool.execute(
      `ALTER TABLE message_shares
         ADD COLUMN signature TEXT NOT NULL
         AFTER nonce`
    );
    console.log('Added message_shares.signature');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // seq_no (replay protection sequence number, from the forwarder's counter)
  try {
    await pool.execute(
      `ALTER TABLE message_shares
         ADD COLUMN seq_no BIGINT UNSIGNED NOT NULL DEFAULT 0
         AFTER signature`
    );
    console.log('Added message_shares.seq_no');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // digest_hash
  try {
    await pool.execute(
      `ALTER TABLE message_shares
         ADD COLUMN digest_hash CHAR(66) NOT NULL DEFAULT ''
         AFTER seq_no`
    );
    console.log('Added message_shares.digest_hash');
  } catch (err) {
    if (err.code !== 'ER_DUP_FIELDNAME') throw err;
  }

  // Replay protection for forwarded shares.
  try {
    await pool.execute(
      'ALTER TABLE message_shares ADD UNIQUE KEY uniq_sharedwith_nonce (shared_with_id, nonce)'
    );
    console.log('Added unique constraint on message_shares (shared_with_id, nonce)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME' && err.code !== 'ER_DUP_ENTRY') throw err;
  }

  // --- public_key_history migrations ---

  // Unique constraint on (user_id, key_type, version) to prevent
  // duplicate version numbers in the audit trail.
  try {
    await pool.execute(
      'ALTER TABLE public_key_history ADD UNIQUE KEY uniq_history_version (user_id, key_type, version)'
    );
    console.log('Added unique constraint on public_key_history (user_id, key_type, version)');
  } catch (err) {
    if (err.code !== 'ER_DUP_KEYNAME') throw err;
  }

  // --- login_attempts table migration (for older schemas) ---
  try {
    await pool.execute(
      `CREATE TABLE IF NOT EXISTS login_attempts (
        id CHAR(36) PRIMARY KEY,
        user_id CHAR(36) NOT NULL,
        ip_address VARCHAR(45) NOT NULL,
        attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        success BOOLEAN NOT NULL DEFAULT FALSE,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        INDEX idx_user_attempts (user_id, attempted_at),
        INDEX idx_ip_attempts (ip_address, attempted_at)
      )`
    );
  } catch (err) {
    // Table already exists — fine.
  }

  console.log('Tables created');
  await pool.end();
}

init().catch(console.error);