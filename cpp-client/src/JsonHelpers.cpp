#include "Client/JsonHelpers.h"

using namespace std;

namespace Client {

// Minimal JSON helpers. We keep parsing and serialization in one place so
// callers don't need to include `nlohmann/json.hpp` directly everywhere.
string JsonHelpers::toString(const Json& json) {
    return json.dump();
}

Json JsonHelpers::fromString(const string& text) {
    // In production you may want to catch parse errors and return a Result type.
    return Json::parse(text);
}

} // namespace Client
