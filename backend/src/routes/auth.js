const { Router } = require('express');
const validate = require('../middleware/validate');

/**
 * Route definitions are separated from controllers.
 * Each route file receives the controller and auth middleware
 * from the router factory in routes/index.js.
 */

function authRoutes(authController, authMw) {
  const router = Router();

  router.post('/register', validate.register, authController.register);
  router.post('/login', validate.login, authController.login);
  router.put('/password', authMw, validate.changePassword, authController.changePassword);
  router.get('/me', authMw, authController.me);

  return router;
}

module.exports = authRoutes;