#include "Client/HttpClient.h"
#include <curl/curl.h>
#include <stdexcept>

namespace Client {

namespace {
size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    auto* buffer = static_cast<std::string*>(userp);
    buffer->append(static_cast<char*>(contents), size * nmemb);
    return size * nmemb;
}
}

HttpClient::HttpClient(const std::string& baseUrl)
    : _baseUrl(baseUrl), _timeoutSeconds(30) {
    curl_global_init(CURL_GLOBAL_DEFAULT);
}

HttpClient::~HttpClient() {
    curl_global_cleanup();
}

void HttpClient::setTimeout(long seconds) {
    _timeoutSeconds = seconds;
}

std::string HttpClient::postJson(const std::string& path,
                                 const std::string& jsonBody,
                                 const std::vector<std::string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize libcurl");
    }

    std::string response;
    std::string url = _baseUrl + path;
    struct curl_slist* headerList = nullptr;
    headerList = curl_slist_append(headerList, "Content-Type: application/json");
    for (const auto& header : headers) {
        headerList = curl_slist_append(headerList, header.c_str());
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, jsonBody.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, jsonBody.size());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headerList);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, _timeoutSeconds);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);

    CURLcode code = curl_easy_perform(curl);
    curl_slist_free_all(headerList);
    curl_easy_cleanup(curl);

    if (code != CURLE_OK) {
        throw std::runtime_error(std::string("HTTP POST failed: ") + curl_easy_strerror(code));
    }

    return response;
}

std::string HttpClient::get(const std::string& path, const std::vector<std::string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize libcurl");
    }

    std::string response;
    std::string url = _baseUrl + path;
    struct curl_slist* headerList = nullptr;
    for (const auto& header : headers) {
        headerList = curl_slist_append(headerList, header.c_str());
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPGET, 1L);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headerList);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, _timeoutSeconds);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);

    CURLcode code = curl_easy_perform(curl);
    curl_slist_free_all(headerList);
    curl_easy_cleanup(curl);

    if (code != CURLE_OK) {
        throw std::runtime_error(std::string("HTTP GET failed: ") + curl_easy_strerror(code));
    }

    return response;
}

} // namespace Client
