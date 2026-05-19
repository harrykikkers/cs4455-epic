#include "Client/ApiClient.h"
#include "Client/CryptoHelpers.h"
#include "Client/JsonHelpers.h"
#include "Client/Models.h"
#include <iostream>
#include <stdexcept>
#include <sodium.h>
#include <curl/curl.h>

using namespace std;
using namespace Client;

// Improved CLI flow:
// - initialize libsodium and libcurl once
// - register/login, publish key
// - fetch recipient public key from server (GET /api/keys/:userId)
// - encrypt, send, then fetch inbox and attempt to decrypt messages addressed to this user
int main(int argc, char* argv[]) {
    try {
        cout << "Epic Secure Messenger C++ Client" << endl;

        // Initialize libsodium once per process
        if (sodium_init() < 0) {
            cerr << "libsodium initialization failed" << endl;
            return EXIT_FAILURE;
        }

        // Initialize libcurl once per process
        curl_global_init(CURL_GLOBAL_DEFAULT);

        const string baseUrl = argc > 1 ? argv[1] : "https://localhost:3000";
        ApiClient api(baseUrl);

        string username;
        string email;
        string password;

        cout << "Username: ";
        getline(cin, username);
        cout << "Email: ";
        getline(cin, email);
        cout << "Password: ";
        getline(cin, password);

        auto registerResponse = api.registerUser(username, email, password);
        cout << "Register response: " << JsonHelpers::toString(registerResponse) << endl;

        auto loginResponse = api.login(username, password);
        cout << "Login response: " << JsonHelpers::toString(loginResponse) << endl;

        if (!loginResponse.contains("data") || !loginResponse["data"].contains("token") || !loginResponse["data"].contains("user")) {
            throw runtime_error("Login did not return expected data");
        }

        string currentUserId = loginResponse["data"]["user"].value("id", string{});

        // Generate an ephemeral keypair for this client run. In production, consider
        // a persistent keypair or OS keyring with explicit user consent.
        string senderSecretKeyBase64;
        string senderPublicKeyBase64 = CryptoHelpers::generateKeypairPublicBase64(senderSecretKeyBase64);
        cout << "Generated ephemeral keypair" << endl;

        auto publishResponse = api.publishPublicKey(senderPublicKeyBase64, "x25519");
        cout << "Publish key response: " << JsonHelpers::toString(publishResponse) << endl;

        string recipientId;
        cout << "Recipient user ID: ";
        getline(cin, recipientId);

        // Fetch recipient's public key from server instead of manual paste.
        auto keyResp = api.getPublicKey(recipientId);
        string recipientPublicKeyBase64;
        if (keyResp.contains("data") && keyResp["data"].contains("public_key")) {
            recipientPublicKeyBase64 = keyResp["data"]["public_key"].get<string>();
        } else {
            throw runtime_error("Failed to retrieve recipient public key");
        }

        string plaintext;
        cout << "Message: ";
        getline(cin, plaintext);

        // Encrypt the message locally. Server never sees plaintext.
        string nonce;
        string ciphertext = CryptoHelpers::encryptMessage(plaintext, recipientPublicKeyBase64, senderSecretKeyBase64, nonce);
        cout << "Encrypted message ciphertext: " << ciphertext << endl;

        auto sendResponse = api.sendEncryptedMessage(recipientId, ciphertext, nonce, senderPublicKeyBase64);
        cout << "Send response: " << JsonHelpers::toString(sendResponse) << endl;

        // Fetch inbox and attempt to decrypt messages addressed to current user.
        auto inboxResponse = api.getInbox();
        cout << "Inbox (raw): " << JsonHelpers::toString(inboxResponse) << endl;

        vector<Message> messages;
        if (inboxResponse.contains("data") && inboxResponse["data"].is_array()) {
            for (const auto& item : inboxResponse["data"]) {
                messages.push_back(Message::fromJson(item));
            }
        }

        // Use STL algorithms + lambda as required by rubric
        auto it = find_if(messages.begin(), messages.end(), [&](const Message& m) {
            return m.recipientId == currentUserId;
        });

        if (it != messages.end()) {
            try {
                string plain = CryptoHelpers::decryptMessage(it->ciphertext, it->nonce, it->senderPublicKey, senderSecretKeyBase64);
                cout << "Decrypted first message addressed to me: " << plain << endl;
            } catch (const exception& ex) {
                cerr << "Failed to decrypt message: " << ex.what() << endl;
            }
        }

        // Clean up libcurl
        curl_global_cleanup();
    } catch (const exception& ex) {
        cerr << "Error: " << ex.what() << endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
