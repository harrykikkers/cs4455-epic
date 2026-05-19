const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');

const config = require('./config');
const { getPool } = require('./config/database');
const ServiceFactory = require('./patterns/factory/ServiceFactory');
const mountRoutes = require('./routes');
const errorHandler = require('./middleware/errorHandler');
const logger = require('./utils/logger').child({ component: 'app' });

async function bootstrap() {
  // Fail fast on missing secrets before anything else happens.
  config.validate();

  const app = express();

  // Trust the first proxy hop so express-rate-limit (and req.ip) read the
  // real client address from X-Forwarded-For rather than the proxy's IP.
  // Without this the auth limiter becomes a global counter behind a proxy.
  app.set('trust proxy', 1);

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

  // Rate limiting — prevents brute-force attacks on auth endpoints
  const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 20, // 20 attempts per window
    message: { error: { code: 'RATE_LIMITED', message: 'Too many requests' } },
  });
  app.use('/api/auth', authLimiter);

  // General rate limiter
  const generalLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 200,
  });
  app.use('/api', generalLimiter);

  // Body parsing
  app.use(express.json({ limit: '1mb' }));

  // ── Dependency wiring (Factory pattern) ──────────────────────
  const pool = getPool();
  const serviceFactory = new ServiceFactory(pool);

  // ── Routes ───────────────────────────────────────────────────
  mountRoutes(app, serviceFactory);

  // ── Global error handler (must be last) ──────────────────────
  app.use(errorHandler);

  // ── Start server ─────────────────────────────────────────────
  const server = app.listen(config.port, () => {
    logger.info(`Server running on port ${config.port} [${config.env}]`);
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
