# Secure Messenger — Python Client

Python client for the CS4455 Epic Project secure messaging application.
Talks to the [backend server](../backend/README.md) over HTTPS, performs
all encryption locally, and computes the keccak256 digest that the server
records on Sepolia. The server never sees plaintext.

## Status

This README describes the **target layout** for the client. The HTTP and
session layers are the immediate focus. The crypto layer and GUI are
deliberately scaffolded but **not implemented yet** — placeholders are
called out below.

## Tech Stack

- **Runtime**: Python 3.11+
- **HTTP**: `requests` (sync) — see *Concurrency model* below
- **Crypto**: *TBD* — must implement HPKE (encryption), Ed25519 (signatures),
  and keccak256 (digest). See [Crypto layer](#crypto-layer).
- **GUI**: *TBD* — see [UI layer](#ui-layer).
- **Config**: `python-dotenv` for `.env` loading
- **Testing**: `pytest` + `responses` (mock HTTP)

## Client Flow

```
UI (GUI / CLI)
    ↓
Session (login state, JWT, current user)
    ↓
Services           (compose API + crypto + local state)
    ↓     ↘
API client     Crypto             (HPKE / Ed25519 / keccak)
    ↓              ↓
HTTPS → server   Local keystore (private keys, pinned peer keys)
```

Each layer has a single responsibility:

- **API client** — thin wrappers around HTTP endpoints. Knows about URLs,
  headers, status codes. Returns typed DTOs. No business logic.
- **Crypto** — pure functions over bytes. No network, no I/O beyond the
  keystore. Easy to unit-test.
- **Services** — orchestrate the two. E.g. *send_message* = encrypt with
  crypto → POST via API → update local state.
- **Session** — holds the JWT and current user info between calls.
- **UI** — pure presentation. Calls services, never the API client
  directly.

## Project Structure

```
client/
├── src/
│   └── secure_messenger_client/
│       ├── __init__.py
│       ├── __main__.py           # Entry point — launches UI
│       ├── config.py             # Env config (server URL, keystore path)
│       ├── api/                  # HTTP client — one module per route group
│       │   ├── __init__.py
│       │   ├── client.py         # Base HTTP client (session, headers, errors)
│       │   ├── auth.py           # /api/auth/* wrappers
│       │   ├── messages.py       # /api/messages/* wrappers
│       │   └── keys.py           # /api/keys/* wrappers
│       ├── crypto/               # TBD — see "Crypto layer" below
│       │   ├── __init__.py
│       │   ├── hpke.py           # HPKE seal / open (recipient pubkey ↔ enc, ciphertext, nonce)
│       │   ├── signing.py        # Ed25519 sign / verify
│       │   ├── digest.py         # keccak256(plaintext) → 32-byte hex
│       │   └── keystore.py       # Local private key + pinned peer key storage
│       ├── services/             # Business logic
│       │   ├── __init__.py
│       │   ├── auth_service.py   # register, login, password change
│       │   ├── message_service.py# send / receive / forward / revoke / delete
│       │   ├── key_service.py    # publish own key, fetch + pin peer keys, reconcile history
│       │   └── chain_service.py  # fetch chain proof for a message
│       ├── models/               # Typed DTOs (dataclasses or pydantic)
│       │   ├── __init__.py
│       │   ├── user.py
│       │   ├── message.py
│       │   └── key.py
│       ├── session.py            # In-memory session state (JWT, current user)
│       ├── errors.py             # Custom exception hierarchy
│       └── ui/                   # TBD — see "UI layer" below
│           └── __init__.py
├── tests/                        # pytest tests, mocked HTTP
├── .env.example                  # SERVER_URL, KEYSTORE_PATH, etc.
├── .gitignore
├── pyproject.toml
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- A running [backend server](../backend/README.md) (default `http://localhost:3000`)
- A `.env` file (copy from `.env.example`)

### Install and Run

```bash
# From the client/ directory
python -m venv .venv
source .venv/bin/activate

# Install in editable mode so `import secure_messenger_client` works while you develop
pip install -e .

# Copy and edit environment config
cp .env.example .env
# Edit .env — set SERVER_URL to your backend, KEYSTORE_PATH for local keys

# Launch the client
python -m secure_messenger_client
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVER_URL` | `http://localhost:3000` | Backend base URL |
| `KEYSTORE_PATH` | `~/.secure_messenger/keystore.json` | Where private keys are stored |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Server Interaction

The API client exposes one Python method per server endpoint. Methods take
plain Python values and return typed DTOs; all HTTP details (URL, headers,
JSON encoding, status code → exception mapping) are hidden.

| Server endpoint | Client method | Notes |
|-----------------|---------------|-------|
| `POST /api/auth/register` | `AuthAPI.register(username, password)` | Returns `{ user_id }` |
| `POST /api/auth/login` | `AuthAPI.login(username, password)` | Stores JWT in `Session` |
| `PUT /api/auth/password` | `AuthAPI.change_password(current, new)` | Requires session |
| `GET /api/auth/me` | `AuthAPI.me()` | Current user info |
| `POST /api/messages` | `MessageAPI.send(recipient_id, enc, ciphertext, nonce, signature, seq_no, digest)` | All crypto fields built by the crypto layer |
| `GET /api/messages/inbox` | `MessageAPI.inbox()` | List of received messages |
| `GET /api/messages/sent` | `MessageAPI.sent()` | List of sent messages |
| `GET /api/messages/:id` | `MessageAPI.get(message_id)` | Single message |
| `GET /api/messages/:id/chain` | `MessageAPI.chain(message_id)` | `{ digest_hash, chain_status, tx_hash, recorded_at }` |
| `POST /api/messages/:id/forward` | `MessageAPI.forward(message_id, recipient_id, enc, ciphertext, nonce)` | Re-encrypted under new recipient |
| `POST /api/messages/:id/revoke` | `MessageAPI.revoke(message_id)` | Revoke shared access |
| `DELETE /api/messages/:id` | `MessageAPI.delete(message_id)` | Soft delete |
| `POST /api/keys` | `KeyAPI.publish(public_key, key_type, acknowledge_rotation=False)` | Publish own public key |
| `GET /api/keys` | `KeyAPI.list_all()` | Directory of all users' keys |
| `GET /api/keys/:user_id` | `KeyAPI.get(user_id)` | Single user's current key |
| `GET /api/keys/:user_id/history/:key_type` | `KeyAPI.history(user_id, key_type)` | Append-only rotation log — reconcile against pinned keys |
| `GET /api/health` | `HealthAPI.check()` | Liveness probe |

### Error handling

The base HTTP client maps server status codes to exceptions:

| Status | Exception | When |
|--------|-----------|------|
| 400 | `ValidationError` | Malformed request / failed input validation |
| 401 | `AuthenticationError` | Missing / invalid / expired JWT |
| 403 | `AuthorizationError` | Authenticated but not allowed |
| 404 | `NotFoundError` | Resource doesn't exist |
| 409 | `ConflictError` | Username taken, duplicate seq_no, etc. |
| 429 | `RateLimitError` | Hit rate limit on auth endpoints |
| 5xx | `ServerError` | Backend failure |

Network failures (timeout, DNS, refused connection) raise `NetworkError`.
The UI layer should catch the base `ClientError` and show a friendly
message.

## Crypto layer

> **Not implemented yet.** This section is the contract the crypto layer
> must satisfy once libraries are chosen.

The server expects these fields for `POST /api/messages`:

| Field | Type | Built by |
|-------|------|---------|
| `enc` | hex string | HPKE encapsulation under recipient's public key |
| `ciphertext` | hex string | HPKE seal output over the plaintext |
| `nonce` | hex string (12 bytes) | HPKE-derived |
| `signature` | hex string | Ed25519 signature over `(ciphertext ‖ nonce ‖ seq_no ‖ recipient_id)` using the sender's signing key |
| `seq_no` | integer | Monotonically increasing per (sender, recipient) — stored locally |
| `digest` | hex string (`0x` + 64 hex) | `keccak256(plaintext)` — must be computed *before* encryption |

The crypto layer must:

1. Generate two key pairs per user — one HPKE (encryption) and one
   Ed25519 (signing). Both get published via `POST /api/keys` with
   distinct `key_type` values.
2. Store private keys in the local keystore (encrypted with the user's
   password? — design decision pending).
3. **Pin** peer public keys on first use. On each subsequent send/receive,
   reconcile the pinned key against
   `GET /api/keys/:user_id/history/:key_type`. If the server returns a key
   not present in the history, that's evidence of server-side substitution
   — surface it to the UI.
4. For receive: open the HPKE envelope, verify the Ed25519 signature, and
   only then surface the plaintext.

Library choice is open — likely candidates are `pyhpke` for HPKE,
`cryptography` for Ed25519, and `eth-hash` or `pycryptodome` for keccak256.
None are wired up yet.

## UI layer

> **Not implemented yet.** Framework choice deferred.

The UI should depend only on the `services/` layer — never on `api/` or
`crypto/` directly — so that it can be swapped out (CLI for tests, GUI for
demos) without touching business logic.

## Concurrency model

HTTP calls are synchronous (`requests`). When a UI is added, network calls
must run on a background thread so the UI stays responsive — the exact
mechanism depends on the GUI framework chosen. Until then, the API and
service layers are safe to call directly from `__main__.py` or tests.

## Blockchain verification

The client does **not** read from Sepolia directly. To verify a message
is anchored on-chain:

1. Compute `keccak256(plaintext)` locally (the crypto layer's `digest`
   function — same one used when sending).
2. Call `MessageAPI.chain(message_id)` → returns `tx_hash`.
3. Hand `tx_hash` and `plaintext` to the standalone verification page (in
   [`verification/`](../verification/)) which fetches the on-chain
   `HashRecorded` event and compares digests.

The verification page is intentionally separate from this client — per
the assignment brief, anyone (not just the sender/recipient) can verify
a message given the plaintext and tx hash.

## Security Notes (client-side responsibilities)

- **Encrypt before send** — the API client must never accept plaintext on
  the `ciphertext` field. Enforce with a type boundary if possible.
- **Compute digest from plaintext, not ciphertext** — the on-chain record
  is meaningless otherwise.
- **Verify signatures before showing plaintext** — an unverified message
  is an attacker-controlled blob.
- **Pin peer keys** — TOFU + reconciliation against the server's key
  history is the only defence against the server lying about who owns
  which key.
- **Never log secrets** — keystore contents, JWTs, plaintext messages.
  Use a logging filter to scrub these.
- **Validate `SERVER_URL` uses HTTPS in production** — config layer should
  refuse `http://` for non-localhost hosts.
