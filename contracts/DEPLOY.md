# Deploying `MessageDigest.sol` to Sepolia via Remix

End-to-end instructions for taking the contract in `src/MessageDigest.sol` from
zero to a verified, working Sepolia deployment that the backend can talk to.

Total time: ~30 minutes including Etherscan verification.

---

## 0. Prerequisites

- [MetaMask](https://metamask.io) installed in your browser
- A MetaMask account with **Sepolia ETH** — get some from a faucet:
  - https://sepoliafaucet.com
  - https://www.alchemy.com/faucets/ethereum-sepolia
  - https://cloud.google.com/application/web3/faucet/ethereum/sepolia

  0.05 ETH is plenty for the entire project.
- An Etherscan account + API key (free) for source verification:
  - Register at https://etherscan.io/register
  - Generate an API key: https://etherscan.io/myapikey

## 1. Open Remix and load the contract

1. Go to https://remix.ethereum.org.
2. In the **File Explorers** panel, create a new workspace (or use the default).
3. Create a new file at `contracts/MessageDigest.sol`.
4. Paste in the contents of `contracts/src/MessageDigest.sol` from this repo.

> Alternative: use the **gist/url import** button to load the file directly
> from GitHub once the repo is pushed.

## 2. Compile

1. Open the **Solidity Compiler** tab (the Solidity icon, left sidebar).
2. Set the compiler version to **`0.8.24`** (must match the `pragma`).
3. Enable optimisation: **Enabled, 200 runs** (saves gas without breaking ABI compatibility).
4. Click **Compile MessageDigest.sol**. Green tick = success.
5. Open the **Compilation Details** modal (next to "Compile"). Copy the **ABI**
   from there — you'll paste it into `contracts/deployments/sepolia.json`
   after deployment.

## 3. Connect MetaMask to Sepolia

1. Click the MetaMask icon, switch the network to **Sepolia Test Network**.
   (If you don't see Sepolia, enable test networks in MetaMask settings →
   Advanced → Show test networks.)
2. Confirm your account has Sepolia ETH from step 0.

## 4. Deploy via Remix

1. Open the **Deploy & Run Transactions** tab (the Ethereum icon).
2. Set **Environment** to **Injected Provider — MetaMask**.
   - Remix will prompt MetaMask to connect; approve it.
   - The **Account** dropdown should now show your MetaMask address with a
     non-zero Sepolia balance.
3. Set **Contract** to **MessageDigest**.
4. Click the orange **Deploy** button.
5. MetaMask pops up with a deploy transaction. Confirm it.
6. Wait ~15s for the block. The deployed contract appears under
   **Deployed Contracts** at the bottom of the panel.

Note three things from the deployment:
- **Contract address** (click the copy icon next to the contract name).
- **Transaction hash** (in the Remix console).
- **Block number** (in the Remix console).

## 5. Authorise the backend's server wallet as a recorder

The contract's `onlyRecorder` modifier means only allow-listed addresses can
call `recordHash`. By default only the deployer is a recorder. The backend
runs on the VM with its own server wallet, so you must allow-list it.

1. Generate a server wallet specifically for the VM. **Do not reuse your
   personal MetaMask wallet** — keep deploy and runtime keys separate.

   In Node:
   ```bash
   node -e "console.log(new (require('ethers')).Wallet.createRandom())"
   ```
   This prints `address`, `privateKey`, and `publicKey`. Save the private key
   to the VM's `.env` as `SEPOLIA_PRIVATE_KEY=…` and **never commit it**.

2. Fund the server wallet with a small amount of Sepolia ETH (~0.02 ETH)
   from the faucet. The backend will spend gas every time a message is sent.

3. In Remix, under **Deployed Contracts → MessageDigest**, find the
   **setRecorder** function. Fill in:
   - `r`: the server wallet's address from step 1
   - `allowed`: `true`
4. Click **transact**, confirm in MetaMask, wait for confirmation.
5. Verify by expanding **recorders** and pasting the server wallet address —
   it should return `true`.

## 6. Verify the source on Etherscan

This step is what lets Le Gear (and anyone else) read your contract's source
on `sepolia.etherscan.io`. It's free, takes 2 minutes, and is a big interview win.

1. In Remix, open the **Contract Verification - Etherscan** plugin
   (Plugin Manager → search "Etherscan" → activate).
2. Enter your Etherscan API key.
3. Choose network **Sepolia**.
4. Paste the deployed contract address.
5. Confirm the contract name is `MessageDigest`, compiler version `0.8.24`,
   optimisation **enabled, 200 runs** (must match step 2).
6. Click **Verify**.
7. Once confirmed, visit
   `https://sepolia.etherscan.io/address/<your-contract-address>#code` —
   your Solidity source should be readable in the browser.

## 7. Save artefacts to the repo

Update `contracts/deployments/sepolia.json` with the real values:

```json
{
  "network": "sepolia",
  "chainId": 11155111,
  "address": "0xYOUR_CONTRACT_ADDRESS",
  "deployTxHash": "0xYOUR_DEPLOY_TX_HASH",
  "deployBlock": 1234567,
  "abi": [ ... paste from Remix Compilation Details ... ]
}
```

The ABI committed in the file before deployment is a hand-rolled copy of what
solc emits; replace it with Remix's output to be safe (the binary signature
matters for verification — field ordering and whitespace don't).

Commit this file to the repo. Both the backend and the verification page read
from it.

## 8. Wire the backend

In `backend/.env` on the VM (NOT committed):

```bash
SEPOLIA_RPC_URL=https://ethereum-sepolia.publicnode.com
SEPOLIA_PRIVATE_KEY=0x...                 # the SERVER wallet's private key
CONTRACT_ADDRESS=0xYOUR_CONTRACT_ADDRESS
```

Free public Sepolia RPCs (no signup needed):
- `https://ethereum-sepolia.publicnode.com`
- `https://rpc.sepolia.org`
- `https://eth-sepolia.g.alchemy.com/v2/<api-key>` (rate-limited free tier
  with signup — more reliable for sustained use)

Restart the backend. On the first message send, you should see in the logs:

```
INFO  [blockchain]  Blockchain digest recorded for message <uuid>: 0x<txhash>
```

If the server wallet isn't authorised, you'll see a `NotRecorder` revert —
go back to step 5.

## 9. Smoke test

```bash
# 1. Send a message via the API (digest is whatever the client computes —
#    here we use keccak256 of the literal string "test" for demonstration)
curl -X POST https://zebra.theburkenator.com/api/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "recipientId": "<some-user-uuid>",
    "ciphertext":  "<some-base64-ciphertext>",
    "nonce":       "<some-base64-nonce>",
    "digest":      "0x9c22ff5f21f0b81b113e63f7db6da94fedef11b2119b4088b89664fb9a3cb658"
  }'

# 2. Fetch the chain proof for that message
curl -H "Authorization: Bearer $TOKEN" \
  https://zebra.theburkenator.com/api/messages/<message-id>/chain
# → { data: { digestHash, chainStatus: "recorded", txHash, recordedAt } }

# 3. Confirm on Sepolia Etherscan
open https://sepolia.etherscan.io/tx/<txHash>
# You should see the HashRecorded event with the same digest.
```

## 10. Rotating or redeploying

If you ever need to redeploy (e.g. you change the contract):

1. Repeat steps 4–7 with the new contract.
2. Old `blockchain_records` rows still point to the old contract address —
   they remain verifiable on-chain, but new writes go to the new address.
3. Update `contracts/deployments/sepolia.json` AND `backend/.env` AND the
   verification page's deployment artefact. All three must agree.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| MetaMask says "insufficient funds" | No Sepolia ETH | Faucet (step 0) |
| `NotRecorder` revert when backend tries to write | Server wallet not allow-listed | Step 5 — `setRecorder(serverAddr, true)` |
| `AlreadyRecorded` revert | Same **messageId** anchored twice (a retry of an already-recorded message) | Expected idempotency guard, not an error — the message is already on-chain. The record is keyed by messageId, so identical plaintexts in *different* messages no longer collide. |
| Etherscan verification fails: bytecode mismatch | Compiler version or optimiser settings differ between Remix and Etherscan | Re-check step 2 settings, redo step 6 |
| Backend logs "Blockchain not configured — skipping chain writes" | `SEPOLIA_RPC_URL`, `SEPOLIA_PRIVATE_KEY`, or `CONTRACT_ADDRESS` missing from `.env` | Step 8 |
