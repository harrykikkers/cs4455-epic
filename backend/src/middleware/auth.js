const { UnauthorisedError } = require('../utils/errors');

/**
 * Express middleware that verifies the JWT from the Authorization header.
 * Attaches the decoded payload to req.user for downstream handlers.
 *
 * Expects: Authorization: Bearer <token>
 */
function authMiddleware(authService) {
  return (req, _res, next) => {
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
      return next(new UnauthorisedError('Missing or malformed Authorization header'));
    }

    const token = header.slice(7);
    try {
      const decoded = authService.verifyToken(token);
      req.user = { id: decoded.sub, username: decoded.username };
      next();
    } catch (err) {
      next(new UnauthorisedError('Invalid or expired token'));
    }
  };
}

module.exports = authMiddleware;
