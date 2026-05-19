#include "Client/JsonHelpers.h"

namespace Client {

// Minimal JSON helpers. We keep parsing and serialization in one place so
// callers don't need to include `nlohmann/json.hpp` directly everywhere.
std::string JsonHelpers::toString(const Json& json) {
    return json.dump();
}

Json JsonHelpers::fromString(const std::string& text) {
    // In production you may want to catch parse errors and return a Result type.
    return Json::parse(text);
}

} // namespace Client
