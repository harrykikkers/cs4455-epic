
/**
 * BlockchainService — writes client-supplied message digests to the
 * MessageDigest contract on Ethereum Sepolia.
 *
 * The digest is computed by the client (keccak256 of the plaintext) and
 * passed in by MessageService when a message is sent. This service never
 * hashes the message content — it relays the commitment the client made,
 * which is what makes the on-chain record a proof of the plaintext rather
 * than of server-controlled ciphertext. (It does derive a bytes32 key from
 * the messageId for the contract's per-message uniqueness slot; that key is
 * routing metadata, not the integrity digest.)
 *
 * On chain-write failure, the message row is flagged chain_status='failed'
 * so a future retry worker (or an operator) can pick it up. Delivery is
 * never blocked by a Sepolia outage.
 */
const { ethers } = require('ethers');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const logger = require('../utils/logger');

// Contract address + ABI live in the deployment artefact produced by
// contracts/DEPLOY.md. Both the backend and the (future) verification
// page read from the same JSON so they can never drift apart.
const deployment = require('../../../contracts/deployments/sepolia.json');

class BlockchainService {
  constructor(messageRepo) {
    this._messageRepo = messageRepo;
    this._provider = null;
    this._wallet = null;
    this._contract = null;
  }

  _getContract() {
    if (this._contract) return this._contract;

    const { rpcUrl, privateKey, contractAddress } = config.blockchain;
    const address = contractAddress || deployment.address;

    if (!rpcUrl || !privateKey || !address) {
      // Not a hard error — local dev and CI both run without Sepolia creds.
      // The message still gets delivered; chain_status stays 'pending'.
      logger.warn('Blockchain not configured — skipping chain writes');
      return null;
    }

    this._provider = new ethers.JsonRpcProvider(rpcUrl); // connects to sepolia node
    this._wallet = new ethers.Wallet(privateKey, this._provider); // servers wallet
    this._contract = new ethers.Contract(address, deployment.abi, this._wallet); // js object representing the deployed smart contract
    return this._contract;
  }

  /**
   * Called by MessageService after a message row is persisted. Wraps
   * recordDigest with the failure-handling logic so a Sepolia outage marks
   * the message chain_failed instead of bubbling up and 500-ing the API.
   */
  async onMessageSent({ messageId, digestHash }) {
    try {
      const result = await this.recordDigest(messageId, digestHash);
      if (result) {
        logger.info(`Blockchain digest recorded for message ${messageId}: ${result.txHash}`);
      }
    } catch (err) {
      logger.error(`Blockchain write failed for message ${messageId}:`, err);
      try {
        await this._messageRepo.markChainFailed(messageId);
      } catch (markErr) {
        logger.error(`Failed to mark message ${messageId} as chain_failed:`, markErr);
      }
    }
  }

  /**
   * Record a digest on Sepolia and persist the resulting txHash. Returns
   * { txHash, digestHash } on success, or null if blockchain is unconfigured.
   *
   * The digest comes from the client — we do not recompute or validate it
   * against the ciphertext. The bytes32 type already enforces the 32-byte
   * length via ethers; malformed input throws before any tx is sent.
   *
   * The contract keys uniqueness on the messageId, not the digest, so two
   * messages with identical plaintext each anchor independently instead of the
   * second reverting AlreadyRecorded. We pass keccak256(messageId) as the
   * bytes32 key (the UUID hashed into the 32-byte slot the contract expects).
   */
  async recordDigest(messageId, digestHash) {
    const contract = this._getContract();
    if (!contract) return null;

    const tx = await contract.recordHash(digestHash, ethers.id(messageId));
    const receipt = await tx.wait();
    const txHash = receipt.hash;

    await this._messageRepo.recordChainEntry({
      id: uuidv4(),
      messageId,
      txHash,
      digestHash,
    });

    return { txHash, digestHash };
  }
}

module.exports = BlockchainService;
