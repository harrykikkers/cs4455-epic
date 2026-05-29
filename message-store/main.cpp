// message-store CLI: AES-256-GCM encrypted on-disk message archive.
//
// Subcommands:
//   add  --archive <path> --id <id> --sender <name> --created <iso8601>  (body via STDIN)
//   get  --archive <path> --id <id>
//   list --archive <path>
//   view [path-to-messages.json]   (legacy conversation viewer)
//
// Key: 64 lowercase hex chars in env var MESSAGE_STORE_KEY (never on argv).
// Exit codes: 0 ok; 2 usage/key error; 3 not found; 1 other/decrypt failure.

#include "Archive.h"
#include "MessageStore.h"

#include <nlohmann/json.hpp>

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
        "  message-store add  --archive <path> --id <id> --sender <name> --created <iso8601>   (body on STDIN)\n"
        "  message-store get  --archive <path> --id <id>\n"
        "  message-store list --archive <path>\n"
        "  message-store view [path-to-messages.json]\n"
        "\n"
        "key: 64 lowercase hex chars in env MESSAGE_STORE_KEY\n";
}

// Parse --flag value pairs from argv[start..argc).
std::map<std::string, std::string> parseFlags(int argc, char* argv[], int start) {
    std::map<std::string, std::string> flags;
    for (int i = start; i < argc; ++i) {
        std::string a = argv[i];
        if (a.rfind("--", 0) == 0) {
            std::string name = a.substr(2);
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

std::string require(const std::map<std::string, std::string>& flags,
                    const std::string& name) {
    auto it = flags.find(name);
    if (it == flags.end()) {
        std::cerr << "[message-store] missing required --" << name << "\n";
        std::exit(EXIT_USAGE);
    }
    return it->second;
}

// Read the entire archive key from the environment, validate, hex-decode.
std::array<unsigned char, archive::kKeyLen> loadKeyOrDie() {
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
        }
    } catch (const archive::DecryptError& e) {
        std::cerr << "[message-store] " << e.what() << "\n";
        return EXIT_OTHER;
    }
    return EXIT_OK;
}

// ---- Legacy "view" subcommand: read ciphertext JSON cache, print conversations ----

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

}  // namespace

int main(int argc, char* argv[]) {
    if (argc < 2) {
        usage();
        return EXIT_USAGE;
    }
    std::string sub = argv[1];
    if (sub == "add")  return cmdAdd(argc, argv);
    if (sub == "get")  return cmdGet(argc, argv);
    if (sub == "list") return cmdList(argc, argv);
    if (sub == "view") return cmdView(argc, argv);

    std::cerr << "[message-store] unknown subcommand: " << sub << "\n";
    usage();
    return EXIT_USAGE;
}
