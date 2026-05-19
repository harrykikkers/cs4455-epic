#pragma once

#include <string>
#include <vector>

namespace Client {

// Small HTTPS helper wrapping libcurl.
// - Basic POST/GET helpers returning raw response bodies.
// - Callers should provide `Authorization` header when required.
class HttpClient {
public:
    // Construct with API base URL, e.g. "https://api.example.com"
    HttpClient(const std::string& baseUrl);
    ~HttpClient();

    // Send JSON via POST. `headers` may include authorization or other custom headers.
    std::string postJson(const std::string& path, const std::string& jsonBody, const std::vector<std::string>& headers = {});

    // Simple GET helper. Returns raw response body.
    std::string get(const std::string& path, const std::vector<std::string>& headers = {});

    // Adjust request timeout (seconds)
    void setTimeout(long seconds);

private:
    std::string _baseUrl;
    long _timeoutSeconds;
};

} // namespace Client
