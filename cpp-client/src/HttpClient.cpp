// HTTPS wrapper around libcurl.
// curl_global_init/cleanup must be called once by main (not here).
// SSL peer verification is disabled automatically for localhost so that
// self-signed development certificates work without extra configuration.

#include "Client/HttpClient.h"
#include <curl/curl.h>
#include <stdexcept>

using namespace std;

namespace Client {

namespace {

// libcurl calls this each time it receives data; we append to a string buffer.
size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    static_cast<string*>(userp)->append(static_cast<char*>(contents), size * nmemb);
    return size * nmemb;
}

// Shared tail for every request: sets common options, runs the request,
// checks both transport errors and HTTP status codes, then cleans up.
// Putting this here (not in the class) keeps CURL* out of the header entirely.
string execute(CURL* curl, curl_slist* headerList, long timeout, bool verifySsl) {
    string response;
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        timeout);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, verifySsl ? 1L : 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, verifySsl ? 2L : 0L);

    CURLcode code = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_slist_free_all(headerList);
    curl_easy_cleanup(curl);

    if (code != CURLE_OK)
        throw runtime_error(string("curl error: ") + curl_easy_strerror(code));
    if (httpCode >= 400)
        throw runtime_error("HTTP " + to_string(httpCode) + ": " + response);
    return response;
}

} // anonymous namespace

HttpClient::HttpClient(const string& baseUrl)
    : _baseUrl(baseUrl), _timeoutSeconds(30) {
    _verifySsl = (baseUrl.find("localhost") == string::npos &&
                  baseUrl.find("127.0.0.1") == string::npos);
}

HttpClient::~HttpClient() {}

void HttpClient::setTimeout(long seconds) { _timeoutSeconds = seconds; }

string HttpClient::postJson(const string& path, const string& jsonBody,
                            const vector<string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) throw runtime_error("Failed to initialize libcurl");

    string url = _baseUrl + path;
    curl_slist* headerList = nullptr;
    headerList = curl_slist_append(headerList, "Content-Type: application/json");
    for (const auto& h : headers)
        headerList = curl_slist_append(headerList, h.c_str());

    curl_easy_setopt(curl, CURLOPT_URL,          url.c_str());
    curl_easy_setopt(curl, CURLOPT_POST,          1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS,    jsonBody.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, (long)jsonBody.size());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER,    headerList);

    return execute(curl, headerList, _timeoutSeconds, _verifySsl);
}

string HttpClient::get(const string& path, const vector<string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) throw runtime_error("Failed to initialize libcurl");

    string url = _baseUrl + path;
    curl_slist* headerList = nullptr;
    for (const auto& h : headers)
        headerList = curl_slist_append(headerList, h.c_str());

    curl_easy_setopt(curl, CURLOPT_URL,       url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPGET,   1L);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headerList);

    return execute(curl, headerList, _timeoutSeconds, _verifySsl);
}

string HttpClient::del(const string& path, const vector<string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) throw runtime_error("Failed to initialize libcurl");

    string url = _baseUrl + path;
    curl_slist* headerList = nullptr;
    for (const auto& h : headers)
        headerList = curl_slist_append(headerList, h.c_str());

    curl_easy_setopt(curl, CURLOPT_URL,           url.c_str());
    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "DELETE");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER,    headerList);

    return execute(curl, headerList, _timeoutSeconds, _verifySsl);
}

} // namespace Client
