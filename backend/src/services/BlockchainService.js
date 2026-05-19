const { ethers } = require('ethers');
const config = require('../config');
const logger = require('../utils/logger');

// Minimal ABI — only the functions our server calls
const CONTRACT_ABI = [
  'function recordHash(bytes32 messageHash) external',
  'function getRecord(bytes32 messageHash) external view returns (uint256 timestamp, address recorder)',
  'event HashRecorded(bytes32 indexed messageHash, uint256 timestamp, address recorder)',
];

/**
 * BlockchainService — writes message digest hashes to Ethereum Sepolia.
 *
 * Subscribes to the EventBus 'message:sent' event (Observer pattern)
 * so it runs automatically whenever a message is sent, without the
 * MessageService knowing about blockchain at all.
 *
 * Uses the Keccak256Strategy (Strategy pattern) for hashing.
 */
class BlockchainService {
  constructor(hashStrategy, eventBus) {
    this._hashStrategy = hashStrategy;
    this._provider = null;
    this._wallet = null;
    this._contract = null;

    // Subscribe to message events
    eventBus.on('message:sent', (payload) => this._onMessageSent(payload));
    eventBus.on('message:forwarded', (payload) => this._onMessageSent(payload));
  }

  /**
   * Lazy initialisation — don't connect to Sepolia until first use.
   * Avoids startup failures when blockchain config is missing (dev mode).
   */
  _getContract() {
    if (!this._contract) {
      if (!config.blockchain.rpcUrl || !config.blockchain.privateKey) {
        logger.warn('Blockchain not configured — skipping chain writes');
        return null;
      }
      this._provider = new ethers.JsonRpcProvider(config.blockchain.rpcUrl);
      this._wallet = new ethers.Wallet(config.blockchain.privateKey, this._provider);
      this._contract = new ethers.Contract(
        config.blockchain.contractAddress,
        CONTRACT_ABI,
        this._wallet
      );
    }
    return this._contract;
  }

  /**
   * Observer handler — called when a message is sent.
   */
  async _onMessageSent({ messageId, ciphertext, timestamp }) {
    try {
      const txHash = await this.recordDigest(ciphertext);
      logger.info(`Blockchain digest recorded for message ${messageId}: ${txHash}`);
    } catch (err) {
      // Log but don't fail — blockchain is best-effort
      logger.error(`Blockchain write failed for message ${messageId}:`, err);
    }
  }

  /**
   * Hash the ciphertext and write the digest to the smart contract.
   * Returns the transaction hash for storage in MySQL.
   */
  async recordDigest(data) {
    const contract = this._getContract();
    if (!contract) return null;

    const hash = await this._hashStrategy.hash(data);
    const tx = await contract.recordHash(hash);
    const receipt = await tx.wait();

    return receipt.hash;
  }

  /**
   * Verify a piece of data against its on-chain record.
   * Used by the verification page endpoint.
   */
  async verifyDigest(data) {
    const contract = this._getContract();
    if (!contract) return { verified: false, reason: 'Blockchain not configured' };

    const hash = await this._hashStrategy.hash(data);
    const record = await contract.getRecord(hash);

    if (record.timestamp === 0n) {
      return { verified: false, reason: 'No on-chain record found' };
    }

    return {
      verified: true,
      hash,
      timestamp: Number(record.timestamp),
      recorder: record.recorder,
    };
  }
}

module.exports = BlockchainService;
