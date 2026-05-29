#include "Archive.h"

#include <nlohmann/json.hpp>
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

namespace archive {

namespace {

// RAII wrapper for the OpenSSL cipher context.
struct CipherCtx {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    CipherCtx() = default;
    ~CipherCtx() { if (ctx) EVP_CIPHER_CTX_free(ctx); }
    CipherCtx(const CipherCtx&) = delete;
    CipherCtx& operator=(const CipherCtx&) = delete;
};

int hexNibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;  // reject uppercase and non-hex
}

// AES-256-GCM encrypt. Returns ciphertext; fills `tag` (16 bytes).
std::vector<unsigned char> gcmEncrypt(
        const std::array<unsigned char, kKeyLen>& key,
        const std::array<unsigned char, kIvLen>& iv,
        const std::vector<unsigned char>& plaintext,
        unsigned char tag[kTagLen]) {
    CipherCtx c;
    if (!c.ctx) throw DecryptError("EVP_CIPHER_CTX_new failed");

    if (EVP_EncryptInit_ex(c.ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1)
        throw DecryptError("EncryptInit (cipher) failed");
    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_SET_IVLEN, kIvLen, nullptr) != 1)
        throw DecryptError("set IV length failed");
    if (EVP_EncryptInit_ex(c.ctx, nullptr, nullptr, key.data(), iv.data()) != 1)
        throw DecryptError("EncryptInit (key/iv) failed");

    int len = 0;
    // AAD = the magic bytes.
    if (EVP_EncryptUpdate(c.ctx, nullptr, &len, kMagic.data(), (int)kMagic.size()) != 1)
        throw DecryptError("EncryptUpdate (AAD) failed");

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
std::vector<unsigned char> gcmDecrypt(
        const std::array<unsigned char, kKeyLen>& key,
        const std::array<unsigned char, kIvLen>& iv,
        const unsigned char tag[kTagLen],
        const std::vector<unsigned char>& ciphertext) {
    CipherCtx c;
    if (!c.ctx) throw DecryptError("EVP_CIPHER_CTX_new failed");

    if (EVP_DecryptInit_ex(c.ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1)
        throw DecryptError("DecryptInit (cipher) failed");
    if (EVP_CIPHER_CTX_ctrl(c.ctx, EVP_CTRL_GCM_SET_IVLEN, kIvLen, nullptr) != 1)
        throw DecryptError("set IV length failed");
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

std::array<unsigned char, kKeyLen> decodeHexKey(const std::string& hex) {
    if (hex.size() != kKeyLen * 2)
        throw std::invalid_argument("key must be exactly 64 hex chars");
    std::array<unsigned char, kKeyLen> key{};
    for (size_t i = 0; i < kKeyLen; ++i) {
        int hi = hexNibble(hex[2 * i]);
        int lo = hexNibble(hex[2 * i + 1]);
        if (hi < 0 || lo < 0)
            throw std::invalid_argument("key must be 64 lowercase hex chars");
        key[i] = (unsigned char)((hi << 4) | lo);
    }
    return key;
}

std::vector<Record> load(const std::string& path,
                         const std::array<unsigned char, kKeyLen>& key) {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return {};  // absent archive => empty array

    std::vector<unsigned char> raw(
        (std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());

    const size_t headerLen = kMagic.size() + kIvLen + kTagLen;  // 6 + 12 + 16 = 34
    if (raw.size() < headerLen)
        throw DecryptError("archive too short / corrupt");
    if (!std::equal(kMagic.begin(), kMagic.end(), raw.begin()))
        throw DecryptError("bad magic / not a ZBAR1 archive");

    std::array<unsigned char, kIvLen> iv{};
    std::copy_n(raw.begin() + kMagic.size(), kIvLen, iv.begin());
    unsigned char tag[kTagLen];
    std::copy_n(raw.begin() + kMagic.size() + kIvLen, kTagLen, tag);

    std::vector<unsigned char> ciphertext(raw.begin() + headerLen, raw.end());
    std::vector<unsigned char> plaintext = gcmDecrypt(key, iv, tag, ciphertext);

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
        records.push_back(std::move(r));
    }
    return records;
}

void save(const std::string& path,
          const std::array<unsigned char, kKeyLen>& key,
          const std::vector<Record>& records) {
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
    std::vector<unsigned char> plaintext(jsonStr.begin(), jsonStr.end());

    // Fresh random IV on every write.
    std::array<unsigned char, kIvLen> iv{};
    if (RAND_bytes(iv.data(), (int)iv.size()) != 1)
        throw DecryptError("RAND_bytes failed for IV");

    unsigned char tag[kTagLen];
    std::vector<unsigned char> ciphertext = gcmEncrypt(key, iv, plaintext, tag);

    // Assemble: magic | iv | tag | ciphertext.
    std::vector<unsigned char> blob;
    blob.reserve(kMagic.size() + kIvLen + kTagLen + ciphertext.size());
    blob.insert(blob.end(), kMagic.begin(), kMagic.end());
    blob.insert(blob.end(), iv.begin(), iv.end());
    blob.insert(blob.end(), tag, tag + kTagLen);
    blob.insert(blob.end(), ciphertext.begin(), ciphertext.end());

    // Atomic write: write to a temp file (0600), then rename over the target.
    std::string tmp = path + ".tmp";
    int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0)
        throw DecryptError(std::string("cannot open temp file: ") + std::strerror(errno));

    size_t written = 0;
    while (written < blob.size()) {
        ssize_t n = ::write(fd, blob.data() + written, blob.size() - written);
        if (n < 0) {
            int err = errno;
            ::close(fd);
            ::unlink(tmp.c_str());
            throw DecryptError(std::string("write failed: ") + std::strerror(err));
        }
        written += (size_t)n;
    }
    if (::fsync(fd) != 0) { /* best effort */ }
    if (::close(fd) != 0)
        throw DecryptError(std::string("close failed: ") + std::strerror(errno));

    if (::rename(tmp.c_str(), path.c_str()) != 0) {
        int err = errno;
        ::unlink(tmp.c_str());
        throw DecryptError(std::string("rename failed: ") + std::strerror(err));
    }
}

}  // namespace archive
