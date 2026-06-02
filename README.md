# Zebra — Secure Messenger

End-to-end encrypted messaging for the CS4455 Epic Project. Messages are
encrypted on the sender's machine and only ever reach the server as opaque
ciphertext; a keccak256 digest of each message is anchored on the Ethereum
Sepolia testnet so its integrity can be verified independently of the app.

## Architecture

```
┌──────────────────────┐   HTTPS (TLS 1.2/3)   ┌──────────────────────┐
│  Python desktop client│ ───────────────────▶ │  provider gateway     │
│  (all crypto, local)  │                        │  terminates TLS (:443)│
└──────────┬───────────┘                        └──────────┬───────────┘
           │                                      HTTP :80  │
           │ decrypted plaintext                            ▼
           ▼                                     ┌──────────────────────┐
┌──────────────────────┐                         │  nginx reverse proxy  │
│  C++ message-store    │                         │  (VM, port 80)        │
│  (encrypted archive)  │                         └──────────┬───────────┘
└──────────────────────┘                          loopback   │ :3000
                                                              ▼
                                                 ┌──────────────────────┐
                                                 │  Node/Express backend │
                                                 │  + MySQL (ciphertext) │
                                                 └──────────┬───────────┘
                                                            │ keccak256 digest
                                                            ▼
┌──────────────────────┐   plaintext + txHash    ┌──────────────────────┐
│  verify.html          │ ◀───────────────────── │  Sepolia: MessageDigest│
│  (standalone, no app) │                         │  contract             │
└──────────────────────┘                         └──────────────────────┘
```

The server never sees plaintext, private keys, or the user's cleartext
password. TLS is terminated at the hosting provider's gateway, which forwards
plain HTTP to nginx on the VM (port 80); the public network surface is the
gateway, and Node and MySQL live behind nginx on loopback.

## Components

| Component | Path | What it does |
|-----------|------|--------------|
| **Python client** | [`client/`](client/README.md) | CustomTkinter desktop app. All E2EE happens here: static ECDH + HKDF + AES-256-GCM + Ed25519. |
| **Backend server** | [`backend/README.md`](backend/README.md) | Node/Express + MySQL. Stores ciphertext, manages auth (JWT, Argon2id) and the public-key directory, anchors digests on-chain. |
| **C++ message store** | [`message-store/`](message-store/README.md) | AES-256-GCM encrypted on-disk archive of downloaded messages, driven by a small CLI. |
| **Smart contract** | [`contracts/`](contracts/DEPLOY.md) | `MessageDigest.sol`, deployed to Sepolia. Records and timestamps message digests. |
| **Verification page** | [`verification/`](verification/verify.html) | Standalone `verify.html` — anyone can confirm a message was anchored, given the plaintext and tx hash. No app or backend required. |
| **Deployment** | [`deploy/nginx/`](deploy/nginx/README.md) | nginx reverse proxy on the VM (HTTP, port 80); TLS is terminated upstream at the hosting provider's gateway. |

## Security model

- **End-to-end encryption.** The client derives a per-pair message key via
  static ECDH (X25519) + HKDF-SHA256 and encrypts with AES-256-GCM. Every
  message is signed with Ed25519. The server stores only ciphertext.
- **No cleartext password on the wire.** The client sends an Argon2id pre-hash;
  the server re-hashes it with its own per-user random salt, so a database leak
  is not directly replayable.
- **Key pinning (TOFU).** Peer keys are pinned on first contact and reconciled
  against an append-only server-side key history to detect substitution.
- **On-chain integrity anchoring.** Each message's keccak256 digest is recorded
  on Sepolia and is verifiable from plaintext alone.
- **Network trust boundary.** TLS terminates at the provider gateway, which
  forwards HTTP to nginx on the VM's port 80; Node (:3000) and MySQL (:3306)
  are loopback-only.

See each component's README for details — the crypto protocol is documented
step by step in [`client/README.md`](client/README.md#crypto-layer).

## Quick start

Each component runs independently; full setup lives in the linked READMEs.

A backend is deployed at **`https://zebra.theburkenator.com`**, and the
client's [`.env.example`](client/.env.example) points at it by default — so to
just use the app you only need the client below. Running your own backend is
optional.

```bash
# Client (Python desktop app)
cd client && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # or: pip install -e ".[dev]"
cp .env.example .env                    # talk to the hosted backend
python src/__main__.py

# Backend (Node + MySQL) — only if self-hosting
cd backend && npm install && npm run db:init && npm run dev

# C++ message store
cd message-store && cmake -B build && cmake --build build
```

The verification page needs no build — open
[`verification/verify.html`](verification/verify.html) in any browser.

## Deployed contract

`MessageDigest` is live on **Sepolia** at
[`0x0a66b77EC17A9b36D2A8a036eC080e2ff83A9328`](https://sepolia.etherscan.io/address/0x0a66b77EC17A9b36D2A8a036eC080e2ff83A9328).
Address and ABI are in [`contracts/deployments/sepolia.json`](contracts/deployments/sepolia.json).
