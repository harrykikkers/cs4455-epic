
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
  next();
}

const validate = {
  register: [
    body('username')
      .trim()
      .isLength({ min: 3, max: 30 })
      .withMessage('Username must be 3–30 characters')
      .matches(/^[a-zA-Z0-9_-]+$/)
      .withMessage('Username may only contain letters, numbers, hyphens, and underscores'),
    body('password')
      .isLength({ min: 12 })
      .withMessage('Password must be at least 12 characters'),
    handleValidation,
  ],

  login: [
    body('username').trim().notEmpty().withMessage('Username required'),
    body('password').notEmpty().withMessage('Password required'),
    handleValidation,
  ],

  changePassword: [
    body('currentPassword').notEmpty().withMessage('Current password required'),
    body('newPassword')
      .isLength({ min: 12 })
      .withMessage('New password must be at least 12 characters'),
    handleValidation,
  ],

  sendMessage: [
    body('recipientId').isUUID().withMessage('Valid recipient ID required'),
    // HPKE encapsulated key — 32-byte X25519 pubkey, base64 → 44 chars.
    // VARCHAR(64) in the schema leaves headroom, but anything outside the
    // 43–64 char window can't be a valid encapsulation.
    body('enc')
      .isString().withMessage('enc must be a string')
      .isLength({ min: 43, max: 64 }).withMessage('enc length is not consistent with a 32-byte HPKE encapsulation')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('enc must be base64 or base64url'),
    body('ciphertext').notEmpty().withMessage('Ciphertext required'),
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
    param('id').isUUID().withMessage('Valid message ID required'),
    body('recipientId').isUUID().withMessage('Valid recipient ID required'),
    // Per-share HPKE encapsulation — the forwarder re-encrypts under the
    // new recipient's X25519 key, so enc is freshly generated, not copied
    // from the original message.
    body('enc')
      .isString().withMessage('enc must be a string')
      .isLength({ min: 43, max: 64 }).withMessage('enc length is not consistent with a 32-byte HPKE encapsulation')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('enc must be base64 or base64url'),
    body('ciphertext').notEmpty().withMessage('Re-encrypted ciphertext required'),
    body('nonce')
      .isString().withMessage('nonce must be a string')
      .isLength({ min: 16, max: 16 }).withMessage('nonce must be exactly 16 chars (base64 of 12-byte IV)')
      .matches(/^[A-Za-z0-9+/=_-]+$/).withMessage('nonce must be base64 or base64url'),
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
  ],
};

module.exports = validate;