// Minimal cryptography helpers using libsodium (C API).
// - Provides base64 helpers and a thin wrapper around `crypto_box` for public-key encryption.
// - All keys and nonces are returned/accepted as base64 strings for transport over JSON.
// Security notes:
// - Caller is responsible for secure key storage and zeroing secrets when appropriate.
// - This example uses `crypto_box_easy` (Curve25519/Xsalsa20-Poly1305) which provides
//   authenticated encryption with sender's secret key and recipient's public key.

#include "Client/CryptoHelpers.h"
#include <sodium.h>
#include <stdexcept>
#include <vector>

namespace Client {

namespace {
// Reserved for potential custom base64 handling; libsodium provides helpers below.
const char b64Chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
}

// Encode binary data to base64 using libsodium helper.
std::string CryptoHelpers::toBase64(const std::vector<unsigned char>& data) {
    size_t encodedLen = sodium_base64_encoded_len(data.size(), sodium_base64_VARIANT_ORIGINAL);
    std::string encoded(encodedLen, '\0');
    sodium_bin2base64(encoded.data(), encodedLen, data.data(), data.size(), sodium_base64_VARIANT_ORIGINAL);
    if (!encoded.empty() && encoded.back() == '\0') {
        encoded.pop_back();
    }
    return encoded;
}

// Decode base64 to binary using libsodium helper.
std::vector<unsigned char> CryptoHelpers::fromBase64(const std::string& text) {
    std::vector<unsigned char> decoded(text.size());
    size_t decodedLen = 0;
    if (sodium_base642bin(decoded.data(), decoded.size(), text.c_str(), text.size(), nullptr, &decodedLen, nullptr, sodium_base64_VARIANT_ORIGINAL) != 0) {
        throw std::runtime_error("Base64 decode failed");
    }
    decoded.resize(decodedLen);
    return decoded;
}

// Generate a random nonce suitable for `crypto_box` and return base64 form.
std::string CryptoHelpers::generateBase64Nonce() {
    std::vector<unsigned char> nonce(crypto_box_NONCEBYTES);
    randombytes_buf(nonce.data(), nonce.size());
    return toBase64(nonce);
}

// Generate an ephemeral keypair. The secret key is returned via the out parameter
// as base64 and the public key is returned as the function result (base64).
std::string CryptoHelpers::generateKeypairPublicBase64(std::string& outSecretKeyBase64) {
    std::vector<unsigned char> publicKey(crypto_box_PUBLICKEYBYTES);
    std::vector<unsigned char> secretKey(crypto_box_SECRETKEYBYTES);
    if (crypto_box_keypair(publicKey.data(), secretKey.data()) != 0) {
        throw std::runtime_error("Failed to generate keypair");
    }
    outSecretKeyBase64 = toBase64(secretKey);
    return toBase64(publicKey);
}

// Encrypt `plaintext` using recipient public key and sender secret key.
// Returns ciphertext as base64 and fills `outNonceBase64` with the generated nonce.
std::string CryptoHelpers::encryptMessage(const std::string& plaintext,
                                          const std::string& recipientPublicKeyBase64,
                                          const std::string& senderSecretKeyBase64,
                                          std::string& outNonceBase64) {
    auto recipientPublicKey = fromBase64(recipientPublicKeyBase64);
    auto senderSecretKey = fromBase64(senderSecretKeyBase64);
    if (recipientPublicKey.size() != crypto_box_PUBLICKEYBYTES || senderSecretKey.size() != crypto_box_SECRETKEYBYTES) {
        throw std::runtime_error("Invalid key sizes for encryption");
    }

    std::vector<unsigned char> nonce(crypto_box_NONCEBYTES);
    randombytes_buf(nonce.data(), nonce.size());
    outNonceBase64 = toBase64(nonce);

    // ciphertext length = plaintext length + MAC
    std::vector<unsigned char> ciphertext(plaintext.size() + crypto_box_MACBYTES);
    if (crypto_box_easy(ciphertext.data(), reinterpret_cast<const unsigned char*>(plaintext.data()), plaintext.size(), nonce.data(), recipientPublicKey.data(), senderSecretKey.data()) != 0) {
        throw std::runtime_error("Encryption failed");
    }

    return toBase64(ciphertext);
}

std::string CryptoHelpers::decryptMessage(const std::string& ciphertextBase64,
                                          const std::string& nonceBase64,
                                          const std::string& senderPublicKeyBase64,
                                          const std::string& recipientSecretKeyBase64) {
    auto ciphertext = fromBase64(ciphertextBase64);
    auto nonce = fromBase64(nonceBase64);
    auto senderPublicKey = fromBase64(senderPublicKeyBase64);
    auto recipientSecretKey = fromBase64(recipientSecretKeyBase64);

    if (nonce.size() != crypto_box_NONCEBYTES || senderPublicKey.size() != crypto_box_PUBLICKEYBYTES || recipientSecretKey.size() != crypto_box_SECRETKEYBYTES) {
        throw std::runtime_error("Invalid sizes for decryption inputs");
    }

    std::vector<unsigned char> plaintext(ciphertext.size() - crypto_box_MACBYTES);
    if (crypto_box_open_easy(plaintext.data(), ciphertext.data(), ciphertext.size(), nonce.data(), senderPublicKey.data(), recipientSecretKey.data()) != 0) {
        throw std::runtime_error("Decryption failed or message forged");
    }

    return std::string(reinterpret_cast<char*>(plaintext.data()), plaintext.size());
}

} // namespace Client
