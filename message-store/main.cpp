// message-store CLI: AES-256-GCM encrypted on-disk message archive.
//
// Subcommands:
//   add    --archive <path> --id <id> --sender <name> --created <iso8601>  (body via STDIN)
//   get    --archive <path> --id <id>
//   list   --archive <path>
//   view   [path-to-messages.json]   (legacy conversation viewer)
//   verify --archive <path> --id <id> --url <backend-base-url> --token <jwt>
//
// Key: 64 lowercase hex chars in env var MESSAGE_STORE_KEY (never on argv).
// Exit codes: 0 ok; 2 usage/key error; 3 not found; 1 other/decrypt failure.

#include "Archive.h"
#include "MessageStore.h"

#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>

using json = nlohmann::json;

namespace {

constexpr int EXIT_OK = 0;
constexpr int EXIT_OTHER = 1;
constexpr int EXIT_USAGE = 2;
constexpr int EXIT_NOTFOUND = 3;

void usage() {
    std::cerr <<
        "usage:\n"
        "  message-store add    --archive <path> --id <id> --sender <name> --created <iso8601>   (body on STDIN)\n"
        "  message-store get    --archive <path> --id <id>\n"
        "  message-store list   --archive <path>\n"
        "  message-store rekey  --archive <path>   (old key in MESSAGE_STORE_KEY, new key in MESSAGE_STORE_NEW_KEY)\n"
        "  message-store view   [path-to-messages.json]\n"
        "  message-store verify --archive <path> --id <id> --url <backend-url> --token <jwt>\n"
        "\n"
        "key: 64 lowercase hex chars in env MESSAGE_STORE_KEY\n";
} // standard error stream for usage and error messages

using Flags = std::map<std::string, std::string>;

// Parse --flag value pairs from argv[start..argc).
Flags parseFlags(int argc, char* argv[], int start) 
// argc is the no of command line arguments, 
// argv is an array of those arguments as c strings
{
    Flags flags;
    for (int i = start; i < argc; ++i) {
        std::string a = argv[i];
        if (a.rfind("--", 0) == 0) {
        // rfind searches for the substring "--" at the start (index 0)
            std::string name = a.substr(2); // cuts off the leading "--" to get the flag name
            if (i + 1 >= argc) {
                std::cerr << "[message-store] missing value for --" << name << "\n";
                std::exit(EXIT_USAGE);
            }
            flags[name] = argv[++i];
        } else {
            std::cerr << "[message-store] unexpected argument: " << a << "\n";
            std::exit(EXIT_USAGE);
        }
    }
    return flags;
}

std::string require(const Flags& flags,
                    const std::string& name) {
    auto it = flags.find(name);
    if (it == flags.end()) {
        std::cerr << "[message-store] missing required --" << name << "\n";
        std::exit(EXIT_USAGE);
    }
    return it->second;
}

// Read the entire archive key from the environment, validate, hex-decode.
archive::AesKey loadKeyOrDie() {
    const char* env = std::getenv("MESSAGE_STORE_KEY");
    if (!env || *env == '\0') {
        std::cerr << "[message-store] MESSAGE_STORE_KEY is not set\n";
        std::exit(EXIT_USAGE);
    }
    try {
        return archive::decodeHexKey(env);
    } catch (const std::invalid_argument& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        std::exit(EXIT_USAGE);
    }
}

// Read all of STDIN verbatim (may contain newlines and NUL-free binary text).
std::string readAllStdin() {
    std::string data;
    char buf[4096];
    while (std::cin.read(buf, sizeof(buf)) || std::cin.gcount() > 0) {
        data.append(buf, (size_t)std::cin.gcount());
    }
    return data;
}

int cmdAdd(int argc, char* argv[]) {
    auto flags = parseFlags(argc, argv, 2);
    std::string path = require(flags, "archive");
    std::string id = require(flags, "id");
    std::string sender = require(flags, "sender");
    std::string created = require(flags, "created");
    auto key = loadKeyOrDie();
    std::string body = readAllStdin();

    try {
        auto records = archive::load(path, key);
        // Upsert by id: replace existing or append.
        bool replaced = false;
        for (auto& r : records) {
            if (r.id == id) {
                r.sender = sender;
                r.created = created;
                r.body = body;
                replaced = true;
                break;
            }
        }
        if (!replaced) {
            records.push_back({id, sender, created, body});
        }
        archive::save(path, key, records);
    } catch (const archive::ArchiveIOError& e) {
        std::cerr << "[message-store] I/O error: " << e.what() << "\n";
        return EXIT_OTHER;
    } catch (const archive::DecryptError& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_OTHER;
    }
    return EXIT_OK;
}

int cmdGet(int argc, char* argv[]) {
    auto flags = parseFlags(argc, argv, 2);
    std::string path = require(flags, "archive");
    std::string id = require(flags, "id");
    auto key = loadKeyOrDie();

    try {
        auto records = archive::load(path, key);
        for (const auto& r : records) {
            if (r.id == id) {
                std::cout << r.body;  // exact body, no extra formatting
                return EXIT_OK;
            }
        }
    } catch (const archive::ArchiveIOError& e) {
        std::cerr << "[message-store] I/O error: " << e.what() << "\n";
        return EXIT_OTHER;
    } catch (const archive::DecryptError& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_OTHER;
    }
    std::cerr << "[message-store] id not found: " << id << "\n";
    return EXIT_NOTFOUND;
}

int cmdList(int argc, char* argv[]) {
    auto flags = parseFlags(argc, argv, 2);
    std::string path = require(flags, "archive");
    auto key = loadKeyOrDie();

    try {
        auto records = archive::load(path, key);
        for (const auto& r : records) {
            std::cout << r.id << '\t' << r.sender << '\t' << r.created << '\n';
        } // prints one line per record
    } catch (const archive::ArchiveIOError& e) {
        std::cerr << "[message-store] I/O error: " << e.what() << "\n";
        return EXIT_OTHER;
    } catch (const archive::DecryptError& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_OTHER;
    }
    return EXIT_OK;
}

// Re-encrypt the archive under a new key. Used after a password change: the
// archive key is HKDF(KEK), so a new password yields a new archive key and the
// old file would otherwise fail GCM authentication on the next add/get. The old
// key arrives in MESSAGE_STORE_KEY (via loadKeyOrDie), the new in
// MESSAGE_STORE_NEW_KEY. No-op success if the archive does not exist yet.
int cmdRekey(int argc, char* argv[]) {
    auto flags = parseFlags(argc, argv, 2);
    std::string path = require(flags, "archive");
    auto oldKey = loadKeyOrDie();

    const char* newEnv = std::getenv("MESSAGE_STORE_NEW_KEY");
    if (!newEnv || *newEnv == '\0') {
        std::cerr << "[message-store] MESSAGE_STORE_NEW_KEY is not set\n";
        return EXIT_USAGE;
    }
    archive::AesKey newKey;
    try {
        newKey = archive::decodeHexKey(newEnv);
    } catch (const std::invalid_argument& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_USAGE;
    }

    std::ifstream probe(path, std::ios::binary);
    if (!probe.is_open()) return EXIT_OK;  // nothing archived yet
    probe.close(); // probe is a file stream open to check if file exists

    try {
        auto records = archive::load(path, oldKey);
        archive::save(path, newKey, records);
    } catch (const archive::ArchiveIOError& e) {
        std::cerr << "[message-store] I/O error: " << e.what() << "\n";
        return EXIT_OTHER;
    } catch (const archive::DecryptError& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_OTHER;
    }
    return EXIT_OK;
}

// ---- Legacy "view" subcommand ----
// Reads a raw ciphertext JSON cache and prints conversation metadata.
// Superseded by the encrypted archive (add/get/list). Retained here because
// it exercises MessageStore — the STL container showcase required for assessment.

std::string legacyCachePath() {
    const char* home = std::getenv("HOME");
    return std::string(home ? home : ".") + "/.zebra/messages.json";
}

std::string jstr(const json& j, const std::string& key) {
    if (j.contains(key) && j[key].is_string()) return j[key].get<std::string>();
    return "";
}

int cmdView(int argc, char* argv[]) {
    std::string path = (argc > 2) ? argv[2] : legacyCachePath();

    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "[zebra-store] cache not found: " << path << "\n";
        return EXIT_OTHER;
    }

