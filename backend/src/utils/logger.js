const { createLogger, format, transports } = require('winston');
const config = require('../config');

/**
 * Structured logger using Winston.
 * Logs JSON in production for machine parsing, colourised text in dev.
 * NEVER log sensitive data (passwords, keys, tokens, plaintext).
 */
const logger = createLogger({
  level: config.env === 'production' ? 'info' : 'debug',
  format: format.combine(
    format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
    format.errors({ stack: true }),
    config.env === 'production'
      ? format.json()
      : format.combine(format.colorize(), format.simple())
  ),
  defaultMeta: { service: 'secure-messenger' },
  transports: [
    new transports.Console(),
    new transports.File({ filename: 'error.log', level: 'error' }),
  ],
});

module.exports = logger;
