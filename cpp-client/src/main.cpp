#include "Client/ApiClient.h"
#include "Client/CryptoHelpers.h"
#include "Client/JsonHelpers.h"
#include <iostream>
#include <stdexcept>

using namespace Client;

int main(int argc, char* argv[]) {
    try {
        std::cout << "Epic Secure Messenger C++ Client" << std::endl;

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

        if (!loginResponse.contains("data") || !loginResponse["data"].contains("token")) {
            throw std::runtime_error("Login did not return token");
        }

        std::string senderSecretKeyBase64;
        std::string senderPublicKeyBase64 = CryptoHelpers::generateKeypairPublicBase64(senderSecretKeyBase64);
        std::cout << "Generated ephemeral keypair" << std::endl;

        auto publishResponse = api.publishPublicKey(senderPublicKeyBase64, "x25519");
        std::cout << "Publish key response: " << JsonHelpers::toString(publishResponse) << std::endl;

        std::string recipientId;
        std::cout << "Recipient user ID: ";
        std::getline(std::cin, recipientId);

        std::string recipientPublicKeyBase64;
        std::cout << "Recipient public key base64: ";
        std::getline(std::cin, recipientPublicKeyBase64);

        std::string plaintext;
        std::cout << "Message: ";
        std::getline(std::cin, plaintext);

        std::string nonce;
        std::string ciphertext = CryptoHelpers::encryptMessage(plaintext, recipientPublicKeyBase64, senderSecretKeyBase64, nonce);
        std::cout << "Encrypted message ciphertext: " << ciphertext << std::endl;

        auto sendResponse = api.sendEncryptedMessage(recipientId, ciphertext, nonce, senderPublicKeyBase64);
        std::cout << "Send response: " << JsonHelpers::toString(sendResponse) << std::endl;

        auto inboxResponse = api.getInbox();
        std::cout << "Inbox: " << JsonHelpers::toString(inboxResponse) << std::endl;
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
