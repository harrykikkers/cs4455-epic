const dotenv = require('dotenv');
const path = require('path');

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

/**
 * Centralised configuration object.
 * Every module reads config from here — never from process.env directly.
 * This is the single source of truth (a lightweight Registry pattern).
 */
const config = {
  env: process.env.NODE_ENV || 'development',
  port: parseInt(process.env.PORT, 10) || 3000,

  db: {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT, 10) || 3306,
    user: process.env.DB_USER || 'messenger',
    password: process.env.DB_PASSWORD || '',
    database: process.env.DB_NAME || 'secure_messenger',
  },

  jwt: {
    // No insecure fallback — bootstrap validates this is set before listen().
    secret: process.env.JWT_SECRET,
    // Default matches .env.example. Short-lived tokens keep the
    // damage window small when password_changed_at invalidation lags
    // (e.g. read replicas, caches).
    expiresIn: process.env.JWT_EXPIRES_IN || '1h',
  },

  argon2: {
    memoryCost: parseInt(process.env.ARGON2_MEMORY_COST, 10) || 65536,
    timeCost: parseInt(process.env.ARGON2_TIME_COST, 10) || 3,
    parallelism: parseInt(process.env.ARGON2_PARALLELISM, 10) || 4,
  },

  blockchain: {
    rpcUrl: process.env.SEPOLIA_RPC_URL || '',
    privateKey: process.env.SEPOLIA_PRIVATE_KEY || '',
    contractAddress: process.env.CONTRACT_ADDRESS || '',
  },

  allowedOrigin: process.env.ALLOWED_ORIGIN || '',

  logging: {
    errorLogPath: process.env.ERROR_LOG_PATH || 'logs/error.log',
  },
};

/**
 * Fail-loud validation. Called once from bootstrap so that one-off scripts
 * like `db:init` can still load config without requiring a JWT secret.
 */
function validate() {
  const errors = [];

  if (!config.jwt.secret || config.jwt.secret.length < 32) {
    errors.push('JWT_SECRET must be set and at least 32 characters long');
  }

  if (config.env === 'production' && !config.allowedOrigin) {
    errors.push('ALLOWED_ORIGIN must be set in production');
  }

  // Argon2id parameter floors. OWASP's 2023 minimum recommendation for
  // Argon2id is m=19 MiB, t=2, p=1 — anything below that and a
  // misconfigured deployment ships near-instant password hashing.
  if (config.argon2.memoryCost < 19456) {
    errors.push(
      `ARGON2_MEMORY_COST=${config.argon2.memoryCost} KiB is below the OWASP minimum of 19456 (19 MiB)`
    );
  }
  if (config.argon2.timeCost < 2) {
    errors.push(`ARGON2_TIME_COST=${config.argon2.timeCost} is below the OWASP minimum of 2`);
  }
  if (config.argon2.parallelism < 1) {
    errors.push(`ARGON2_PARALLELISM=${config.argon2.parallelism} must be at least 1`);
  }

  if (errors.length) {
    throw new Error(`Invalid configuration:\n  - ${errors.join('\n  - ')}`);
  }
}

module.exports = config;
module.exports.validate = validate;
