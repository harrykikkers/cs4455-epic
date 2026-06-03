const { UnauthorisedError } = require('../utils/errors');

/**
 * Express middleware that verifies the JWT from the Authorization header.
 * Attaches the decoded payload to req.user for downstream handlers.
 *
 * Expects: Authorization: Bearer <token>
 */
function authMiddleware(authService) {
  return async (req, _res, next) => { 
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
      return next(new UnauthorisedError('Missing or malformed Authorization header'));
    } // If it's missing or doesn't start with Bearer  — Error

    const token = header.slice(7);
    try {
      const decoded = await authService.verifyToken(token); // async allows await - we wait for verifyToken to finish then continue
      req.user = { id: decoded.sub, username: decoded.username };
      next();
    } catch (err) {
      // Preserve specific reasons (e.g. "Token invalidated by password change",
      // "User no longer exists") instead of collapsing them all into a generic
      // 401 — the JWT library's own errors still get the generic message.
      if (err instanceof UnauthorisedError) return next(err);
      next(new UnauthorisedError('Invalid or expired token'));
    }
  };
}

module.exports = authMiddleware;
