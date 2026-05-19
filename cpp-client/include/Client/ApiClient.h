#pragma once

#include <string>
#include <optional>
#include <vector>
#include "JsonHelpers.h"

namespace Client {

class ApiClient {
public:
    ApiClient(const std::string& baseUrl);

    void setJwtToken(const std::string& token);
    Json registerUser(const std::string& username, const std::string& email, const std::string& password);
    Json login(const std::string& username, const std::string& password);
    Json getMe();
    Json publishPublicKey(const std::string& publicKeyBase64, const std::string& keyType = "x25519");
    Json sendEncryptedMessage(const std::string& recipientId,
                              const std::string& ciphertext,
                              const std::string& nonce,
                              const std::string& senderPublicKey);
    Json getInbox(int limit = 50, int offset = 0);
    Json getSent(int limit = 50, int offset = 0);
    Json getMessage(const std::string& messageId);
    Json forwardMessage(const std::string& messageId,
                        const std::string& recipientId,
                        const std::string& ciphertext,
                        const std::string& nonce);
    Json revokeAccess(const std::string& messageId, const std::string& targetUserId);

private:
    std::string _baseUrl;
    std::string _jwtToken;
};

} // namespace Client
