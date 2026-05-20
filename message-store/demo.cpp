#include "MessageStore.h"
#include <iostream>

using namespace std;

int main() {
    MessageStore store;

    store.add({"msg-1", "alice", "bob", "cipher1", "nonce1", "alicePubKey", "2024-01-01T10:00:00Z"});
    store.add({"msg-2", "alice", "bob", "cipher2", "nonce2", "alicePubKey", "2024-01-01T10:05:00Z"});
    store.add({"msg-3", "carol", "bob", "cipher3", "nonce3", "carolPubKey", "2024-01-01T11:00:00Z"});

    cout << "=== Inbox for bob ===\n";
    for (const auto& m : store.inbox("bob"))
        cout << "  from=" << m.senderId << " id=" << m.id << "\n";

    cout << "\n=== Conversations ===\n";
    for (const auto& conv : store.conversations()) {
        cout << "  Conversation with " << conv.peerId
             << " (" << conv.messages.size() << " messages)\n";
        for (const auto& m : conv.messages)
            cout << "    [" << m.createdAt << "] id=" << m.id << "\n";
    }

    cout << "\n=== Find by ID ===\n";
    const Message* found = store.findById("msg-2");
    if (found)
        cout << "  Found: " << found->id << " from " << found->senderId << "\n";

    const Message* missing = store.findById("msg-999");
    cout << "  msg-999: " << (missing ? "found" : "not found") << "\n";

    return 0;
}
