const path = require('path');
const fs = require('fs');
const { createLogger, format, transports } = require('winston'); // logging library
const config = require('../config');

// Ensure log directory exists
const logDir = path.dirname(path.resolve(config.logging?.errorLogPath || 'logs/error.log'));
try { fs.mkdirSync(logDir, { recursive: true }); } catch (_) {}

// Shared formatters
const consoleFormat = format.combine(
  format.timestamp(),
  format.errors({ stack: true }),
  format.colorize(),
  format.printf(({ timestamp, level, component, message, stack }) => {
    const tag = component ? `[${component}]` : '[app]';
    const line = `${timestamp} ${level} ${tag} ${message}`;
    return stack ? `${line}\n${stack}` : line;
  })
);

const fileFormat = format.combine(
  format.timestamp(),
  format.errors({ stack: true }),
  format.uncolorize(),
  format.printf(({ timestamp, level, component, message, stack }) => {
    const tag = component ? `[${component}]` : '[app]';
    const line = `${timestamp} ${level} ${tag} ${message}`;
    return stack ? `${line}\n${stack}` : line;
  })
);

// Main logger
const logger = createLogger({
  level: process.env.LOG_LEVEL || (config.env === 'production' ? 'info' : 'debug'),
  exitOnError: false,
  transports: [
    new transports.Console({ format: consoleFormat }),
    new transports.File({
      filename: path.join(logDir, 'error.log'),
      level: 'error',
      format: fileFormat,
      maxsize: 5 * 1024 * 1024,
      maxFiles: 5,
    }),
  ],
});

// Audit logger 
const audit = logger.child({ component: 'audit' });
audit.add(new transports.File({
  filename: path.join(logDir, 'audit.log'),
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  maxsize: 10 * 1024 * 1024,
  maxFiles: 10,
}));

module.exports = logger;
module.exports.audit = audit;