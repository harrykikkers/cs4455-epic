# Backend — Gaps vs CS4455 Epic Project Spec

A punch list of what is missing or half-wired in `backend/*` relative to the
project brief and the four minor rubrics. Items are grouped by the subject
they affect and tagged with severity:

- **[BLOCKER]** Required by the rubric; missing or broken
- **[GAP]** Required but partially implemented / not defensible at interview
- **[DOC]** Required artefact for the submission package
- **[NICE]** Improves the grade but not strictly required


Can do any labelled [DOC] towards the end of project

---

## Computer Networks & Cybersecurity (Burkley) — 25%

### Authentication / brute-force protection

- **[BLOCKER] `LoginAttemptRepository` is built but never wired.**
  [src/repositories/LoginAttemptRepository.js](src/repositories/LoginAttemptRepository.js)
  exists with `record()`, `countRecentFailures()`, `clearFailures()`, and the
  `login_attempts` table is created by [scripts/init-db.js](scripts/init-db.js).
  [src/services/AuthService.js:21](src/services/AuthService.js#L21) accepts it
  as an *optional* third constructor argument with `= null` default. But
  [src/app.js:92](src/app.js#L92) constructs `AuthService` with only two
  arguments, so `_loginAttempts` is always null and the `LOCKOUT_MAX_FAILURES`
  / `LOCKOUT_WINDOW_MS` constants at
  [src/services/AuthService.js:17-18](src/services/AuthService.js#L17-L18) are
  dead code. The rubric explicitly lists "Broken Authentication" as a control
  Burkley will test. Wire it up: instantiate `LoginAttemptRepository(pool)`,
  pass it to `AuthService`, gate `login()` on `countRecentFailures()`, and
  call `clearFailures()` on success.

- **[GAP] No IP-based throttle in service layer.** The `login_attempts` table
  is already indexed on `ip_address`
  ([scripts/init-db.js:38](scripts/init-db.js#L38)) but `LoginAttemptRepository`
  only counts failures by `user_id`. An attacker rotating usernames against
  one IP is invisible to the per-user counter. Either add
  `countRecentFailuresByIp()` or document that `express-rate-limit` on
  `/api/auth` is the IP layer.

- **[GAP] JWT algorithm not pinned.**
  [src/services/AuthService.js:72](src/services/AuthService.js#L72) calls
  `jwt.sign(payload, secret, { expiresIn })` without `algorithm:`, and
  `jwt.verify` at line 129 doesn't pass `algorithms: ['HS256']`. Defaults
  protect us today, but an algorithm-confusion / `alg: none` attack is one
  of the classic JWT pentests. Pin both sides explicitly.

### TLS / transport security

- **[GAP] Backend listens over plain HTTP.**
  [src/app.js:105](src/app.js#L105) uses `app.listen(...)` with no TLS.
  [.env.example:43-44](.env.example#L43-L44) declares `TLS_CERT_PATH` and
  `TLS_KEY_PATH` but neither variable is read in [src/config/index.js](src/config/index.js)
  or used in `app.js`. The project relies on nginx at
  [../deploy/nginx/zebra.theburkenator.com.conf](../deploy/nginx/zebra.theburkenator.com.conf)
  to terminate TLS, which is fine for the deployment — but the dead env vars
  imply a code path that doesn't exist. **Either** delete the unused vars and
  document "TLS terminated at nginx" in the README's Network Architecture
  section, **or** add an `https.createServer` branch driven by those vars for
  local dev / standalone runs.

- **[DOC] Network architecture diagram.** The README has a 6-line ASCII flow.
  The rubric calls for "Network architecture documentation; Connections to
  external services (MySQL server, etc) are documented". Add a diagram (Mermaid
  is fine, the README already uses it for the schema) showing:
  client → nginx (TLS) → Express → MySQL, plus the outbound
  Express → Sepolia RPC edge.

### OWASP top-10 coverage

- **[DOC] No explicit mapping document.** The rubric enumerates Improper Input
  Validation, Broken Authentication, Broken Access Control, Cryptographic
  Issues, Injection, Security Misconfiguration, Sensitive Data Exposure,
  Vulnerable Components — and expects you to *demonstrate* you checked each.
  Create `backend/SECURITY.md` (or a section in the README) walking through
  each item with the file/line that implements it.

- **[GAP] Per-field size limits.** [src/app.js:82](src/app.js#L82) caps the
  whole body at 256 KB, but `body('ciphertext').notEmpty()` in
  [src/middleware/validate.js:56](src/middleware/validate.js#L56) places no
  upper bound on the ciphertext field. A 250 KB ciphertext is a 256 KB body
  — fine — but no individual cap means a future bug widening the body limit
  would silently widen the per-field limit too. Add `.isLength({ max: ... })`.

- **[GAP] CSP not configured.** Helmet defaults are loaded
  ([src/app.js:42](src/app.js#L42)) but `contentSecurityPolicy` ships with a
  permissive default in dev mode and can be tightened. Either explicitly
  configure a CSP appropriate for this JSON API (`default-src 'none'`,
  effectively) or document why the default is acceptable.

- **[GAP] User enumeration via response codes.**
  [src/services/AuthService.js:36-41](src/services/AuthService.js#L36-L41)
  hashes before the uniqueness check (good for *timing*), but `register`
  still returns 409 vs 201 — i.e. the response code differentiates. The
  comment at line 30 calls this out as a deliberate trade-off. Document it
  explicitly in `SECURITY.md` as a known limitation accepted on UX grounds.

### Pentest report

- **[BLOCKER] Penetration testing report missing.** The rubric has a dedicated
  10-mark "Pentest and known vulnerabilities" criterion. Need a document
  (PDF or Markdown) covering: tests run (auth bypass attempts, SQLi probes,
  JWT manipulation, rate-limit bypass via X-Forwarded-For spoofing, replay
  attacks against the nonce uniqueness constraint, etc.), tools used (curl,
  Burp, sqlmap, etc.), findings, and the request ID of each interesting
  request so the auditor can correlate with `logs/audit.log`. Place at
  `backend/PENTEST.md` or in a `reports/` directory at the repo root.

### Replay protection / message ordering

- **[GAP] `seq_no` is stored but never checked.** The schema enforces
  `UNIQUE (recipient_id, nonce)`
  ([scripts/init-db.js:107](scripts/init-db.js#L107)), which gives replay
  protection. But the `seq_no` column at
  [scripts/init-db.js:100](scripts/init-db.js#L100) — explicitly described in
  the surrounding comment as "monotonically increasing per-recipient sequence
  number" — is never read back to verify monotonicity. The send path accepts
  any `seqNo >= 0` and writes it. Either enforce monotonic per `(sender_id,
  recipient_id)` in `MessageRepository.create`, or remove the field and
  rely on nonce-uniqueness alone (and update the schema comment).

---

## Cryptography (O'Brien) — 25%

Most cryptography lives in the client and the contract. The backend's
crypto surface is: Argon2id password hashing, JWT signing, transport (TLS),
and *not* touching message payloads. Gaps for the *backend's* slice:

- **[DOC] Cryptographic Design Document missing (server portion).** The rubric
  calls for a 2-6 page design doc. The server contributes: Argon2id parameter
  justification (current values are in [.env.example:19-21](.env.example#L19-L21)
  but the *rationale* isn't written down), JWT algorithm + secret length
  justification, and the explicit "the server does not see plaintext" property.
  Either create `backend/CRYPTO.md` covering the server slice, or contribute
  these sections to the team-level design document.

- **[GAP] Argon2 parameter justification.**
  [src/services/PasswordHasher.js:9](src/services/PasswordHasher.js#L9)
  comment says "OWASP recommended used" but doesn't cite the version of the
  OWASP cheatsheet or explain why those specific values (`m=65536, t=3, p=4`)
  were chosen for this deployment's hardware. Rubric: *"'it's standard' and
  'Eoin recommended it' are not justifications."*

- **[GAP] No HKDF on the server.** The server never derives keys (all key
  derivation is client-side), so this is N/A — but the design doc should
  state that explicitly so the interviewer doesn't expect to find HKDF here.

- **[GAP] Sensitive Data Exposure — log scrubbing.** Confirm the audit log
  doesn't include `password`, `ciphertext`, `enc`, or `signature` fields.
  [src/utils/logger.js](src/utils/logger.js) should be reviewed and a test
  added that asserts no request body fields land in logs verbatim.

---

## Blockchain (Le Gear) — 25%

- **[GAP] No retry worker for `chain_status = 'failed'`.**
  [src/services/BlockchainService.js:67](src/services/BlockchainService.js#L67)
  flags rows `chain_failed` on Sepolia outage and the schema has
  `idx_chain_status (chain_status, created_at)`
  ([scripts/init-db.js:110](scripts/init-db.js#L110)) for exactly this query.
  But nothing reads that index. A short retry job (cron, or in-process
  `setInterval`) that selects failed/pending rows and re-calls `recordDigest`
  is the obvious follow-up. At minimum, document the gap as "operator
  follow-up" in the README.

- **[GAP] Per-message chain writes — gas trade-off not documented.** The brief
  literally says "Pay attention to trade offs in persisting to the chain.
  E.g. a hash for each message may be excessive." The current design writes
  one tx per message. Either batch (Merkle root of N messages per tx) or
  write a paragraph in the README justifying per-message recording for this
  scale of demo.

- **[GAP] No `/api/messages/:id/chain` test.** `BlockchainService.test.js`
  exists but there's no integration test that exercises the
  `GET /api/messages/:id/chain` endpoint end-to-end (controller → service →
  repo → response shape). Worth adding for the verification-page integration.

---

## Submission Artefacts (cross-cutting)

- **[DOC] AI Prompt Artefacts.** New for 2026, explicitly required. Each
  contributor needs screenshots or exported logs of significant prompts, a
  reflective commentary, and evidence of critical evaluation. Backend-side,
  create `backend/AI_PROMPTS.md` (or a top-level `ai-artefacts/` dir) with
  the prompts used while building the server.

- **[DOC] Cover document.** Group name "Zebra", student IDs, GitHub URL,
  contribution breakdown by member. Lives at the repo root, not in backend,
  but mentioned here so it doesn't get forgotten.

- **[DOC] README — brute-force protection claim is currently false.**
  [README.md:241](README.md#L241) says "Rate limiting on auth endpoints
  prevents brute-force attacks". True for the IP-level `express-rate-limit`,
  but the README also implies (via the `login_attempts` schema in the ERD)
  that per-user lockout exists. Once the wiring above is fixed this becomes
  accurate; until then either fix the code or qualify the claim.

---

## Tests — coverage gaps

- **[GAP] No tests for `forwardMessage`, `revokeAccess`, `deleteMessage`.**
  `MessageService.test.js` covers send/get but not the access-control
  branches in [src/services/MessageService.js:79-124](src/services/MessageService.js#L79-L124).
  These are exactly the Broken Access Control surface the pentest report
  will probe.

- **[GAP] No tests for `/api/keys/:userId/history/:keyType`.** The rotation
  audit trail is a security-critical endpoint; needs a test that a rotated
  key shows up in history with the correct version.

- **[GAP] No negative-path JWT tests.** No test for: expired token, token
  with `alg: none`, token signed with a different secret, token whose
  `pwdChangedAt` predates the user's current `password_changed_at`. The
  last one is the only one with a comment-asserted behaviour
  ([src/services/AuthService.js:147](src/services/AuthService.js#L147)) and
  it's untested.

---

## Quick wins (do these first)

1. Wire `LoginAttemptRepository` into `AuthService` — closes a rubric
   criterion with ~20 lines of code.
2. Pin JWT `algorithm: 'HS256'` on both sign and verify — 2 lines.
3. Add `.isLength({ max: 200_000 })` to `ciphertext` in validate.js — 1 line.
4. Delete unused `TLS_CERT_PATH` / `TLS_KEY_PATH` from `.env.example` and
   add a "TLS terminated at nginx" line to the README — defensible.
5. Add `SECURITY.md` mapping OWASP top-10 → file/line — pure documentation,
   directly graded.
6. Add `PENTEST.md` with at least 5 documented tests + findings — directly
   graded, 10 marks under Burkley.
