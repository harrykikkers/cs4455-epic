const AuthService = require('../../src/services/AuthService');
const UserRepository = require('../../src/repositories/UserRepository');
const PasswordHasher = require('../../src/services/PasswordHasher');
const { ConflictError, UnauthorisedError } = require('../../src/utils/errors');
const { makeFakePool } = require('../helpers/fakePool');

/**
 * Every test below wires AuthService with:
 *   - the real UserRepository class (src/repositories/UserRepository.js)
 *   - the real PasswordHasher (src/services/PasswordHasher.js)
 *   - a fake mysql2 pool whose only job is to back the repo with an
 *     in-memory store (tests/helpers/fakePool.js)
 *
 * Nothing in src/ is stubbed — the service runs its real flows: real
 * Argon2id hashing, real JWT signing/verifying, real find/create/update
 * paths through the production repository code.
 */

function build() {
  const pool = makeFakePool();
  const userRepo = new UserRepository(pool);
  const passwordHasher = new PasswordHasher();
  const svc = new AuthService(userRepo, passwordHasher);
  return { pool, userRepo, passwordHasher, svc };
}

describe('AuthService', () => {
  describe('register', () => {
    test('hashes the password BEFORE checking username uniqueness (timing-safe)', async () => {
      const { passwordHasher, userRepo, svc } = build();

      // Record call order without replacing implementations — the spies
      // call through to the real argon2 hash and real repo lookup.
      const order = [];
      const realHash = passwordHasher.hash.bind(passwordHasher);
      const realFind = userRepo.findByUsername.bind(userRepo);
      jest.spyOn(passwordHasher, 'hash').mockImplementation(async (pw) => {
        order.push('hash');
        return realHash(pw);
      });
      jest.spyOn(userRepo, 'findByUsername').mockImplementation(async (u) => {
        order.push('findByUsername');
        return realFind(u);
      });

      await svc.register({ username: 'alice', password: 'correcthorsebattery' });

      // Hashing must come first; otherwise an attacker can distinguish
      // "username taken" from "username free" by response latency.
      expect(order[0]).toBe('hash');
    });

    test('throws ConflictError when the username is taken', async () => {
      const { svc } = build();
      await svc.register({ username: 'alice', password: 'p'.repeat(12) });

      await expect(svc.register({ username: 'alice', password: 'p'.repeat(12) }))
        .rejects.toBeInstanceOf(ConflictError);
    });

    test('returns a generated userId on success and persists the user', async () => {
      const { svc, userRepo } = build();

      const result = await svc.register({ username: 'bob', password: 'p'.repeat(12) });

      expect(result.username).toBe('bob');
      expect(result.userId).toMatch(/^[0-9a-f-]{36}$/);

      // The real repo went through the real fake pool — confirm the user landed.
      const stored = await userRepo.findByUsername('bob');
      expect(stored.user_id).toBe(result.userId);
      expect(stored.password_hash).toMatch(/^\$argon2id\$/);
    });
  });

  describe('login', () => {
    test('returns the same UnauthorisedError for unknown user and bad password', async () => {
      const unknown = build();
      const known = build();
      await known.svc.register({ username: 'alice', password: 'p'.repeat(12) });

      const errA = await unknown.svc
        .login({ username: 'ghost', password: 'wrong-password' })
        .catch((e) => e);
      const errB = await known.svc
        .login({ username: 'alice', password: 'wrong-password' })
        .catch((e) => e);

      expect(errA).toBeInstanceOf(UnauthorisedError);
      expect(errB).toBeInstanceOf(UnauthorisedError);
      // Identical message — no enumeration via response body.
      expect(errA.message).toBe(errB.message);
    });

    test('burns time by hashing even when the user does not exist', async () => {
      const { passwordHasher, svc } = build();
      const hashSpy = jest.spyOn(passwordHasher, 'hash');

      await svc.login({ username: 'ghost', password: 'whatever' }).catch(() => {});

      expect(hashSpy).toHaveBeenCalledWith('whatever');
    });

    test('issues a JWT stamped with the password version on success', async () => {
      const { svc, userRepo } = build();
      await svc.register({ username: 'alice', password: 'p'.repeat(12) });

      const { token } = await svc.login({ username: 'alice', password: 'p'.repeat(12) });

      // Decode without verification — we just want to inspect the payload shape.
      const [, payloadB64] = token.split('.');
      const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString());

      const user = await userRepo.findByUsername('alice');
      expect(payload.sub).toBe(user.user_id);
      expect(payload.username).toBe('alice');
      expect(payload.pwdChangedAt).toBe(
        Math.floor(new Date(user.password_changed_at).getTime() / 1000)
      );
    });
  });

  describe('verifyToken', () => {
    test('rejects a token issued before the user changed their password', async () => {
      const { svc, pool } = build();
      await svc.register({ username: 'alice', password: 'p'.repeat(12) });

      // Login while password_changed_at is still the registration time.
      const { token, user } = await svc.login({ username: 'alice', password: 'p'.repeat(12) });

      // Advance password_changed_at to a future instant — simulates a
      // password change happening after the token was issued. Done via
      // the test helper to avoid sleeping past a second boundary.
      pool._setPasswordChangedAt(user.userId, new Date(Date.now() + 60_000));

      await expect(svc.verifyToken(token)).rejects.toMatchObject({
        message: 'Token invalidated by password change',
      });
    });

    test('rejects when the user no longer exists', async () => {
      const { svc, userRepo } = build();
      const { userId } = await svc.register({ username: 'alice', password: 'p'.repeat(12) });

      const { token } = await svc.login({ username: 'alice', password: 'p'.repeat(12) });

      await userRepo.deleteById(userId);

      await expect(svc.verifyToken(token)).rejects.toMatchObject({
        message: 'User no longer exists',
      });
    });

    test('accepts a freshly issued token and returns the decoded payload', async () => {
      const { svc } = build();
      const { userId } = await svc.register({ username: 'alice', password: 'p'.repeat(12) });

      const { token } = await svc.login({ username: 'alice', password: 'p'.repeat(12) });
      const decoded = await svc.verifyToken(token);

      expect(decoded.sub).toBe(userId);
      expect(decoded.username).toBe('alice');
    });
  });
});
