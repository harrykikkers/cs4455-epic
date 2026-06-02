#include "MessageStore.h"
#include <algorithm>
#include <map>

void MessageStore::add(const Message& m) {
    _messages.push_back(m);
}

std::vector<Message> MessageStore::inbox(const std::string& myUserId) const {
    std::vector<Message> result;
    std::copy_if(_messages.begin(), _messages.end(), std::back_inserter(result), // calls push_back on whatever is written
            [&](const Message& m) { return m.recipientId == myUserId; });
            // [&] captures all local variables by reference, allowing the lambda to access myUserId
    return result;
}

std::vector<Conversation> MessageStore::conversations() const {
    std::map<std::string, Conversation> convMap;
    for (const auto& m : _messages) {
        auto& conv = convMap[m.senderId]; // if sender doesn't have an entry yet, map creates one automatically
        conv.peerId = m.senderId;
        conv.messages.push_back(m);
    }
    std::vector<Conversation> result;
    for (auto& [peerId, conv] : convMap) {
        std::sort(conv.messages.begin(), conv.messages.end(),
             [](const Message& a, const Message& b) { return a.createdAt < b.createdAt; });
        result.push_back(std::move(conv));
    }// move transfers ownership of conv into the vector without copying, which is more efficient since Conversation contains a vector of Messages.
    return result;
}

const Message* MessageStore::findById(const std::string& id) const {
    auto it = std::find_if(_messages.begin(), _messages.end(),
                      [&](const Message& m) { return m.id == id; });
    return it != _messages.end() ? &*it : nullptr;
    // *it dereferences the iterator to get a reference to the Message, and & takes its address to return a pointer.
}
