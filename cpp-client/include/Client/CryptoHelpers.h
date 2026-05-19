#pragma once

#include <string>
#include <vector>

using std::string;
using std::vector;

namespace Client {

// Thin libsodium-based helpers.
// - Keys and nonces are encoded as base64 strings for JSON transport.
// - This module focuses on correct use of `crypto_box`; it does not
//   provide secure key storage — callers must protect secret keys.
class CryptoHelpers {
public:
    // Create a base64-encoded nonce suitable for the `crypto_box` API.
    static string generateBase64Nonce();

    // Encrypt plaintext using recipient public key and sender secret key.
    // Returns ciphertext (base64) and writes base64 nonce into outNonceBase64.
    static string encryptMessage(const string& plaintext,
                                 const string& recipientPublicKeyBase64,
                                 const string& senderSecretKeyBase64,
                                 string& outNonceBase64);

    // Generate a keypair. Returns public key (base64) and sets outSecretKeyBase64.
    static string generateKeypairPublicBase64(string& outSecretKeyBase64);

    // Base64 helpers for binary <-> text conversion.
    static string toBase64(const vector<unsigned char>& data);
    static vector<unsigned char> fromBase64(const string& text);
    // Decrypt a ciphertext produced by crypto_box_easy. Returns plaintext.
    static string decryptMessage(const string& ciphertextBase64,
                                 const string& nonceBase64,
                                 const string& senderPublicKeyBase64,
                                 const string& recipientSecretKeyBase64);
};

} // namespace Client
