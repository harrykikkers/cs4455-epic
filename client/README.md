# Secure Messenger — Python Client

Python desktop client for the CS4455 Epic Project secure messaging application.
Runs locally on the user's machine as a GUI application, performs all
encryption locally, and communicates with the
[backend server](../backend/README.md) over HTTPS. The server never sees
plaintext.

## Status

This README describes the **target layout** for the client. The HTTP and
session layers are the immediate focus. The crypto layer and GUI are
deliberately scaffolded but **not implemented yet** — placeholders are
called out below.

## Tech Stack

- **Runtime**: Python 3.11+
- **GUI**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) —
  modern-looking desktop UI built on top of Tkinter (ships with Python, no
  external system dependencies). See [UI layer](#ui-layer).
- **HTTP**: `requests` (sync) — see *Concurrency model* below
- **Crypto**:
  - `pyhpke` — HPKE Mode_Base (`DHKEM(X25519, HKDF-SHA256)`) for key
    encapsulation and forward secrecy
  - `cryptography` — Ed25519 signing/verification, AES-256-GCM
    authenticated encryption, HKDF-SHA256 key derivation
  - `argon2-cffi` — Argon2id password hashing (local KEK derivation for
    encrypting private keys at rest)
  - `pycryptodome` — keccak256 digest computation (blockchain anchoring)
- **Config**: `python-dotenv` for `.env` loading
- **Testing**: `pytest` + `responses` (mock HTTP)

## Client Flow

```
UI (CustomTkinter desktop app)
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
│       ├── __main__.py           # Entry point — launches GUI
│       ├── config.py             # Env config (server URL, keystore path)
│       ├── api/                  # HTTP client — one module per route group
│       │   ├── __init__.py
│       │   ├── client.py         # Base HTTP client (session, headers, errors)
│       │   ├── auth.py           # /api/auth/* wrappers
│       │   ├── messages.py       # /api/messages/* wrappers
│       │   └── keys.py           # /api/keys/* wrappers
│       ├── crypto/               # Local cryptography — all E2EE happens here
│       │   ├── __init__.py
│       │   ├── hpke.py           # HPKE Mode_Base seal / open (pyhpke)
│       │   ├── signing.py        # Ed25519 sign / verify (cryptography)
│       │   ├── aead.py           # AES-256-GCM encrypt / decrypt (cryptography)
│       │   ├── kdf.py            # HKDF-SHA256 key derivation + domain separation (cryptography)
│       │   ├── digest.py         # keccak256(plaintext) → 0x-prefixed hex (pycryptodome)
│       │   └── keystore.py       # Local private key storage + KEK + pinned peer keys
│       ├── services/             # Business logic
│       │   ├── __init__.py
│       │   ├── auth_service.py   # register, login, password change
│       │   ├── message_service.py# send / receive / forward / revoke / delete
│       │   ├── key_service.py    # publish own key, fetch + pin peer keys, reconcile history
│       │   └── chain_service.py  # fetch chain proof for a message
│       ├── models/               # Typed DTOs (dataclasses)
│       │   ├── __init__.py
│       │   ├── user.py
│       │   ├── message.py
│       │   └── key.py
│       ├── session.py            # In-memory session state (JWT, current user)
│       ├── errors.py             # Custom exception hierarchy
│       └── ui/                   # CustomTkinter GUI
│           ├── __init__.py
│           ├── app.py            # Main application window + frame manager
│           ├── login_frame.py    # Login / register screen
│           ├── inbox_frame.py    # Message list (inbox + sent tabs)
│           ├── compose_frame.py  # Compose new message
│           ├── message_frame.py  # Single message view (forward, revoke, delete, download)
│           └── widgets.py        # Shared UI components (status bar, key warning banner)
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
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows

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
| `KEYSTORE_PATH` | `~/.secure_messenger/keystore.json` | Where private keys are stored (encrypted) |
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
The UI layer catches the base `ClientError` and shows a user-friendly
message in the status bar.

### TLS Certificate Verification

The backend server uses a certificate issued by **Let's Encrypt**. The
`requests` library verifies the server's TLS certificate by default
using the system CA bundle (via `certifi`). The client enforces:

- Certificate chain validation against trusted CAs — self-signed
  certificates are rejected
- Hostname verification — the certificate's Subject Alternative Name
  must match the server URL
- Expiry checks — expired certificates are rejected
- `config.py` refuses non-`https://` values for `SERVER_URL` when the
  host is not `localhost` or `127.0.0.1`

TLS verification is never disabled in production. During local
development, `http://localhost` is permitted.

### Input Validation (client-side)

The client sanitises all user input before it reaches the API client or
crypto layer. Validation runs in the service layer so both the UI and
any future CLI can share the same checks:

- **Usernames** — alphanumeric plus hyphens/underscores, length-bounded,
  stripped of leading/trailing whitespace
- **Passwords** — minimum length enforced, no maximum (hashed
  immediately), reject null bytes
- **Message body** — reject empty input, enforce a maximum plaintext
  length before encryption, strip control characters
- **Recipient selection** — must resolve to a valid user ID from the key
  directory; the compose screen only offers known users
- **Sequence numbers** — validated as positive integers; the service
  layer manages the counter, the UI never sets it directly
- **Hex-encoded crypto fields** — length and format checks before POSTing
  (e.g. `enc`, `ciphertext`, `nonce`, `signature` must be valid hex of
  expected byte lengths)

Server-side validation is the last line of defence — the client does not
rely on it.

## Crypto Layer

All encryption and decryption runs locally in the Python process on the
user's machine. The server never sees plaintext, private keys, or shared
secrets.

### Libraries

| Library | Purpose | Why |
|---------|---------|-----|
| `pyhpke` | HPKE Mode_Base — `DHKEM(X25519, HKDF-SHA256)` | RFC 9180 compliant; provides key encapsulation with ephemeral keys for forward secrecy |
| `cryptography` | Ed25519 signing/verification, AES-256-GCM, HKDF-SHA256 | Vetted, well-maintained; covers AEAD, KDF, and signing in one library |
| `argon2-cffi` | Argon2id password hashing | Memory-hard KDF for deriving the local key-encryption key (KEK) from the user's password |
| `pycryptodome` | keccak256 digest | Computes the message digest that the server records on Sepolia |

### Cryptographic Protocol — Alice sends a message to Bob

**Step 1 — Unlock keys.**
Alice logs in. Her password derives the local KEK via HKDF, decrypting
her stored private keys. The local KEK is derived with a different salt
and info string than the server auth token. The password is never sent
to the server in plaintext.

**Step 2 — Fetch Bob's public keys.**
Alice requests Bob's X25519 and Ed25519 public keys from the server's
key directory. On first contact she pins them (Trust On First Use). An
attacker present at first contact can permanently pin their own key —
this is a known TOFU limitation stated in the design document.

**Step 3 — Generate ephemeral X25519 keypair.**
Alice generates a fresh X25519 keypair for this message only. This is
the foundation for forward secrecy — the private key will exist only
long enough to derive the shared secret. The ephemeral keypair is
generated using a CSPRNG (`os.urandom`), never any non-cryptographically
secure source.

**Step 4 — HPKE Mode_Base encapsulate.**
Alice runs HPKE encapsulation using her ephemeral secret key and Bob's
static X25519 public key. This produces a shared secret that only Bob
can recover. Mode_Base means no sender authentication at the HPKE
level — that is handled separately by Ed25519. The DH computation is
`shared_secret = X25519(eph_sk, bob_x25519_pk)`. Bob will compute the
same value as `X25519(bob_x25519_sk, eph_pk)`.

**Step 5 — HKDF derive message key + nonce.**
Alice uses HKDF to derive the AES-256-GCM encryption key from the
shared secret, with domain-separated info strings. The nonce is random,
not counter-based, because each key is used exactly once — making
collision probability negligible.

**Step 6 — AES-256-GCM encrypt with replay-protected AAD.**
Alice encrypts the plaintext client-side (never server-side). The AAD
includes a monotonic sequence number per recipient, binding message
ordering into the GCM authentication tag. The sequence number is per
(sender, recipient) and strictly increasing. Alice stores her current
counter for each recipient locally.

**Step 7 — Ed25519 sign payload.**
Alice signs the entire outgoing payload with her long-term Ed25519
signing key, proving to Bob that she authored this message. The
signature covers the sequence number — an attacker cannot forge a valid
signature with a different sequence number. The signature and GCM tag
both independently protect message ordering.

**Step 8 — Erase ephemeral private key.**
Alice securely erases the ephemeral X25519 private key and all derived
secrets from memory. After this, nobody can decrypt this message from
the wire payload. Forward secrecy is achieved at this step.

**Step 9 — Transmit and store.**
Alice sends the assembled payload over TLS to the server. The server
stores it as an opaque blob and records its keccak256 hash on-chain.
The server only ever sees ciphertext and metadata.

**Step 10 — Verify, check replay, decrypt (Bob's side).**
Bob performs five checks in sequence: (1) signature verification
(authenticity), (2) replay detection via sequence number against his
local counter (ordering), (3) HPKE decapsulation to recover the shared
secret, (4) HKDF expansion to derive the message key, and
(5) AES-256-GCM decryption (confidentiality and integrity). Only after
all five pass is the plaintext surfaced to the UI.

### Key Storage at Rest

Private keys (X25519 decapsulation key + Ed25519 signing key) are stored
in `KEYSTORE_PATH` as a JSON file, encrypted under a key-encryption key
(KEK) derived from the user's password:

```
KEK = HKDF-Expand(
    prk  = Argon2id(password, salt),
    info = "local-key-encrypt-v1",
    len  = 32
)
```

The Argon2id parameters and salt are stored alongside the encrypted keys
in the keystore file. These parameters are **separate** from the
server-side password hash — the server never sees the KEK or the salt
used to derive it.

### TOFU Key Pinning

On first contact with a peer, their public keys (X25519 + Ed25519) are
pinned locally. On each subsequent interaction:

1. Fetch the peer's current key from the server
2. Compare against the pinned key
3. If changed — fetch key history from
   `GET /api/keys/:user_id/history/:key_type`
4. If the new key is in the history (legitimate rotation) — prompt the
   user to accept and update the pin
5. If the new key is **not** in the history — display a warning banner
   (possible server-side key substitution attack)

## UI Layer

The GUI is built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter),
a modern-themed wrapper around Python's built-in Tkinter. It provides a
native desktop window without requiring any system-level dependencies
beyond Python itself — no Electron, no browser, no web server.

The application runs as a single Python process on the user's machine.
All cryptography executes in-process, so plaintext never leaves the
application boundary.

### Screens

| Screen | Purpose |
|--------|---------|
| Login / Register | Username + password entry; register creates account and generates keypairs |
| Inbox | List of received messages with sender, timestamp, and chain status |
| Sent | List of sent messages |
| Compose | Recipient picker (from key directory), plaintext input, send button |
| Message detail | Decrypted plaintext, metadata, forward / revoke / delete / download actions |
| Key warning | Banner shown when a peer's public key changes unexpectedly |

### Message Download (C++ message store)

When a user downloads a message, the Python client decrypts it locally
and hands the plaintext to the **C++ local message store** — a separate
component that manages an encrypted on-disk archive of downloaded
messages. The flow is:

1. User selects a message (owned or shared) and clicks **Download**
2. Python client fetches the ciphertext from the server, decrypts it
   locally, and writes the plaintext to a temporary file
3. The C++ message store binary is invoked to import, index, and
   encrypt the message into its local store
4. The temporary plaintext file is securely erased

The C++ component is documented separately in
[`cpp-message-store/`](../cpp-message-store/). It handles persistent
local storage, search, and export — the Python client only handles
decryption and handoff.

### Threading

CustomTkinter runs on the main thread. All network calls (API requests)
and crypto operations run on background threads via `threading.Thread` to
keep the UI responsive. Results are posted back to the main thread using
Tkinter's `after()` method. The UI shows a loading indicator during
network calls.

## Concurrency Model

HTTP calls are synchronous (`requests`). The GUI dispatches network and
crypto work to background threads so the main thread stays responsive.
The service layer is thread-safe — each call is independent and does not
share mutable state beyond the `Session` (which is protected by a lock).

## Blockchain Verification

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
a message given the plaintext and transaction hash.

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
- **Erase sensitive memory** — ephemeral keys and derived secrets must be
  overwritten after use. Python's garbage collector does not guarantee
  immediate erasure, so use `ctypes.memset` or `bytearray` zeroing
  where possible.