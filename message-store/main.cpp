#include "MessageStore.h"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <cstdlib>
#include <string>

using namespace std;
using json = nlohmann::json;

static string cachePath() {
    const char* home = getenv("HOME");
    return string(home ? home : ".") + "/.zebra/messages.json";
}

static string str(const json& j, const string& key) {
    if (j.contains(key) && j[key].is_string()) return j[key].get<string>();
    return "";
}

int main(int argc, char* argv[]) {
    string path = (argc > 1) ? argv[1] : cachePath();

    ifstream f(path);
    if (!f.is_open()) {
        cerr << "[zebra-store] cache not found: " << path << "\n";
        return 1;
    }

    json root;
    try {
        f >> root;
    } catch (const json::parse_error& e) {
        cerr << "[zebra-store] parse error: " << e.what() << "\n";
        return 1;
    }

    if (!root.is_array()) {
        cerr << "[zebra-store] expected a JSON array of messages\n";
        return 1;
    }

    MessageStore store;
    for (const auto& item : root) {
        Message m;
        m.id              = str(item, "messageId");
        m.senderId        = str(item, "sender_id");
        m.recipientId     = str(item, "recipient_id");
        m.ciphertext      = str(item, "ciphertext");
        m.nonce           = str(item, "nonce");
        m.senderPublicKey = str(item, "senderPublicKey");
        m.createdAt       = str(item, "created_at");
        store.add(m);
    }

    auto convs = store.conversations();
    cout << "\n=== Zebra local message store ===\n";
    cout << root.size() << " messages, " << convs.size() << " conversation(s)\n\n";

    for (const auto& conv : convs) {
        string peerName = conv.peerId;
        // Try to get a username from the first message in the conversation
        for (const auto& item : root) {
            if (str(item, "sender_id") == conv.peerId && item.contains("sender_username"))
                { peerName = str(item, "sender_username"); break; }
            if (str(item, "recipient_id") == conv.peerId && item.contains("recipient_username"))
                { peerName = str(item, "recipient_username"); break; }
        }
        cout << "  [" << peerName << "]  " << conv.messages.size() << " message(s)\n";
        for (const auto& m : conv.messages)
            cout << "    " << m.createdAt << "  id=" << m.id << "\n";
    }
    cout << "\n";
    return 0;
}
