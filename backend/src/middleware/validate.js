
/**
 * Runs express-validator checks and throws BadRequestError if any fail.
 * Use as the last item in a validation chain:
 *   router.post('/register', validate.register, controller.register)
 */
const { body, param, query, validationResult } = require('express-validator');
const { BadRequestError } = require('../utils/errors');

function handleValidation(req, _res, next) {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    const messages = errors.array().map((e) => e.msg);
    return next(new BadRequestError(messages.join('; ')));
  }
  next(); // proceed to the next middleware 
}

// The client never sends the cleartext password. It sends a 64-char lowercase
// hex Argon2id pre-hash (client crypto.kdf.derive_auth_hash), so the plaintext
// never leaves the device. Password *strength* is therefore enforced
// client-side; here we only check the credential's shape. AuthService still
// salts and re-hashes this value with Argon2id (PasswordHasher) before storage,
// so a leaked password_hash is not directly replayable.
const AUTH_CREDENTIAL = /^[0-9a-f]{64}$/; // regex

// Explicit upper bound on the relayed AES-GCM ciphertext (base64). The whole
// JSON body is already capped at 256 KB by express.json, but that ceiling is
// shared with every other field; bounding ciphertext on its own rejects a
// single oversized blob early and keeps the per-field limit auditable.
// 200_000 base64 chars ≈ 150 KB of ciphertext, comfortably under the body cap.
const MAX_CIPHERTEXT_LEN = 200000;

function ciphertext(label = 'Ciphertext') {
  return body('ciphertext')
    .isString().withMessage('ciphertext must be a string')
    .notEmpty().withMessage(`${label} required`)
    .isLength({ max: MAX_CIPHERTEXT_LEN })
    .withMessage(`ciphertext exceeds ${MAX_CIPHERTEXT_LEN}-char limit`);
}

function authCredential(field, label) {
  return body(field)
    .isString().withMessage(`${label} must be a string`)
    .matches(AUTH_CREDENTIAL)
    .withMessage(`${label} must be the client-side password hash (64 hex chars)`);
}

const validate = {
  register: [
    body('username')
      .trim()
      .isLength({ min: 3, max: 30 })
      .withMessage('Username must be 3–30 characters')
      .matches(/^[a-zA-Z0-9_-]+$/)
      .withMessage('Username may only contain letters, numbers, hyphens, and underscores'),
    authCredential('password', 'Password'),
    handleValidation,
  ],

  login: [
    body('username').trim().notEmpty().withMessage('Username required'),
    authCredential('password', 'Password'),
    handleValidation,
  ],

  changePassword: [
    authCredential('currentPassword', 'Current password'),
    authCredential('newPassword', 'New password'),
    handleValidation,
  ],

  sendMessage: [
    body('recipientId').isUUID().withMessage('Valid recipient ID required'),
    ciphertext('Ciphertext'),
    // 12-byte AES-GCM IV, base64 → exactly 16 chars (CHAR(16) in schema).
    body('nonce')
      .isString().withMessage('nonce must be a string')
      .isLength({ min: 16, max: 16 }).withMessage('nonce must be exactly 16 chars (base64 of 12-byte IV)')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('nonce must be base64 or base64url'),
    body('signature')
      .isString().withMessage('signature must be a string')
      .notEmpty().withMessage('Ed25519 signature required')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('signature must be base64 or base64url'),
    body('seqNo')
      .exists().withMessage('seqNo required')
      .isInt({ min: 0 }).withMessage('seqNo must be a non-negative integer')
      .toInt(),
    // Client-supplied keccak256 of the plaintext, 0x + 64 hex chars (32 bytes).
    // The server never sees plaintext, so it cannot compute this itself —
    // it relays whatever the client commits to, then writes it on-chain.
    body('digest')
      .isString().withMessage('digest must be a string')
      .matches(/^0x[0-9a-fA-F]{64}$/).withMessage('digest must be 0x + 64 hex chars (keccak256)'),
    handleValidation,
  ],

  forwardMessage: [
    // A forward is a direct message where the forwarder is the sender, so the
    // crypto fields match sendMessage exactly: the forwarder re-encrypts the
    // plaintext under the new recipient's pinned X25519 key with a fresh nonce,
    // Ed25519-signs it, and supplies seq_no + digest. There is no enc field.
    param('id').isUUID().withMessage('Valid message ID required'),
    body('recipientId').isUUID().withMessage('Valid recipient ID required'),
    ciphertext('Re-encrypted ciphertext'),
    body('nonce')
      .isString().withMessage('nonce must be a string')
      .isLength({ min: 16, max: 16 }).withMessage('nonce must be exactly 16 chars (base64 of 12-byte IV)')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('nonce must be base64 or base64url'),
    body('signature')
      .isString().withMessage('signature must be a string')
      .notEmpty().withMessage('Ed25519 signature required')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('signature must be base64 or base64url'),
    body('seqNo')
      .exists().withMessage('seqNo required')
      .isInt({ min: 0 }).withMessage('seqNo must be a non-negative integer')
      .toInt(),
    body('digest')
      .isString().withMessage('digest must be a string')
      .matches(/^0x[0-9a-fA-F]{64}$/).withMessage('digest must be 0x + 64 hex chars (keccak256)'),
    handleValidation,
  ],

  revokeAccess: [
    param('id').isUUID().withMessage('Valid message ID required'),
    body('userId').isUUID().withMessage('Valid user ID to revoke required'),
    handleValidation,
  ],

  publishKey: [
    // x25519 and ed25519 public keys are 32 raw bytes. Accept either
    // base64 (44 chars, padded), base64url (43 chars, unpadded), or
    // hex (64 chars). The exact length depends on encoding, but anything
    // outside the 43–88 char window can't possibly be a valid 32-byte key.
    body('publicKey')
      .isString().withMessage('publicKey must be a string')
      .isLength({ min: 43, max: 88 })
      .withMessage('publicKey length is not consistent with a 32-byte key')
      .matches(/^[A-Za-z0-9+/=_-]+$/)
      .withMessage('publicKey must be base64, base64url, or hex'),
    body('keyType')
      .isIn(['x25519', 'ed25519'])
      .withMessage('keyType must be x25519 or ed25519'),
    body('acknowledgeRotation')
      .optional()
      .isBoolean().withMessage('acknowledgeRotation must be a boolean')
      .toBoolean(),
    handleValidation,
  ],

  pagination: [
    query('limit').optional().isInt({ min: 1, max: 100 }).toInt(),
    query('offset').optional().isInt({ min: 0 }).toInt(),
    handleValidation,
  ], // Validates the URL query params for pagination (e.g., ?limit=20&offset=40)

  lookupUser: [
    query('username')
      .isString().withMessage('username query param required')
      .trim()
      .isLength({ min: 1 }).withMessage('username cannot be empty'),
    handleValidation,
  ],
};

module.exports = validate;