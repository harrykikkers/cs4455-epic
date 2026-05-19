#include "Client/ApiClient.h"
#include "Client/CryptoHelpers.h"
#include "Client/JsonHelpers.h"
#include "Client/Models.h"
#include <iostream>
#include <stdexcept>
#include <filesystem>
#include <cstdlib>
#include <sodium.h>
#include <curl/curl.h>

using namespace std;
using namespace Client;
namespace fs = filesystem;

struct CurlGuard {
    CurlGuard()  { curl_global_init(CURL_GLOBAL_DEFAULT); }
    ~CurlGuard() { curl_global_cleanup(); }
};

// Zeros a string's memory on destruction — guarantees the secret key is wiped
// even if an exception unwinds the stack before the end of main's try block.
struct ZeroOnExit {
    string& s;
    ~ZeroOnExit() { if (!s.empty()) sodium_memzero(s.data(), s.size()); }
};

static vector<Message> showInbox(ApiClient& api, MessageStore& store,
                                  const string& myUserId, const string& secretKey) {
    auto resp = api.getInbox();
    store = MessageStore{};
    if (resp.contains("data") && resp["data"].is_array()) {
        for (const auto& item : resp["data"])
            store.add(Message::fromJson(item));
    }

    auto convs = store.conversations(myUserId);
    if (convs.empty()) { cout << "Inbox is empty.\n"; return {}; }

    // Build a flat list in the same order as displayed so that the index
    // shown to the user always matches what we look up later.
    vector<Message> displayed;
    for (const auto& conv : convs) {
        cout << "\n--- From " << conv.peerId << " ---\n";
        for (const auto& m : conv.messages) {
            cout << "[" << displayed.size() << "] id=" << m.id
                 << "  at=" << m.createdAt << "\n";
            try {
                string plain = CryptoHelpers::decryptMessage(
                    m.ciphertext, m.nonce, m.senderPublicKey, secretKey);
                cout << "    " << plain << "\n";
            } catch (...) {
                cout << "    (encrypted for a different keypair — cannot decrypt)\n";
            }
            displayed.push_back(m);
        }
    }
    return displayed;
}

static void showSent(ApiClient& api) {
    auto resp = api.getSent();
    if (!resp.contains("data") || !resp["data"].is_array()) {
        cout << "No sent messages.\n";
        return;
    }
    const auto& data = resp["data"];
    if (data.empty()) { cout << "No sent messages.\n"; return; }
    for (size_t i = 0; i < data.size(); ++i) {
        auto m = Message::fromJson(data[i]);
        cout << "[" << i << "] id=" << m.id
             << "  to=" << m.recipientId
             << "  at=" << m.createdAt << "\n"
             // Sent messages are encrypted with the recipient's public key —
             // only the recipient can decrypt them.
             << "    (encrypted — only the recipient can read this)\n";
    }
}

static bool parseIndex(const string& s, size_t& out, size_t maxExclusive) {
    try { out = stoul(s); } catch (...) { cerr << "Invalid number.\n"; return false; }
    if (out >= maxExclusive) { cerr << "Out of range.\n"; return false; }
    return true;
}

