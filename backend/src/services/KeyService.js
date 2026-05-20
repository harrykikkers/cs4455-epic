/**
 * KeyService — manages public key storage and retrieval under TOFU.
 *
 * Pin-on-first-use: the first key a user publishes for a given key_type is
 * accepted unconditionally. Subsequent publishes are classified:
 *
 *   - unchanged → idempotent re-publish, no-op
 *   - rotation_required → the new key differs from the pinned one; reject
 *     unless the caller explicitly sets acknowledgeRotation=true. This
 *     models the SSH known_hosts warning: a key change is a security event
 *     the user must consent to, not something the server quietly accepts.
 *
 * On accepted rotation, the old key is archived to public_key_history so a
 * compromised server cannot substitute a user's key without leaving an
 * auditable trail.
 */
const { ConflictError, NotFoundError } = require('../utils/errors');
const logger = require('../utils/logger');

class KeyService {
  constructor(keyRepository) {
    this._keyRepo = keyRepository;
  }

  async publishKey({ userId, publicKey, keyType, acknowledgeRotation = false }) {
    const current = await this._keyRepo.findCurrent(userId, keyType);

    if (!current) {
      const { version } = await this._keyRepo.insertFirst({ userId, publicKey, keyType });
      logger.info(`Public key (${keyType}) pinned for user ${userId} v${version}`);
      return { status: 'pinned', version };
    }

    if (current.public_key === publicKey) {
      // Idempotent re-publish — client is just confirming the pin.
      return { status: 'unchanged', version: current.version };
    }

    if (!acknowledgeRotation) {
      // Refuse to overwrite. The client must re-submit with
      // acknowledgeRotation: true after the user confirms the change.
      throw new ConflictError(
        'A different public key is already pinned for this user and key type. ' +
        'Re-publish with acknowledgeRotation=true to rotate.'
      );
    }

    const { version } = await this._keyRepo.rotate({
      userId,
      keyType,
      current,
      newPublicKey: publicKey,
    });
    logger.warn(`Public key (${keyType}) ROTATED for user ${userId} v${version}`);
    return { status: 'rotated', version, previousVersion: current.version };
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

  async getKeyHistory(userId, keyType) {
    return this._keyRepo.getHistory(userId, keyType);
  }
}

module.exports = KeyService;
