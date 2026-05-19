#pragma once

#include <string>
#include <vector>
#include "HttpClient.h"
#include "JsonHelpers.h"

using namespace std;

namespace Client {

// Maps application operations to HTTPS endpoints.
// Owns one HttpClient and automatically attaches the JWT Authorization header
// to every authenticated call.
class ApiClient {
public:
    explicit ApiClient(const string& baseUrl);

    void setJwtToken(const string& token);

    Json registerUser(const string& username, const string& email,
                      const string& password);
    Json login(const string& username, const string& password);
    Json getMe();
    Json publishPublicKey(const string& publicKeyBase64,
                          const string& keyType = "x25519");
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
    Json revokeAccess(const string& messageId,
                      const string& targetUserId);
    Json deleteMessage(const string& messageId);

private:
    vector<string> authHeaders() const;

    string _jwtToken;
    HttpClient _http;
};

} // namespace Client
