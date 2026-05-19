#include "Client/JsonHelpers.h"

using namespace std;

namespace Client {
namespace JsonHelpers {

string toString(const Json& json) {
    return json.dump();
}

Json fromString(const string& text) {
    try { return Json::parse(text); }
    catch (const Json::parse_error& e) {
        throw runtime_error(string("Bad JSON from server: ") + e.what() + "\nBody: " + text);
    }
}

} // namespace JsonHelpers
} // namespace Client
