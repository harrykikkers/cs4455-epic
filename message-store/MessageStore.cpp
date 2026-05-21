#include "MessageStore.h"
#include <algorithm>
#include <map>

using namespace std;

void MessageStore::add(const Message& m) {
    _messages.push_back(m);
}

vector<Message> MessageStore::inbox(const string& myUserId) const {
    vector<Message> result;
    copy_if(_messages.begin(), _messages.end(), back_inserter(result),
            [&](const Message& m) { return m.recipientId == myUserId; });
    return result;
}

vector<Conversation> MessageStore::conversations() const {
    map<string, Conversation> convMap;
    for (const auto& m : _messages) {
        auto& conv = convMap[m.senderId];
        conv.peerId = m.senderId;
        conv.messages.push_back(m);
    }
    vector<Conversation> result;
    for (auto& [peerId, conv] : convMap) {
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
