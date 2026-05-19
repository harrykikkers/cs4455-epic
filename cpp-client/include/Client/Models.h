#pragma once

#include <string>
#include <vector>
#include "JsonHelpers.h"

using namespace std;

namespace Client {

struct User {
    string id;
    string username;
    string email;

    static User fromJson(const Json& j);
};

struct Message {
    string id;
    string senderId;
    string recipientId;
    string ciphertext;
    string nonce;
    string senderPublicKey;
    string createdAt;

    static Message fromJson(const Json& j);
};

// All messages exchanged with one other user.
struct Conversation {
    string peerId;
    vector<Message> messages;
};

// Local cache of messages fetched from the server.
// Lets you filter and group without hitting the network again.
class MessageStore {
public:
    void add(const Message& m);
    void addAll(const vector<Message>& msgs);

    // Messages where you are the recipient.
    vector<Message> inbox(const string& myUserId) const;

    // Messages where you are the sender.
    vector<Message> sent(const string& myUserId) const;

    // Inbox messages grouped by sender into Conversation objects,
    // sorted chronologically within each conversation.
    vector<Conversation> conversations(const string& myUserId) const;

    // Returns a pointer to the message with the given id, or nullptr if not found.
    const Message* findById(const string& id) const;

    const vector<Message>& all() const;

private:
    vector<Message> _messages;
};

} // namespace Client
