#pragma once

#include <string>
#include "JsonHelpers.h"

using std::string;

namespace Client {

struct User {
    string id;
    string username;
    string email;

    static User fromJson(const Json& j) {
        return User{ j.value("id", string{}), j.value("username", string{}), j.value("email", string{}) };
    }
};

struct Message {
    string id;
    string senderId;
    string recipientId;
    string ciphertext;
    string nonce;
    string senderPublicKey;
    string createdAt;

    static Message fromJson(const Json& j) {
        return Message{
            j.value("id", string{}),
            j.value("sender_id", string{}),
            j.value("recipient_id", string{}),
            j.value("ciphertext", string{}),
            j.value("nonce", string{}),
            j.value("sender_public_key", string{}),
            j.value("created_at", string{})
        };
    }
};

} // namespace Client
