const path = require('path');
const fs = require('fs');
const { createLogger, format, transports } = require('winston');
const config = require('../config');

/**
 * Structured logger using Winston.
 *
 * Output uses fixed-width columns so log lines align vertically and stay
 * easy to scan in a terminal or pager:
 *
 *   2026-05-19T18:12:03.421Z  INFO   [auth]        User registered: alice
 *
 * Per-module tags come from logger.child({ component }) — each service
 * creates a child logger at import time, so call sites stay terse.
 *
 * The console transport is colorised; the file transport is plain so a
 * `cat`/`less` of the log file doesn't show ANSI escape codes.
 *
 * NEVER log sensitive data (passwords, keys, tokens, plaintext).
 */

const TIMESTAMP_WIDTH = 24; // ISO 8601 with ms + Z
const LEVEL_WIDTH = 5;      // longest is "error" / "debug"
const COMPONENT_WIDTH = 12; // accommodates "[blockchain]"

const CONTINUATION_INDENT = ' '.repeat(
  TIMESTAMP_WIDTH + 2 + LEVEL_WIDTH + 2 + COMPONENT_WIDTH + 2
);

const LEVEL_COLOR = {
  error: '[31m', // red
  warn: '[33m',  // yellow
  info: '[36m',  // cyan
  debug: '[90m', // grey
};
const RESET = '[0m';

function padRight(value, width) {
  return value.length >= width ? value : value + ' '.repeat(width - value.length);
}

function indentBlock(text) {
  return text
    .split('\n')
    .map((line) => CONTINUATION_INDENT + line)
    .join('\n');
}

function buildLine(info, colored) {
  const ts = info.timestamp;
  const rawLevel = info.level;
  const levelText = padRight(rawLevel.toUpperCase(), LEVEL_WIDTH);
  const level = colored && LEVEL_COLOR[rawLevel]
    ? `${LEVEL_COLOR[rawLevel]}${levelText}${RESET}`
    : levelText;
  const tag = padRight(`[${info.component || 'app'}]`, COMPONENT_WIDTH);

  let line = `${ts}  ${level}  ${tag}  ${info.message}`;
  if (info.stack) {
    line += '\n' + indentBlock(info.stack);
  }
  return line;
}

const lineFormat = (colored) => format.combine(
  format.timestamp(),
  format.errors({ stack: true }),
  format.printf((info) => buildLine(info, colored))
);

// Make sure the log directory exists before Winston tries to open the file.
fs.mkdirSync(
  path.dirname(path.resolve(config.logging.errorLogPath)),
  { recursive: true }
);

const isProd = config.env === 'production';

const logger = createLogger({
  level: process.env.LOG_LEVEL || (isProd ? 'info' : 'debug'),
  exitOnError: false,
  transports: [
    new transports.Console({ format: lineFormat(true) }),
    new transports.File({
      filename: config.logging.errorLogPath,
      level: 'error',
      format: lineFormat(false),
      maxsize: 5 * 1024 * 1024,
      maxFiles: 5,
      tailable: true,
    }),
  ],
});

/**
 * Audit log — a write-only record of security-relevant events for the
 * pentest report and post-incident forensics. Kept in its own file so
 * (a) it isn't lost in the noise of the general app log, and (b) so the
 * file can be made append-only on disk (`chattr +a`) without breaking
 * normal logging.
 *
 * Events emitted via auditLogger.info / .warn:
 *   - auth.login.success / auth.login.failure
 *   - auth.register.success
 *   - auth.password.changed
 *   - auth.token.invalidated (password change forced)
 *   - key.published / key.rotated
 *   - access.denied (any 403)
 *
 * Pentest-relevant: every entry includes the request ID stamped by the
 * requestId middleware, so a finding ("I forwarded a message I didn't
 * own at 14:32:18") maps directly to the server-side audit row.
 */
// Resolve audit.log to live in the same directory as the error log,
// regardless of what filename the operator chose for error_log_path.
const errorLogResolved = path.resolve(config.logging.errorLogPath || 'logs/error.log');
const auditLogPath = path.join(path.dirname(errorLogResolved), 'audit.log');

const auditLogger = createLogger({
  level: 'info',
  exitOnError: false,
  transports: [
    new transports.File({
      filename: auditLogPath,
      format: lineFormat(false),
      maxsize: 10 * 1024 * 1024,
      maxFiles: 10,
      tailable: true,
    }),
  ],
});

// Tag every audit line with component=audit so the formatter aligns it
// with the rest of the columned output, and so anyone tailing the file
// sees the same shape they're used to from the app log.
const audit = auditLogger.child({ component: 'audit' });

module.exports = logger;
module.exports.audit = audit;
