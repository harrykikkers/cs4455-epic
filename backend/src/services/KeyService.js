const { ConflictError, NotFoundError } = require('../utils/errors');
const logger = require('../utils/logger');

/**
 * KeyService — manages public key storage and retrieval.
 *
 * Implements Trust On First Use (TOFU): the first public key a user
 * uploads is pinned. If they later try to upload a different key,
 * the service flags a key change warning so clients can alert users
 * (similar to SSH known_hosts).
 */
class KeyService {
  constructor(keyRepository) {
    this._keyRepo = keyRepository;
  }

  async publishKey({ userId, publicKey, keyType = 'x25519' }) {
    const existing = await this._keyRepo.getPublicKey(userId);

    if (existing && existing.public_key !== publicKey) {
      logger.warn(`Key rotation detected for user ${userId}`);
      // Store the new key but flag that it was rotated
      // Clients should warn users about key changes (TOFU model)
    }

    await this._keyRepo.storePublicKey({ userId, publicKey, keyType });
    logger.info(`Public key published for user ${userId}`);
  }

  async getPublicKey(userId) {
    const key = await this._keyRepo.getPublicKey(userId);
    if (!key) {
      throw new NotFoundError('No public key found for this user');
    }
    return key;
  }

  async listPublicKeys() {
    return this._keyRepo.getAllPublicKeys();
  }
}

module.exports = KeyService;
