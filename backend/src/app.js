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

const AuthService = require('./services/AuthService');
const MessageService = require('./services/MessageService');
const BlockchainService = require('./services/BlockchainService');
const KeyService = require('./services/KeyService');
const PasswordHasher = require('./services/PasswordHasher');

async function bootstrap() {
  // Fail fast on missing secrets before anything else happens.
  config.validate();

  const app = express();

  // Trust the first proxy hop so express-rate-limit (and req.ip) read the
  // real client address from X-Forwarded-For rather than the proxy's IP.
  // Without this the auth limiter becomes a global counter behind a proxy.
  app.set('trust proxy', 1);

  // ── Request correlation ───────────────────────────────────────
  // Stamp every request with a UUID before any other middleware runs so
  // that rate-limit denials, validation errors, and unhandled exceptions
  // all carry the same correlation ID — essential for the pentest report.
  app.use(requestId);

  // ── Security middleware ───────────────────────────────────────
  // Helmet sets secure HTTP headers (X-Content-Type-Options,
  // X-Frame-Options, Strict-Transport-Security, etc.)
  app.use(helmet());

  // CORS — restrict to the configured origin in production, permissive in dev
  app.use(cors({
    origin: config.env === 'production' ? config.allowedOrigin : '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  }));

  // ── Rate limiting ─────────────────────────────────────────────
  // Brute-force resilience on auth endpoints. The express-rate-limit
  // middleware tracks per-IP (req.ip is correct because of `trust proxy 1`).
  //
  // Register has its own stricter limit because the endpoint inherently
  // confirms username existence (409 vs 201) — a UX necessity, but it
  // means low rate limits are the primary defence against enumeration.
  const registerLimiter = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 5,
    message: { error: { code: 'RATE_LIMITED', message: 'Too many registration attempts' } },
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api/auth/register', registerLimiter);

  const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 20, // login + password change combined
    message: { error: { code: 'RATE_LIMITED', message: 'Too many requests' } },
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api/auth', authLimiter);

  // General rate limiter — outer ceiling for the rest of /api. nginx adds
  // a second layer (10 req/s burst 20) at the edge.
  const generalLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 200,
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/api', generalLimiter);

  // Body parsing. 256 KB is generous for an AEAD ciphertext + nonce + metadata
  // and starves attackers trying to wedge the JSON parser with megabytes of
  // input. nginx's client_max_body_size is set to the same value at the edge
  // so oversized bodies are dropped before they reach Node.
  app.use(express.json({ limit: '256kb' }));

  // ── Dependency wiring ────────────────────────────────────────
  // Build repositories on the shared pool, then assemble services on top.
  // BlockchainService is constructed eagerly so its Sepolia provider is
  // ready before the first POST /api/messages fires. MessageService takes
  // it as a direct collaborator — no event bus indirection.
  const pool = getPool();
  const userRepo = new UserRepository(pool);
  const messageRepo = new MessageRepository(pool);
  const keyRepo = new KeyRepository(pool);

  const blockchainService = new BlockchainService(messageRepo);
  const services = {
    authService: new AuthService(userRepo, new PasswordHasher()),
    messageService: new MessageService(messageRepo, blockchainService),
    keyService: new KeyService(keyRepo),
  };

  // ── Routes ───────────────────────────────────────────────────
  mountRoutes(app, services);

  // ── Global error handler (must be last) ──────────────────────
  app.use(errorHandler);

  // ── Start server ─────────────────────────────────────────────
  // Bind loopback-only in production. The public entry point is nginx on
  // :443, which proxies to 127.0.0.1:3000. Binding to loopback means Node
  // physically cannot accept off-host connections even if the firewall
  // misconfigures — defence in depth for the "compromised infrastructure"
  // posture. In development, bind to all interfaces for easier testing.
  const bindHost = config.env === 'production' ? '127.0.0.1' : '0.0.0.0';
  const server = app.listen(config.port, bindHost, () => {
    logger.info(`Server running on ${bindHost}:${config.port} [${config.env}]`);
  });

  // ── Graceful shutdown — drain connections then close the pool ─
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
