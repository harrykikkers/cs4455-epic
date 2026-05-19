#pragma once

#include <string>
#include "JsonHelpers.h"

namespace Client {

struct User {
    std::string id;
    std::string username;
    std::string email;

    static User fromJson(const Json& j) {
        return User{ j.value("id", std::string{}), j.value("username", std::string{}), j.value("email", std::string{}) };
    }
};

struct Message {
    std::string id;
    std::string senderId;
    std::string recipientId;
    std::string ciphertext;
    std::string nonce;
    std::string senderPublicKey;
    std::string createdAt;

    static Message fromJson(const Json& j) {
        return Message{
            j.value("id", std::string{}),
            j.value("sender_id", std::string{}),
            j.value("recipient_id", std::string{}),
            j.value("ciphertext", std::string{}),
            j.value("nonce", std::string{}),
            j.value("sender_public_key", std::string{}),
            j.value("created_at", std::string{})
        };
    }
};

} // namespace Client
