#include "Client/CryptoHelpers.h"
#include <sodium.h>
#include <stdexcept>
#include <vector>

namespace Client {

namespace {
const char b64Chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
}

std::string CryptoHelpers::toBase64(const std::vector<unsigned char>& data) {
    size_t encodedLen = sodium_base64_encoded_len(data.size(), sodium_base64_VARIANT_ORIGINAL);
    std::string encoded(encodedLen, '\0');
    sodium_bin2base64(encoded.data(), encodedLen, data.data(), data.size(), sodium_base64_VARIANT_ORIGINAL);
    if (!encoded.empty() && encoded.back() == '\0') {
        encoded.pop_back();
    }
    return encoded;
}

std::vector<unsigned char> CryptoHelpers::fromBase64(const std::string& text) {
    std::vector<unsigned char> decoded(text.size());
    size_t decodedLen = 0;
    if (sodium_base642bin(decoded.data(), decoded.size(), text.c_str(), text.size(), nullptr, &decodedLen, nullptr, sodium_base64_VARIANT_ORIGINAL) != 0) {
        throw std::runtime_error("Base64 decode failed");
    }
    decoded.resize(decodedLen);
    return decoded;
}

std::string CryptoHelpers::generateBase64Nonce() {
    std::vector<unsigned char> nonce(crypto_box_NONCEBYTES);
    randombytes_buf(nonce.data(), nonce.size());
    return toBase64(nonce);
}

std::string CryptoHelpers::generateKeypairPublicBase64(std::string& outSecretKeyBase64) {
    std::vector<unsigned char> publicKey(crypto_box_PUBLICKEYBYTES);
    std::vector<unsigned char> secretKey(crypto_box_SECRETKEYBYTES);
    if (crypto_box_keypair(publicKey.data(), secretKey.data()) != 0) {
        throw std::runtime_error("Failed to generate keypair");
    }
    outSecretKeyBase64 = toBase64(secretKey);
    return toBase64(publicKey);
}

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

    std::vector<unsigned char> ciphertext(plaintext.size() + crypto_box_MACBYTES);
    if (crypto_box_easy(ciphertext.data(), reinterpret_cast<const unsigned char*>(plaintext.data()), plaintext.size(), nonce.data(), recipientPublicKey.data(), senderSecretKey.data()) != 0) {
        throw std::runtime_error("Encryption failed");
    }

    return toBase64(ciphertext);
}

} // namespace Client
