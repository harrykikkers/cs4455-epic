# Zebra — Secure Messenger

End-to-end encrypted messaging for the CS4455 Epic Project. Messages are
encrypted on the sender's machine and only ever reach the server as opaque
ciphertext; a keccak256 digest of each message is anchored on the Ethereum
Sepolia testnet so its integrity can be verified independently of the app.

## Architecture

```
┌──────────────────────┐         HTTPS          ┌──────────────────────┐
│  Python desktop client│ ───────────────────▶ │  nginx (TLS, :443)    │
│  (all crypto, local)  │                        │  reverse proxy        │
└──────────┬───────────┘                        └──────────┬───────────┘
           │                                                │ loopback :3000
           │ decrypted plaintext                            ▼
           ▼                                     ┌──────────────────────┐
┌──────────────────────┐                         │  Node/Express backend │
│  C++ message-store    │                         │  + MySQL (ciphertext) │
│  (encrypted archive)  │                         └──────────┬───────────┘
└──────────────────────┘                                     │ keccak256 digest
                                                              ▼
┌──────────────────────┐   plaintext + txHash    ┌──────────────────────┐
│  verify.html          │ ◀───────────────────── │  Sepolia: MessageDigest│
│  (standalone, no app) │                         │  contract             │
└──────────────────────┘                         └──────────────────────┘
```

The server never sees plaintext, private keys, or the user's cleartext
password. The only public network surface is nginx; Node and MySQL live behind
it on loopback.

## Components

| Component | Path | What it does |
|-----------|------|--------------|
| **Python client** | [`client/`](client/README.md) | CustomTkinter desktop app. All E2EE happens here: static ECDH + HKDF + AES-256-GCM + Ed25519. |
| **Backend server** | [`backend/README.md`](backend/README.md) | Node/Express + MySQL. Stores ciphertext, manages auth (JWT, Argon2id) and the public-key directory, anchors digests on-chain. |
| **C++ message store** | [`message-store/`](message-store/README.md) | AES-256-GCM encrypted on-disk archive of downloaded messages, driven by a small CLI. |
| **Smart contract** | [`contracts/`](contracts/DEPLOY.md) | `MessageDigest.sol`, deployed to Sepolia. Records and timestamps message digests. |
| **Verification page** | [`verification/`](verification/README.md) | Standalone `verify.html` — anyone can confirm a message was anchored, given the plaintext and tx hash. No app or backend required. |
| **Deployment** | [`deploy/nginx/`](deploy/nginx/README.md) | nginx TLS-terminating reverse proxy with auto-renewing Let's Encrypt certs. |

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
- **Network trust boundary.** Only nginx :80/:443 are exposed; Node (:3000) and
  MySQL (:3306) are loopback-only.

See each component's README for details — the crypto protocol is documented
step by step in [`client/README.md`](client/README.md#crypto-layer).

## Quick start

Each component runs independently; full setup lives in the linked READMEs.

```bash
# Backend (Node + MySQL)
cd backend && npm install && npm run db:init && npm run dev

# Client (Python desktop app)
cd client && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && python src/__main__.py

# C++ message store
cd message-store && cmake -B build && cmake --build build
```

The verification page needs no build — open
[`verification/verify.html`](verification/verify.html) in any browser.

## Deployed contract

`MessageDigest` is live on **Sepolia** at
[`0x230Ce7b063DCFE8fd79e3f07B3403b59a6750b8f`](https://sepolia.etherscan.io/address/0x230Ce7b063DCFE8fd79e3f07B3403b59a6750b8f).
Address and ABI are in [`contracts/deployments/sepolia.json`](contracts/deployments/sepolia.json).
