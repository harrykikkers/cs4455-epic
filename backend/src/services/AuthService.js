
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
const { audit } = require('../utils/logger');

class AuthService {
  constructor(userRepository, hashStrategy) {
    this._userRepo = userRepository;
    this._hashStrategy = hashStrategy;
  }

  async register({ username, password }) {
    // Hash unconditionally before the uniqueness check so register-time
    // latency doesn't leak whether the username is already taken. The
    // _response_ still differentiates (409 CONFLICT for a taken name) —
    // that's a deliberate UX trade-off, since users have to be told to
    // pick a different name. The 5-req/hour rate limit on /api/auth/register
    // (see app.js) is the primary defence against scripted enumeration.
    const passwordHash = await this._hashStrategy.hash(password);

    const existing = await this._userRepo.findByUsername(username);
    if (existing) {
      throw new ConflictError('Username already taken');
    }

    const userId = uuidv4();
    await this._userRepo.create({ userId, username, passwordHash });

    logger.info(`User registered: ${username}`);
    audit.info(`auth.register.success user=${username} userId=${userId}`);
    return { userId, username };
  }

  async login({ username, password }) {
    const user = await this._userRepo.findByUsername(username);
    if (!user) {
      // Burn time so missing-user latency matches verify() latency.
      // try/catch because argon2.hash throws on empty/non-string input —
      // without it, a missing user with a malformed password would 500
      // instead of 401 and leak existence via the status code.
      try { await this._hashStrategy.hash(password); } catch { /* intentionally ignored */ }
      audit.warn(`auth.login.failure reason=unknown_user attempted_username=${username}`);
      throw new UnauthorisedError('Invalid username or password');
    }

    const valid = await this._hashStrategy.verify(password, user.password_hash);
    if (!valid) {
      audit.warn(`auth.login.failure reason=bad_password user=${user.username} userId=${user.user_id}`);
      throw new UnauthorisedError('Invalid username or password');
    }

    const token = jwt.sign(
      {
        sub: user.user_id,
        username: user.username,
        // Stamp the token with the password version it was issued against.
        // verifyToken refuses tokens whose stamp is older than the user's
        // current password_changed_at — i.e. tokens issued before a password
        // change are invalidated immediately on next use.
        pwdChangedAt: pwdChangedAtSeconds(user),
      },
      config.jwt.secret,
      { expiresIn: config.jwt.expiresIn }
    );

    logger.info(`User logged in: ${username}`);
    audit.info(`auth.login.success user=${user.username} userId=${user.user_id}`);
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
    audit.info(`auth.password.changed user=${user.username} userId=${userId}`);
  }

  async verifyToken(token) {
    const decoded = jwt.verify(token, config.jwt.secret);

    // DB-side check: refuse tokens whose pwdChangedAt stamp predates the
    // user's current password_changed_at. This is what makes a password
    // change immediately invalidate every outstanding session, instead of
    // waiting for the token to expire on its own.
    const user = await this._userRepo.findById(decoded.sub);
    if (!user) {
      throw new UnauthorisedError('User no longer exists');
    }
    const current = pwdChangedAtSeconds(user);
    if (!decoded.pwdChangedAt || decoded.pwdChangedAt < current) {
      audit.warn(`auth.token.invalidated user=${user.username} userId=${user.user_id} reason=password_changed`);
      throw new UnauthorisedError('Token invalidated by password change');
    }

    return decoded;
  }
}

/** Unix-seconds stamp of the user's current password version. */
function pwdChangedAtSeconds(user) {
  const dt = user.password_changed_at || user.created_at;
  return Math.floor(new Date(dt).getTime() / 1000);
}

module.exports = AuthService;