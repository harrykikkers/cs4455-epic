#pragma once

#include <string>
#include <vector>

using namespace std;

namespace Client {

// Small HTTPS helper wrapping libcurl.
// SSL certificate verification is automatically disabled when connecting to
// localhost or 127.0.0.1, so self-signed dev certs work out of the box.
class HttpClient {
public:
    explicit HttpClient(const string& baseUrl);
    ~HttpClient();

    string postJson(const string& path, const string& jsonBody,
                    const vector<string>& headers = {});
    string get(const string& path,
               const vector<string>& headers = {});
    string del(const string& path,
               const vector<string>& headers = {});

    void setTimeout(long seconds);

private:
    string _baseUrl;
    long _timeoutSeconds;
    bool _verifySsl;
};

} // namespace Client
