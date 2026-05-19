#pragma once

#include <string>
#include <vector>

namespace Client {

class HttpClient {
public:
    HttpClient(const std::string& baseUrl);
    ~HttpClient();

    std::string postJson(const std::string& path, const std::string& jsonBody, const std::vector<std::string>& headers = {});
    std::string get(const std::string& path, const std::vector<std::string>& headers = {});
    void setTimeout(long seconds);

private:
    std::string _baseUrl;
    long _timeoutSeconds;
};

} // namespace Client
