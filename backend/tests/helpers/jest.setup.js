/**
 * Global test setup. Loaded once by Jest before any test file runs.
 *
 * - Forces NODE_ENV=test so config validation accepts a placeholder JWT
 *   secret and skips production-only checks.
 * - Provides a 32+ char JWT secret so config.validate() doesn't throw
 *   when tests indirectly load config (e.g. AuthService imports config).
 * - Silences the winston file transport — tests should never write to
 *   logs/error.log or logs/audit.log.
 */
process.env.NODE_ENV = process.env.NODE_ENV || 'test';
process.env.JWT_SECRET = process.env.JWT_SECRET
  || 'test-secret-for-jest-only-not-for-real-use-12345678';
process.env.JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '1h';
process.env.ERROR_LOG_PATH = process.env.ERROR_LOG_PATH || '/tmp/secure-messenger-test.log';
process.env.LOG_LEVEL = 'error'; // suppress info/debug noise during tests
