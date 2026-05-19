const argon2 = require('argon2');
const config = require('../../config');

/**
 * GoF Strategy pattern — HashStrategy
 *
 * The auth system needs to hash passwords (Argon2id) and the blockchain
 * module needs to hash message digests (keccak256). Both are "hashing"
 * but with completely different algorithms and purposes.
 *
 * The Strategy pattern lets the AuthService and BlockchainService each
 * receive the hashing behaviour they need without knowing the algorithm
 * details. It also makes testing easy — swap in a fast mock strategy
 * during unit tests.
 *
 * Why here: O'Brien's rubric explicitly requires Argon2id with justified
 * parameters. Encapsulating the parameter selection in a strategy makes
 * the justification traceable to one place.
 */

/**
 * Strategy interface (duck-typed — JS doesn't have interfaces).
 * Every strategy must implement:
 *   hash(input) → string
 *   verify(input, hash) → boolean
 */

class Argon2Strategy {
  constructor() {
    // type: argon2id — hybrid of argon2i (side-channel resistant)
    //                   and argon2d (GPU resistant)
    this.options = {
      type: argon2.argon2id,
      memoryCost: config.argon2.memoryCost,
      timeCost: config.argon2.timeCost,
      parallelism: config.argon2.parallelism,
    };
  }

  async hash(password) {
    return argon2.hash(password, this.options);
  }

  /**
   * Constant-time verify. argon2.verify compares the derived hash against
   * the embedded hash using a constant-time routine inside libargon2, so a
   * timing side-channel can't reveal how many leading bytes matched.
   */
  async verify(password, hash) {
    return argon2.verify(hash, password);
  }
}

class Keccak256Strategy {
  /**
   * Used by the blockchain module to hash message content.
   * ethers.keccak256 expects bytes, so we encode to UTF-8 first.
   */
  async hash(data) {
    const { keccak256, toUtf8Bytes } = require('ethers');
    return keccak256(toUtf8Bytes(data));
  }

  /**
   * Plain string-equality compare — NOT constant-time. Acceptable here
   * because both operands are public values (an on-chain hash and a hash
   * of public content), so there is no timing oracle to protect against.
   * Do NOT reuse this strategy for password or MAC verification.
   */
  async verify(data, expectedHash) {
    const computed = await this.hash(data);
    return computed === expectedHash;
  }
}

module.exports = { Argon2Strategy, Keccak256Strategy };
