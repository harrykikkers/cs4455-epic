
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

  async sendMessage({ senderId, recipientId, ciphertext, nonce, digest }) {
    const messageId = uuidv4();

    await this._messageRepo.create({
      messageId, senderId, recipientId, ciphertext, nonce, digestHash: digest,
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
      digestHash: message.digest_hash || null,
      chainStatus: message.chain_status,
      txHash: record ? record.tx_hash : null,
      recordedAt: record ? record.created_at : null,
    };
  }

  async getInbox(userId, options) {
    return this._messageRepo.findByRecipient(userId, options);
  }

  async getSent(userId, options) {
    return this._messageRepo.findBySender(userId, options);
  }

  async getMessage(messageId, userId) {
    const message = await this._messageRepo.findById(messageId);
    if (!message) {
      throw new NotFoundError('Message not found');
    }

    if (message.sender_id !== userId && message.recipient_id !== userId) {
      const shares = await this._messageRepo.findSharedWith(messageId);
      const isShared = shares.some((s) => s.shared_with_id === userId);
      if (!isShared) {
        throw new ForbiddenError('You do not have access to this message');
      }
    }

    return message;
  }

  async forwardMessage({ messageId, forwarderId, recipientId, ciphertext, nonce }) {
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
    });

    // Forwards do not trigger a new chain write — the original message's
    // chain record already attests to the plaintext that was forwarded.
    logger.info(`Message ${messageId} forwarded to ${recipientId}`);
    return { id };
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

module.exports = MessageService;