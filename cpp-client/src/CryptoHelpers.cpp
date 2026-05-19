// Cryptography helpers using libsodium.
//
// Messaging: crypto_box_easy (Curve25519 key agreement + XSalsa20-Poly1305 AEAD).
//   The MAC inside crypto_box guarantees both confidentiality and integrity —
//   the recipient can verify the message is unmodified and came from the sender.
//
// Key persistence: Argon2id (crypto_pwhash) to derive a symmetric key from the
//   user's password, then crypto_secretbox_easy to encrypt the private key at rest.
//   Argon2id is memory-hard, making brute-force attacks expensive.

#include "Client/CryptoHelpers.h"
#include <sodium.h>
#include <fstream>
#include <stdexcept>
#include <vector>

using namespace std;

namespace Client {
namespace CryptoHelpers {

// --- Base64 ---

string toBase64(const vector<unsigned char>& data) {
    size_t len = sodium_base64_encoded_len(data.size(), sodium_base64_VARIANT_ORIGINAL);
    string out(len, '\0');
    sodium_bin2base64(out.data(), len, data.data(), data.size(),
                      sodium_base64_VARIANT_ORIGINAL);
    if (!out.empty() && out.back() == '\0') out.pop_back();
    return out;
}

vector<unsigned char> fromBase64(const string& text) {
    vector<unsigned char> out(text.size());
    size_t outLen = 0;
    if (sodium_base642bin(out.data(), out.size(), text.c_str(), text.size(),
                          nullptr, &outLen, nullptr,
                          sodium_base64_VARIANT_ORIGINAL) != 0) {
        throw runtime_error("Base64 decode failed");
    }
    out.resize(outLen);
    return out;
}

// --- Keypair ---

string generateKeypairPublicBase64(string& outSecretKeyBase64) {
    vector<unsigned char> pub(crypto_box_PUBLICKEYBYTES);
    vector<unsigned char> sec(crypto_box_SECRETKEYBYTES);
    if (crypto_box_keypair(pub.data(), sec.data()) != 0)
        throw runtime_error("Failed to generate keypair");
    outSecretKeyBase64 = toBase64(sec);
    sodium_memzero(sec.data(), sec.size());
    return toBase64(pub);
}

// Curve25519: public key = secret key * base point.
// This lets us store only the secret key and always re-derive the public key.
string publicKeyFromSecretKey(const string& secretKeyBase64) {
    auto sec = fromBase64(secretKeyBase64);
    vector<unsigned char> pub(crypto_box_PUBLICKEYBYTES);
    crypto_scalarmult_base(pub.data(), sec.data());
    sodium_memzero(sec.data(), sec.size());
    return toBase64(pub);
}

// --- Messaging ---

string encryptMessage(const string& plaintext,
                      const string& recipientPublicKeyBase64,
                      const string& senderSecretKeyBase64,
                      string& outNonceBase64) {
    auto recipientPub = fromBase64(recipientPublicKeyBase64);
    auto senderSec    = fromBase64(senderSecretKeyBase64);

    if (recipientPub.size() != crypto_box_PUBLICKEYBYTES ||
        senderSec.size()    != crypto_box_SECRETKEYBYTES) {
        sodium_memzero(senderSec.data(), senderSec.size());
        throw runtime_error("Invalid key sizes for encryption");
    }

    // libsodium's CSPRNG draws from the OS entropy source (e.g. /dev/urandom).
    vector<unsigned char> nonce(crypto_box_NONCEBYTES);
    randombytes_buf(nonce.data(), nonce.size());
    outNonceBase64 = toBase64(nonce);

    // ciphertext = plaintext + 16-byte Poly1305 MAC appended by crypto_box_easy
    vector<unsigned char> ciphertext(plaintext.size() + crypto_box_MACBYTES);
    int encRc = crypto_box_easy(ciphertext.data(),
                                reinterpret_cast<const unsigned char*>(plaintext.data()),
                                plaintext.size(), nonce.data(),
                                recipientPub.data(), senderSec.data());
    sodium_memzero(senderSec.data(), senderSec.size());
    if (encRc != 0) throw runtime_error("Encryption failed");
    return toBase64(ciphertext);
}

string decryptMessage(const string& ciphertextBase64,
                      const string& nonceBase64,
                      const string& senderPublicKeyBase64,
                      const string& recipientSecretKeyBase64) {
    auto ciphertext   = fromBase64(ciphertextBase64);
    auto nonce        = fromBase64(nonceBase64);
    auto senderPub    = fromBase64(senderPublicKeyBase64);
    auto recipientSec = fromBase64(recipientSecretKeyBase64);

    if (nonce.size()        != crypto_box_NONCEBYTES     ||
        senderPub.size()    != crypto_box_PUBLICKEYBYTES ||
        recipientSec.size() != crypto_box_SECRETKEYBYTES) {
        sodium_memzero(recipientSec.data(), recipientSec.size());
        throw runtime_error("Invalid sizes for decryption inputs");
    }

    vector<unsigned char> plain(ciphertext.size() - crypto_box_MACBYTES);
    int decRc = crypto_box_open_easy(plain.data(), ciphertext.data(), ciphertext.size(),
                                     nonce.data(), senderPub.data(), recipientSec.data());
    sodium_memzero(recipientSec.data(), recipientSec.size());
    if (decRc != 0) throw runtime_error("Decryption failed or message forged");
    return string(reinterpret_cast<char*>(plain.data()), plain.size());
}

// --- Key persistence ---

void saveSecretKey(const string& path, const string& secretKeyBase64,
                   const string& password) {
    auto secretKey = fromBase64(secretKeyBase64);

    // Random salt — different every save, so even the same password produces
    // a different derived key each time.
    vector<unsigned char> salt(crypto_pwhash_SALTBYTES);
    randombytes_buf(salt.data(), salt.size());

    // Argon2id: derives a 32-byte symmetric key from the password + salt.
    // INTERACTIVE parameters are tuned to take ~0.1s on typical hardware.
    vector<unsigned char> derivedKey(crypto_secretbox_KEYBYTES);
    if (crypto_pwhash(derivedKey.data(), derivedKey.size(),
                      password.c_str(), password.size(), salt.data(),
                      crypto_pwhash_OPSLIMIT_INTERACTIVE,
                      crypto_pwhash_MEMLIMIT_INTERACTIVE,
                      crypto_pwhash_ALG_DEFAULT) != 0) {
        sodium_memzero(secretKey.data(), secretKey.size());
        throw runtime_error("Key derivation failed (out of memory?)");
    }

    vector<unsigned char> nonce(crypto_secretbox_NONCEBYTES);
    randombytes_buf(nonce.data(), nonce.size());

    // secretbox appends a 16-byte MAC so tampering is detected on load.
    vector<unsigned char> ciphertext(secretKey.size() + crypto_secretbox_MACBYTES);
    crypto_secretbox_easy(ciphertext.data(), secretKey.data(), secretKey.size(),
                          nonce.data(), derivedKey.data());
    sodium_memzero(secretKey.data(),  secretKey.size());
    sodium_memzero(derivedKey.data(), derivedKey.size());

    // Write: salt | nonce | ciphertext  (all raw bytes)
    ofstream file(path, ios::binary);
    if (!file) throw runtime_error("Cannot write key file: " + path);
    file.write(reinterpret_cast<const char*>(salt.data()),       salt.size());
    file.write(reinterpret_cast<const char*>(nonce.data()),      nonce.size());
    file.write(reinterpret_cast<const char*>(ciphertext.data()), ciphertext.size());
    if (!file) throw runtime_error("Failed writing key file (disk full?): " + path);
}

string loadSecretKey(const string& path, const string& password) {
    ifstream file(path, ios::binary);
    if (!file) throw runtime_error("Key file not found: " + path);

    vector<unsigned char> salt(crypto_pwhash_SALTBYTES);
    file.read(reinterpret_cast<char*>(salt.data()), salt.size());

    vector<unsigned char> nonce(crypto_secretbox_NONCEBYTES);
    file.read(reinterpret_cast<char*>(nonce.data()), nonce.size());

    vector<unsigned char> ciphertext(
        (istreambuf_iterator<char>(file)), istreambuf_iterator<char>());

    vector<unsigned char> derivedKey(crypto_secretbox_KEYBYTES);
    if (crypto_pwhash(derivedKey.data(), derivedKey.size(),
                      password.c_str(), password.size(), salt.data(),
                      crypto_pwhash_OPSLIMIT_INTERACTIVE,
                      crypto_pwhash_MEMLIMIT_INTERACTIVE,
                      crypto_pwhash_ALG_DEFAULT) != 0) {
        sodium_memzero(derivedKey.data(), derivedKey.size());
        throw runtime_error("Key derivation failed");
    }

    if (ciphertext.size() < crypto_secretbox_MACBYTES) {
        sodium_memzero(derivedKey.data(), derivedKey.size());
        throw runtime_error("Key file is corrupted");
    }

    vector<unsigned char> secretKey(ciphertext.size() - crypto_secretbox_MACBYTES);
    int loadRc = crypto_secretbox_open_easy(secretKey.data(), ciphertext.data(),
                                            ciphertext.size(), nonce.data(), derivedKey.data());
    sodium_memzero(derivedKey.data(), derivedKey.size());
    if (loadRc != 0) throw runtime_error("Wrong password or corrupted key file");
    string result = toBase64(secretKey);
    sodium_memzero(secretKey.data(), secretKey.size());
    return result;
}

} // namespace CryptoHelpers
} // namespace Client
