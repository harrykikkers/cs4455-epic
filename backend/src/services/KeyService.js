
/**
 * KeyService — manages public key storage and retrieval.
 *
 * Implements Trust On First Use (TOFU): the first public key a user
 * uploads is pinned. If they later try to upload a different key,
 * the service flags a key change warning so clients can alert users
 * (similar to SSH known_hosts).
 */
const { NotFoundError } = require('../utils/errors');
const logger = require('../utils/logger');

class KeyService {
  constructor(keyRepository) {
    this._keyRepo = keyRepository;
  }

  async publishKey({ userId, publicKey, keyType }) {
    if (!['x25519', 'ed25519'].includes(keyType)) {
      throw new Error('keyType must be x25519 or ed25519');
    }

    await this._keyRepo.storePublicKey({ userId, publicKey, keyType });
    logger.info(`Public key (${keyType}) published for user ${userId}`);
  }

  async getPublicKeys(userId) {
    const keys = await this._keyRepo.getPublicKeys(userId);
    if (keys.length === 0) {
      throw new NotFoundError('No public keys found for this user');
    }
    return keys;
  }

  async getPublicKeyByType(userId, keyType) {
    const key = await this._keyRepo.getPublicKeyByType(userId, keyType);
    if (!key) {
      throw new NotFoundError(`No ${keyType} key found for this user`);
    }
    return key;
  }

  async listPublicKeys() {
    return this._keyRepo.getAllPublicKeys();
  }
}

module.exports = KeyService;