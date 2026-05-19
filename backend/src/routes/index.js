const authRoutes = require('./auth');
const messageRoutes = require('./messages');
const keyRoutes = require('./keys');
const blockchainRoutes = require('./blockchain');

const AuthController = require('../controllers/AuthController');
const MessageController = require('../controllers/MessageController');
const KeyController = require('../controllers/KeyController');
const BlockchainController = require('../controllers/BlockchainController');
const authMiddleware = require('../middleware/auth');

/**
 * Mounts all API routes onto the Express app.
 * Uses the ServiceFactory to get service instances,
 * then creates controllers and hands them to route builders.
 */
function mountRoutes(app, serviceFactory) {
  // Build services
  const authService = serviceFactory.getAuthService();
  const messageService = serviceFactory.getMessageService();
  const keyService = serviceFactory.getKeyService();
  const blockchainService = serviceFactory.getBlockchainService();

  // Build controllers
  const authCtrl = new AuthController(authService);
  const messageCtrl = new MessageController(messageService);
  const keyCtrl = new KeyController(keyService);
  const blockchainCtrl = new BlockchainController(blockchainService);

  // Auth middleware (curried with authService)
  const authMw = authMiddleware(authService);

  // Mount route groups
  app.use('/api/auth', authRoutes(authCtrl, authMw));
  app.use('/api/messages', messageRoutes(messageCtrl, authMw));
  app.use('/api/keys', keyRoutes(keyCtrl, authMw));
  app.use('/api/blockchain', blockchainRoutes(blockchainCtrl));

  // Health check (no auth)
  app.get('/api/health', (_req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });
}

module.exports = mountRoutes;
