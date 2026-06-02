/**
 * MessageService — flow tests.
 *
 * The service only ever sees ciphertext + a client-supplied digest;
 * confidentiality/integrity of the plaintext is the client's job. The server
 * is still responsible for the security invariants tested here:
 *
 *   - access control (only sender / recipient / active-share-recipient can read)
 *   - replay rejection (unique recipient_id + nonce, shared_with_id + nonce)
 *   - revocation authority (only the original sender can revoke)
 *   - soft-delete that does not leak message existence to third parties
 *   - relaying the client digest to BlockchainService without blocking delivery
 *
 * Wiring mirrors AuthService.test.js / KeyService.test.js: the real
 * MessageRepository runs its production body against the in-memory fakePool;
 * nothing in src/ is stubbed except BlockchainService, which is injected as a
 * spy so chain side-effects are observable without touching Sepolia.
 *
 * The lower-value permutations (pagination/ordering coercion, exhaustive
 * chain-proof states) remain as `test.todo` below — the security-critical
 * access-control + replay paths are implemented.
 */
const MessageService = require('../../src/services/MessageService');
const MessageRepository = require('../../src/repositories/MessageRepository');
const { NotFoundError, ForbiddenError, ConflictError } = require('../../src/utils/errors');
const { makeFakePool } = require('../helpers/fakePool');

function build() {
  const pool = makeFakePool();
  const messageRepo = new MessageRepository(pool);
  const blockchain = { onMessageSent: jest.fn().mockResolvedValue(undefined) };
  const svc = new MessageService(messageRepo, blockchain);
  return { pool, messageRepo, blockchain, svc };
}

// Seed a user row directly so the sender/recipient JOINs have a counterpart.
// Bypasses AuthService to keep these tests focused on the message flow.
function seedUser(pool, userId, username) {
  pool._store.set(userId, {
    user_id: userId,
    username,
    password_hash: 'unused',
    password_changed_at: new Date(),
    created_at: new Date(),
  });
}

// Alice (sender), Bob (recipient), Carol (third party / forward target).
function seedTrio(pool) {
  seedUser(pool, 'alice', 'alice');
  seedUser(pool, 'bob', 'bob');
  seedUser(pool, 'carol', 'carol');
}

// A complete send payload with a caller-chosen nonce (nonces must be unique
// per recipient — the replay backstop — so tests vary them explicitly).
function sendPayload(overrides = {}) {
  return {
    senderId: 'alice',
    recipientId: 'bob',
    ciphertext: 'ct-base64',
    nonce: 'nonce-0000000001',
    signature: 'sig-base64',
    seqNo: 1,
    digest: '0x' + 'a'.repeat(64),
    ...overrides,
  };
}

