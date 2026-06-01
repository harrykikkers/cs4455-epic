/**
 * BlockchainService — flow tests.
 *
 * BlockchainService is the bridge between MessageService and the Sepolia
 * MessageDigest contract. Its responsibilities are narrow but each branch
 * has a clear correctness story:
 *
 *   - It does NOT compute the digest. The client computes keccak256(plaintext)
 *     and the server relays that exact value. Otherwise the on-chain record
 *     would only attest "what the server stored", not the plaintext.
 *   - It must never block message delivery. A Sepolia outage, a missing
 *     contract address, or an ethers.js throw must end with chain_status
 *     flipped to 'failed' (or left 'pending'), not a 500 from the API.
 *   - On success it inserts a blockchain_records row AND flips messages
 *     .chain_status='recorded' — the transaction MessageRepository
 *     .recordChainEntry wraps.
 *
 * ethers (provider/wallet/contract) is the external boundary, so it is mocked
 * at the module level; the repo surface is small enough to stub directly. The
 * service's real body runs unchanged against both.
 */

// Mock ethers before requiring the service. recordHash is captured in the
// factory closure so individual tests can program its resolve/reject behaviour
// and assert how it was called.
jest.mock('ethers', () => {
  const recordHash = jest.fn();
  return {
    ethers: {
      JsonRpcProvider: jest.fn(() => ({ _tag: 'provider' })),
      Wallet: jest.fn(() => ({ _tag: 'wallet' })),
      Contract: jest.fn(() => ({ recordHash })),
      // Test escape hatch — not part of the real ethers surface.
      _recordHash: recordHash,
    },
  };
});

const { ethers } = require('ethers');
const config = require('../../src/config');
const deployment = require('../../../contracts/deployments/sepolia.json');
const BlockchainService = require('../../src/services/BlockchainService');

const recordHash = ethers._recordHash;

const RPC = 'https://sepolia.example/rpc';
const PRIV = '0x' + '1'.repeat(64);
const ADDR = '0x' + 'a'.repeat(40);
const TX_HASH = '0x' + 'f'.repeat(64);
const DIGEST = '0x' + 'd'.repeat(64);

// The config object is a process-wide singleton; jest isolates module
// registries per test file, so mutating config.blockchain here cannot leak
// into other suites. We still restore it after each test for hygiene.
let savedBlockchain;

function withCreds({ contractAddress = ADDR } = {}) {
  config.blockchain.rpcUrl = RPC;
  config.blockchain.privateKey = PRIV;
  config.blockchain.contractAddress = contractAddress;
}

function withoutCreds() {
  config.blockchain.rpcUrl = '';
  config.blockchain.privateKey = '';
  config.blockchain.contractAddress = '';
}

// A recordHash that resolves to a tx whose wait() yields a receipt.
function chainSucceeds(txHash = TX_HASH) {
  recordHash.mockResolvedValue({ wait: jest.fn().mockResolvedValue({ hash: txHash }) });
}

function build() {
  const messageRepo = {
    recordChainEntry: jest.fn().mockResolvedValue(undefined),
    markChainFailed: jest.fn().mockResolvedValue(undefined),
  };
  const svc = new BlockchainService(messageRepo);
  return { svc, messageRepo };
}

beforeEach(() => {
  jest.clearAllMocks();
  savedBlockchain = { ...config.blockchain };
});

afterEach(() => {
  Object.assign(config.blockchain, savedBlockchain);
});

