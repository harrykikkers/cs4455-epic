const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { ConflictError, UnauthorisedError } = require('../utils/errors');
const logger = require('../utils/logger').child({ component: 'auth' });

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
    // Hash first so all branches incur the same cost — keeps timing flat
    // regardless of whether the username/email is taken.
    const passwordHash = await this._hashStrategy.hash(password);

    const [existingUsername, existingEmail] = await Promise.all([
      this._userRepo.findByUsername(username),
      this._userRepo.findByEmail(email),
    ]);
    if (existingUsername) throw new ConflictError('Username already taken');
    if (existingEmail) throw new ConflictError('Email already registered');

    const id = uuidv4();
    try {
      await this._userRepo.create({ id, username, email, passwordHash });
    } catch (err) {
      // Race window between the check above and INSERT — let the unique
      // index do its job and translate the driver error.
      if (err && err.code === 'ER_DUP_ENTRY') {
        throw new ConflictError('Username or email already registered');
      }
      throw err;
    }

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

    let valid = false;
    try {
      valid = await this._hashStrategy.verify(password, user.password_hash);
    } catch {
      // Corrupted or malformed hash — treat as failed auth, not a 500
      valid = false;
    }
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

  /**
   * Fetches the live user record so /api/auth/me reflects DB state
   * (deletes, renames) rather than the JWT claims at issue time.
   */
  async getUser(userId) {
    const user = await this._userRepo.findById(userId);
    if (!user) {
      throw new UnauthorisedError('User no longer exists');
    }
    return { id: user.id, username: user.username, email: user.email };
  }

  verifyToken(token) {
    return jwt.verify(token, config.jwt.secret);
  }
}

module.exports = AuthService;
