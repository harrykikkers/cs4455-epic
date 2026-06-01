#pragma once

// Archive: AES-256-GCM encrypted on-disk message archive.
//
// File format (single file):
//   [0..6)   magic      = the 6 ASCII bytes  Z B A R 1 \n
//   [6..18)  iv         = 12 random bytes, fresh on every write (RAND_bytes)
//   [18..34) tag        = 16-byte GCM auth tag
//   [34..)   ciphertext
//   AAD                 = the 6 magic bytes
//   plaintext           = UTF-8 JSON array of {"id","sender","created","body"}

#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace archive {

// The 6 magic bytes that prefix every archive and serve as the GCM AAD.
constexpr std::array<unsigned char, 6> kMagic = {'Z', 'B', 'A', 'R', '1', '\n'};
constexpr size_t kKeyLen = 32;  // AES-256
constexpr size_t kIvLen = 12;   // GCM nonce
constexpr size_t kTagLen = 16;  // GCM tag

// One archived message record. Mirrors the on-disk JSON object.
struct Record {
    std::string id;
    std::string sender;
    std::string created;
    std::string body;
};

// Thrown for decrypt/auth failures and malformed archives. Maps to exit code 1.
struct DecryptError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// Decode a 64-char lowercase-hex key into 32 raw bytes.
// Throws std::invalid_argument if not exactly 64 hex chars.
std::array<unsigned char, kKeyLen> decodeHexKey(const std::string& hex);

// Load + decrypt an archive into records. Returns an empty vector if the file
// does not exist. Throws DecryptError on any tampering / wrong key / corruption.
std::vector<Record> load(const std::string& path,
                         const std::array<unsigned char, kKeyLen>& key);

// Serialize records to JSON, encrypt with a fresh random IV, and write the file
// atomically (temp file + rename) with mode 0600.
void save(const std::string& path,
          const std::array<unsigned char, kKeyLen>& key,
          const std::vector<Record>& records);

}  // namespace archive
