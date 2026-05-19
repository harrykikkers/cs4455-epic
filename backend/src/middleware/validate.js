
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
    body('ciphertext').notEmpty().withMessage('Ciphertext required'),
    body('nonce').notEmpty().withMessage('Nonce required'),
    handleValidation,
  ],

  forwardMessage: [
    param('id').isUUID().withMessage('Valid message ID required'),
    body('recipientId').isUUID().withMessage('Valid recipient ID required'),
    body('ciphertext').notEmpty().withMessage('Re-encrypted ciphertext required'),
    body('nonce').notEmpty().withMessage('Nonce required'),
    handleValidation,
  ],

  revokeAccess: [
    param('id').isUUID().withMessage('Valid message ID required'),
    body('userId').isUUID().withMessage('Valid user ID to revoke required'),
    handleValidation,
  ],

  publishKey: [
    body('publicKey').notEmpty().withMessage('Public key required'),
    body('keyType')
      .isIn(['x25519', 'ed25519'])
      .withMessage('keyType must be x25519 or ed25519'),
    handleValidation,
  ],

  pagination: [
    query('limit').optional().isInt({ min: 1, max: 100 }).toInt(),
    query('offset').optional().isInt({ min: 0 }).toInt(),
    handleValidation,
  ],
};

module.exports = validate;