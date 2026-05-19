const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { ConflictError, UnauthorisedError } = require('../utils/errors');
const logger = require('../utils/logger');

/**
 * AuthService handles registration and login.
 * Receives a UserRepository and a HashStrategy via constructor injection
 * (wired by ServiceFactory).
 *
 * The hash strategy is Argon2id in production — see HashStrategy.js
 * for parameter justification.
 */
class AuthService {
  constructor(userRepository, hashStrategy) {
    this._userRepo = userRepository;
    this._hashStrategy = hashStrategy;
  }

  async register({ username, email, password }) {
    // Check for existing user (prevents enumeration via timing — both paths hash)
    const existing = await this._userRepo.findByUsername(username);
    if (existing) {
      throw new ConflictError('Username already taken');
    }

    const id = uuidv4();
    const passwordHash = await this._hashStrategy.hash(password);

    await this._userRepo.create({ id, username, email, passwordHash });

    logger.info(`User registered: ${username}`);
    return { id, username, email };
  }

  async login({ username, password }) {
    const user = await this._userRepo.findByUsername(username);
    if (!user) {
      // Hash anyway to prevent timing-based user enumeration
      await this._hashStrategy.hash(password);
      throw new UnauthorisedError('Invalid username or password');
    }

    const valid = await this._hashStrategy.verify(password, user.password_hash);
    if (!valid) {
      throw new UnauthorisedError('Invalid username or password');
    }

    const token = jwt.sign(
      { sub: user.id, username: user.username },
      config.jwt.secret,
      { expiresIn: config.jwt.expiresIn }
    );

    logger.info(`User logged in: ${username}`);
    return {
      token,
      user: { id: user.id, username: user.username, email: user.email },
    };
  }

  verifyToken(token) {
    return jwt.verify(token, config.jwt.secret);
  }
}

module.exports = AuthService;
