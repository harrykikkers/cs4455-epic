#pragma once

#include <nlohmann/json.hpp>
#include <string>

using namespace std;

namespace Client {

using Json = nlohmann::json;

// Free functions — no class needed when there is no instance state.
namespace JsonHelpers {
    string toString(const Json& json);
    Json fromString(const string& text);
} // namespace JsonHelpers

} // namespace Client
