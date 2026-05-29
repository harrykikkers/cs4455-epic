# message-store

An AES-256-GCM encrypted, on-disk message archive with a small CLI. The Python
client invokes the built `message-store` binary to store and retrieve message
bodies; secrets (the archive key and message bodies) are kept off the process
argument list.

## Build

Requires CMake (>= 3.16), a C++20 compiler, and OpenSSL 3.
`nlohmann/json` is fetched automatically via CMake `FetchContent`.

```sh
cmake -S message-store -B message-store/build \
      -DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3
cmake --build message-store/build
```

On macOS the `OPENSSL_ROOT_DIR` hint is applied automatically if
`/opt/homebrew/opt/openssl@3` exists, so the flag is usually optional.

Built binaries:

- `message-store/build/message-store` — the CLI (main deliverable).
- `message-store/build/demo` — legacy in-memory conversation-view demo.

## Key / environment contract

The archive key is **32 bytes**, supplied as **64 lowercase hex characters** in
the environment variable `MESSAGE_STORE_KEY`. It is never accepted on the command
line. If the variable is missing or is not exactly 64 lowercase hex chars, the
program prints an error and exits with code **2**.

Message bodies for `add` are read from **STDIN** (may contain newlines), again to
keep them out of `ps` / argv.

## Subcommands

```
message-store add  --archive <path> --id <id> --sender <name> --created <iso8601>
    Body is read from STDIN. Loads + decrypts the existing archive (treats a
    missing file as an empty archive), upserts by id (replace if the id exists,
    else append), then re-encrypts with a fresh IV and writes atomically (0600).

message-store get  --archive <path> --id <id>
    Decrypts and prints the matching body to stdout with no extra formatting.
    Exits 3 if the id is not found.

message-store list --archive <path>
    Decrypts and prints one line per message:  <id>\t<sender>\t<created>

message-store view [path-to-messages.json]
    Legacy viewer: reads a ciphertext JSON cache (default ~/.zebra/messages.json)
    and prints a conversation summary.
```

### Exit codes

| Code | Meaning                                   |
|------|-------------------------------------------|
| 0    | success                                   |
| 1    | other error / decryption (auth) failure   |
| 2    | usage error or key error                  |
| 3    | id not found (`get`)                       |

## Archive file format

A single binary file (path from `--archive`):

```
[0..6)    magic = the 6 ASCII bytes  Z B A R 1 \n   (hex: 5a 42 41 52 31 0a)
[6..18)   iv    = 12 random bytes, fresh on every write (RAND_bytes)
[18..34)  tag   = 16-byte GCM authentication tag
[34..)    ciphertext
```

- Cipher: **AES-256-GCM** via OpenSSL EVP.
- **AAD** = the 6 magic bytes (so the header is authenticated).
- Plaintext payload = a UTF-8 JSON array of objects, each:
  `{"id", "sender", "created", "body"}`.

Any tampering, a wrong key, or corruption fails GCM authentication and causes a
clean exit code 1 without printing plaintext.

## Example

```sh
KEY=$(python3 -c "import os;print(os.urandom(32).hex())")

printf 'hello\nmultiline body' | \
  MESSAGE_STORE_KEY=$KEY message-store add \
    --archive /tmp/arch.bin --id m1 --sender alice --created 2026-05-29T10:00:00Z

MESSAGE_STORE_KEY=$KEY message-store get  --archive /tmp/arch.bin --id m1
MESSAGE_STORE_KEY=$KEY message-store list --archive /tmp/arch.bin
```

## Source layout

- `Archive.h` / `Archive.cpp` — the AEAD archive module (key hex-decode,
  load/decrypt, save/encrypt, atomic write).
- `main.cpp` — CLI dispatch, flag parsing, STDIN/env handling, legacy `view`.
- `MessageStore.h` / `MessageStore.cpp` — legacy in-memory conversation model
  (used by `demo` and `view`).
- `demo.cpp` — legacy API demo.
