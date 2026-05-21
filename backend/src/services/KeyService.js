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
const { audit } = require('../utils/logger');

class KeyService {
  constructor(keyRepository) {
    this._keyRepo = keyRepository;
  }

  async publishKey({ userId, publicKey, keyType, acknowledgeRotation = false }) {
    const result = await this._keyRepo.publishKey({
      userId,
      publicKey,
      keyType,
      acknowledgeRotation,
    });

    switch (result.status) {
      case 'pinned':
        logger.info(`Public key (${keyType}) pinned for user ${userId} v${result.version}`);
        audit.info(`key.published userId=${userId} keyType=${keyType} version=${result.version} status=pinned`);
        return { status: 'pinned', version: result.version };

      case 'unchanged':
        // Idempotent re-publish — client is just confirming the pin.
        return { status: 'unchanged', version: result.version };

      case 'rotation_required':
        audit.warn(`key.rotation.refused userId=${userId} keyType=${keyType} reason=no_acknowledgement`);
        // Refuse to overwrite. The client must re-submit with
        // acknowledgeRotation: true after the user confirms the change.
        throw new ConflictError(
          'A different public key is already pinned for this user and key type. ' +
          'Re-publish with acknowledgeRotation=true to rotate.'
        );

      case 'rotated':
        logger.warn(`Public key (${keyType}) ROTATED for user ${userId} v${result.version}`);
        audit.warn(`key.rotated userId=${userId} keyType=${keyType} version=${result.version} previousVersion=${result.previousVersion}`);
        return { status: 'rotated', version: result.version, previousVersion: result.previousVersion };
    }
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
