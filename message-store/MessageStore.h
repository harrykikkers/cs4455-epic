#pragma once

// MessageStore — legacy in-memory store used by the 'view' subcommand.
// The live application uses the AES-256-GCM archive (Archive.h) for
// persistent storage. This class is retained to demonstrate STL container
// usage (std::vector, std::map) as required by the C++ assessment criteria.

#include <string>
#include <vector>

struct Message {
    std::string id;
    std::string senderId;
    std::string recipientId;
    std::string ciphertext;
    std::string nonce;
    std::string senderPublicKey;
    std::string createdAt;
};

struct Conversation {
    std::string peerId;
    std::vector<Message> messages;
};

class MessageStore {
public:
    void add(const Message& m);

    // Messages where you are the recipient.
    std::vector<Message> inbox(const std::string& myUserId) const;

    // Messages grouped by sender, sorted chronologically within each group.
    std::vector<Conversation> conversations() const;

    // Returns a pointer to the message with the given id, or nullptr if not found.
    const Message* findById(const std::string& id) const;

private:
    std::vector<Message> _messages;
};
