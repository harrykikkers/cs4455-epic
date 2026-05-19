const logger = require('../utils/logger');
const { AppError } = require('../utils/errors');

/**
 * Global error-handling middleware (must have 4 params for Express to recognise it).
 *
 * Catches AppError subclasses and returns structured JSON.
 * Unknown errors get a generic 500 to avoid leaking internals.
 */
function errorHandler(err, _req, res, _next) {
  // Operational errors we threw deliberately
  if (err instanceof AppError) {
    return res.status(err.statusCode).json({
      error: {
        code: err.code,
        message: err.message,
      },
    });
  }

  // Validation errors from express-validator
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({
      error: {
        code: 'INVALID_JSON',
        message: 'Request body contains invalid JSON',
      },
    });
  }

  // Unexpected errors — log the full stack but return generic message
  logger.error('Unhandled error:', err);
  return res.status(500).json({
    error: {
      code: 'INTERNAL_ERROR',
      message: 'An unexpected error occurred',
    },
  });
}

module.exports = errorHandler;
