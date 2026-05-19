const mysql = require('mysql2/promise');
const config = require('./index');
const logger = require('../utils/logger');

/**
 * Singleton pattern — one connection pool for the entire process.
 * mysql2 pool already manages multiple connections internally;
 * wrapping it in a singleton prevents accidental duplicate pools.
 */
let pool = null;

function getPool() {
  if (!pool) {
    pool = mysql.createPool({
      host: config.db.host,
      port: config.db.port,
      user: config.db.user,
      password: config.db.password,
      database: config.db.database,
      waitForConnections: true,
      connectionLimit: 10,
      queueLimit: 0,
      // Always use parameterised queries — never interpolate user input
      namedPlaceholders: true,
    });

    logger.info('MySQL connection pool created');
  }
  return pool;
}

module.exports = { getPool };
