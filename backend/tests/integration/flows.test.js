/**
 * End-to-end flow scaffold (TODOs).
 *
 * These tests stitch the real services together against the fakePool and
 * drive each user-visible flow from the brief from end to end. They are
 * the closest thing we have to "did the system actually deliver the
 * features the brief asked for?" — unit tests prove each piece, these
 * prove the pieces compose.
 *
 * Suggested wiring (every test starts from a fresh build()):
 *
 *   function build() {
 *     const pool = makeFakePool();
 *     const userRepo    = new UserRepository(pool);
 *     const keyRepo     = new KeyRepository(pool);
 *     const messageRepo = new MessageRepository(pool);
 *     const hasher      = new PasswordHasher();
 *     const blockchain  = { onMessageSent: jest.fn().mockResolvedValue() };
 *
 *     const auth     = new AuthService(userRepo, hasher);
 *     const keys     = new KeyService(keyRepo);
 *     const messages = new MessageService(messageRepo, blockchain);
 *     return { pool, auth, keys, messages, blockchain };
 *   }
 *
 *   async function setupAliceAndBob({ auth, keys }) {
 *     const alice = await auth.register({ username: 'alice', password: 'p'.repeat(12) });
 *     const bob   = await auth.register({ username: 'bob',   password: 'p'.repeat(12) });
 *     await keys.publishKey({ userId: alice.userId, publicKey: 'alice-x25519', keyType: 'x25519' });
 *     await keys.publishKey({ userId: bob.userId,   publicKey: 'bob-x25519',   keyType: 'x25519' });
 *     return { alice, bob };
 *   }
 *
 * NOTE: fakePool needs message + share + chain table routes added before
 * any message flow runs. Add them alongside the first test that needs them.
 */

describe('End-to-end flows', () => {

  describe('Account lifecycle — "User sign-up, login and password management"', () => {
    test.todo('register → login → verifyToken returns a payload with sub=userId and the right pwdChangedAt stamp');
    test.todo('register with a duplicate username throws ConflictError but takes the same wall time as a fresh register (hash-first)');
    test.todo('login with a wrong password throws UnauthorisedError with the same message as login for a nonexistent user');
    test.todo('changePassword invalidates the previously-issued JWT on next verifyToken call');
    test.todo('after changePassword, login with the new password succeeds and old password fails');
  });

  describe('Key publication — TOFU pinning', () => {
    test.todo('a freshly-registered user has no public keys; listPublicKeys reflects that');
    test.todo('first publishKey for a (user, keyType) pins it; getPublicKeyByType returns it on subsequent lookup');
    test.todo('publishing the same key again is unchanged (idempotent); no version bump');
    test.todo('publishing a different key without acknowledgeRotation throws ConflictError and leaves the pinned key intact');
    test.todo('publishing with acknowledgeRotation=true rotates the key and archives the previous version in history');
  });

  describe('Send + read — "Creating and sending" + "Downloading a message (owned or shared)"', () => {
    test.todo('Alice sends a message to Bob; Bob sees it in his inbox; Alice sees it in her sent list');
    test.todo('a third party (Carol) calling getMessage on the same id gets ForbiddenError');
    test.todo('Carol\'s inbox does not contain the message (access control at the list level, not just the row level)');
    test.todo('Bob\'s GET /api/messages/:id/chain returns the digest Alice computed and (eventually) the txHash');
    test.todo('a replayed (recipient=Bob, nonce) ciphertext is rejected at the server with ConflictError');
  });

  describe('Forward — "Forwarding after verifying identity"', () => {
    test.todo('Alice forwards to Carol — Carol can now read it, Bob is unaffected, Alice still owns the original');
    test.todo('Bob (the original recipient) can also forward to Carol — share row is correctly attributed to Bob');
    test.todo('forwarding does not produce a new chain write (BlockchainService.onMessageSent NOT called again)');
    test.todo('Carol cannot forward to Dave until Alice or Bob shares with Carol first — chain of access is enforced per-hop');
  });

  describe('Revoke — "Revoking a user\'s access"', () => {
    test.todo('after Alice revokes Carol, Carol\'s getMessage returns ForbiddenError');
    test.todo('Bob (original recipient) is unaffected by revocation of Carol\'s share');
    test.todo('only the original sender (Alice) can revoke — Bob attempting to revoke Carol is ForbiddenError');
    test.todo('revoking a share does NOT delete the historical share row — audit trail survives');
  });

  describe('Delete — "Deleting a message"', () => {
    test.todo('Alice deletes the message; it disappears from her sent list AND Bob\'s inbox');
    test.todo('the on-chain digest record is preserved — GET /:id/chain still returns the txHash after delete');
    test.todo('Carol (third party) calling delete on Alice\'s message gets NotFoundError — same response as a nonexistent id');
    test.todo('soft-delete is a one-way door: Alice cannot "undelete" by re-sending with the same id (uuid collision unlikely; replay nonce blocks anyway)');
  });

  describe('Cross-cutting security invariants', () => {
    test.todo('server-side message rows never contain plaintext — only ciphertext/nonce/signature/digest');
    test.todo('password_hash is never returned by any service method (register, login, getUserProfile)');
    test.todo('changing Alice\'s password does not affect Bob\'s outstanding tokens (per-user JWT invalidation)');
    test.todo('blockchain write failure on send does not roll back the message — the row is delivered with chain_status="failed"');
    test.todo('client-supplied digest is what reaches contract.recordHash — server never recomputes from ciphertext');
  });
});
