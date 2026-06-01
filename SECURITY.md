# Security Controls — Secure Messenger (Team Zebra)

This document maps each security control area enumerated in the CS4455
**Computer Networks & Cybersecurity** rubric to where it is implemented in the
codebase, so the control can be inspected and verified directly. It is the
"we actively checked for this" companion to the penetration-testing report
(`PENTEST.md`).

Paths are relative to `backend/`. Client-side controls live in the Python
client (`client/`) and the C++ message store (`message-store/`); the
end-to-end cryptographic design is documented separately in the team
Cryptographic Design Document.

## Trust boundary

```
[ Python client / C++ store ]      <- holds plaintext + private keys; trusted
            | HTTPS (TLS 1.2/1.3)
            v
[ nginx :443 ]                     <- TLS termination, edge headers, HTTP->HTTPS
            | loopback HTTP :3000
            v
[ Express backend ]                <- relays ciphertext; NEVER sees plaintext
            | loopback
            v
[ MySQL :3306, bind 127.0.0.1 ]    <- stores ciphertext + metadata only
            | outbound
            v
[ Ethereum Sepolia RPC ]           <- receives keccak256 digests only
```

The only public network surface is nginx. Everything past it (Node, MySQL)
shares one trust domain on loopback. The server is **untrusted with respect to
message confidentiality**: it stores and forwards ciphertext, and the design
goal is that a fully compromised server still cannot read messages or forge
them. See the Cryptographic Design Document for the formal threat model.

## At a glance

| # | Control area | Status | Primary location |
|---|--------------|--------|------------------|
| 1 | Improper Input Validation | Implemented | `src/middleware/validate.js` |
| 2 | Broken Authentication | Implemented | `src/services/AuthService.js`, `src/middleware/auth.js` |
| 3 | Broken Access Control | Implemented | `src/services/MessageService.js`, `src/controllers/MessageController.js` |
| 4 | Cryptographic Issues | Implemented | `src/services/PasswordHasher.js`, `src/services/AuthService.js`, client crypto layer |
| 5 | Injection | Implemented | `src/repositories/*`, `src/middleware/validate.js` |
| 6 | Security Misconfiguration | Implemented (minor hardening planned) | `src/app.js`, `deploy/nginx/`, `src/middleware/errorHandler.js` |
| 7 | Sensitive Data Exposure | Implemented (one regression test planned) | `src/services/AuthService.js`, `src/middleware/errorHandler.js`, `src/utils/logger.js` |
| 8 | Vulnerable & Outdated Components | Implemented | `package.json`, `package-lock.json` |

