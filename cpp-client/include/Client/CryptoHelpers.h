#pragma once

#include <string>
#include <vector>

using namespace std;

namespace Client {
namespace CryptoHelpers {

// --- Messaging crypto (Curve25519 / XSalsa20-Poly1305 via libsodium) ---

// Encrypt plaintext using recipient public key and sender secret key.
// Returns ciphertext (base64) and writes the generated nonce into outNonceBase64.
string encryptMessage(const string& plaintext,
                      const string& recipientPublicKeyBase64,
                      const string& senderSecretKeyBase64,
                      string& outNonceBase64);

// Decrypt a ciphertext produced by encryptMessage. Returns plaintext.
string decryptMessage(const string& ciphertextBase64,
                      const string& nonceBase64,
                      const string& senderPublicKeyBase64,
                      const string& recipientSecretKeyBase64);

// Generate a Curve25519 keypair. Returns public key (base64), sets outSecretKeyBase64.
string generateKeypairPublicBase64(string& outSecretKeyBase64);

// Derive the public key that corresponds to a given secret key (both base64).
string publicKeyFromSecretKey(const string& secretKeyBase64);

// --- Key persistence (Argon2id + XSalsa20-Poly1305) ---

// Encrypt the secret key with the user's password and save to a file.
// File layout: Argon2id salt | secretbox nonce | encrypted key.
void saveSecretKey(const string& path, const string& secretKeyBase64,
                   const string& password);

// Load and decrypt a saved secret key. Throws on wrong password or corrupt file.
string loadSecretKey(const string& path, const string& password);

// --- Base64 helpers ---
string toBase64(const vector<unsigned char>& data);
vector<unsigned char> fromBase64(const string& text);

} // namespace CryptoHelpers
} // namespace Client
