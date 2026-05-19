#include "Client/Models.h"
#include <algorithm>
#include <map>

using namespace std;

namespace Client {

User User::fromJson(const Json& j) {
    return User{
        .id       = j.value("id",       string{}),
        .username = j.value("username", string{}),
        .email    = j.value("email",    string{})
    };
}

Message Message::fromJson(const Json& j) {
    return Message{
        .id              = j.value("id",                string{}),
        .senderId        = j.value("sender_id",         string{}),
        .recipientId     = j.value("recipient_id",      string{}),
        .ciphertext      = j.value("ciphertext",        string{}),
        .nonce           = j.value("nonce",             string{}),
        .senderPublicKey = j.value("sender_public_key", string{}),
        .createdAt       = j.value("created_at",        string{})
    };
}

void MessageStore::add(const Message& m) {
    _messages.push_back(m);
}

vector<Message> MessageStore::inbox(const string& myUserId) const {
    vector<Message> result;
    copy_if(_messages.begin(), _messages.end(), back_inserter(result),
            [&](const Message& m) { return m.recipientId == myUserId; });
    return result;
}

vector<Conversation> MessageStore::conversations(const string& myUserId) const {
    map<string, Conversation> convMap;
    for (const auto& m : _messages) {
        if (m.recipientId == myUserId) {
            auto& conv = convMap[m.senderId];
            conv.peerId = m.senderId;
            conv.messages.push_back(m);
        }
    }
    vector<Conversation> result;
    for (auto& [peerId, conv] : convMap) {
        // Sort each conversation's messages chronologically by creation timestamp.
        sort(conv.messages.begin(), conv.messages.end(),
             [](const Message& a, const Message& b) { return a.createdAt < b.createdAt; });
        result.push_back(move(conv));
    }
    return result;
}

const Message* MessageStore::findById(const string& id) const {
    auto it = find_if(_messages.begin(), _messages.end(),
                      [&](const Message& m) { return m.id == id; });
    return it != _messages.end() ? &*it : nullptr;
}

} // namespace Client