Items marked with an outstanding step are listed in full under
[Known limitations and planned hardening](#known-limitations-and-planned-hardening).

---

## 1. Improper Input Validation

All request input is validated at the edge of the API before it reaches any
business logic, using `express-validator` chains defined in
`src/middleware/validate.js` and attached per route in `src/routes/*`.

- **Auth credential** (`authCredential`): the `password` / `currentPassword` /
  `newPassword` fields must match `^[0-9a-f]{64}$` — the client only ever sends
  a 64-char Argon2id pre-hash, so the server validates that exact shape and
  rejects anything else.
- **Username**: trimmed, length 3–30, restricted to `^[a-zA-Z0-9_-]+$`.
- **Message send / forward** (`validate.sendMessage`, `validate.forwardMessage`):
  `recipientId` must be a UUID; `nonce` must be exactly 16 chars (base64 of the
  12-byte AES-GCM IV) matching a base64/base64url charset; `signature` must be
  non-empty base64; `seqNo` must be an integer ≥ 0; `digest` must match
  `^0x[0-9a-fA-F]{64}$` (keccak256). Route params (`:id`) are UUID-checked.
- **Key publication** (`validate.publishKey`): `publicKey` length 43–88 with a
  base64/hex charset (the only lengths consistent with a 32-byte key);
  `keyType` constrained to the enum `x25519 | ed25519`; `acknowledgeRotation`
  an optional boolean.
- **Pagination** (`validate.pagination`): `limit` bounded to 1–100, `offset` ≥ 0,
  both coerced to integers.
- **Mass-assignment defence**: controllers destructure request bodies field by
  field (`src/controllers/MessageController.js`), so a client cannot inject
  `senderId` — that value is always taken from the authenticated token
  (`req.user.id`), never from the body.
- **Body size**: a fixed request-body limit on the JSON parser; oversized
  bodies are rejected with `413 PAYLOAD_TOO_LARGE` before any handler runs
  (`src/middleware/errorHandler.js`, `entity.too.large`). Malformed JSON is
  rejected with `400 INVALID_JSON`.

Validation failures are funnelled through `handleValidation`, which raises a
single `BadRequestError` carrying the collected messages.

The `ciphertext` field is validated as a non-empty string with an explicit
upper bound of 200 000 base64 chars (≈150 KB) in `validate.js`, in addition to
the shared 256 KB whole-body cap on the JSON parser.

## 2. Broken Authentication

**Password handling.** The cleartext password never reaches the server. The
client derives an Argon2id pre-hash (`client crypto.kdf.derive_auth_hash`) and
sends that. The server treats the pre-hash as the credential and **re-hashes it
again** with Argon2id and its own per-user random salt
(`src/services/PasswordHasher.js`) before storing it in `users.password_hash`.
Consequences:

- the server never learns the real password — it cannot be logged or leaked;
- a database leak does not yield a value that can be replayed straight to
  `/login`, because what is stored is a salted Argon2id hash of the pre-hash.

Argon2id parameters are `memory_cost = 65536` (64 MiB), `time_cost = 3`,
`parallelism = 4`, `hash_len = 32` (RFC 9106), and the client KEK derivation
uses the same parameters so both sides agree.

**Timing.** `AuthService.login` and `AuthService.register` hash unconditionally,
even for a non-existent user (with a `try/catch` so malformed input still
returns 401 rather than 500), so missing-user and wrong-password latency match
and existence cannot be inferred from response time.

**Sessions (JWT).** On login the server issues a JWT signed with HS256
(`jsonwebtoken`). `src/middleware/auth.js` parses the `Authorization: Bearer`
header and calls `AuthService.verifyToken`, which:

- rejects a token whose `pwdChangedAt` predates the user's current
  `password_changed_at` — so **changing a password invalidates all previously
  issued tokens**;
- rejects a token for a user that no longer exists;
- preserves specific failure reasons rather than collapsing everything into a
  generic 401.

**Online-guessing defence.** `src/app.js` applies `express-rate-limit`: a strict
limiter on `/api/auth/register` and a combined limiter on `/api/auth`
(login + password change) over a 15-minute window. `app.set('trust proxy', 1)`
ensures the limiter keys on the real client IP from `X-Forwarded-For` behind
nginx rather than the proxy address.

**Per-user lockout.** Active and wired. The `login_attempts` table
(`scripts/init-db.js`, indexed on both `user_id` and `ip_address`) backs a
`LoginAttemptRepository` (`record`, `countRecentFailures`, `clearFailures`),
which `app.js` injects into `AuthService` as its third constructor argument.
`login()` records every failure and, once `countRecentFailures()` reaches
`LOCKOUT_MAX_FAILURES = 5` inside `LOCKOUT_WINDOW_MS = 15 min`, rejects with
`401 Account temporarily locked — too many failed attempts`; a successful login
calls `clearFailures()` to reset the streak. This sits underneath the IP-layer
rate limiter above as a second, per-account online-guessing defence. The
six-bad-logins test is enumerated as F-02 in [PENTEST.md](PENTEST.md).

The JWT algorithm is pinned explicitly — `HS256` on both sign and verify
(`AuthService.js`) — removing any `alg: none` / algorithm-confusion surface.

## 3. Broken Access Control

Every `/api/messages/*` and `/api/keys/*` route is mounted behind the JWT auth
middleware (`src/routes/messages.js`, `src/routes/keys.js`), so all of them
require a valid session. Authorisation is enforced in the service layer against
the raw database row, before any data is returned:

- **Read a message** (`MessageService.getMessage`): allowed only if the caller
  is the sender, the original recipient, or the holder of an active share;
  otherwise `ForbiddenError`. A non-existent message is `NotFoundError`.
- **Forward** (`MessageService.forwardMessage`): calls `getMessage` for the
  forwarder first, so a user can only forward a message they are actually a
  party to. Access is enforced per hop.
- **Revoke** (`MessageService.revokeAccess`): only the **original sender** may
  revoke a share; anyone else gets `ForbiddenError`.
- **Delete** (`MessageService.deleteMessage`): the soft-delete is scoped to the
  caller, and a caller with no access receives `NotFoundError` rather than
  `ForbiddenError` — deliberately, so an attacker cannot use the response code
  to probe for message IDs they are not party to.
- **Chain proof** (`MessageService.getChainProof`): reuses the same `getMessage`
  authorisation, so the blockchain endpoint cannot leak the existence or digest
  of a message the caller cannot read.

The identity used for all of these is `req.user.id` from the verified token,
never a client-supplied field.

## 4. Cryptographic Issues

The server's cryptographic surface is deliberately small: **Argon2id** password
hashing, **HS256** JWT signing, and **TLS** in transit. The server does not
touch message plaintext at all — it relays the client's ciphertext and the
client-supplied keccak256 digest without inspecting or recomputing them
(`src/services/BlockchainService.js`, `src/services/MessageService.js`).

Message confidentiality, integrity, and sender authentication are end-to-end
and implemented in the client: **static ECDH (X25519) → HKDF-SHA256 →
AES-256-GCM**, with independent **Ed25519** signatures for sender authentication
and replay-protected associated data. The full construction, parameter-level
justification, threat model, and known limitations (including the deliberate
absence of forward secrecy under static ECDH) are in the Cryptographic Design
Document.

Forbidden primitives are not used anywhere in a security-relevant role: no MD5
or SHA-1 for authentication, no DES/3DES/RC4, no ECB mode, no textbook RSA, no
hardcoded keys or IVs, and no nonce reuse (a fresh 12-byte CSPRNG nonce per
message). All randomness comes from an OS CSPRNG (the `cryptography` library /
OpenSSL `RAND_bytes` in the C++ store / `ethers` for chain operations). The
`bytes32` type on the contract enforces the digest length, and `ethers`
rejects a malformed digest before any transaction is sent.

## 5. Injection

- **SQL injection.** All data access goes through the repository layer
  (`src/repositories/*`), which uses `mysql2` parameterised/prepared statements
  exclusively (`namedPlaceholders: true`, `src/config/database.js`). No user
  input is ever concatenated into a query string. The one-off DDL in
  `scripts/init-db.js` contains no user input.
- **Shape validation** (section 1) rejects malformed identifiers, nonces,
  signatures, and digests before they reach the database, narrowing the input
  space well beyond what parameterisation alone guarantees.
- **Command / code injection.** The backend performs no shell execution and no
  `eval` on request data. (The C++ message store is invoked only by the local
  client, with controlled arguments and the message body passed on **stdin**,
  never on the command line.)
- **Output.** The API returns JSON only and renders no server-side HTML or
  templates, so the classic reflected/stored XSS surface does not exist on the
  server; the client is responsible for safe rendering.

## 6. Security Misconfiguration

- **Security headers** via Helmet (`src/app.js`): HSTS, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options` (Helmet's default is `SAMEORIGIN`; the nginx edge
  sets `DENY`), `Referrer-Policy`, and an explicit Content-Security-Policy locked
  down to `default-src 'none'; frame-ancestors 'none'` — appropriate for a
  JSON-only API that serves no markup, scripts, or frames.
- **CORS** restricted to the configured origin in production and only the
  methods/headers the API uses (`src/app.js`).
- **Error handling** (`src/middleware/errorHandler.js`): deliberate
  (`AppError`) failures return structured JSON with a stable error code;
  unexpected errors return a generic `500 INTERNAL_ERROR` with **only** a
  request ID — the stack trace is logged server-side and never sent to the
  client. Every response carries the per-request UUID stamped by
  `src/middleware/requestId.js`, so a pentest finding can be traced to a single
  server log line.
- **Edge (nginx, `deploy/nginx/`)**: TLS 1.2/1.3 only with a Let's Encrypt
  certificate and full chain, OCSP stapling, HTTP→HTTPS 301 redirect, HSTS at
  the edge, and `server_tokens off` to hide the nginx version.
- **Network exposure**: MySQL is bound to `127.0.0.1` (loopback only); the only
  public surface is nginx. Node runs under a hardened systemd unit
  (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`,
  restricted `ReadWritePaths`).