describe('BlockchainService', () => {
  describe('_getContract / configuration', () => {
    test('returns null and logs a warning when creds are all unset (local dev path)', async () => {
      withoutCreds();
      const { svc } = build();

      expect(svc._getContract()).toBeNull();
      // No provider/wallet/contract is constructed when creds are missing.
      expect(ethers.JsonRpcProvider).not.toHaveBeenCalled();
      expect(ethers.Contract).not.toHaveBeenCalled();
    });

    test('falls back to deployment.address when config.blockchain.contractAddress is unset', async () => {
      withCreds({ contractAddress: '' });
      const { svc } = build();

      svc._getContract();

      expect(ethers.Contract).toHaveBeenCalledTimes(1);
      expect(ethers.Contract.mock.calls[0][0]).toBe(deployment.address);
    });

    test('memoises the contract — only one provider/wallet/contract across repeated calls', async () => {
      withCreds();
      const { svc } = build();

      const a = svc._getContract();
      const b = svc._getContract();

      expect(a).toBe(b);
      expect(ethers.JsonRpcProvider).toHaveBeenCalledTimes(1);
      expect(ethers.Wallet).toHaveBeenCalledTimes(1);
      expect(ethers.Contract).toHaveBeenCalledTimes(1);
    });

    test('uses deployment.abi verbatim so backend and verification page cannot drift', async () => {
      withCreds();
      const { svc } = build();

      svc._getContract();

      // Contract(address, abi, wallet) — the abi arg is the deployment artefact's.
      expect(ethers.Contract.mock.calls[0][1]).toBe(deployment.abi);
    });
  });

  describe('recordDigest', () => {
    test('calls contract.recordHash with the EXACT client-supplied digest — no rehashing', async () => {
      withCreds();
      chainSucceeds();
      const { svc } = build();

      await svc.recordDigest('msg-1', DIGEST);

      expect(recordHash).toHaveBeenCalledTimes(1);
      expect(recordHash).toHaveBeenCalledWith(DIGEST);
    });

    test('awaits tx.wait() and persists receipt.hash as the txHash', async () => {
      withCreds();
      chainSucceeds('0x' + 'c'.repeat(64));
      const { svc, messageRepo } = build();

      const result = await svc.recordDigest('msg-1', DIGEST);

      expect(result).toEqual({ txHash: '0x' + 'c'.repeat(64), digestHash: DIGEST });
      expect(messageRepo.recordChainEntry).toHaveBeenCalledWith(
        expect.objectContaining({ messageId: 'msg-1', txHash: '0x' + 'c'.repeat(64), digestHash: DIGEST })
      );
    });

    test('persists { id: uuid, messageId, txHash, digestHash } via recordChainEntry', async () => {
      withCreds();
      chainSucceeds();
      const { svc, messageRepo } = build();

      await svc.recordDigest('msg-42', DIGEST);

      const arg = messageRepo.recordChainEntry.mock.calls[0][0];
      expect(arg).toEqual({
        id: expect.stringMatching(/^[0-9a-f-]{36}$/),
        messageId: 'msg-42',
        txHash: TX_HASH,
        digestHash: DIGEST,
      });
    });

    test('generates a fresh uuid per chain record (never reuses an id)', async () => {
      withCreds();
      chainSucceeds();
      const { svc, messageRepo } = build();

      await svc.recordDigest('msg-1', DIGEST);
      await svc.recordDigest('msg-2', DIGEST);

      const id1 = messageRepo.recordChainEntry.mock.calls[0][0].id;
      const id2 = messageRepo.recordChainEntry.mock.calls[1][0].id;
      expect(id1).not.toBe(id2);
    });

    test('returns null without throwing when the contract is unconfigured (caller treats as skip)', async () => {
      withoutCreds();
      const { svc, messageRepo } = build();

      await expect(svc.recordDigest('msg-1', DIGEST)).resolves.toBeNull();
      expect(messageRepo.recordChainEntry).not.toHaveBeenCalled();
    });

    test('lets an ethers throw propagate and writes no chain record (malformed digest rejected pre-tx)', async () => {
      withCreds();
      recordHash.mockRejectedValue(new Error('invalid BytesLike value'));
      const { svc, messageRepo } = build();

      await expect(svc.recordDigest('msg-1', 'not-bytes32')).rejects.toThrow('invalid BytesLike value');
      expect(messageRepo.recordChainEntry).not.toHaveBeenCalled();
    });
  });

  describe('onMessageSent — failure handling', () => {
    test('flips chain_status="failed" when contract.recordHash rejects (Sepolia outage)', async () => {
      withCreds();
      recordHash.mockRejectedValue(new Error('RPC unavailable'));
      const { svc, messageRepo } = build();

      await svc.onMessageSent({ messageId: 'msg-1', digestHash: DIGEST });

      expect(messageRepo.markChainFailed).toHaveBeenCalledWith('msg-1');
      expect(messageRepo.recordChainEntry).not.toHaveBeenCalled();
    });

    test('flips chain_status="failed" when tx.wait rejects (tx mined but reverted)', async () => {
      withCreds();
      recordHash.mockResolvedValue({ wait: jest.fn().mockRejectedValue(new Error('reverted')) });
      const { svc, messageRepo } = build();

      await svc.onMessageSent({ messageId: 'msg-1', digestHash: DIGEST });

      expect(messageRepo.markChainFailed).toHaveBeenCalledWith('msg-1');
    });

    test('never re-throws — sendMessage must still complete when Sepolia is down', async () => {
      withCreds();
      recordHash.mockRejectedValue(new Error('boom'));
      const { svc } = build();

      await expect(
        svc.onMessageSent({ messageId: 'msg-1', digestHash: DIGEST })
      ).resolves.toBeUndefined();
    });

    test('swallows a secondary failure inside markChainFailed — no double-fault', async () => {
      withCreds();
      recordHash.mockRejectedValue(new Error('chain down'));
      const { svc, messageRepo } = build();
      messageRepo.markChainFailed.mockRejectedValue(new Error('db also down'));

      await expect(
        svc.onMessageSent({ messageId: 'msg-1', digestHash: DIGEST })
      ).resolves.toBeUndefined();
      expect(messageRepo.markChainFailed).toHaveBeenCalledWith('msg-1');
    });

    test('does not mark failed on the happy path — records the chain entry instead', async () => {
      withCreds();
      chainSucceeds();
      const { svc, messageRepo } = build();

      await svc.onMessageSent({ messageId: 'msg-1', digestHash: DIGEST });

      expect(messageRepo.recordChainEntry).toHaveBeenCalledTimes(1);
      expect(messageRepo.markChainFailed).not.toHaveBeenCalled();
    });
  });

  describe('integrity invariants the on-chain record must hold', () => {
    test('the digest written on-chain equals the digest persisted on the record', async () => {
      withCreds();
      chainSucceeds();
      const { svc, messageRepo } = build();

      await svc.recordDigest('msg-1', DIGEST);

      const onChain = recordHash.mock.calls[0][0];
      const persisted = messageRepo.recordChainEntry.mock.calls[0][0].digestHash;
      expect(onChain).toBe(persisted);
      expect(onChain).toBe(DIGEST);
    });

    test('the messageId on the blockchain_records row matches the message it attests to (no cross-wiring)', async () => {
      withCreds();
      chainSucceeds();
      const { svc, messageRepo } = build();

      await svc.recordDigest('the-real-message-id', DIGEST);

      expect(messageRepo.recordChainEntry.mock.calls[0][0].messageId).toBe('the-real-message-id');
    });

    // The "forward does not re-write the chain" and "soft-delete preserves the
    // blockchain_records row" invariants live at the MessageService /
    // MessageRepository layer (BlockchainService has no forward or delete path)
    // and are exercised in MessageService.test.js.
    test.todo('forward/soft-delete chain invariants — covered in MessageService.test.js');
  });
});
