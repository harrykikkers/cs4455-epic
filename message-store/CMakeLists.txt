cmake_minimum_required(VERSION 3.16)
project(MessageStore CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- nlohmann/json via FetchContent (self-contained, no system install needed) ---
include(FetchContent)
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(nlohmann_json)

# --- libcurl (HTTPS chain verification with TLS certificate verification) ---
find_package(CURL REQUIRED)

# --- OpenSSL (AES-256-GCM via EVP) ---
# On macOS Homebrew installs under /opt/homebrew/opt/openssl@3; hint find_package
# if the caller didn't already pass -DOPENSSL_ROOT_DIR.
if(APPLE AND NOT DEFINED OPENSSL_ROOT_DIR AND EXISTS "/opt/homebrew/opt/openssl@3")
    set(OPENSSL_ROOT_DIR "/opt/homebrew/opt/openssl@3")
endif()
find_package(OpenSSL REQUIRED)


# Legacy in-memory conversation-view demo (kept compiling).
add_executable(demo demo.cpp MessageStore.cpp)
target_link_libraries(demo PRIVATE nlohmann_json::nlohmann_json)

# Main CLI binary: message-store.
add_executable(message-store main.cpp MessageStore.cpp Archive.cpp)
target_link_libraries(message-store
    PRIVATE
        nlohmann_json::nlohmann_json
        OpenSSL::Crypto
        CURL::libcurl
)
