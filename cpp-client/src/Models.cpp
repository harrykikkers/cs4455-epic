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

vector<Conversation> MessageStore::conversations(const string&) const {
    map<string, Conversation> convMap;
    // Every message in the store is already for the current user (loaded from inbox),
    // so no recipient filter is needed.
    for (const auto& m : _messages) {
        auto& conv = convMap[m.senderId];
        conv.peerId = m.senderId;
        conv.messages.push_back(m);
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
    // In Python this would return the item or None.
    // Here: &*it converts the iterator to a pointer (& = address-of, * = dereference),
    // and nullptr is C++'s equivalent of None.
    return it != _messages.end() ? &*it : nullptr;
}

} // namespace Client
