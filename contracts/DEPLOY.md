# Deploying `MessageDigest.sol` to Sepolia via Remix

End-to-end instructions for taking the contract in `src/MessageDigest.sol` from
zero to a verified, working Sepolia deployment that the backend can talk to.

Total time: ~30 minutes including Etherscan verification.

---

## 0. Prerequisites

- [MetaMask](https://metamask.io) installed in your browser (I used Chrome)
- A MetaMask account with **Sepolia ETH** — get some from a faucet:
  - https://sepoliafaucet.com
  - https://www.alchemy.com/faucets/ethereum-sepolia
  - https://cloud.google.com/application/web3/faucet/ethereum/sepolia

  0.05 ETH should be enough for the entire project.
- An Etherscan account + API key (free) for source verification:
  - Register at https://etherscan.io/register
  - Generate an API key: https://etherscan.io/myapikey

## 1. Open Remix and load the contract

1. Go to https://remix.ethereum.org.
2. In the **File Explorers** panel, create a new workspace (or use the default).
3. Create a new file at `contracts/MessageDigest.sol`.
4. Paste in the contents of `contracts/src/MessageDigest.sol` from this repo.

## 2. Compile

1. Open the **Solidity Compiler** tab (the Solidity icon, left sidebar).
2. Set the compiler version to **`0.8.24`** (must match the `pragma`).
3. Leave optimisation at the Remix default: **Disabled**, EVM version
   **default (`shanghai` for 0.8.24)**. These are the settings this contract
   was actually deployed with.
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
call `recordHash`. By default only the deployer is a recorder. If the VM runs a
**separate** server wallet, you must allow-list it (steps 1–5 below). **If you
reuse the deployer key as the runtime key** (see the note in step 1), it's
already a recorder — skip steps 2–5 entirely; the only thing you need is the
private key in the VM's `.env`.

1. Generate a server wallet specifically for the VM. **Do not reuse your
   personal MetaMask wallet** — keep deploy and runtime keys separate.

   In Node:
   ```bash
   node -e "console.log(new (require('ethers')).Wallet.createRandom())"
   ```
   This prints `address`, `privateKey`, and `publicKey`. Save the private key
   to the VM's `.env` as `SEPOLIA_PRIVATE_KEY=…` and **never commit it**.

   > **Note on this deployment:** the wallet used here is a dedicated,
   > testnet-only MetaMask account with no mainnet balance or other value. An
   > EVM private key controls the same address on every chain, so the reason to
   > keep the deployer key off the VM is to limit blast radius if the box is
   > compromised. Because this key guards nothing of value (just a little
   > Sepolia ETH), we reuse the deployer key as the runtime recorder rather than
   > provisioning a separate server wallet. The separate-wallet pattern above is
   > still the right call for any wallet that holds real funds or is reused
   > elsewhere.

**Steps 2–5 apply only if you provisioned a separate server wallet in step 1.**
If you reused the deployer key, it's already funded and already a recorder —
you're done with this section.

2. Fund the server wallet with a small amount of Sepolia ETH (~0.02 ETH)
   from the faucet. The backend will spend gas every time a message is sent.

3. In Remix, under **Deployed Contracts → MessageDigest**, find the
   **setRecorder** function. Fill in:
   - `r`: the server wallet's address from step 1
   - `allowed`: `true`
4. Click **transact**, confirm in MetaMask, wait for confirmation.
5. Verify by expanding **recorders** and pasting the server wallet address —
   it should return `true`.

## 6. Save artefacts to the repo

Update `contracts/deployments/sepolia.json` with the real values:

```json
{
  "network": "sepolia",
  "chainId": 11155111,
  "address": "0xYOUR_CONTRACT_ADDRESS",
  "deployTxHash": "0xYOUR_DEPLOY_TX_HASH",
  "deployBlock": 1234567,
  "abi": [
    {
      "inputs": [],
      "stateMutability": "nonpayable",
      "type": "constructor"
    },
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "messageId",
          "type": "bytes32"
        }
      ],
      "name": "AlreadyRecorded",
      "type": "error"
    },
    {
      "inputs": [],
      "name": "NotOwner",
      "type": "error"
    },
    {
      "inputs": [],
      "name": "NotRecorder",
      "type": "error"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "bytes32",
          "name": "digest",
          "type": "bytes32"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "timestamp",
          "type": "uint256"
        },
        {
          "indexed": true,
          "internalType": "address",
          "name": "recorder",
          "type": "address"
        }
      ],
      "name": "HashRecorded",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "recorder",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "bool",
          "name": "allowed",
          "type": "bool"
        }
      ],
      "name": "RecorderUpdated",
      "type": "event"
    },
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "messageId",
          "type": "bytes32"
        }
      ],
      "name": "getRecord",
      "outputs": [
        {
          "internalType": "bytes32",
          "name": "digest",
          "type": "bytes32"
        },
        {
          "internalType": "uint256",
          "name": "timestamp",
          "type": "uint256"
        },
        {
          "internalType": "address",
          "name": "recorder",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "owner",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "digest",
          "type": "bytes32"
        },
        {
          "internalType": "bytes32",
          "name": "messageId",
          "type": "bytes32"
        }
      ],
      "name": "recordHash",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "name": "recorders",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "r",
          "type": "address"
        },
        {
          "internalType": "bool",
          "name": "allowed",
          "type": "bool"
        }
      ],
      "name": "setRecorder",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    }
  ]
}
```

## 7. Wire the backend

In `backend/.env` on the VM (NOT committed):

```bash
SEPOLIA_RPC_URL=https://ethereum-sepolia.publicnode.com
SEPOLIA_PRIVATE_KEY=0x...                 # the SERVER wallet's private key
CONTRACT_ADDRESS=0xYOUR_CONTRACT_ADDRESS
```

Restart the backend. On the first message send, you should see in the logs:

```
INFO  [blockchain]  Blockchain digest recorded for message <uuid>: 0x<txhash>
```

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