- **Secrets**: all secrets (DB credentials, JWT secret, Sepolia key, contract
  address) are supplied via `.env`, which is git-ignored (`.gitignore`); none
  are committed to the repository.

**Residual risk:** the backend listens over plain HTTP behind nginx (TLS
terminated at the edge), and the unused `TLS_CERT_PATH` / `TLS_KEY_PATH`
variables in `.env.example` should be removed or wired. Tracked under planned
hardening.

## 7. Sensitive Data Exposure

- **Message plaintext** is never exposed to the server — it stores and forwards
  only AES-256-GCM ciphertext. This is demonstrable from the database and logs
  at the demo, and holds even against a fully compromised server.
- **Passwords** are never sent in cleartext and are stored only as a salted
  Argon2id hash of the client pre-hash (section 2), so a database breach does
  not expose passwords or yield a directly replayable credential.
- **Private keys** never leave the client; they are encrypted at rest under an
  Argon2id-derived KEK (client keystore) and are not recoverable from the
  server or from a stolen *locked* device.
- **In transit**: all client↔server traffic is TLS (nginx, HSTS).
- **Error responses** leak no internals — only a request ID (section 6).
- **Logging** uses structured Winston logs plus a dedicated audit log
  (`src/utils/logger.js`); request bodies are not logged verbatim, so the auth
  credential, ciphertext, and signature do not land in logs.
