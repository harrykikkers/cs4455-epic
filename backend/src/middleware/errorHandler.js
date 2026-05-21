const logger = require('../utils/logger').child({ component: 'http' });
const { AppError } = require('../utils/errors');

/**
 * Global error-handling middleware (must have 4 params for Express to recognise it).
 *
 * Catches AppError subclasses and returns structured JSON.
 * Unknown errors get a generic 500 to avoid leaking internals.
 *
 * Every response carries the request ID stamped by requestId middleware
 * so a finding in the pentest report can be traced back to a single
 * log line on the server.
 */
function errorHandler(err, req, res, _next) {
  const requestId = req.id || null;

  // Operational errors we threw deliberately
  if (err instanceof AppError) {
    return res.status(err.statusCode).json({
      error: {
        code: err.code,
        message: err.message,
        requestId,
      },
    });
  }

  // Malformed JSON from express.json body parser
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({
      error: {
        code: 'INVALID_JSON',
        message: 'Request body contains invalid JSON',
        requestId,
      },
    });
  }

  // Payload too large — body parser refused before we even saw it
  if (err.type === 'entity.too.large') {
    return res.status(413).json({
      error: {
        code: 'PAYLOAD_TOO_LARGE',
        message: 'Request body exceeds the configured limit',
        requestId,
      },
    });
  }

  // Unexpected errors — log the full stack with the request ID, but
  // return only the request ID to the client. The stack stays server-side.
  logger.error(`Unhandled error [req=${requestId}]:`, err);
  return res.status(500).json({
    error: {
      code: 'INTERNAL_ERROR',
      message: 'An unexpected error occurred',
      requestId,
    },
  });
}

module.exports = errorHandler;
