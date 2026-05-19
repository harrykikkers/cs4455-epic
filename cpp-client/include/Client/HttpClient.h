#pragma once

#include <string>
#include <vector>

using std::string;
using std::vector;

namespace Client {

// Small HTTPS helper wrapping libcurl.
// - Basic POST/GET helpers returning raw response bodies.
// - Callers should provide `Authorization` header when required.
class HttpClient {
public:
    // Construct with API base URL, e.g. "https://api.example.com"
    HttpClient(const string& baseUrl);
    ~HttpClient();

    // Send JSON via POST. `headers` may include authorization or other custom headers.
    string postJson(const string& path, const string& jsonBody, const vector<string>& headers = {});

    // Simple GET helper. Returns raw response body.
    string get(const string& path, const vector<string>& headers = {});

    // Adjust request timeout (seconds)
    void setTimeout(long seconds);

private:
    string _baseUrl;
    long _timeoutSeconds;
};

} // namespace Client
