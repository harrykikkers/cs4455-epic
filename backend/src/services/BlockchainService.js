
/**
 * BlockchainService — writes message digest hashes to Ethereum Sepolia.
 *
 * Subscribes to the EventBus 'message:sent' event (Observer pattern)
 * so it runs automatically whenever a message is sent, without the
 * MessageService knowing about blockchain at all.
 *
 * Uses the Keccak256Strategy (Strategy pattern) for hashing. The
 * MessageRepository dependency exists so we can write the transaction
 * hash back to the messages row after a successful chain write.
 */
const { ethers } = require('ethers');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const logger = require('../utils/logger');

const CONTRACT_ABI = [
  'function recordHash(bytes32 messageHash) external',
  'function getRecord(bytes32 messageHash) external view returns (uint256 timestamp, address recorder)',
  'event HashRecorded(bytes32 indexed messageHash, uint256 timestamp, address recorder)',
];

class BlockchainService {
  constructor(hashStrategy, eventBus, dbPool) {
    this._hashStrategy = hashStrategy;
    this._pool = dbPool;
    this._provider = null;
    this._wallet = null;
    this._contract = null;

    eventBus.on('message:sent', (payload) => this._onMessageSent(payload));
    eventBus.on('message:forwarded', (payload) => this._onMessageSent(payload));
  }

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

  async _onMessageSent({ messageId, ciphertext }) {
    try {
      const result = await this.recordDigest(messageId, ciphertext);
      if (result) {
        logger.info(`Blockchain digest recorded for message ${messageId}: ${result.txHash}`);
      }
    } catch (err) {
      logger.error(`Blockchain write failed for message ${messageId}:`, err);
    }
  }

  async recordDigest(messageId, data) {
    const contract = this._getContract();
    if (!contract) return null;

    const digestHash = await this._hashStrategy.hash(data);
    const tx = await contract.recordHash(digestHash);
    const receipt = await tx.wait();
    const txHash = receipt.hash;

    // Write to blockchain_records table
    const id = uuidv4();
    await this._pool.execute(
      'INSERT INTO blockchain_records (id, message_id, tx_hash, digest_hash) VALUES (?, ?, ?, ?)',
      [id, messageId, txHash, digestHash]
    );

    return { txHash, digestHash };
  }

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