    json root;
    try {
        f >> root;
    } catch (const json::parse_error& e) {
        std::cerr << "[zebra-store] parse error: " << e.what() << "\n";
        return EXIT_OTHER;
    }
    if (!root.is_array()) {
        std::cerr << "[zebra-store] expected a JSON array of messages\n";
        return EXIT_OTHER;
    }

    MessageStore store;
    for (const auto& item : root) {
        Message m;
        m.id              = jstr(item, "messageId");
        m.senderId        = jstr(item, "sender_id");
        m.recipientId     = jstr(item, "recipient_id");
        m.ciphertext      = jstr(item, "ciphertext");
        m.nonce           = jstr(item, "nonce");
        m.senderPublicKey = jstr(item, "senderPublicKey");
        m.createdAt       = jstr(item, "created_at");
        store.add(m);
    }

    auto convs = store.conversations();
    std::cout << "\n=== Zebra local message store ===\n";
    std::cout << root.size() << " messages, " << convs.size() << " conversation(s)\n\n";

    for (const auto& conv : convs) {
        std::string peerName = conv.peerId;
        for (const auto& item : root) {
            if (jstr(item, "sender_id") == conv.peerId && item.contains("sender_username"))
                { peerName = jstr(item, "sender_username"); break; }
            if (jstr(item, "recipient_id") == conv.peerId && item.contains("recipient_username"))
                { peerName = jstr(item, "recipient_username"); break; }
        }
        std::cout << "  [" << peerName << "]  " << conv.messages.size() << " message(s)\n";
        for (const auto& m : conv.messages)
            std::cout << "    " << m.createdAt << "  id=" << m.id << "\n";
    }
    std::cout << "\n";
    return EXIT_OK;
}