describe('MessageService', () => {
  describe('sendMessage — "Creating and sending a new message"', () => {
    test('persists ciphertext + nonce + signature + seq_no for the recipient and returns a messageId', async () => {
      const { svc, pool } = build();
      seedTrio(pool);

      const { messageId } = await svc.sendMessage(sendPayload());

      expect(messageId).toEqual(expect.any(String));
      const row = pool._messagesStore.get(messageId);
      expect(row).toMatchObject({
        sender_id: 'alice',
        recipient_id: 'bob',
        ciphertext: 'ct-base64',
        nonce: 'nonce-0000000001',
        signature: 'sig-base64',
        seq_no: 1,
        digest_hash: '0x' + 'a'.repeat(64),
        chain_status: 'pending',
        deleted_at: null,
      });
    });

    test('forwards the client-supplied digest to BlockchainService.onMessageSent', async () => {
      const { svc, pool, blockchain } = build();
      seedTrio(pool);

      const { messageId } = await svc.sendMessage(sendPayload({ digest: '0x' + 'b'.repeat(64) }));

      expect(blockchain.onMessageSent).toHaveBeenCalledTimes(1);
      expect(blockchain.onMessageSent).toHaveBeenCalledWith({
        messageId,
        digestHash: '0x' + 'b'.repeat(64),
      });
    });

    test('rejects a duplicate (recipient_id, nonce) as ConflictError — anti-replay', async () => {
      const { svc, pool } = build();
      seedTrio(pool);

      await svc.sendMessage(sendPayload({ nonce: 'nonce-replay-0001' }));

      // Same recipient + nonce = a replayed ciphertext. The unique key fires.
      await expect(
        svc.sendMessage(sendPayload({ nonce: 'nonce-replay-0001' }))
      ).rejects.toThrow(ConflictError);
    });

    test('allows the same nonce to a DIFFERENT recipient — uniqueness is per (recipient, nonce)', async () => {
      const { svc, pool } = build();
      seedTrio(pool);

      await svc.sendMessage(sendPayload({ recipientId: 'bob', nonce: 'shared-nonce-001' }));
      await expect(
        svc.sendMessage(sendPayload({ recipientId: 'carol', nonce: 'shared-nonce-001' }))
      ).resolves.toEqual({ messageId: expect.any(String) });
    });

    test('does not block delivery when the chain write is swallowed (Sepolia outage)', async () => {
      const { svc, pool, blockchain } = build();
      seedTrio(pool);
      // BlockchainService swallows its own errors and resolves; MessageService
      // must still complete the send rather than surfacing a chain problem.
      blockchain.onMessageSent.mockResolvedValue(undefined);

      const { messageId } = await svc.sendMessage(sendPayload());

      expect(messageId).toEqual(expect.any(String));
      expect(pool._messagesStore.has(messageId)).toBe(true);
    });

    test.todo('never inspects ciphertext — server cannot derive the digest itself');
    test.todo('surfaces an unknown recipient as a validation/FK error, not an unhandled 500');
  });

  describe('getInbox / getSent — "Viewing a list of sent and received messages"', () => {
    test('inbox returns only messages where the caller is the recipient', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-1' }));
      await svc.sendMessage(sendPayload({ senderId: 'carol', recipientId: 'bob', nonce: 'n-2' }));
      await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'carol', nonce: 'n-3' }));

      const inbox = await svc.getInbox('bob');

      expect(inbox).toHaveLength(2);
      expect(inbox.every((m) => m.senderId === 'alice' || m.senderId === 'carol')).toBe(true);
      // The message addressed to carol must not appear in bob's inbox.
      expect(inbox.some((m) => m.recipientId === 'carol')).toBe(false);
    });

    test('sent returns only messages where the caller is the sender', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-1' }));
      await svc.sendMessage(sendPayload({ senderId: 'carol', recipientId: 'bob', nonce: 'n-2' }));

      const sent = await svc.getSent('alice');

      expect(sent).toHaveLength(1);
      expect(sent[0].recipientId).toBe('bob');
    });

    test('soft-deleted messages are excluded from both inbox and sent', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      const { messageId } = await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-1' }));

      await svc.deleteMessage(messageId, 'alice');

      await expect(svc.getInbox('bob')).resolves.toHaveLength(0);
      await expect(svc.getSent('alice')).resolves.toHaveLength(0);
    });

    test.todo('results are ordered by created_at DESC');
    test.todo('respects limit and offset pagination');
    test.todo('coerces string limit/offset query params to integers (mysql2 prepared-statement quirk)');
  });

  describe('getMessage — "Downloading a message (owned or shared)"', () => {
    async function seedMessage() {
      const ctx = build();
      seedTrio(ctx.pool);
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-read' }));
      return { ...ctx, messageId };
    }

    test('sender can read their own message', async () => {
      const { svc, messageId } = await seedMessage();
      const msg = await svc.getMessage(messageId, 'alice');
      expect(msg.messageId).toBe(messageId);
    });

    test('original recipient can read the message', async () => {
      const { svc, messageId } = await seedMessage();
      const msg = await svc.getMessage(messageId, 'bob');
      expect(msg.messageId).toBe(messageId);
    });

    test('a user with an active share row can read the message', async () => {
      const { svc, messageId } = await seedMessage();
      // Bob forwards to Carol — Carol now has an active share.
      await svc.forwardMessage({
        messageId, forwarderId: 'bob', recipientId: 'carol',
        ciphertext: 'ct-for-carol', nonce: 'n-share-carol', signature: 'sig', seqNo: 1,
        digest: '0x' + 'c'.repeat(64),
      });
      await expect(svc.getMessage(messageId, 'carol')).resolves.toMatchObject({ messageId });
    });

    test('a user whose share was revoked is denied with ForbiddenError', async () => {
      const { svc, messageId } = await seedMessage();
      await svc.forwardMessage({
        messageId, forwarderId: 'bob', recipientId: 'carol',
        ciphertext: 'ct-for-carol', nonce: 'n-share-carol', signature: 'sig', seqNo: 1,
        digest: '0x' + 'c'.repeat(64),
      });
      // Original sender revokes Carol's access.
      await svc.revokeAccess(messageId, 'alice', 'carol');

      await expect(svc.getMessage(messageId, 'carol')).rejects.toThrow(ForbiddenError);
    });

    test('an unrelated third party gets ForbiddenError (message exists, no access)', async () => {
      const { svc, pool, messageId } = await seedMessage();
      seedUser(pool, 'mallory', 'mallory');
      await expect(svc.getMessage(messageId, 'mallory')).rejects.toThrow(ForbiddenError);
    });

    test('returns NotFoundError for a non-existent messageId', async () => {
      const { svc } = await seedMessage();
      await expect(svc.getMessage('does-not-exist', 'alice')).rejects.toThrow(NotFoundError);
    });

    test('returns NotFoundError for a soft-deleted message', async () => {
      const { svc, messageId } = await seedMessage();
      await svc.deleteMessage(messageId, 'alice');
      await expect(svc.getMessage(messageId, 'bob')).rejects.toThrow(NotFoundError);
    });
  });

  describe('forwardMessage — "Forwarding a message after verifying identity"', () => {
    async function seedMessage() {
      const ctx = build();
      seedTrio(ctx.pool);
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-fwd' }));
      return { ...ctx, messageId };
    }

    function fwdPayload(messageId, overrides = {}) {
      return {
        messageId,
        forwarderId: 'bob',
        recipientId: 'carol',
        ciphertext: 'ct-resealed',
        nonce: 'n-forward-0001',
        signature: 'sig',
        seqNo: 1,
        digest: '0x' + 'c'.repeat(64),
        ...overrides,
      };
    }

    test('the original sender can forward the message', async () => {
      const { svc, pool, messageId } = await seedMessage();
      const { id } = await svc.forwardMessage(fwdPayload(messageId, { forwarderId: 'alice' }));
      expect(id).toEqual(expect.any(String));
      expect(pool._messageSharesStore).toHaveLength(1);
    });

    test('the original recipient can forward the message', async () => {
      const { svc, pool, messageId } = await seedMessage();
      await svc.forwardMessage(fwdPayload(messageId, { forwarderId: 'bob' }));
      expect(pool._messageSharesStore).toHaveLength(1);
    });

    test('an active share recipient can re-forward the message', async () => {
      const { svc, pool, messageId } = await seedMessage();
      seedUser(pool, 'dave', 'dave');
      // Bob -> Carol, then Carol -> Dave.
      await svc.forwardMessage(fwdPayload(messageId, { forwarderId: 'bob', recipientId: 'carol', nonce: 'n-bob-carol' }));
      await svc.forwardMessage(fwdPayload(messageId, { forwarderId: 'carol', recipientId: 'dave', nonce: 'n-carol-dave' }));
      expect(pool._messageSharesStore).toHaveLength(2);
    });

    test('a user with no access gets ForbiddenError and NO share row is written', async () => {
      const { svc, pool, messageId } = await seedMessage();
      seedUser(pool, 'mallory', 'mallory');

      await expect(
        svc.forwardMessage(fwdPayload(messageId, { forwarderId: 'mallory' }))
      ).rejects.toThrow(ForbiddenError);
      expect(pool._messageSharesStore).toHaveLength(0);
    });

    test('forwarding does NOT trigger a new chain write — the original digest already attests the plaintext', async () => {
      const { svc, blockchain, messageId } = await seedMessage();
      blockchain.onMessageSent.mockClear(); // ignore the original send's write

      await svc.forwardMessage(fwdPayload(messageId));

      expect(blockchain.onMessageSent).not.toHaveBeenCalled();
    });

    test('a duplicate (shared_with_id, nonce) on the share row surfaces as ConflictError — anti-replay on forwards', async () => {
      const { svc, messageId } = await seedMessage();
      await svc.forwardMessage(fwdPayload(messageId, { nonce: 'dup-share-nonce' }));

      await expect(
        svc.forwardMessage(fwdPayload(messageId, { nonce: 'dup-share-nonce' }))
      ).rejects.toThrow(ConflictError);
    });
  });

  describe('revokeAccess — "Revoking a user\'s access to a previously shared message"', () => {
    async function seedShared() {
      const ctx = build();
      seedTrio(ctx.pool);
      seedUser(ctx.pool, 'dave', 'dave');
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-rev' }));
      // Bob forwards to Carol.
      await ctx.svc.forwardMessage({
        messageId, forwarderId: 'bob', recipientId: 'carol',
        ciphertext: 'ct', nonce: 'n-share-rev', signature: 'sig', seqNo: 1, digest: '0x' + 'c'.repeat(64),
      });
      return { ...ctx, messageId };
    }

    test('only the original sender can revoke — the original recipient cannot', async () => {
      const { svc, messageId } = await seedShared();
      await expect(svc.revokeAccess(messageId, 'bob', 'carol')).rejects.toThrow(ForbiddenError);
    });

    test('a share recipient cannot revoke another user', async () => {
      const { svc, messageId } = await seedShared();
      await expect(svc.revokeAccess(messageId, 'carol', 'carol')).rejects.toThrow(ForbiddenError);
    });

    test('after revocation, the previously-shared user can no longer read the message', async () => {
      const { svc, messageId } = await seedShared();
      await expect(svc.getMessage(messageId, 'carol')).resolves.toMatchObject({ messageId });

      await svc.revokeAccess(messageId, 'alice', 'carol');

      await expect(svc.getMessage(messageId, 'carol')).rejects.toThrow(ForbiddenError);
    });

    test('revoking on a non-existent message throws NotFoundError', async () => {
      const { svc } = await seedShared();
      await expect(svc.revokeAccess('no-such-message', 'alice', 'carol')).rejects.toThrow(NotFoundError);
    });
  });

  describe('deleteMessage — "Deleting a message"', () => {
    async function seedMessage() {
      const ctx = build();
      seedTrio(ctx.pool);
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-del' }));
      return { ...ctx, messageId };
    }

    test('the sender can soft-delete their own message', async () => {
      const { svc, pool, messageId } = await seedMessage();
      await expect(svc.deleteMessage(messageId, 'alice')).resolves.toBeUndefined();
      expect(pool._messagesStore.get(messageId).deleted_at).toBeInstanceOf(Date);
    });

    test('the recipient can soft-delete from their own view', async () => {
      const { svc, pool, messageId } = await seedMessage();
      await svc.deleteMessage(messageId, 'bob');
      expect(pool._messagesStore.get(messageId).deleted_at).toBeInstanceOf(Date);
    });

    test('a third party gets NotFoundError — does NOT distinguish "no access" from "not found" (no ID enumeration)', async () => {
      const { svc, pool, messageId } = await seedMessage();
      seedUser(pool, 'mallory', 'mallory');
      // Same error class whether the message is missing or simply not theirs.
      await expect(svc.deleteMessage(messageId, 'mallory')).rejects.toThrow(NotFoundError);
      await expect(svc.deleteMessage('totally-made-up-id', 'mallory')).rejects.toThrow(NotFoundError);
      // The row survives the unauthorised attempt.
      expect(pool._messagesStore.get(messageId).deleted_at).toBeNull();
    });

    test('delete is a soft-delete — the row is retained with deleted_at set, not removed', async () => {
      const { svc, pool, messageId } = await seedMessage();
      await svc.deleteMessage(messageId, 'alice');
      expect(pool._messagesStore.has(messageId)).toBe(true);
      expect(pool._messagesStore.get(messageId).deleted_at).toBeInstanceOf(Date);
    });

    test('a soft-deleted message is invisible to subsequent getMessage', async () => {
      const { svc, messageId } = await seedMessage();
      await svc.deleteMessage(messageId, 'alice');
      await expect(svc.getMessage(messageId, 'alice')).rejects.toThrow(NotFoundError);
    });

    test('the on-chain digest record outlives the deleted message (tamper-evidence persists)', async () => {
      const { svc, messageRepo, messageId } = await seedMessage();
      // Simulate a confirmed Sepolia write for this message.
      await messageRepo.recordChainEntry({
        id: 'chain-rec-1', messageId, txHash: '0x' + 'd'.repeat(64), digestHash: '0x' + 'a'.repeat(64),
      });

      await svc.deleteMessage(messageId, 'alice');

      const record = await messageRepo.findChainRecord(messageId);
      expect(record).not.toBeNull();
      expect(record.tx_hash).toBe('0x' + 'd'.repeat(64));
    });
  });

  describe('deleteShare — "Deleting a forward by its share id"', () => {
    // Alice sends to Bob; Bob forwards to Carol. Returns the share id Bob owns.
    async function seedShare() {
      const ctx = build();
      seedTrio(ctx.pool);
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-delshare' }));
      const { id: shareId } = await ctx.svc.forwardMessage({
        messageId, forwarderId: 'bob', recipientId: 'carol',
        ciphertext: 'ct', nonce: 'n-share-del', signature: 'sig', seqNo: 1, digest: '0x' + 'c'.repeat(64),
      });
      return { ...ctx, messageId, shareId };
    }

    test('the forwarder can delete their own forward — revoked_at is set', async () => {
      const { svc, pool, shareId } = await seedShare();
      await expect(svc.deleteShare(shareId, 'bob')).resolves.toBeUndefined();
      expect(pool._messageSharesStore[0].revoked_at).toBeInstanceOf(Date);
    });

    test('deleting a forward removes it from the recipient\'s inbox and the forwarder\'s sent view', async () => {
      const { svc, shareId } = await seedShare();
      await svc.deleteShare(shareId, 'bob');
      expect(await svc.getInbox('carol')).toHaveLength(0);
      expect((await svc.getSent('bob')).filter((m) => m.shared)).toHaveLength(0);
    });

    test('a non-forwarder cannot delete the share — NotFoundError, and the row survives', async () => {
      const { svc, pool, shareId } = await seedShare();
      // Carol is the recipient of the forward, not its owner; Alice is the
      // original sender but did not create this share. Neither can delete it.
      await expect(svc.deleteShare(shareId, 'carol')).rejects.toThrow(NotFoundError);
      await expect(svc.deleteShare(shareId, 'alice')).rejects.toThrow(NotFoundError);
      expect(pool._messageSharesStore[0].revoked_at).toBeNull();
    });

    test('deleting a non-existent share id throws NotFoundError (no ID enumeration)', async () => {
      const { svc } = await seedShare();
      await expect(svc.deleteShare('made-up-share-id', 'bob')).rejects.toThrow(NotFoundError);
    });

    test('deleting the ORIGINAL cascades: a forward of it disappears too (self-forward to the same recipient)', async () => {
      const ctx = build();
      seedTrio(ctx.pool);
      // Alice sends to Bob, then forwards that same message to Bob again.
      const { messageId } = await ctx.svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-orig' }));
      await ctx.svc.forwardMessage({
        messageId, forwarderId: 'alice', recipientId: 'bob',
        ciphertext: 'ct', nonce: 'n-selffwd', signature: 'sig', seqNo: 1, digest: '0x' + 'c'.repeat(64),
      });
      // Bob sees two: the direct message and the forward.
      expect(await ctx.svc.getInbox('bob')).toHaveLength(2);

      // Alice deletes only the ORIGINAL.
      await ctx.svc.deleteMessage(messageId, 'alice');

      // The forward, anchored to the now-deleted original, falls out of both
      // Bob's inbox and Alice's sent view — no explicit share delete needed.
      expect(await ctx.svc.getInbox('bob')).toHaveLength(0);
      expect(await ctx.svc.getSent('alice')).toHaveLength(0);
    });
  });

  describe('getChainProof — blockchain verification endpoint', () => {
    test('rejects with ForbiddenError if the caller cannot read the underlying message (no leak via chain endpoint)', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      seedUser(pool, 'mallory', 'mallory');
      const { messageId } = await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-chain' }));

      await expect(svc.getChainProof(messageId, 'mallory')).rejects.toThrow(ForbiddenError);
    });

    test('returns NotFoundError for a non-existent messageId', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      await expect(svc.getChainProof('nope', 'alice')).rejects.toThrow(NotFoundError);
    });

    test('returns chainStatus="pending" with a null txHash before the chain write completes', async () => {
      const { svc, pool } = build();
      seedTrio(pool);
      const { messageId } = await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-chain2' }));

      const proof = await svc.getChainProof(messageId, 'alice');
      expect(proof).toMatchObject({ messageId, chainStatus: 'pending', txHash: null, recordedAt: null });
    });

    test('returns chainStatus="recorded" with the real txHash after a successful Sepolia write', async () => {
      const { svc, messageRepo, pool } = build();
      seedTrio(pool);
      const { messageId } = await svc.sendMessage(sendPayload({ senderId: 'alice', recipientId: 'bob', nonce: 'n-chain3' }));
      await messageRepo.recordChainEntry({
        id: 'rec-1', messageId, txHash: '0x' + 'e'.repeat(64), digestHash: '0x' + 'a'.repeat(64),
      });

      const proof = await svc.getChainProof(messageId, 'bob');
      expect(proof).toMatchObject({ messageId, chainStatus: 'recorded', txHash: '0x' + 'e'.repeat(64) });
    });

    test.todo('returns chainStatus="failed" with null txHash when BlockchainService flagged the row');
  });
});
