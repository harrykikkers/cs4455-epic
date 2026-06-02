#include "Archive.h"

#include <nlohmann/json.hpp> // for JSON parsing and building
#include <openssl/evp.h>
#include <openssl/rand.h>

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <unistd.h>

using json = nlohmann::json;

// Init — set up the cipher, key, IV
// Update — feed data in (can call multiple times)
// Final — flush remaining bytes, verify tag
namespace archive {

namespace {
// inner namespace means evrything inside is private to this file
// RAII wrapper for OpenSSL.
struct CipherCtx {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new(); // EVP_CIPHER_CTX_new() allocates it on the heap and returns a pointer. 
    // EVP_CIPHER_CTX holds the state of an ongoing encrypt/decrypt operation
    CipherCtx() = default; // use the compiler-generated one.
    ~CipherCtx() { if (ctx) EVP_CIPHER_CTX_free(ctx); } // destructor ~ runs automatically when object is out of scope
    CipherCtx(const CipherCtx&) = delete; // deletes copy constructor
    CipherCtx& operator=(const CipherCtx&) = delete; // deletes copy assignment
};

int hexNibble(char c) {
    // called by decodeHexKey
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;  // reject uppercase and non-hex
} // converts hex character to its numeric value

// AES-256-GCM encrypt. Returns ciphertext; fills `tag` (16 bytes).
ByteVec gcmEncrypt(
        const AesKey& key,
        const GcmIV& iv,
        const ByteVec& plaintext,
        unsigned char tag[kTagLen]) {
    CipherCtx c;
    if (!c.ctx) throw DecryptError("EVP_CIPHER_CTX_new failed");
    // checks if pointer is null, which would indicate a failure to allocate the context
    if (EVP_EncryptInit_ex(c.ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) // use AES-256-GCM
        throw DecryptError("EncryptInit (cipher) failed");
    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_SET_IVLEN, kIvLen, nullptr) != 1) // set the IV length for GCM mode
        throw DecryptError("set GcmIV length failed");
    if (EVP_EncryptInit_ex(c.ctx, nullptr, nullptr, key.data(), iv.data()) != 1) // set the key and IV for encryption
        throw DecryptError("EncryptInit (key/iv) failed");
        // nullptr here for cipher means "keep the same cipher from before 

    int len = 0;
    // AAD = the magic bytes.
    if (EVP_EncryptUpdate(c.ctx, nullptr, &len, kMagic.data(), (int)kMagic.size()) != 1) // feeds the aad into GCM
        throw DecryptError("EncryptUpdate (AAD) failed"); // if anyone tampers with the header, decryption fails.

    std::vector<unsigned char> out(plaintext.size());
    int outLen = 0;
    if (!plaintext.empty()) {
        if (EVP_EncryptUpdate(c.ctx, out.data(), &outLen,
                              plaintext.data(), (int)plaintext.size()) != 1)
            throw DecryptError("EncryptUpdate failed");
    }
    int finalLen = 0;
    if (EVP_EncryptFinal_ex(c.ctx, out.data() + outLen, &finalLen) != 1)
        throw DecryptError("EncryptFinal failed");
    out.resize(outLen + finalLen);

    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_GET_TAG, kTagLen, tag) != 1)
        throw DecryptError("get GCM tag failed");
    return out;
}

// AES-256-GCM decrypt + authenticate. Throws DecryptError if the tag is wrong.
ByteVec gcmDecrypt(
        const AesKey& key,
        const GcmIV& iv,
        const unsigned char tag[kTagLen],
        const ByteVec& ciphertext) {
    CipherCtx c;
    if (!c.ctx) throw DecryptError("EVP_CIPHER_CTX_new failed");

    if (EVP_DecryptInit_ex(c.ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1)
        throw DecryptError("DecryptInit (cipher) failed");
    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_SET_IVLEN, kIvLen, nullptr) != 1)
        throw DecryptError("set GcmIV length failed");
    if (EVP_DecryptInit_ex(c.ctx, nullptr, nullptr, key.data(), iv.data()) != 1)
        throw DecryptError("DecryptInit (key/iv) failed");

    int len = 0;
    if (EVP_DecryptUpdate(c.ctx, nullptr, &len, kMagic.data(), (int)kMagic.size()) != 1)
        throw DecryptError("DecryptUpdate (AAD) failed");

    std::vector<unsigned char> out(ciphertext.size());
    int outLen = 0;
    if (!ciphertext.empty()) {
        if (EVP_DecryptUpdate(c.ctx, out.data(), &outLen,
                              ciphertext.data(), (int)ciphertext.size()) != 1)
            throw DecryptError("DecryptUpdate failed");
    }

    // Provide the expected tag, then verify in Final.
    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_SET_TAG, kTagLen,
                            const_cast<unsigned char*>(tag)) != 1)
        throw DecryptError("set GCM tag failed");

    int finalLen = 0;
    if (EVP_DecryptFinal_ex(c.ctx, out.data() + outLen, &finalLen) != 1)
        throw DecryptError("authentication failed (wrong key or tampered archive)");
    out.resize(outLen + finalLen);
    return out;
}

}  // namespace