int main(int argc, char* argv[]) {
    // libsodium must be initialised before any crypto call.
    if (sodium_init() < 0) {
        cerr << "libsodium initialization failed\n";
        return EXIT_FAILURE;
    }

    CurlGuard curlGuard;

    try {
        const string baseUrl = argc > 1 ? argv[1] : "https://localhost:3000";
        ApiClient api(baseUrl);

        cout << "=== Epic Secure Messenger ===\n"
             << "Server: " << baseUrl << "\n\n";

        // --- Authentication ---
        cout << "1) Register  2) Login\n> ";
        string mode;
        getline(cin, mode);

        string username, password;
        cout << "Username: "; getline(cin, username);
        cout << "Password: "; getline(cin, password);

        if (mode == "1") {
            string email;
            cout << "Email: "; getline(cin, email);
            api.registerUser(username, email, password);
            cout << "Registered successfully.\n";
        }

        auto loginResp = api.login(username, password);
        if (!loginResp.contains("data") || !loginResp["data"].contains("user"))
            throw runtime_error("Login failed — check your credentials");

        string myUserId = loginResp["data"]["user"].value("id", string{});
        cout << "Logged in. User ID: " << myUserId << "\n";

        // --- Keypair (persistent across runs) ---
        // Store the encrypted private key in ~/.epic_client/<username>.key
        // so old messages remain decryptable after restart.
        const char* home = getenv("HOME");
        string keyDir = home ? string(home) + "/.epic_client" : ".epic_client";
        fs::create_directories(keyDir);
        string keyPath = keyDir + "/" + username + ".key";

        string secretKey, publicKey;
        ZeroOnExit zeroSecretKey{secretKey};
        if (fs::exists(keyPath)) {
            cout << "Loading saved keypair...\n";
            secretKey = CryptoHelpers::loadSecretKey(keyPath, password);
            // Derive public key from secret key — no need to store it separately.
            publicKey = CryptoHelpers::publicKeyFromSecretKey(secretKey);
        } else {
            cout << "Generating new keypair...\n";
            publicKey = CryptoHelpers::generateKeypairPublicBase64(secretKey);
            CryptoHelpers::saveSecretKey(keyPath, secretKey, password);
        }

        // Always publish so the server has the current public key for this user.
        api.publishPublicKey(publicKey, "x25519");
        cout << "Keypair ready.\n";

        // --- Menu loop ---
        MessageStore store;

        while (true) {
            cout << "\n1) Send message\n"
                 << "2) View inbox\n"
                 << "3) View sent messages\n"
                 << "4) Forward a message\n"
                 << "5) Revoke access to a message\n"
                 << "6) Download a message\n"
                 << "7) Delete a message\n"
                 << "8) Quit\n> ";
            string choice;
            if (!getline(cin, choice)) break;

            if (choice == "1") {
                string recipientId;
                cout << "Recipient user ID: ";
                getline(cin, recipientId);

                auto keyResp = api.getPublicKey(recipientId);
                if (!keyResp.contains("data") || !keyResp["data"].contains("public_key")) {
                    cerr << "Could not fetch recipient public key.\n";
                    continue;
                }
                string recipientPubKey = keyResp["data"]["public_key"].get<string>();

                string plaintext;
                cout << "Message: ";
                getline(cin, plaintext);

                string nonce;
                string ciphertext = CryptoHelpers::encryptMessage(
                    plaintext, recipientPubKey, secretKey, nonce);
                api.sendEncryptedMessage(recipientId, ciphertext, nonce, publicKey);
                cout << "Message sent.\n";

            } else if (choice == "2") {
                showInbox(api, store, myUserId, secretKey);

            } else if (choice == "3") {
                showSent(api);

            } else if (choice == "4") {
                // Decrypt a received message and re-encrypt it for a new recipient.
                auto msgs = showInbox(api, store, myUserId, secretKey);
                if (msgs.empty()) continue;

                cout << "Message number to forward: ";
                string s; getline(cin, s);
                size_t idx;
                if (!parseIndex(s, idx, msgs.size())) continue;

                string plaintext;
                try {
                    plaintext = CryptoHelpers::decryptMessage(
                        msgs[idx].ciphertext, msgs[idx].nonce,
                        msgs[idx].senderPublicKey, secretKey);
                } catch (...) {
                    cerr << "Cannot forward — could not decrypt this message.\n";
                    continue;
                }

                string recipientId;
                cout << "Forward to user ID: ";
                getline(cin, recipientId);

                auto keyResp = api.getPublicKey(recipientId);
                if (!keyResp.contains("data") || !keyResp["data"].contains("public_key")) {
                    cerr << "Could not fetch recipient public key.\n";
                    continue;
                }

                string nonce;
                string ciphertext = CryptoHelpers::encryptMessage(
                    plaintext, keyResp["data"]["public_key"].get<string>(), secretKey, nonce);
                api.forwardMessage(msgs[idx].id, recipientId, ciphertext, nonce);
                cout << "Message forwarded.\n";

            } else if (choice == "5") {
                auto msgs = showInbox(api, store, myUserId, secretKey);
                if (msgs.empty()) continue;

                cout << "Message number: ";
                string s; getline(cin, s);
                size_t idx;
                if (!parseIndex(s, idx, msgs.size())) continue;

                string targetUserId;
                cout << "Revoke access for user ID: ";
                getline(cin, targetUserId);

                api.revokeAccess(msgs[idx].id, targetUserId);
                cout << "Access revoked.\n";

            } else if (choice == "6") {
                cout << "Message ID to download: ";
                string msgId; getline(cin, msgId);

                // Use findById to check if it's already in the local store first.
                const Message* cached = store.findById(msgId);
                if (cached) {
                    cout << "id=" << cached->id
                         << "  from=" << cached->senderId
                         << "  at="   << cached->createdAt << "\n";
                    try {
                        string plain = CryptoHelpers::decryptMessage(
                            cached->ciphertext, cached->nonce,
                            cached->senderPublicKey, secretKey);
                        cout << plain << "\n";
                    } catch (...) {
                        cout << "(encrypted for a different keypair — cannot decrypt)\n";
                    }
                } else {
                    // Not cached — fetch from server.
                    auto resp = api.getMessage(msgId);
                    if (!resp.contains("data")) {
                        cerr << "Message not found.\n";
                        continue;
                    }
                    auto m = Message::fromJson(resp["data"]);
                    cout << "id=" << m.id
                         << "  from=" << m.senderId
                         << "  at="   << m.createdAt << "\n";
                    try {
                        string plain = CryptoHelpers::decryptMessage(
                            m.ciphertext, m.nonce, m.senderPublicKey, secretKey);
                        cout << plain << "\n";
                    } catch (...) {
                        cout << "(encrypted for a different keypair — cannot decrypt)\n";
                    }
                }

            } else if (choice == "7") {
                string msgId;
                cout << "Message ID to delete: ";
                getline(cin, msgId);
                api.deleteMessage(msgId);
                cout << "Deleted.\n";

            } else if (choice == "8") {
                break;
            } else {
                cout << "Unknown option.\n";
            }
        }

    } catch (const exception& ex) {
        cerr << "Fatal error: " << ex.what() << "\n";
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
