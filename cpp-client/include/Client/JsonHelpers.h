#pragma once

#include <nlohmann/json.hpp>
#include <string>

namespace Client {

using Json = nlohmann::json;

// Small wrapper so callers don't need to include nlohmann/json everywhere.
// Centralizes future changes to serialization (pretty-printing, error handling).
class JsonHelpers {
public:
    static std::string toString(const Json& json);
    static Json fromString(const std::string& text);
};

} // namespace Client
