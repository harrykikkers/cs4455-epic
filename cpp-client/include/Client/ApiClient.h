#pragma once

#include <string>
#include <optional>
#include <vector>
#include "JsonHelpers.h"

using std::string;
using std::vector;

namespace Client {

// Convenience API client that maps application operations to HTTP endpoints.
// - Keeps JSON (de)serialization in one place and automatically sets the
//   `Authorization: Bearer <token>` header for authenticated calls.
// - Returns `Json` objects for the caller to inspect; callers should handle
//   application-level errors according to server responses.
class ApiClient {
public:
    ApiClient(const string& baseUrl);

    // Set the JWT token obtained from login so subsequent calls are authenticated.
    void setJwtToken(const string& token);

    Json registerUser(const string& username, const string& email, const string& password);
    Json login(const string& username, const string& password);
    Json getMe();
    Json publishPublicKey(const string& publicKeyBase64, const string& keyType = "x25519");
    Json sendEncryptedMessage(const string& recipientId,
                              const string& ciphertext,
                              const string& nonce,
                              const string& senderPublicKey);
    Json getInbox(int limit = 50, int offset = 0);
    Json getSent(int limit = 50, int offset = 0);
    Json getMessage(const string& messageId);
    Json getPublicKey(const string& userId);
    Json forwardMessage(const string& messageId,
                        const string& recipientId,
                        const string& ciphertext,
                        const string& nonce);
    Json revokeAccess(const string& messageId, const string& targetUserId);

private:
    string _baseUrl;
    string _jwtToken;
};

} // namespace Client
