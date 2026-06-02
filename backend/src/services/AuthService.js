
/**
 * AuthService handles registration and login.
 * Receives a UserRepository and a PasswordHasher via constructor injection
 * (wired in app.js).
 */
const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { ConflictError, UnauthorisedError, NotFoundError } = require('../utils/errors');
const logger = require('../utils/logger');
const { audit } = require('../utils/logger');

// Lockout policy: more than this many failures inside the window blocks
// further attempts until the window slides past. Matches the comment in
// the login_attempts schema (5 failures within 15 minutes).
const LOCKOUT_MAX_FAILURES = 5;
const LOCKOUT_WINDOW_MS = 15 * 60 * 1000;

class AuthService {
  constructor(userRepository, passwordHasher, loginAttemptRepository = null) {
    this._userRepo = userRepository;
    this._passwordHasher = passwordHasher;
    // Optional — services constructed in older tests can omit it and the
    // login flow falls back to express-rate-limit alone.
    this._loginAttempts = loginAttemptRepository;
  }

  async register({ username, password }) {
    // Hash unconditionally before the uniqueness check so register-time
    // latency doesn't leak whether the username is already taken. The
    // _response_ still differentiates (409 CONFLICT for a taken name) —
    // that's a deliberate UX trade-off, since users have to be told to
    // pick a different name. The 5-req/hour rate limit on /api/auth/register
    // (see app.js) is the primary defence against scripted enumeration.
    const passwordHash = await this._passwordHasher.hash(password);

    const existing = await this._userRepo.findByUsername(username);
    if (existing) {
      throw new ConflictError('Username already taken');
    }

    const userId = uuidv4();
    await this._userRepo.create({ userId, username, passwordHash });

    audit.info(`auth.register.success user=${username} userId=${userId}`);
    return { userId, username };
  }

  async login({ username, password, ipAddress = 'unknown' }) {
    const user = await this._userRepo.findByUsername(username);
    if (!user) {
      // Burn time so missing-user latency matches verify() latency.
      // try/catch because argon2.hash throws on empty/non-string input —
      // without it, a missing user with a malformed password would 500
      // instead of 401 and leak existence via the status code.
      try { await this._passwordHasher.hash(password); } catch { /* intentionally ignored */ }
      audit.warn({
        event: 'auth.login.failure',
        reason: 'unknown_user',
        attempted_username: username,
      });
      throw new UnauthorisedError('Invalid username or password');
    }

    if (this._loginAttempts) {
      const failures = await this._loginAttempts.countRecentFailures(user.user_id, LOCKOUT_WINDOW_MS);
      if (failures >= LOCKOUT_MAX_FAILURES) {
        audit.warn(`auth.login.locked user=${user.username} userId=${user.user_id} failures=${failures}`);
        throw new UnauthorisedError('Account temporarily locked — too many failed attempts');
      }
    }

    const valid = await this._passwordHasher.verify(password, user.password_hash);
    if (!valid) {
      if (this._loginAttempts) {
        await this._loginAttempts.record({ userId: user.user_id, ipAddress, success: false });
      }
      audit.warn(`auth.login.failure reason=bad_password user=${user.username} userId=${user.user_id}`);
      throw new UnauthorisedError('Invalid username or password');
    }

    if (this._loginAttempts) {
      await this._loginAttempts.record({ userId: user.user_id, ipAddress, success: true });
      await this._loginAttempts.clearFailures(user.user_id);
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
      // Pin the signing algorithm. Without this the library picks HS256 by
      // default, but stating it explicitly keeps sign/verify symmetric and
      // documents the intent.
      { expiresIn: config.jwt.expiresIn, algorithm: 'HS256' }
    );

    audit.info(`auth.login.success user=${user.username} userId=${user.user_id}`);
    return {
      token,
      user: { userId: user.user_id, username: user.username },
    };
  }

  async getUserProfile(userId) {
    const user = await this._userRepo.findById(userId);
    if (!user) {
      throw new UnauthorisedError('User not found');
    }
    // Never expose password_hash. The middleware has already verified the
    // token belongs to this user, so the rest is safe to surface.
    return {
      userId: user.user_id,
      username: user.username,
      createdAt: user.created_at,
      passwordChangedAt: user.password_changed_at,
    };
  }

  async lookupByUsername(username) {
    const user = await this._userRepo.findByUsername(username);
    if (!user) throw new NotFoundError('User not found');
    return { userId: user.user_id, username: user.username };
  }

  async changePassword({ userId, currentPassword, newPassword }) {
    const user = await this._userRepo.findById(userId);
    if (!user) {
      throw new UnauthorisedError('User not found');
    }

    const valid = await this._passwordHasher.verify(currentPassword, user.password_hash);
    if (!valid) {
      throw new UnauthorisedError('Current password is incorrect');
    }

    const newHash = await this._passwordHasher.hash(newPassword);
    await this._userRepo.updatePassword(userId, newHash);

    audit.info(`auth.password.changed user=${user.username} userId=${userId}`);
  }

  async verifyToken(token) {
    let decoded;

    try {
      // Allow-list HS256 only. This is what closes the `alg:none` /
      // algorithm-confusion vector (F-04): a token whose header advertises
      // `none`, RS256, or anything other than HS256 is rejected outright
      // rather than relying on the library's default behaviour.
      decoded = jwt.verify(token, config.jwt.secret, { algorithms: ['HS256'] });
    } catch (err) {
      audit.warn(`auth.token.rejected reason=${err.name}`);
      throw new UnauthorisedError('Invalid or expired token');
    }

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
      audit.warn(
        `auth.token.invalidated user=${user.username} userId=${user.user_id} reason=password_changed`
      );

      throw new UnauthorisedError(
        'Token invalidated by password change'
      );
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