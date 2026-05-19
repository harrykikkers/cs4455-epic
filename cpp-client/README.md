# Epic Secure Messenger — C++ Client

This is a minimal C++ client for the Epic Secure Messenger backend.

Requirements
- A Linux development environment
- C++20 toolchain (g++, clang++)
- CMake >= 3.16
- Development packages: libcurl4-openssl-dev, libsodium-dev, nlohmann-json3-dev, pkg-config

Quick build

```bash
cd cpp-client
cmake .
cmake --build .
```

Run

```bash
# default base URL is https://localhost:3000
./epic_client [base_url]
```

Notes
- This client expects the server to perform authentication and accept the payloads described in the backend README.
- All message encryption is performed client-side using libsodium (`crypto_box_easy`). The client only sends `ciphertext`, `nonce`, and the sender's public key to the backend.
- The client uses `nlohmann/json` for JSON handling and `libcurl` for HTTPS requests.

Security
- This is an example client: store and manage secret keys securely in production (use OS keyrings, hardware modules, or secure enclaves).