- **JWT secret** is supplied via `JWT_SECRET` in `.env` (not committed) and
  should be at least 32 bytes of CSPRNG output.

**Known trade-off:** registration returns `409` for a taken username versus
`201` on success, so the status code distinguishes existing accounts. This is
accepted on UX grounds (users must be told to pick another name) and is
mitigated by the strict rate limit on `/api/auth/register`.

**Residual risk:** add a regression test asserting that no sensitive request
field (password, ciphertext, signature) is ever written to a log line — this is
currently confirmed by manual review only. Tracked under planned hardening.

## 8. Vulnerable and Outdated Components

- Dependencies are pinned via `package-lock.json` for reproducible installs.
- The known transitive advisory in **`ws`** (pulled in via `ethers` v6) is
  mitigated with an explicit override in `package.json`:
  `"overrides": { "ws": ">=8.18.2" }`. This is preferred over
  `npm audit fix --force`, which would downgrade `ethers` to v5 and break the
  v6 API the backend depends on.
- Core dependencies are current: `express` ^4.21, `express-rate-limit` ^7.4,
  `express-validator` ^7.2, `helmet` ^8, `jsonwebtoken` ^9, `mysql2` ^3.11,
  `argon2` ^0.41, `ethers` ^6.13, `winston` ^3.17.
- The C++ component depends on **OpenSSL 3** (EVP, system) and **libcurl**
  (system), with **nlohmann/json** pinned to v3.11.3 via CMake `FetchContent`.

**Process:** re-run `npm audit` immediately before submission and document any
remaining advisory together with its justification.

---

## Testing and verification

The controls above are exercised by the penetration-testing report
(`PENTEST.md`), which records the tests run (authentication-bypass attempts,
SQL-injection probes, JWT manipulation, rate-limit bypass via `X-Forwarded-For`
spoofing, and replay against the `(recipient_id, nonce)` uniqueness
constraint), the tools used, and the request ID of each interesting request so
each finding correlates with a single server log line.

A Jest suite under `tests/` provides the harness; the access-control and
negative-path flows are enumerated as `test.todo` cases and are being filled in.

## Known limitations and planned hardening

These are the items above that are not yet fully closed, gathered in one place
for transparency:

1. **Username enumeration via register status code** — accepted trade-off,
   documented and rate-limited.
2. **Add a log-scrubbing regression test** asserting no sensitive field is ever
   logged verbatim.
3. **Remove the unused `TLS_CERT_PATH` / `TLS_KEY_PATH` variables** (TLS is
   terminated at nginx).
