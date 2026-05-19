
/**
 * AuthService handles registration and login.
 * Receives a UserRepository and a HashStrategy via constructor injection
 * (wired by ServiceFactory).
 *
 * The hash strategy is Argon2id in production — see HashStrategy.js
 * for parameter justification.
 */
const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { ConflictError, UnauthorisedError } = require('../utils/errors');
const logger = require('../utils/logger');

class AuthService {
  constructor(userRepository, hashStrategy) {
    this._userRepo = userRepository;
    this._hashStrategy = hashStrategy;
  }

  async register({ username, password }) {
    const existing = await this._userRepo.findByUsername(username);
    if (existing) {
      throw new ConflictError('Username already taken');
    }

    const userId = uuidv4();
    const passwordHash = await this._hashStrategy.hash(password);

    await this._userRepo.create({ userId, username, passwordHash });

    logger.info(`User registered: ${username}`);
    return { userId, username };
  }

  async login({ username, password }) {
    const user = await this._userRepo.findByUsername(username);
    if (!user) {
      await this._hashStrategy.hash(password);
      throw new UnauthorisedError('Invalid username or password');
    }

    const valid = await this._hashStrategy.verify(password, user.password_hash);
    if (!valid) {
      throw new UnauthorisedError('Invalid username or password');
    }

    const token = jwt.sign(
      { sub: user.user_id, username: user.username },
      config.jwt.secret,
      { expiresIn: config.jwt.expiresIn }
    );

    logger.info(`User logged in: ${username}`);
    return {
      token,
      user: { userId: user.user_id, username: user.username },
    };
  }

  async changePassword({ userId, currentPassword, newPassword }) {
    const user = await this._userRepo.findById(userId);
    if (!user) {
      throw new UnauthorisedError('User not found');
    }

    const valid = await this._hashStrategy.verify(currentPassword, user.password_hash);
    if (!valid) {
      throw new UnauthorisedError('Current password is incorrect');
    }

    const newHash = await this._hashStrategy.hash(newPassword);
    await this._userRepo.updatePassword(userId, newHash);

    logger.info(`Password changed for user: ${user.username}`);
  }

  verifyToken(token) {
    return jwt.verify(token, config.jwt.secret);
  }
}

module.exports = AuthService;