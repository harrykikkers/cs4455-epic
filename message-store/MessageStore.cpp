#include "MessageStore.h"
#include <algorithm>
#include <map>

void MessageStore::add(const Message& m) {
    _messages.push_back(m);
}

std::vector<Message> MessageStore::inbox(const std::string& myUserId) const {
    std::vector<Message> result;
    std::copy_if(_messages.begin(), _messages.end(), std::back_inserter(result),
            [&](const Message& m) { return m.recipientId == myUserId; });
    return result;
}

std::vector<Conversation> MessageStore::conversations() const {
    std::map<std::string, Conversation> convMap;
    for (const auto& m : _messages) {
        auto& conv = convMap[m.senderId];
        conv.peerId = m.senderId;
        conv.messages.push_back(m);
    }
    std::vector<Conversation> result;
    for (auto& [peerId, conv] : convMap) {
        std::sort(conv.messages.begin(), conv.messages.end(),
             [](const Message& a, const Message& b) { return a.createdAt < b.createdAt; });
        result.push_back(std::move(conv));
    }
    return result;
}

const Message* MessageStore::findById(const std::string& id) const {
    auto it = std::find_if(_messages.begin(), _messages.end(),
                      [&](const Message& m) { return m.id == id; });
    return it != _messages.end() ? &*it : nullptr;
}
