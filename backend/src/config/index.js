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
    secret: process.env.JWT_SECRET || 'CHANGE_ME',
    expiresIn: process.env.JWT_EXPIRES_IN || '24h',
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

  tls: {
    certPath: process.env.TLS_CERT_PATH || '',
    keyPath: process.env.TLS_KEY_PATH || '',
  },
};

module.exports = config;
