#pragma once

#include <nlohmann/json.hpp>
#include <string>

namespace Client {

using Json = nlohmann::json;

class JsonHelpers {
public:
    static std::string toString(const Json& json);
    static Json fromString(const std::string& text);
};

} // namespace Client
