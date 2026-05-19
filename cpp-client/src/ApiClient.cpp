// API client: small convenience layer mapping high-level operations to HTTP calls.
// - Handles JSON serialization and automatic inclusion of the JWT Authorization header
//   for authenticated endpoints.
// - Returns raw JSON objects (nlohmann::json) for the caller to interpret.

#include "Client/ApiClient.h"
#include "Client/HttpClient.h"
#include "Client/JsonHelpers.h"
#include <stdexcept>

namespace Client {

ApiClient::ApiClient(const std::string& baseUrl)
    : _baseUrl(baseUrl) {
}

void ApiClient::setJwtToken(const std::string& token) {
    _jwtToken = token;
}

// Register a new user. Returns server JSON response.
Json ApiClient::registerUser(const std::string& username,
                             const std::string& email,
                             const std::string& password) {
    HttpClient client(_baseUrl);
    Json payload = {
        {"username", username},
        {"email", email},
        {"password", password}
    };
    std::string response = client.postJson("/api/auth/register", JsonHelpers::toString(payload));
    return JsonHelpers::fromString(response);
}

// Login and capture JWT token if returned under `data.token`.
Json ApiClient::login(const std::string& username, const std::string& password) {
    HttpClient client(_baseUrl);
    Json payload = {
        {"username", username},
        {"password", password}
    };
    std::string response = client.postJson("/api/auth/login", JsonHelpers::toString(payload));
    Json result = JsonHelpers::fromString(response);
    if (result.contains("data") && result["data"].contains("token")) {
        setJwtToken(result["data"]["token"].get<std::string>());
    }
    return result;
}

Json ApiClient::getMe() {
    HttpClient client(_baseUrl);
    std::vector<std::string> headers;
    if (!_jwtToken.empty()) {
        headers.push_back("Authorization: Bearer " + _jwtToken);
    }
    std::string response = client.get("/api/auth/me", headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::publishPublicKey(const std::string& publicKeyBase64, const std::string& keyType) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for publishPublicKey");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"publicKey", publicKeyBase64},
        {"keyType", keyType}
    };
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.postJson("/api/keys", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

// Send an already-encrypted message (ciphertext + nonce + sender public key).
Json ApiClient::sendEncryptedMessage(const std::string& recipientId,
                                     const std::string& ciphertext,
                                     const std::string& nonce,
                                     const std::string& senderPublicKey) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for sendEncryptedMessage");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"recipientId", recipientId},
        {"ciphertext", ciphertext},
        {"nonce", nonce},
        {"senderPublicKey", senderPublicKey}
    };
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.postJson("/api/messages", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getInbox(int limit, int offset) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for getInbox");
    }
    HttpClient client(_baseUrl);
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.get("/api/messages/inbox?limit=" + std::to_string(limit) + "&offset=" + std::to_string(offset), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getSent(int limit, int offset) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for getSent");
    }
    HttpClient client(_baseUrl);
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.get("/api/messages/sent?limit=" + std::to_string(limit) + "&offset=" + std::to_string(offset), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getMessage(const std::string& messageId) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for getMessage");
    }
    HttpClient client(_baseUrl);
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.get("/api/messages/" + messageId, headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::getPublicKey(const std::string& userId) {
    HttpClient client(_baseUrl);
    std::vector<std::string> headers;
    if (!_jwtToken.empty()) {
        headers.push_back("Authorization: Bearer " + _jwtToken);
    }
    std::string response = client.get("/api/keys/" + userId, headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::forwardMessage(const std::string& messageId,
                               const std::string& recipientId,
                               const std::string& ciphertext,
                               const std::string& nonce) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for forwardMessage");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"recipientId", recipientId},
        {"ciphertext", ciphertext},
        {"nonce", nonce}
    };
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.postJson("/api/messages/" + messageId + "/forward", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

Json ApiClient::revokeAccess(const std::string& messageId, const std::string& targetUserId) {
    if (_jwtToken.empty()) {
        throw std::runtime_error("JWT token required for revokeAccess");
    }
    HttpClient client(_baseUrl);
    Json payload = {
        {"userId", targetUserId}
    };
    std::vector<std::string> headers = {"Authorization: Bearer " + _jwtToken};
    std::string response = client.postJson("/api/messages/" + messageId + "/revoke", JsonHelpers::toString(payload), headers);
    return JsonHelpers::fromString(response);
}

} // namespace Client
