# Standalone Anchor Verification

`verify.html` lets **anyone** confirm that a plaintext message was anchored on
the Ethereum Sepolia chain, given only the plaintext and the transaction hash.
It is intentionally decoupled from the messaging client and backend — per the
brief, verification must not require trusting (or even running) the app.

## Usage

Open `verify.html` directly in any browser (`file://` works). It loads
**ethers.js v6** from a CDN (`esm.sh`) for keccak256, ABI decoding, and the
JSON-RPC call, so it needs internet to load — but it talks only to public
Sepolia RPCs, never to the messaging app. Then:

1. **Original message content** — paste the decrypted message text, exactly as
   sent (UTF-8). Its `keccak256` digest is shown live as you type.
2. **Recording transaction hash** — the `txHash` from `GET /api/messages/:id/chain`.
3. Click **Verify**.

No transaction handy? Use **Load a demo record** to see a self-contained,
clearly-labelled PASS (then edit the message to see a FAIL).

The page:

- recomputes `keccak256(utf8(plaintext))` locally with ethers,
- fetches the transaction + receipt from a public Sepolia JSON-RPC endpoint,
- decodes the `HashRecorded(bytes32 indexed digest, uint256 timestamp, address indexed recorder)`
  event, **pinned to the configured registry contract**,
- and shows a clear **pass / fail** with the on-chain timestamp, block,
  recorder, and an Etherscan link.

## Result meanings

| Verdict | Meaning |
|---|---|
| ✓ **Integrity verified** | The computed digest matches the digest anchored in this tx. |
| ✕ **Verification failed** | The tx anchored a *different* digest — the content was altered or this tx anchors another message. |
| **No digest found** | The tx emitted no `HashRecorded` event on the registry (wrong tx hash, or not a record tx). |
| **Recorded by a different contract** | A `HashRecorded` event exists but not from the configured `CONTRACT_ADDRESS` — fix the address. |
| **Transaction still pending / not found** | Not mined yet (wait ~15s) or the hash is wrong / on another network. |

## Configuration

The constants at the top of the `<script type="module">` block must match your
deployment (see [`../contracts/DEPLOY.md`](../contracts/DEPLOY.md)):

- **`CONTRACT_ADDRESS`** — your deployed `MessageDigest` address. It ships as a
  placeholder; live verification is pinned to it, so it **must** be set to the
  real address before live verification works. Keep it in sync with
  [`../contracts/deployments/sepolia.json`](../contracts/deployments/sepolia.json)
  and `backend/.env` `CONTRACT_ADDRESS`.
- **`RPC_URLS`** — public Sepolia RPCs, tried in order until one responds.
- **`ABI`** — mirrors [`../contracts/src/MessageDigest.sol`](../contracts/src/MessageDigest.sol)
  (`recordHash`, `getRecord`, and the `HashRecorded` event). The event `topic0`
  is derived from this at runtime, so it cannot drift from the contract.
