const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');

const config = require('./config');
const { getPool } = require('./config/database');
const mountRoutes = require('./routes');
const errorHandler = require('./middleware/errorHandler');
const requestId = require('./middleware/requestId');
const logger = require('./utils/logger').child({ component: 'app' });

const UserRepository = require('./repositories/UserRepository');
const MessageRepository = require('./repositories/MessageRepository');
const KeyRepository = require('./repositories/KeyRepository');
const LoginAttemptRepository = require('./repositories/LoginAttemptRepository');

const AuthService = require('./services/AuthService');
const MessageService = require('./services/MessageService');
const BlockchainService = require('./services/BlockchainService');
const KeyService = require('./services/KeyService');
const PasswordHasher = require('./services/PasswordHasher');

async function bootstrap() {
  config.validate();

  const app = express();

  // Trust the first proxy hop so express-rate-limit (and req.ip) read the
  // real client address from X-Forwarded-For rather than the proxy's IP.
  // Without this the auth limiter becomes a global counter behind a proxy.
  app.set('trust proxy', 1);

  // Request correlation 
  // Stamp every request with a UUID before any other middleware runs so
  // that rate-limit denials, validation errors, and unhandled exceptions
  // all carry the same correlation ID — essential for the pentest report.
  app.use(requestId);

  // Security Middleware
  // Helmet sets secure HTTP headers (X-Content-Type-Options,
  // X-Frame-Options, Strict-Transport-Security, etc.)
  //
  // This service only ever returns JSON — it serves no HTML, scripts, styles,
  // images, or frames — so the CSP is locked all the way down to
  // `default-src 'none'`. Every fetch directive falls back to default-src, so
  // a single 'none' covers script/img/connect/etc. `frame-ancestors` does not
  // fall back, so it is set explicitly to forbid the API being framed.
  app.use(helmet({ // helmet automatically sets secure HTTP response headers.
    contentSecurityPolicy: {
      useDefaults: false,
      directives: {
        'default-src': ["'none'"],
        'frame-ancestors': ["'none'"],
      },
    },
  }));

  // CORS — restrict to the configured origin in production, permissive in dev
  app.use(cors({
    origin: config.env === 'production' ? config.allowedOrigin : '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  }));

  // Rate limiting 
  const registerLimiter = rateLimit({
    windowMs: config.rateLimits.register.windowMs,
    max: config.rateLimits.register.max,
    message: { error: { code: 'RATE_LIMITED', message: 'Too many registration attempts' } },
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api/auth/register', registerLimiter);

  const authLimiter = rateLimit({
    windowMs: config.rateLimits.auth.windowMs, // 15 minutes
    max: config.rateLimits.auth.max, // login + password change combined
    message: { error: { code: 'RATE_LIMITED', message: 'Too many requests' } },
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api/auth', authLimiter);

  // General rate limiter — outer ceiling for the rest of /api. nginx adds
  const generalLimiter = rateLimit({
    windowMs: config.rateLimits.general.windowMs,
    max: config.rateLimits.general.max,
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api', generalLimiter);


  // nginx's client_max_body_size is set to the same value at the edge
  // so oversized bodies are dropped before they reach Node.
  app.use(express.json({ limit: '256kb' }));

  // Dependency wiring 
  const pool = getPool();
  const userRepo = new UserRepository(pool);
  const messageRepo = new MessageRepository(pool);
  const keyRepo = new KeyRepository(pool);
  const loginAttemptRepo = new LoginAttemptRepository(pool);

  const blockchainService = new BlockchainService(messageRepo);
  const services = {
    authService: new AuthService(userRepo, new PasswordHasher(), loginAttemptRepo),
    messageService: new MessageService(messageRepo, blockchainService),
    keyService: new KeyService(keyRepo),
  };

  // Routes
  mountRoutes(app, services);

  // Global error handler
  app.use(errorHandler);

  // Start server
  const bindHost = config.env === 'production' ? '127.0.0.1' : '0.0.0.0';
  const server = app.listen(config.port, bindHost, () => {
    logger.info(`Server running on ${bindHost}:${config.port} [${config.env}]`);
  });

  // Graceful shutdown
  const shutdown = (signal) => {
    logger.info(`${signal} received — shutting down`);
    server.close(async (closeErr) => {
      if (closeErr) logger.error('HTTP server close error:', closeErr);
      try {
        await pool.end();
      } catch (poolErr) {
        logger.error('Pool close error:', poolErr);
      }
      process.exit(closeErr ? 1 : 0);
    });
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

bootstrap().catch((err) => {
  logger.error('Failed to start server:', err);
  process.exit(1);
});