AesKey decodeHexKey(const std::string& hex) {
    if (hex.size() != kKeyLen * 2)
        throw std::invalid_argument("key must be exactly 64 hex chars");
    AesKey key{}; // Creates a zero-initialised 32-byte array. The {} means all bytes start as 0.
    for (size_t i = 0; i < kKeyLen; ++i) {
        int hi = hexNibble(hex[2 * i]);
        int lo = hexNibble(hex[2 * i + 1]);
        if (hi < 0 || lo < 0)
            throw std::invalid_argument("key must be 64 lowercase hex chars");
        key[i] = (unsigned char)((hi << 4) | lo);
    }
    return key;
}

std::vector<Record> load(const std::string& path, const AesKey& key) {
    std::ifstream f(path, std::ios::binary); // opens file in binary mode
    if (!f.is_open()) return {};  // absent archive => empty array

    std::vector<unsigned char> raw(
        (std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());

    const size_t headerLen = kMagic.size() + kIvLen + kTagLen;  // 6 + 12 + 16 = 34
    if (raw.size() < headerLen)
        throw DecryptError("archive too short / corrupt");
    if (!std::equal(kMagic.begin(), kMagic.end(), raw.begin()))
        throw DecryptError("bad magic / not a ZBAR1 archive");

    GcmIV iv{};
    std::copy_n(raw.begin() + kMagic.size(), kIvLen, iv.begin());
    unsigned char tag[kTagLen];
    std::copy_n(raw.begin() + kMagic.size() + kIvLen, kTagLen, tag);

    ByteVec ciphertext(raw.begin() + headerLen, raw.end());
    ByteVec plaintext = gcmDecrypt(key, iv, tag, ciphertext);

    json arr;
    try {
        arr = json::parse(plaintext);
    } catch (const json::parse_error& e) {
        throw DecryptError(std::string("decrypted payload is not valid JSON: ") + e.what());
    }
    if (!arr.is_array())
        throw DecryptError("decrypted payload is not a JSON array");

    std::vector<Record> records;
    for (const auto& item : arr) {
        Record r;
        r.id      = item.value("id", "");
        r.sender  = item.value("sender", "");
        r.created = item.value("created", "");
        r.body    = item.value("body", "");
        records.push_back(std::move(r)); // push_back adds an element to the end of the array
        // std::move(r) transfers ownership of r into the vector instead of copying it
        // avoids duplicating all the strings inside Record.  
    }
    return records;
}

void save(const std::string& path, const AesKey& key, const std::vector<Record>& records) {
    // Serialize to JSON plaintext.
    json arr = json::array();
    for (const auto& r : records) {
        arr.push_back({
            {"id", r.id},
            {"sender", r.sender},
            {"created", r.created},
            {"body", r.body},
        });
    }
    std::string jsonStr = arr.dump();
    ByteVec plaintext(jsonStr.begin(), jsonStr.end());

    // Fresh random GcmIV on every write.
    GcmIV iv{};
    if (RAND_bytes(iv.data(), (int)iv.size()) != 1) 
        throw ArchiveIOError("RAND_bytes failed for IV");

    unsigned char tag[kTagLen];
    ByteVec ciphertext = gcmEncrypt(key, iv, plaintext, tag);

    // Assemble: magic | iv | tag | ciphertext.
    ByteVec blob;
    blob.reserve(kMagic.size() + kIvLen + kTagLen + ciphertext.size()); // allocates memory
    blob.insert(blob.end(), kMagic.begin(), kMagic.end());
    blob.insert(blob.end(), iv.begin(), iv.end());
    blob.insert(blob.end(), tag, tag + kTagLen);
    blob.insert(blob.end(), ciphertext.begin(), ciphertext.end());

    // Atomic write: write to a temp file (0600), then rename over the target.
    std::string tmp = path + ".tmp";
    int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    // fd = file descriptor, an integer that uniquely identifies the open file in the OS.
    if (fd < 0)
        throw ArchiveIOError(std::string("cannot open temp file: ") + std::strerror(errno));

    size_t written = 0;
    while (written < blob.size()) {
        ssize_t n = ::write(fd, blob.data() + written, blob.size() - written);
        // ssize_t is a signed integer type used for byte counts and can represent -1 for errors, 
        // while size_t is unsigned and cannot represent negative values.
        if (n < 0) {
            int err = errno;
            ::close(fd);
            ::unlink(tmp.c_str()); // deletes a file
            throw ArchiveIOError(std::string("write failed: ") + std::strerror(err));
        }
        written += (size_t)n; // casting n to size_t because we know after the check it must be non-negative
    } // :: means global scope and avoids any potential name collisions with other functions.
    if (::fsync(fd) != 0) { /* best effort */ } // fsync flushes OS buffer in disk
    if (::close(fd) != 0) // flushes and releases the file descriptor
        throw ArchiveIOError(std::string("close failed: ") + std::strerror(errno));

    if (::rename(tmp.c_str(), path.c_str()) != 0) {
        int err = errno;
        ::unlink(tmp.c_str());
        throw ArchiveIOError(std::string("rename failed: ") + std::strerror(err));
    }
}

}  // namespace archive
