// API client: small convenience layer mapping high-level operations to HTTP calls.
// - Handles JSON serialization and automatic inclusion of the JWT Authorization header
//   for authenticated endpoints.
// - Returns raw JSON objects (nlohmann::json) for the caller to interpret.

#include "Client/ApiClient.h"
#include "Client/HttpClient.h"
#include "Client/JsonHelpers.h"
#include <stdexcept>

using namespace std;

namespace Client {

ApiClient::ApiClient(const string& baseUrl)
    : _baseUrl(baseUrl) {
}

void ApiClient::setJwtToken(const string& token) {
    _jwtToken = token;
}

// Register a new user. Returns server JSON response.
Json ApiClient::registerUser(const string& username,
                              const string& email,
                              const string& password) {
    HttpClient client(_baseUrl);
    Json payload = {
        {"username", username},
        {"email", email},
        {"password", password}
    };
    string response = client.postJson("/api/auth/register", JsonHelpers::toString(payload));
    return JsonHelpers::fromString(response);
}

// Login and capture JWT token if returned under `data.token`.
Json ApiClient::login(const string& username, const string& password) {
    HttpClient client(_baseUrl);
    Json payload = {
        {"username", username},
        {"password", password}
    };
    string response = client.postJson("/api/auth/login", JsonHelpers::toString(payload));
    Json result = JsonHelpers::fromString(response);
    if (result.contains("data") && result["data"].contains("token")) {
        setJwtToken(result["data"]["token"].get<string>());
    }
    return result;
}

Json ApiClient::getMe() {
    HttpClient client(_baseUrl);
    vector<string> headers;
    if (!_jwtToken.empty()) {
        headers.push_back("Authorization: Bearer " + _jwtToken);
    }
    string response = client.get("/api/auth/me", headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::publishPublicKey(const string& publicKeyBase64, const string& keyType) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for publishPublicKey");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"publicKey", publicKeyBase64},
        {"keyType", keyType}
    };
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.postJson("/api/keys", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

// Send an already-encrypted message (ciphertext + nonce + sender public key).
Json ApiClient::sendEncryptedMessage(const string& recipientId,
                                      const string& ciphertext,
                                      const string& nonce,
                                      const string& senderPublicKey) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for sendEncryptedMessage");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"recipientId", recipientId},
        {"ciphertext", ciphertext},
        {"nonce", nonce},
        {"senderPublicKey", senderPublicKey}
    };
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.postJson("/api/messages", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getInbox(int limit, int offset) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for getInbox");
    }
    HttpClient client(_baseUrl);
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.get("/api/messages/inbox?limit=" + to_string(limit) + "&offset=" + to_string(offset), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getSent(int limit, int offset) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for getSent");
    }
    HttpClient client(_baseUrl);
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.get("/api/messages/sent?limit=" + to_string(limit) + "&offset=" + to_string(offset), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getMessage(const string& messageId) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for getMessage");
    }
    HttpClient client(_baseUrl);
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.get("/api/messages/" + messageId, headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getPublicKey(const string& userId) {
    HttpClient client(_baseUrl);
    vector<string> headers;
    if (!_jwtToken.empty()) {
        headers.push_back("Authorization: Bearer " + _jwtToken);
    }
    string response = client.get("/api/keys/" + userId, headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::forwardMessage(const string& messageId,
                               const string& recipientId,
                               const string& ciphertext,
                               const string& nonce) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for forwardMessage");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"recipientId", recipientId},
        {"ciphertext", ciphertext},
        {"nonce", nonce}
    };
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.postJson("/api/messages/" + messageId + "/forward", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::revokeAccess(const string& messageId, const string& targetUserId) {
    if (_jwtToken.empty()) {
        throw runtime_error("JWT token required for revokeAccess");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"userId", targetUserId}
    };
    vector<string> headers = {"Authorization: Bearer " + _jwtToken};
    string response = client.postJson("/api/messages/" + messageId + "/revoke", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

} // namespace Client
