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
    return keys.map(toKeyDTO);
  }

  async getPublicKeyByType(userId, keyType) {
    const key = await this._keyRepo.getPublicKeyByType(userId, keyType);
    if (!key) {
      throw new NotFoundError(`No ${keyType} key found for this user`);
    }
    return toKeyDTO(key);
  }

  async listPublicKeys() {
    const keys = await this._keyRepo.getAllPublicKeys();
    return keys.map(toDirectoryDTO);
  }

  async getKeyHistory(userId, keyType) {
    const history = await this._keyRepo.getHistory(userId, keyType);
    return history.map(toHistoryDTO);
  }
}

// Raw key rows are stored snake_case; the API exposes camelCase to match the
// rest of the surface (auth payloads, request bodies, chain proof).

function toKeyDTO(row) {
  return {
    publicKey: row.public_key,
    keyType: row.key_type,
    version: row.version,
    createdAt: row.created_at,
    rotatedAt: row.rotated_at,
  };
}

function toDirectoryDTO(row) {
  return {
    userId: row.user_id,
    username: row.username,
    publicKey: row.public_key,
    keyType: row.key_type,
    version: row.version,
  };
}

function toHistoryDTO(row) {
  return {
    publicKey: row.public_key,
    keyType: row.key_type,
    version: row.version,
    pinnedAt: row.pinned_at,
    rotatedAt: row.rotated_at,
  };
}

module.exports = KeyService;
