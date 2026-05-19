const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');

const config = require('./config');
const { getPool } = require('./config/database');
const ServiceFactory = require('./patterns/factory/ServiceFactory');
const mountRoutes = require('./routes');
const errorHandler = require('./middleware/errorHandler');
const logger = require('./utils/logger');

async function bootstrap() {
  const app = express();

  // ── Security middleware ───────────────────────────────────────
  // Helmet sets secure HTTP headers (X-Content-Type-Options,
  // X-Frame-Options, Strict-Transport-Security, etc.)
  app.use(helmet());

  // CORS — restrict to your domain in production
  app.use(cors({
    origin: config.env === 'production'
      ? `https://${process.env.ALLOWED_ORIGIN || 'localhost'}`
      : '*',
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
  app.listen(config.port, () => {
    logger.info(`Server running on port ${config.port} [${config.env}]`);
  });
}

bootstrap().catch((err) => {
  logger.error('Failed to start server:', err);
  process.exit(1);
});
