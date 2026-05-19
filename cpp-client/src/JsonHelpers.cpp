#include "Client/JsonHelpers.h"

namespace Client {

std::string JsonHelpers::toString(const Json& json) {
    return json.dump();
}

Json JsonHelpers::fromString(const std::string& text) {
    return Json::parse(text);
}

} // namespace Client
