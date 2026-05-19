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

// RAII guard — the constructor runs setup, the destructor runs cleanup automatically.
// In Python terms: like a "with" block. curl_global_cleanup() is guaranteed to run
// even if an exception is thrown, because C++ always calls destructors on scope exit.
struct CurlGuard {
    CurlGuard()  { curl_global_init(CURL_GLOBAL_DEFAULT); }
    ~CurlGuard() { curl_global_cleanup(); }
};

// Same RAII pattern — destructor overwrites the secret key's memory with zeroes
// the moment this struct goes out of scope. Needed because C++ strings sit in heap
// memory that could be read by another process after deallocation if not wiped.
// Python's garbage collector handles this automatically; C++ does not.
struct ZeroOnExit {
    string& s;
    ~ZeroOnExit() { if (!s.empty()) sodium_memzero(s.data(), s.size()); }
};

static bool parseIndex(const string& s, size_t& out, size_t maxExclusive) {
    try { out = stoul(s); } catch (...) { cerr << "Invalid number.\n"; return false; }
    if (out >= maxExclusive) { cerr << "Out of range.\n"; return false; }
    return true;
}

// Fetches received messages, groups them into conversations, and lists the peers.
// Returns the conversations so the caller can let the user pick one.
static vector<Conversation> listConversations(ApiClient& api, MessageStore& store,
                                              const string& myUserId) {
    auto resp = api.getInbox();
    store = MessageStore{};
    if (resp.contains("data") && resp["data"].is_array()) {
        for (const auto& item : resp["data"])
            store.add(Message::fromJson(item));
    }
    auto convs = store.conversations(myUserId);
    if (convs.empty()) { cout << "No conversations yet.\n"; return {}; }
    cout << "\n--- Conversations ---\n";
    for (size_t i = 0; i < convs.size(); ++i) {
        cout << "[" << i << "] " << convs[i].peerId
             << "  (" << convs[i].messages.size() << " message"
             << (convs[i].messages.size() == 1 ? "" : "s") << ")\n";
    }
    return convs;
}

// Displays all messages in one conversation thread and returns them for indexing.
static vector<Message> showThread(const Conversation& conv, const string& secretKey) {
    cout << "\n--- Thread with " << conv.peerId << " ---\n";
    for (size_t i = 0; i < conv.messages.size(); ++i) {
        const auto& m = conv.messages[i];
        cout << "[" << i << "] " << m.createdAt << "  id=" << m.id << "\n";
        try {
            string plain = CryptoHelpers::decryptMessage(
                m.ciphertext, m.nonce, m.senderPublicKey, secretKey);
            cout << "    " << plain << "\n";
        } catch (...) {
            cout << "    (encrypted for a different keypair — cannot decrypt)\n";
        }
    }
    return conv.messages;
}

static void showSent(ApiClient& api) {
    auto resp = api.getSent();
    if (!resp.contains("data") || !resp["data"].is_array()) {
        cout << "No sent messages.\n";
        return;
    }
    const auto& data = resp["data"];
    if (data.empty()) { cout << "No sent messages.\n"; return; }
    cout << "\n--- Sent messages ---\n";
    for (size_t i = 0; i < data.size(); ++i) {
        auto m = Message::fromJson(data[i]);
        cout << "[" << i << "] " << m.createdAt
             << "  to=" << m.recipientId
             << "  id=" << m.id << "\n"
             // Sent messages are encrypted with the recipient's public key —
             // only the recipient can decrypt them.
             << "    (encrypted — only the recipient can read this)\n";
    }
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
                 << "2) View conversations\n"
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
                // List conversations, let the user pick one to open as a thread.
                auto convs = listConversations(api, store, myUserId);
                if (convs.empty()) continue;

                cout << "Conversation number (or Enter to go back): ";
                string s; getline(cin, s);
                if (s.empty()) continue;
                size_t idx;
                if (!parseIndex(s, idx, convs.size())) continue;

                showThread(convs[idx], secretKey);

            } else if (choice == "3") {
                showSent(api);

            } else if (choice == "4") {
                cout << "Message ID to forward: ";
                string msgId; getline(cin, msgId);

                auto resp = api.getMessage(msgId);
                if (!resp.contains("data")) { cerr << "Message not found.\n"; continue; }
                auto m = Message::fromJson(resp["data"]);

                string plaintext;
                try {
                    plaintext = CryptoHelpers::decryptMessage(
                        m.ciphertext, m.nonce, m.senderPublicKey, secretKey);
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
                api.forwardMessage(m.id, recipientId, ciphertext, nonce);
                cout << "Message forwarded.\n";

            } else if (choice == "5") {
                cout << "Message ID to revoke: ";
                string msgId; getline(cin, msgId);

                string targetUserId;
                cout << "Revoke access for user ID: ";
                getline(cin, targetUserId);

                api.revokeAccess(msgId, targetUserId);
                cout << "Access revoked.\n";

            } else if (choice == "6") {
                cout << "Message ID to download: ";
                string msgId; getline(cin, msgId);

                // Check local store first before hitting the network.
                const Message* cached = store.findById(msgId);
                if (cached) {
                    cout << "from=" << cached->senderId
                         << "  at=" << cached->createdAt << "\n";
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
                    cout << "from=" << m.senderId
                         << "  at=" << m.createdAt << "\n";
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
