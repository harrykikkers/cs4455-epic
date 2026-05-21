/**
 * MessageService — flow scaffold (TODOs).
 *
 * Each `test.todo` corresponds to a flow the brief requires the server to
 * handle. The service only ever sees ciphertext + client-supplied digest;
 * confidentiality/integrity of the plaintext is the client's job, but the
 * server is still responsible for:
 *
 *   - access control (only sender/recipient/share-recipient can read)
 *   - replay rejection (unique recipient_id + nonce)
 *   - relaying the client digest to BlockchainService
 *   - soft-delete + share revocation semantics
 *
 * Suggested wiring (mirrors AuthService.test.js / KeyService.test.js):
 *
 *   function build() {
 *     const pool = makeFakePool();                  // needs message routes added
 *     const messageRepo = new MessageRepository(pool);
 *     const blockchain  = { onMessageSent: jest.fn().mockResolvedValue() };
 *     const svc = new MessageService(messageRepo, blockchain);
 *     return { pool, messageRepo, blockchain, svc };
 *   }
 *
 * NOTE: fakePool.js currently has no routes for `messages`, `message_shares`,
 * or `blockchain_records`. Filling these tests in will require extending the
 * dispatcher with INSERT/SELECT/UPDATE branches for each table.
 */

describe('MessageService', () => {
  describe('sendMessage — "Creating and sending a new message"', () => {
    test.todo('persists ciphertext + nonce + signature + seq_no for the recipient and returns a messageId');
    test.todo('forwards the client-supplied digest to BlockchainService.onMessageSent');
    test.todo('never inspects ciphertext — server cannot derive the digest itself');
    test.todo('rejects a duplicate (recipient_id, nonce) as ConflictError — anti-replay');
    test.todo('still returns success when BlockchainService swallows a chain failure (delivery not blocked by Sepolia outage)');
    test.todo('does not 500 when the recipient does not exist — surfaced as a validation/FK error, not an unhandled throw');
  });

  describe('getInbox / getSent — "Viewing a list of sent and received messages"', () => {
    test.todo('inbox returns only messages where the caller is the recipient');
    test.todo('sent returns only messages where the caller is the sender');
    test.todo('soft-deleted messages (deleted_at IS NOT NULL) are excluded from both lists');
    test.todo('results are ordered by created_at DESC');
    test.todo('respects limit and offset pagination');
    test.todo('coerces string limit/offset query params to integers (mysql2 prepared-statement quirk)');
  });

  describe('getMessage — "Downloading a message (owned or shared)"', () => {
    test.todo('sender can read their own message');
    test.todo('original recipient can read the message');
    test.todo('a user with an active share row can read the message');
    test.todo('a user with a revoked share (revoked_at IS NOT NULL) is denied with ForbiddenError');
    test.todo('an unrelated third party gets ForbiddenError, not NotFoundError — but only after the message exists check passes');
    test.todo('returns NotFoundError for a non-existent messageId');
    test.todo('returns NotFoundError for a soft-deleted message (deleted_at IS NOT NULL)');
  });

  describe('forwardMessage — "Forwarding a message after verifying identity"', () => {
    test.todo('sender of the original message can forward it');
    test.todo('original recipient can forward the message');
    test.todo('an active share recipient can forward the message');
    test.todo('a user with no access gets ForbiddenError and no share row is written');
    test.todo('forwarding creates a new message_shares row with fresh (enc, ciphertext, nonce) for the new recipient');
    test.todo('forwarding does NOT trigger a new chain write — original digest already attests the plaintext');
    test.todo('duplicate (shared_with_id, nonce) on the share row surfaces as ConflictError — anti-replay on shares');
  });

  describe('revokeAccess — "Revoking a user\'s access to a previously shared message"', () => {
    test.todo('only the original sender can revoke — original recipient cannot');
    test.todo('a share recipient cannot revoke another share recipient');
    test.todo('revoking sets revoked_at on the matching message_shares row');
    test.todo('after revocation, the previously-shared user can no longer getMessage');
    test.todo('revoking a non-existent share is a no-op (idempotent)');
    test.todo('revoking on a non-existent message throws NotFoundError');
  });

  describe('deleteMessage — "Deleting a message"', () => {
    test.todo('sender can soft-delete their own message');
    test.todo('recipient can soft-delete from their own inbox');
    test.todo('a third party gets NotFoundError — does NOT distinguish "no access" from "not found" (avoids ID enumeration)');
    test.todo('deletion is a soft-delete: deleted_at is set, the row is not removed');
    test.todo('a soft-deleted message is invisible to subsequent getMessage / inbox / sent calls');
    test.todo('the on-chain digest record is preserved after delete — tamper-evidence outlives the row');
  });

  describe('getChainProof — blockchain verification endpoint', () => {
    test.todo('returns { digestHash, chainStatus, txHash, recordedAt } for a message the caller can read');
    test.todo('returns chainStatus="pending" with null txHash before the chain write completes');
    test.todo('returns chainStatus="failed" with null txHash when BlockchainService flagged the row');
    test.todo('returns chainStatus="recorded" with the real txHash after a successful Sepolia write');
    test.todo('rejects with ForbiddenError if the caller cannot read the underlying message (no leak via chain endpoint)');
    test.todo('rejects with NotFoundError for a non-existent messageId');
  });
});
