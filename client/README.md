# Secure Messenger — Python Client

Python desktop client for the CS4455 Epic Project secure messaging application.
Runs locally on the user's machine as a GUI application, performs all
encryption locally, and communicates with the
[backend server](../backend/README.md) over HTTPS. The server never sees
plaintext.

## Status

This client is **implemented and working end-to-end**. The `crypto`,
`services`, and `api` layers are built; registration, login, key publishing,
and encrypted messaging all run the real pipeline. The message path performs
genuine **static ECDH + HKDF + AES-256-GCM + Ed25519** encryption (see
[Crypto Layer](#crypto-layer)) — verified by sending a message between two
users and confirming the server stores only opaque ciphertext.

The auth and messaging flows go through the service layer: the login/register
frames call `AuthService`, and the chat panel drives `MessageService` /
`KeyService` for send, receive, and forward. The remaining read/state
operations in `main_frame` (inbox/sent listing, delete, key lookups, password
change) still issue HTTP requests directly — a pending tidy-up, not a
correctness gap, since none of them touch plaintext or private keys.

## Tech Stack

- **Runtime**: Python 3.11+
- **GUI**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) —
  modern-looking desktop UI built on top of Tkinter (ships with Python, no
  external system dependencies). See [UI layer](#ui-layer).
- **HTTP**: `requests` (sync) — see *Concurrency model* below
- **Crypto**:
  - `cryptography` — X25519 (static ECDH key agreement), Ed25519
    signing/verification, AES-256-GCM authenticated encryption, HKDF-SHA256
    key derivation
  - `argon2-cffi` — Argon2id password hashing (local KEK derivation for
    encrypting private keys at rest)
  - `pycryptodome` — keccak256 digest computation (blockchain anchoring)
- **Config**: `python-dotenv` for `.env` loading
- **Testing**: `pytest`. The current suite is integration tests that exercise
  a running backend; `responses` is available (the `dev` extra) for future
  mocked unit tests.

## Client Flow

```
UI (CustomTkinter desktop app)
    ↓
Session (login state, JWT, current user)
    ↓
Services           (compose API + crypto + local state)
    ↓     ↘
API client     Crypto             (static ECDH / Ed25519 / keccak)
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
├── src/                          # flat layout — modules below are top-level
│   ├── __main__.py               # Entry point — launches the GUI
│   ├── config.py                 # Env config (server URL, keystore path)
│   ├── session.py                # In-memory session state (JWT, current user)
│   ├── errors.py                 # Custom exception hierarchy
│   ├── api/                      # HTTP client — one module per route group
│   │   ├── __init__.py
│   │   ├── client.py             # Base HTTP client (session, headers, errors)
│   │   ├── auth.py               # /api/auth/* wrappers
│   │   ├── messages.py           # /api/messages/* wrappers
│   │   └── keys.py               # /api/keys/* wrappers
│   ├── crypto/                   # Local cryptography — all E2EE happens here
│   │   ├── __init__.py
│   │   ├── messaging.py          # seal / open: static ECDH + HKDF + AES-GCM + Ed25519
│   │   ├── signing.py            # Ed25519 sign / verify (cryptography)
│   │   ├── aead.py               # AES-256-GCM encrypt / decrypt (cryptography)
│   │   ├── kdf.py                # HKDF-SHA256 message key + Argon2id KEK derivation
│   │   ├── digest.py             # keccak256(plaintext) → 0x-prefixed hex (pycryptodome)
│   │   └── keystore.py           # Local private key storage + KEK + pinned peer keys
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py       # register, login, password change
│   │   ├── message_service.py    # send / receive / forward / revoke / delete
│   │   ├── key_service.py        # publish own key, fetch + pin peer keys, reconcile history
│   │   └── chain_service.py      # fetch chain proof for a message
│   └── ui/                       # CustomTkinter GUI
│       ├── __init__.py
│       ├── app.py                # Main application window + frame manager
│       ├── login_frame.py        # Login screen
│       ├── register_frame.py     # Register screen
│       ├── main_frame.py         # Chat UI: sidebar + thread + compose (monolith — see note)
│       ├── inbox_frame.py        # (planned) message list, to be split out of main_frame
│       ├── compose_frame.py      # (planned) compose, to be split out of main_frame
│       ├── message_frame.py      # (planned) single-message view, to be split out of main_frame
│       └── widgets.py            # (planned) shared UI components (status bar, key warning banner)
├── tests/                        # pytest tests (integration — need a running backend)
├── .env.example                  # SERVER_URL, KEYSTORE_PATH, etc.
├── .gitignore
├── pyproject.toml
└── README.md
```

This is a **flat layout**: the modules under `src/` are top-level (`config`,
`api`, `ui`, …) rather than nested under a single package, so there is no
`secure_messenger_client` import name and no `python -m` entry point — run
the app via the script path shown in [Setup](#setup). The chat UI currently
lives entirely in `ui/main_frame.py`; `inbox_frame`/`compose_frame`/
`message_frame`/`widgets` are stubs for the planned decomposition.

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

# Install dependencies (editable). The [dev] extra adds pytest + responses.
pip install -e ".[dev]"

# Copy and edit environment config
cp .env.example .env
# Edit .env — set SERVER_URL to your backend, KEYSTORE_PATH for local keys

# Launch the client (flat layout — run the entry script under src/)
python src/__main__.py
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVER_URL` | `http://localhost:3000` | Backend base URL |
| `KEYSTORE_PATH` | `~/.secure_messenger/keystore.json` | Where private keys are stored (encrypted) |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python logging level |

### Running tests

```bash
# from the client/ directory, with the venv active and `pip install -e ".[dev]"` done
pytest
```

`pyproject.toml` puts `src/` and `tests/` on the path, so no manual
`PYTHONPATH` is needed. The current suite is **integration tests** — they
register users, send messages, etc. against a live backend, so a server must
be running at `SERVER_URL` (default `http://localhost:3000`). With no backend
up the tests fail fast with `ConnectionError`.

## Server Interaction

The API client exposes one Python method per server endpoint. Methods take
plain Python values and return typed DTOs; all HTTP details (URL, headers,
JSON encoding, status code → exception mapping) are hidden.

| Server endpoint | Client method | Notes |
|-----------------|---------------|-------|
| `POST /api/auth/register` | `AuthAPI.register(username, password)` | Returns `{ user_id }` |
| `POST /api/auth/login` | `AuthAPI.login(username, password)` | Stores JWT in `Session` |
| `PUT /api/auth/password` | `AuthAPI.change_password(current, new)` | Requires session |
| `GET /api/auth/user` | `AuthAPI.get_user(username)` | Resolve a recipient username → user id (New Chat / Forward) |
| `POST /api/messages` | `MessageAPI.send(recipient_id, ciphertext, nonce, signature, seq_no, digest)` | All crypto fields built by the crypto layer |
| `GET /api/messages/inbox` | `MessageAPI.inbox()` | List of received messages |
| `GET /api/messages/sent` | `MessageAPI.sent()` | List of sent messages |
| `GET /api/messages/:id/chain` | `MessageAPI.chain(message_id)` | `{ digest_hash, chain_status, tx_hash, recorded_at }` |
| `POST /api/messages/:id/forward` | `MessageAPI.forward(message_id, recipient_id, ciphertext, nonce, signature, seq_no, digest)` | Re-sealed under new recipient (same envelope as a direct send) |
| `POST /api/messages/:id/revoke` | `MessageAPI.revoke(message_id)` | Revoke shared access |
| `DELETE /api/messages/:id` | `MessageAPI.delete(message_id)` | Soft delete |
| `POST /api/keys` | `KeyAPI.publish(public_key, key_type, acknowledge_rotation=False)` | Publish own public key |
| `GET /api/keys/:user_id` | `KeyAPI.get(user_id)` | Single user's current key |
| `GET /api/keys/:user_id/history/:key_type` | `KeyAPI.history(user_id, key_type)` | Append-only rotation log — reconcile against pinned keys |

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
- **Encoded crypto fields** — length and format checks before POSTing
  (`ciphertext`, `nonce`, `signature` are base64; `digest` is `0x` + 64 hex),
  each validated against its expected byte length

Server-side validation is the last line of defence — the client does not
rely on it.

## Crypto Layer

All encryption and decryption runs locally in the Python process on the
user's machine. The server never sees plaintext, private keys, or shared
secrets.

### Libraries

| Library | Purpose | Why |
|---------|---------|-----|
| `cryptography` | X25519 (static ECDH), Ed25519 signing/verification, AES-256-GCM, HKDF-SHA256 | Vetted, well-maintained; covers key agreement, AEAD, KDF, and signing in one library |
| `argon2-cffi` | Argon2id password hashing | Memory-hard KDF for deriving the local key-encryption key (KEK) from the user's password |
| `pycryptodome` | keccak256 digest | Computes the message digest that the server records on Sepolia |

### Cryptographic Protocol — Alice sends a message to Bob

**Step 1 — Unlock keys.**
Alice logs in. Her password is used two independent, domain-separated ways:
it derives the local KEK via HKDF (decrypting her stored private keys) and —
separately — the [authentication credential](#authentication-credential) sent
to the server. Both come from `crypto/kdf.py` with different salts and `info`
strings; the cleartext password is never sent to the server.

**Step 2 — Fetch Bob's public keys.**
Alice requests Bob's X25519 and Ed25519 public keys from the server's
key directory. On first contact she pins them (Trust On First Use). An
attacker present at first contact can permanently pin their own key —
this is a known TOFU limitation stated in the design document.

**Step 3 — Derive the shared secret (static ECDH).**
Alice computes `dh_out = X25519(alice_x25519_sk, bob_x25519_pk)` using her
own long-term X25519 private key and Bob's pinned static X25519 public key.
Bob recovers the identical value as `X25519(bob_x25519_sk, alice_x25519_pk)`.
No per-message public key is sent on the wire — the recipient already holds
the sender's pinned key, so static ECDH needs nothing extra. This is a
**static** key agreement: the same shared secret is derived for every
Alice→Bob message.

> **Forward-secrecy tradeoff.** Because the key agreement is static (no
> ephemeral keypair), this design does **not** provide forward secrecy — a
> future compromise of either party's long-term X25519 key would expose past
> messages. This is a deliberate simplification; see the design document.

**Step 4 — HKDF derive the message key.**
Alice derives the AES-256-GCM key with `HKDF-SHA256(dh_out, info="zebra-msg-v1")`,
domain-separated from the keystore KEK (`"local-key-encrypt-v1"`) and the auth
credential (`"server-auth-v1"`) so the same material can never collide across
purposes. The message key is **static per (sender, recipient) pair**, so AES-GCM
confidentiality rests entirely on never reusing a (key, nonce) pair — a repeat
would be catastrophic (Step 5).

**Step 5 — AES-256-GCM encrypt with replay-protected AAD.**
Alice encrypts the plaintext client-side (never server-side) under a random
12-byte (96-bit) nonce drawn from the OS CSPRNG. Because the key is static, the
nonce is *not* "used once" in a counter sense; safety comes from the random
96-bit space being large enough that a collision is improbable across the
realistic message volume of a single (sender, recipient) pair (the birthday
bound puts a meaningful reuse risk only after ~2³² messages). The AAD is `sender_id ‖ recipient_id ‖ seq_no`,
binding message ordering into the GCM authentication tag. The sequence number is
per (sender, recipient) and strictly increasing; Alice persists her counter for
each recipient locally.

**Step 6 — Ed25519 sign.**
Alice signs `sender_id ‖ recipient_id ‖ seq_no ‖ ciphertext ‖ nonce` with her
long-term Ed25519 signing key, proving she authored this message. The signature
covers the sequence number, so an attacker cannot forge a valid signature with a
different `seq_no` — the signature and the GCM tag both independently protect
ordering.

**Step 7 — Transmit and store.**
Alice sends the assembled payload (ciphertext, nonce, signature, seqNo, digest)
over TLS to the server. The server stores it as an opaque blob and records its
keccak256 digest on-chain. The server only ever sees ciphertext and metadata.

**Step 8 — Verify, check replay, decrypt (Bob's side).**
Bob performs four checks **in order**: (1) Ed25519 signature verification against
Alice's pinned key (authenticity), (2) replay detection — `seq_no` must be
strictly greater than the last accepted counter for Alice (ordering), (3) static
ECDH + HKDF to recover the message key, and (4) AES-256-GCM decryption with the
reconstructed AAD (confidentiality + integrity; a bad tag raises before any
plaintext exists). Only after all four pass is the plaintext surfaced to the UI.

### Key Storage at Rest

Private keys (X25519 key-agreement key + Ed25519 signing key) are stored
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

### Authentication Credential

The cleartext password never leaves the device — not even to the server.
On register and login the client derives a password *pre-hash* and sends
that as the `password` field instead:

```
auth_hash = HKDF-Expand(
    prk  = Argon2id(password, salt),    # salt = SHA256("server-auth-salt-v1|" + username)[:16]
    info = "server-auth-v1",
    len  = 32
)                                       # sent hex-encoded → 64 chars
```

The salt is derived **deterministically from the (normalised) username** so
every login reproduces the same pre-hash. Per-user *random* salting happens
server-side: the server treats `auth_hash` as the credential and re-hashes it
with Argon2id under its own random salt before storing it, so a leaked
`password_hash` is not directly replayable (see the backend's
[Authentication](../backend/README.md#authentication) section).

This derivation is **domain-separated** from the local KEK above — a
different salt *and* a different HKDF `info` string ensure the value sent to
the server can never coincide with the key that encrypts the private keys at
rest. Password strength (min 12 chars) is checked client-side before hashing;
the server only ever sees a uniform 64-hex credential.

Implemented in `crypto/kdf.py` as `derive_auth_hash(password, username)` and
used by `services/auth_service.py` (and the login/register UI frames). The
pre-hash hides the plaintext from the server — it does **not** replace TLS,
since the pre-hash is itself a password-equivalent in transit.

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

The client is a single resizable window (titled **Zebra — Secure Messenger**)
that swaps between three full-window frames — **Login**, **Register**, and
**Main** — managed by `app.py`. The Main frame opens additional modal dialogs
for details, settings, and prompts.

| Frame / dialog | Purpose |
|----------------|---------|
| **Login** | Username + password entry, "Login" and "Create Account" buttons, inline error message. A built-in dev login (`test` / `test1234`) bypasses the backend and loads demo data. |
| **Register** | Username, password (min 12 chars) and confirmation, with client-side validation and an animated progress indicator while the account is created. |
| **Main — sidebar** | App header with the logged-in username, **+ New Chat**, a search box that filters chats, the scrollable conversation list (peer name, last-message preview, timestamp, and a **KEY CHANGED** badge when relevant), and **Account** / **Logout** buttons. |
| **Main — chat panel** | Header with the active peer's name and a **Refresh** button, an optional key-change warning banner, the scrollable message thread, and a bottom input bar (text entry + **Send**). |
| **Message bubble** | Sent messages align right, received left; undecrypted messages show an "Encrypted message" placeholder. A **⋯** toggle reveals per-message actions: **Details**, **Forward**, **Download**, and (for your own messages) **Delete**. |
| **Message Details dialog** | Sender, date, message ID, chain status (click to view the blockchain proof), the message body, and a **Forwarded To** list with a **Revoke** button per recipient. |
| **Key Change dialog** | Explains a peer's key change and offers **Accept New Key**, **View History**, or **Reject**. |
| **Account Settings dialog** | Shows username and user ID and provides a change-password form (current + new + confirm, min 12 chars). |
| **Prompts** | Lightweight input dialogs for **New Chat** and **Forward** (recipient username), plus a **Blockchain Proof** info dialog. |

### User Flows

- **Register → Login.** From Login, **Create Account** opens the Register
  frame. Once the client-side checks pass (username + password present,
  password ≥ 12 chars, confirmation matches), the client posts to the
  backend and, on success, returns to Login to sign in.
- **Browse and open a conversation.** After login the Main frame loads the
  inbox and sent messages and groups them by peer into the sidebar. Clicking
  a conversation opens its thread in the chat panel; **Refresh** reloads from
  the server. The search box filters the list by peer name.
- **Start a new chat.** **+ New Chat** prompts for a username, resolves it to
  a user via the backend, and opens an empty thread (dev mode creates the
  conversation locally).
- **Send a message.** Type in the input bar and press **Send** or Enter. The
  message appears in the thread; in live mode it is posted to the backend and
  the thread reloads.
- **Message actions.** A bubble's **⋯** menu opens **Details**, **Forward**,
  **Download**, and **Delete** (own messages only). **Download** archives the
  decrypted message into the C++ encrypted local store (see
  [Message Download](#message-download-c-message-store)); **Delete** asks for
  confirmation first.
- **Forward & revoke.** **Forward** prompts for a recipient username and
  re-sends the message to them. In **Details**, each recipient the message
  was forwarded to can have their access **Revoke**d (with confirmation).
- **Key-change warning.** When a peer's key has changed, a warning banner
  appears above the thread and a **KEY CHANGED** badge shows on their
  conversation row. Opening the Key Change dialog lets the user accept,
  inspect history, or reject the new key.
- **Account & logout.** **Account** opens settings with the username, user
  ID, and change-password form. **Logout** clears the session and returns to
  the Login screen.

### Message Download (C++ message store)

The **Download** action archives a decrypted message into the **C++ local
message store** — a separate component that manages an encrypted on-disk
archive of downloaded messages. Plaintext is decrypted locally and handed to
the C++ binary; it is never written to disk in the clear and never passed on
the command line. The flow is:

1. User selects a message (owned or shared) and clicks **Download**.
2. The Python client uses the locally decrypted plaintext (the message must
   already be decrypted — otherwise Download reports it cannot proceed).
3. The client derives a 32-byte **archive key** from the keystore KEK
   (`HKDF-Expand(SHA256, info="zebra-msgarchive-v1")`, domain-separated from
   the KEK and the message cache) and passes it to the binary **only** via the
   `MESSAGE_STORE_KEY` environment variable as 64 lowercase hex chars.
4. The plaintext is piped to the binary on **stdin** (never argv). The binary
   is invoked as:

   ```
   message-store add --archive <keystore>.archive \
       --id <messageId> --sender <sender> --created <iso8601>
   ```

5. The C++ store encrypts the message with **AES-256-GCM** under the archive
   key and appends it to its archive at `<keystore>.archive` (a sibling of the
   keystore). A non-zero exit surfaces the binary's stderr in an error dialog;
   exit codes are `0` ok, `2` usage/key error, `3` not found, `1` other.

The subprocess call runs on a background thread so the UI stays responsive
(see [Threading](#threading)).

**Locating the binary.** The client resolves `message-store` in this order:
the `MESSAGE_STORE_BIN` environment override, the default cmake build location
`<repo>/message-store/build/message-store`, then a `PATH` lookup. If none is
found, Download shows a clear error telling the user to build it first:

```bash
cd message-store && cmake -B build && cmake --build build
```

The C++ component lives in [`message-store/`](../message-store/) and handles
persistent local storage, search, and export — the Python client only handles
decryption and the handoff (key via env, plaintext via stdin).

### Threading

CustomTkinter runs on the main thread. All network calls (API requests)
and crypto operations run on background threads via `threading.Thread` to
keep the UI responsive. Results are posted back to the main thread using
Tkinter's `after()` method. The registration screen shows a progress
indicator while it works; other screens update in place once results arrive.

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
- **Never send the cleartext password** — derive the authentication
  pre-hash (`derive_auth_hash`, domain-separated from the KEK) and send that;
  the server re-hashes it. See [Authentication Credential](#authentication-credential).
- **Validate `SERVER_URL` uses HTTPS in production** — config layer should
  refuse `http://` for non-localhost hosts.
- **Erase sensitive memory** — derived message keys and the keystore KEK must be
  overwritten after use. Python's garbage collector does not guarantee
  immediate erasure, so use `ctypes.memset` or `bytearray` zeroing
  where possible.