const { ethers } = require('ethers');
const config = require('../config');
const logger = require('../utils/logger').child({ component: 'blockchain' });

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
 * Uses the Keccak256Strategy (Strategy pattern) for hashing. The
 * MessageRepository dependency exists so we can write the transaction
 * hash back to the messages row after a successful chain write.
 */
class BlockchainService {
  constructor(hashStrategy, eventBus, messageRepository) {
    this._hashStrategy = hashStrategy;
    this._messageRepo = messageRepository;
    this._provider = null;
    this._wallet = null;
    this._contract = null;

    // Subscribe to message events. Sent and forwarded are handled
    // separately because only 'sent' has a row to update on the
    // messages table — forwards are tracked in message_shares.
    eventBus.on('message:sent', (payload) => this._onMessageSent(payload));
    eventBus.on('message:forwarded', (payload) => this._onMessageForwarded(payload));
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
   * Observer handler — called when a new message is sent.
   * Writes the digest on-chain and persists the tx hash on the row.
   */
  async _onMessageSent({ messageId, ciphertext }) {
    try {
      const txHash = await this.recordDigest(ciphertext);
      if (!txHash) return; // chain not configured — already logged
      await this._messageRepo.updateTxHash(messageId, txHash);
      logger.info(`Blockchain digest recorded for message ${messageId}: ${txHash}`);
    } catch (err) {
      // Log but don't fail — blockchain is best-effort
      logger.error(`Blockchain write failed for message ${messageId}:`, err);
    }
  }

  /**
   * Observer handler — called when a message is forwarded (re-encrypted
   * for a new recipient). The original messages.tx_hash should NOT be
   * overwritten with the forward's digest; the forward gets its own
   * on-chain record but no DB write-back today.
   */
  async _onMessageForwarded({ shareId, ciphertext }) {
    try {
      const txHash = await this.recordDigest(ciphertext);
      if (!txHash) return;
      logger.info(`Blockchain digest recorded for share ${shareId}: ${txHash}`);
    } catch (err) {
      logger.error(`Blockchain write failed for share ${shareId}:`, err);
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
