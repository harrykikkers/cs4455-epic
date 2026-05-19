#pragma once

#include <string>
#include <vector>

namespace Client {

// Thin libsodium-based helpers.
// - Keys and nonces are encoded as base64 strings for JSON transport.
// - This module focuses on correct use of `crypto_box`; it does not
//   provide secure key storage — callers must protect secret keys.
class CryptoHelpers {
public:
    // Create a base64-encoded nonce suitable for the `crypto_box` API.
    static std::string generateBase64Nonce();

    // Encrypt plaintext using recipient public key and sender secret key.
    // Returns ciphertext (base64) and writes base64 nonce into outNonceBase64.
    static std::string encryptMessage(const std::string& plaintext,
                                      const std::string& recipientPublicKeyBase64,
                                      const std::string& senderSecretKeyBase64,
                                      std::string& outNonceBase64);

    // Generate a keypair. Returns public key (base64) and sets outSecretKeyBase64.
    static std::string generateKeypairPublicBase64(std::string& outSecretKeyBase64);

    // Base64 helpers for binary <-> text conversion.
    static std::string toBase64(const std::vector<unsigned char>& data);
    static std::vector<unsigned char> fromBase64(const std::string& text);
    // Decrypt a ciphertext produced by crypto_box_easy. Returns plaintext.
    static std::string decryptMessage(const std::string& ciphertextBase64,
                                      const std::string& nonceBase64,
                                      const std::string& senderPublicKeyBase64,
                                      const std::string& recipientSecretKeyBase64);
};

} // namespace Client
