const authRoutes = require('./auth');
const messageRoutes = require('./messages');
const keyRoutes = require('./keys');

const AuthController = require('../controllers/AuthController');
const MessageController = require('../controllers/MessageController');
const KeyController = require('../controllers/KeyController');
const authMiddleware = require('../middleware/auth');

/**
 * Mounts all API routes onto the Express app. Receives the service
 * instances wired in app.js, builds controllers around them, and curries
 * the auth middleware with authService so JWT verification reuses the
 * same instance that issued the tokens.
 */
function mountRoutes(app, { authService, messageService, keyService }) {
  const authCtrl = new AuthController(authService);
  const messageCtrl = new MessageController(messageService);
  const keyCtrl = new KeyController(keyService);

  const authMw = authMiddleware(authService);

  app.use('/api/auth', authRoutes(authCtrl, authMw));
  app.use('/api/messages', messageRoutes(messageCtrl, authMw));
  app.use('/api/keys', keyRoutes(keyCtrl, authMw));

  // Health check (no auth)
  app.get('/api/health', (_req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });
}

module.exports = mountRoutes;
