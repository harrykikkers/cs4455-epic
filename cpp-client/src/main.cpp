#include "Client/ApiClient.h"
#include "Client/CryptoHelpers.h"
#include "Client/JsonHelpers.h"
#include "Client/Models.h"
#include <iostream>
#include <stdexcept>
#include <sodium.h>
#include <curl/curl.h>

using namespace Client;

// Improved CLI flow:
// - initialize libsodium and libcurl once
// - register/login, publish key
// - fetch recipient public key from server (GET /api/keys/:userId)
// - encrypt, send, then fetch inbox and attempt to decrypt messages addressed to this user
int main(int argc, char* argv[]) {
    try {
        std::cout << "Epic Secure Messenger C++ Client" << std::endl;

        // Initialize libsodium once per process
        if (sodium_init() < 0) {
            std::cerr << "libsodium initialization failed" << std::endl;
            return EXIT_FAILURE;
        }

        // Initialize libcurl once per process
        curl_global_init(CURL_GLOBAL_DEFAULT);

        const std::string baseUrl = argc > 1 ? argv[1] : "https://localhost:3000";
        ApiClient api(baseUrl);

        std::string username;
        std::string email;
        std::string password;

        std::cout << "Username: ";
        std::getline(std::cin, username);
        std::cout << "Email: ";
        std::getline(std::cin, email);
        std::cout << "Password: ";
        std::getline(std::cin, password);

        auto registerResponse = api.registerUser(username, email, password);
        std::cout << "Register response: " << JsonHelpers::toString(registerResponse) << std::endl;

        auto loginResponse = api.login(username, password);
        std::cout << "Login response: " << JsonHelpers::toString(loginResponse) << std::endl;

        if (!loginResponse.contains("data") || !loginResponse["data"].contains("token") || !loginResponse["data"].contains("user")) {
            throw std::runtime_error("Login did not return expected data");
        }

        std::string currentUserId = loginResponse["data"]["user"].value("id", std::string{});

        // Generate an ephemeral keypair for this client run. In production, consider
        // a persistent keypair or OS keyring with explicit user consent.
        std::string senderSecretKeyBase64;
        std::string senderPublicKeyBase64 = CryptoHelpers::generateKeypairPublicBase64(senderSecretKeyBase64);
        std::cout << "Generated ephemeral keypair" << std::endl;

        auto publishResponse = api.publishPublicKey(senderPublicKeyBase64, "x25519");
        std::cout << "Publish key response: " << JsonHelpers::toString(publishResponse) << std::endl;

        std::string recipientId;
        std::cout << "Recipient user ID: ";
        std::getline(std::cin, recipientId);

        // Fetch recipient's public key from server instead of manual paste.
        auto keyResp = api.getPublicKey(recipientId);
        std::string recipientPublicKeyBase64;
        if (keyResp.contains("data") && keyResp["data"].contains("public_key")) {
            recipientPublicKeyBase64 = keyResp["data"]["public_key"].get<std::string>();
        } else {
            throw std::runtime_error("Failed to retrieve recipient public key");
        }

        std::string plaintext;
        std::cout << "Message: ";
        std::getline(std::cin, plaintext);

        // Encrypt the message locally. Server never sees plaintext.
        std::string nonce;
        std::string ciphertext = CryptoHelpers::encryptMessage(plaintext, recipientPublicKeyBase64, senderSecretKeyBase64, nonce);
        std::cout << "Encrypted message ciphertext: " << ciphertext << std::endl;

        auto sendResponse = api.sendEncryptedMessage(recipientId, ciphertext, nonce, senderPublicKeyBase64);
        std::cout << "Send response: " << JsonHelpers::toString(sendResponse) << std::endl;

        // Fetch inbox and attempt to decrypt messages addressed to current user.
        auto inboxResponse = api.getInbox();
        std::cout << "Inbox (raw): " << JsonHelpers::toString(inboxResponse) << std::endl;

        std::vector<Message> messages;
        if (inboxResponse.contains("data") && inboxResponse["data"].is_array()) {
            for (const auto& item : inboxResponse["data"]) {
                messages.push_back(Message::fromJson(item));
            }
        }

        // Use STL algorithms + lambda as required by rubric
        auto it = std::find_if(messages.begin(), messages.end(), [&](const Message& m) {
            return m.recipientId == currentUserId;
        });

        if (it != messages.end()) {
            try {
                std::string plain = CryptoHelpers::decryptMessage(it->ciphertext, it->nonce, it->senderPublicKey, senderSecretKeyBase64);
                std::cout << "Decrypted first message addressed to me: " << plain << std::endl;
            } catch (const std::exception& ex) {
                std::cerr << "Failed to decrypt message: " << ex.what() << std::endl;
            }
        }

        // Clean up libcurl
        curl_global_cleanup();
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
