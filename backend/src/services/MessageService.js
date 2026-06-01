
/**
 * MessageService — orchestrates message operations.
 *
 * The server only ever handles ciphertext. It cannot read, decrypt,
 * or verify message contents. All encryption happens client-side.
 */
const { v4: uuidv4 } = require('uuid');
const { NotFoundError, ForbiddenError } = require('../utils/errors');
const logger = require('../utils/logger');

class MessageService {
  constructor(messageRepository, blockchainService) {
    this._messageRepo = messageRepository;
    this._blockchain = blockchainService;
  }

  async sendMessage({ senderId, recipientId, ciphertext, nonce, signature, seqNo, digest }) {
    const messageId = uuidv4();

    await this._messageRepo.create({
      messageId, senderId, recipientId, ciphertext, nonce, signature, seqNo, digestHash: digest,
    });

    // Hand the client-supplied digest to the blockchain service. The server
    // never computes the digest itself — it relays whatever the client
    // committed to. That's what makes the on-chain record a proof of the
    // plaintext rather than a proof of "what the server stored".
    // BlockchainService swallows its own errors and flags chain_failed on
    // the row, so a Sepolia outage never blocks message delivery.
    await this._blockchain.onMessageSent({ messageId, digestHash: digest });

    logger.info(`Message sent: ${messageId} from ${senderId} to ${recipientId}`);
    return { messageId };
  }

  /**
   * Returns the chain proof for a message the caller has access to.
   * Used by GET /api/messages/:id/chain — the verification page feeds the
   * returned txHash into Sepolia directly to confirm.
   */
  async getChainProof(messageId, userId) {
    const message = await this.getMessage(messageId, userId);
    const record = await this._messageRepo.findChainRecord(messageId);
    return {
      messageId,
      digestHash: message.digestHash || null,
      chainStatus: message.chainStatus,
      txHash: record ? record.tx_hash : null,
      recordedAt: record ? record.created_at : null,
    };
  }

  async getInbox(userId, options) {
    // The inbox surfaces direct messages addressed to the user and forwarded
    // shares received by the user as one stream. Both carry the same crypto
    // fields (the forwarder is the sender of a share), so they merge cleanly
    // and sort by createdAt DESC into a single chronological view.
    const direct = (await this._messageRepo.findByRecipient(userId, options)).map(toMessageDTO);
    const shared = (await this._messageRepo.findSharedWithUser(userId, options)).map(toSharedInboxDTO);
    return [...direct, ...shared].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }

  async getSent(userId, options) {
    const direct = (await this._messageRepo.findBySender(userId, options)).map(toMessageDTO);
    const forwarded = (await this._messageRepo.findSharedByUser(userId, options)).map(toSharedSentDTO);
    return [...direct, ...forwarded].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }

  async getMessage(messageId, userId) {
    const message = await this._messageRepo.findById(messageId);
    if (!message) {
      throw new NotFoundError('Message not found');
    }

    // Access control runs against the raw row (snake_case) before it is
    // mapped to the API shape below.
    if (message.sender_id !== userId && message.recipient_id !== userId) {
      const shares = await this._messageRepo.findSharedWith(messageId);
      const isShared = shares.some((s) => s.shared_with_id === userId);
      if (!isShared) {
        throw new ForbiddenError('You do not have access to this message');
      }
    }

    return toMessageDTO(message);
  }

  async forwardMessage({ messageId, forwarderId, recipientId, ciphertext, nonce, signature, seqNo, digest }) {
    // Authorisation: the forwarder must have access to the message —
    // either as the sender, the original recipient, or a current share
    // recipient. getMessage() throws NotFoundError / ForbiddenError if not.
    await this.getMessage(messageId, forwarderId);

    const id = uuidv4();

    await this._messageRepo.createShare({
      id,
      messageId,
      sharedById: forwarderId,
      sharedWithId: recipientId,
      ciphertext,
      nonce,
      signature,
      seqNo,
      digestHash: digest,
    });

    // Forwards do not trigger a new chain write — the original message's
    // chain record already attests to the plaintext that was forwarded.
    logger.info(`Message ${messageId} forwarded to ${recipientId}`);
    return { id };
  }

  async getShares(messageId, userId) {
    await this.getMessage(messageId, userId);
    const rows = await this._messageRepo.findSharedWith(messageId);
    return rows.map(r => ({
      userId: r.shared_with_id,
      username: r.username,
      sharedAt: r.created_at,
    }));
  }

  async revokeAccess(messageId, userId, revokeUserId) {
    const message = await this._messageRepo.findById(messageId);
    if (!message) {
      throw new NotFoundError('Message not found');
    }
    if (message.sender_id !== userId) {
      throw new ForbiddenError('Only the sender can revoke access');
    }

    await this._messageRepo.revokeShare(messageId, revokeUserId);
    logger.info(`Access revoked: ${revokeUserId} from message ${messageId}`);
  }

  async deleteMessage(messageId, userId) {
    const affected = await this._messageRepo.softDelete(messageId, userId);
    if (!affected) {
      // Don't distinguish "doesn't exist" from "you don't own it" — that would
      // let an attacker probe for valid message IDs they aren't a party to.
      throw new NotFoundError('Message not found');
    }
    logger.info(`Message soft-deleted: ${messageId} by ${userId}`);
  }
}

/**
 * Maps a raw message row (snake_case, as stored) to the camelCase shape the
 * API exposes — the same convention AuthService and getChainProof return, and
 * the convention the request bodies already use. Only emits the columns
 * present on the row, so it serves the inbox view (sender side), the sent
 * view (recipient side), and the full single-message view alike.
 */
function toMessageDTO(row) {
  const dto = {
    messageId: row.message_id,
    ciphertext: row.ciphertext,
    nonce: row.nonce,
    signature: row.signature,
    seqNo: row.seq_no,
    digestHash: row.digest_hash,
    chainStatus: row.chain_status,
    createdAt: row.created_at,
  };
  if (row.sender_id !== undefined) dto.senderId = row.sender_id;
  if (row.recipient_id !== undefined) dto.recipientId = row.recipient_id;
  if (row.sender_username !== undefined) dto.senderUsername = row.sender_username;
  if (row.recipient_username !== undefined) dto.recipientUsername = row.recipient_username;
  return dto;
}

/**
 * Maps a received-share row (from findSharedWithUser) to the inbox share shape.
 * messageId is the SHARE row id (unique per share) so the client's per-message
 * plaintext cache never collides when two people forward the same original to
 * the same recipient; originalMessageId carries the original for the chain view
 * and re-forwarding. senderId is the forwarder, so the client decrypts with the
 * forwarder's pinned keys against the same replay counter as direct messages.
 */
function toSharedSentDTO(row) {
  return {
    messageId: row.share_id,
    originalMessageId: row.message_id,
    shared: true,
    recipientId: row.recipient_id,
    recipientUsername: row.recipient_username,
    ciphertext: row.ciphertext,
    nonce: row.nonce,
    signature: row.signature,
    seqNo: row.seq_no,
    digestHash: row.digest_hash,
    chainStatus: row.chain_status,
    createdAt: row.created_at,
  };
}

function toSharedInboxDTO(row) {
  return {
    messageId: row.share_id,
    originalMessageId: row.message_id,
    shared: true,
    senderId: row.sender_id,
    senderUsername: row.sender_username,
    ciphertext: row.ciphertext,
    nonce: row.nonce,
    signature: row.signature,
    seqNo: row.seq_no,
    digestHash: row.digest_hash,
    chainStatus: row.chain_status,
    createdAt: row.created_at,
  };
}

module.exports = MessageService;