// libcurl write callback — appends received bytes into a std::string.
// libcurl calls thus every time it receives data from http response
static size_t curlWrite(const char* ptr, size_t size, size_t nmemb, std::string* out) {
    out->append(ptr, size * nmemb);
    return size * nmemb;
}

// verify --archive <path> --id <message-id> --url <backend-base-url> --token <jwt>
//
// Loads the archived message locally, fetches its blockchain chain proof from
// the backend over verified TLS, and compares the on-chain digest against the
// locally stored plaintext.
//
// Flow:
//   1. Load message body from the local AES-256-GCM archive.
//   2. GET /api/messages/:id/chain  (libcurl, TLS cert verified).
//   3. Parse digestHash + txHash from the JSON response.
//   4. TODO: compute keccak256(body) in C++ and compare to digestHash.
//      (Requires a Ethereum-compatible keccak library — OpenSSL's EVP SHA3
//       uses the NIST padding, not Ethereum's, so a dedicated impl is needed.)
//   5. Print PASS / FAIL + txHash + timestamp.
int cmdVerify(int argc, char* argv[]) {
    auto flags      = parseFlags(argc, argv, 2);
    std::string archivePath = require(flags, "archive");
    std::string msgId       = require(flags, "id");
    std::string baseUrl     = require(flags, "url");
    std::string token       = require(flags, "token");

    // Step 1 — load the message from the local encrypted archive.
    auto key = loadKeyOrDie();
    std::vector<archive::Record> records;
    try {
        records = archive::load(archivePath, key);
    } catch (const std::exception& e) {
        std::cerr << "[message-store] failed to open archive: " << e.what() << "\n";
        return EXIT_OTHER;
    }
    auto it = std::find_if(records.begin(), records.end(),
                           [&](const archive::Record& r) { return r.id == msgId; });
    if (it == records.end()) {
        std::cerr << "[message-store] message " << msgId << " not found in archive\n";
        return EXIT_NOTFOUND;
    }
    const std::string& body = it->body;

    // Step 2 — fetch the chain proof from the backend over verified TLS.
    const std::string url = baseUrl + "/api/messages/" + msgId + "/chain";
    std::string response;

    CURL* curl = curl_easy_init(); // libcurl handle
    if (!curl) {
        std::cerr << "[message-store] curl_easy_init failed\n";
        return EXIT_OTHER;
    }

    const std::string authHeader = "Authorization: Bearer " + token;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, authHeader.c_str());
    headers = curl_slist_append(headers, "Accept: application/json");

    curl_easy_setopt(curl, CURLOPT_URL,            url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER,     headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  curlWrite);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &response);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L); // verify cert chain
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L); // verify hostname
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        10L); // L = LONG INTEGER

    CURLcode res = curl_easy_perform(curl); // http get request, opens tcp connection, resolves dns and does tls handshake
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        std::cerr << "[message-store] chain fetch failed: "
                  << curl_easy_strerror(res) << "\n";
        return EXIT_OTHER;
    }

    // Step 3 — parse the chain proof.
    json proof;
    try {
        proof = json::parse(response);
    } catch (...) {
        std::cerr << "[message-store] invalid JSON from backend\n";
        return EXIT_OTHER;
    }
    std::string chainStatus = proof.value("data", json::object()).value("chainStatus", "unknown");
    std::string txHash      = proof.value("data", json::object()).value("txHash", "");
    std::string digestHash  = proof.value("data", json::object()).value("digestHash", "");

    if (chainStatus != "recorded" || digestHash.empty()) {
        std::cout << "CHAIN STATUS: " << chainStatus << " — not yet recorded on-chain\n";
        return EXIT_OK;
    }

    // Step 4 — TODO: compute keccak256(body) and compare to digestHash.
    // Ethereum keccak256 uses pre-NIST Keccak padding (not SHA3-256).
    // Add a keccak library (e.g. https://github.com/brainhub/SHA3IUF) and
    // replace this block:
    //
    //   std::string computed = "0x" + keccak256_hex(body);
    //   bool match = (computed == digestHash);
    //
    // For now we print the on-chain digest so it can be verified manually.
    std::cout << "TX HASH:       " << txHash << "\n";
    std::cout << "ON-CHAIN HASH: " << digestHash << "\n";
    std::cout << "ARCHIVE BODY:  " << body.size() << " bytes\n";
    std::cout << "\n";
    std::cout << "TODO: keccak256 C++ implementation needed to auto-verify.\n";
    std::cout << "Verify manually: keccak256 of the archived body should equal the on-chain hash.\n";

    return EXIT_OK;
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc < 2) {
        usage();
        return EXIT_USAGE;
    }
    std::string sub = argv[1];
    if (sub == "add")    return cmdAdd(argc, argv);
    if (sub == "get")    return cmdGet(argc, argv);
    if (sub == "list")   return cmdList(argc, argv);
    if (sub == "rekey")  return cmdRekey(argc, argv);
    if (sub == "view")   return cmdView(argc, argv);
    if (sub == "verify") return cmdVerify(argc, argv);

    std::cerr << "[message-store] unknown subcommand: " << sub << "\n";
    usage();
    return EXIT_USAGE;
}
