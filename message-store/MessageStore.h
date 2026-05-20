#pragma once

#include <string>
#include <vector>

using namespace std;

struct Message {
    string id;
    string senderId;
    string recipientId;
    string ciphertext;
    string nonce;
    string senderPublicKey;
    string createdAt;
};

struct Conversation {
    string peerId;
    vector<Message> messages;
};

class MessageStore {
public:
    void add(const Message& m);

    // Messages where you are the recipient.
    vector<Message> inbox(const string& myUserId) const;

    // Messages grouped by sender, sorted chronologically within each group.
    vector<Conversation> conversations() const;

    // Returns a pointer to the message with the given id, or nullptr if not found.
    const Message* findById(const string& id) const;

private:
    vector<Message> _messages;
};
