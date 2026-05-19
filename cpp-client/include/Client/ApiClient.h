#pragma once

#include <string>
#include <optional>
#include <vector>
#include "JsonHelpers.h"

namespace Client {

// Convenience API client that maps application operations to HTTP endpoints.
// - Keeps JSON (de)serialization in one place and automatically sets the
//   `Authorization: Bearer <token>` header for authenticated calls.
// - Returns `Json` objects for the caller to inspect; callers should handle
//   application-level errors according to server responses.
class ApiClient {
public:
    ApiClient(const std::string& baseUrl);

    // Set the JWT token obtained from login so subsequent calls are authenticated.
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
    Json getPublicKey(const std::string& userId);
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
