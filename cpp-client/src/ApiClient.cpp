// API client: maps application operations to HTTPS calls.
// All authenticated endpoints automatically receive the JWT Authorization header.

#include "Client/ApiClient.h"
#include "Client/JsonHelpers.h"
#include <stdexcept>

using namespace std;

namespace Client {

ApiClient::ApiClient(const string& baseUrl)
    : _http(baseUrl) {}

void ApiClient::setJwtToken(const string& token) {
    _jwtToken = token;
}

vector<string> ApiClient::authHeaders() const {
    if (_jwtToken.empty()) throw runtime_error("Not logged in — call login() first");
    return {"Authorization: Bearer " + _jwtToken};
}

Json ApiClient::registerUser(const string& username,
                              const string& email,
                              const string& password) {
    Json payload = {{"username", username}, {"email", email}, {"password", password}};
    return JsonHelpers::fromString(
        _http.postJson("/api/auth/register", JsonHelpers::toString(payload)));
}

Json ApiClient::login(const string& username, const string& password) {
    Json payload = {{"username", username}, {"password", password}};
    string response = _http.postJson("/api/auth/login", JsonHelpers::toString(payload));
    Json result = JsonHelpers::fromString(response);
    if (result.contains("data") && result["data"].contains("token")) {
        setJwtToken(result["data"]["token"].get<string>());
    }
    return result;
}

Json ApiClient::getMe() {
    // getMe is callable before login (returns 401 from server if not authed)
    vector<string> headers;
    if (!_jwtToken.empty()) headers.push_back("Authorization: Bearer " + _jwtToken);
    return JsonHelpers::fromString(_http.get("/api/auth/me", headers));
}

Json ApiClient::publishPublicKey(const string& publicKeyBase64, const string& keyType) {
    Json payload = {{"publicKey", publicKeyBase64}, {"keyType", keyType}};
    return JsonHelpers::fromString(
        _http.postJson("/api/keys", JsonHelpers::toString(payload), authHeaders()));
}

Json ApiClient::sendEncryptedMessage(const string& recipientId, const string& ciphertext,
                                      const string& nonce, const string& senderPublicKey) {
    Json payload = {{"recipientId", recipientId}, {"ciphertext", ciphertext},
                    {"nonce", nonce}, {"senderPublicKey", senderPublicKey}};
    return JsonHelpers::fromString(
        _http.postJson("/api/messages", JsonHelpers::toString(payload), authHeaders()));
}

Json ApiClient::getInbox(int limit, int offset) {
    return JsonHelpers::fromString(
        _http.get("/api/messages/inbox?limit=" + to_string(limit) +
                  "&offset=" + to_string(offset), authHeaders()));
}

Json ApiClient::getSent(int limit, int offset) {
    return JsonHelpers::fromString(
        _http.get("/api/messages/sent?limit=" + to_string(limit) +
                  "&offset=" + to_string(offset), authHeaders()));
}

Json ApiClient::getMessage(const string& messageId) {
    return JsonHelpers::fromString(_http.get("/api/messages/" + messageId, authHeaders()));
}

Json ApiClient::getPublicKey(const string& userId) {
    // Public key lookup works unauthenticated, but attach token if we have one.
    vector<string> headers;
    if (!_jwtToken.empty()) headers.push_back("Authorization: Bearer " + _jwtToken);
    return JsonHelpers::fromString(_http.get("/api/keys/" + userId, headers));
}

Json ApiClient::forwardMessage(const string& messageId, const string& recipientId,
                               const string& ciphertext, const string& nonce) {
    Json payload = {{"recipientId", recipientId}, {"ciphertext", ciphertext}, {"nonce", nonce}};
    return JsonHelpers::fromString(
        _http.postJson("/api/messages/" + messageId + "/forward",
                       JsonHelpers::toString(payload), authHeaders()));
}

Json ApiClient::revokeAccess(const string& messageId, const string& targetUserId) {
    Json payload = {{"userId", targetUserId}};
    return JsonHelpers::fromString(
        _http.postJson("/api/messages/" + messageId + "/revoke",
                       JsonHelpers::toString(payload), authHeaders()));
}

Json ApiClient::deleteMessage(const string& messageId) {
    return JsonHelpers::fromString(_http.del("/api/messages/" + messageId, authHeaders()));
}

} // namespace Client
