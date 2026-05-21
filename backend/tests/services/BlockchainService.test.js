/**
 * BlockchainService — flow scaffold (TODOs).
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
 *     .chain_status='recorded' — this is the transaction MessageRepository
 *     .recordChainEntry wraps.
 *
 * Suggested wiring (no fakePool — the repo surface is small enough to stub):
 *
 *   function build({ withCreds = true } = {}) {
 *     const messageRepo = {
 *       recordChainEntry: jest.fn().mockResolvedValue(),
 *       markChainFailed:  jest.fn().mockResolvedValue(),
 *     };
 *     // Stub config + ethers — see comments under each test for which knobs.
 *     const svc = new BlockchainService(messageRepo);
 *     return { svc, messageRepo };
 *   }
 *
 * NOTE: ethers.JsonRpcProvider / ethers.Wallet / ethers.Contract are
 * instantiated lazily in _getContract(). The cleanest approach is to
 * jest.mock('ethers') at the top of the file and assert on the mocked
 * contract.recordHash + tx.wait calls.
 */

describe('BlockchainService', () => {
  describe('_getContract / configuration', () => {
    test.todo('returns null and logs a warning when rpcUrl / privateKey / contractAddress are all unset (local dev path)');
    test.todo('falls back to deployment.address from contracts/deployments/sepolia.json when config.blockchain.contractAddress is unset');
    test.todo('memoises the contract instance — only one provider/wallet/contract is created across repeated calls');
    test.todo('uses deployment.abi verbatim so backend and verification page cannot drift');
  });

  describe('recordDigest', () => {
    test.todo('calls contract.recordHash(digestHash) with the EXACT client-supplied bytes — no rehashing on the server');
    test.todo('awaits tx.wait() and uses receipt.hash as the txHash persisted in blockchain_records');
    test.todo('calls messageRepo.recordChainEntry with { id: uuid, messageId, txHash, digestHash }');
    test.todo('generates a fresh uuid per chain record (never reuses an id across messages)');
    test.todo('returns { txHash, digestHash } on success');
    test.todo('returns null without throwing when the contract is unconfigured (caller treats this as "skip")');
    test.todo('lets ethers throw propagate — bytes32 length validation happens before any tx is sent');
  });

  describe('onMessageSent — failure handling', () => {
    test.todo('on contract.recordHash rejection (Sepolia outage / RPC error), flips chain_status="failed" via markChainFailed');
    test.todo('on tx.wait rejection (tx mined but reverted), flips chain_status="failed"');
    test.todo('never re-throws — MessageService.sendMessage must complete the 201 response even if Sepolia is down');
    test.todo('swallows secondary failures inside markChainFailed (logs only — no double-fault)');
    test.todo('logs the successful txHash at info level for operator observability');
    test.todo('logs the failure with the messageId at error level (enough context to retry by hand)');
  });

  describe('integrity invariants the on-chain record must hold', () => {
    test.todo('the digest written on-chain equals the digest persisted on the messages row');
    test.todo('the messageId in the blockchain_records row matches the message it attests to (no cross-wiring)');
    test.todo('a forwarded message does NOT produce a second chain write — the original record is the proof');
    test.todo('after a soft-delete on the message, the blockchain_records row is preserved (verification still possible)');
  });
});
