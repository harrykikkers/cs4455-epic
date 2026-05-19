const { v4: uuidv4 } = require('uuid');
const { NotFoundError, ForbiddenError } = require('../utils/errors');
const logger = require('../utils/logger');

/**
 * MessageService — orchestrates message operations.
 *
 * The server only ever handles ciphertext. It cannot read, decrypt,
 * or verify message contents. All encryption happens client-side.
 *
 * Uses the Observer pattern (EventBus) to notify the blockchain module
 * when messages are sent, without depending on it directly.
 */
class MessageService {
  constructor(messageRepository, eventBus) {
    this._messageRepo = messageRepository;
    this._eventBus = eventBus;
  }

  async sendMessage({ senderId, recipientId, ciphertext, nonce, senderPublicKey }) {
    const id = uuidv4();

    await this._messageRepo.create({
      id, senderId, recipientId, ciphertext, nonce, senderPublicKey, txHash: null,
    });

    // Emit event — blockchain listener will pick this up and record the hash
    await this._eventBus.emit('message:sent', {
      messageId: id,
      senderId,
      recipientId,
      ciphertext,
      timestamp: new Date().toISOString(),
    });

    logger.info(`Message sent: ${id} from ${senderId} to ${recipientId}`);
    return { id };
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

    // Access control — only sender or recipient can view
    if (message.sender_id !== userId && message.recipient_id !== userId) {
      // Check if it was shared with this user
      const shares = await this._messageRepo.findSharedWith(messageId);
      const isShared = shares.some((s) => s.shared_with_id === userId);
      if (!isShared) {
        throw new ForbiddenError('You do not have access to this message');
      }
    }

    return message;
  }

  async forwardMessage({ messageId, forwarderId, recipientId, ciphertext, nonce }) {
    const id = uuidv4();

    await this._messageRepo.createShare({
      id,
      messageId,
      sharedById: forwarderId,
      sharedWithId: recipientId,
      ciphertext,
      nonce,
    });

    await this._eventBus.emit('message:forwarded', {
      shareId: id,
      messageId,
      forwarderId,
      recipientId,
      ciphertext,
      timestamp: new Date().toISOString(),
    });

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
    await this._messageRepo.softDelete(messageId, userId);
    logger.info(`Message soft-deleted: ${messageId} by ${userId}`);
  }
}

module.exports = MessageService;
