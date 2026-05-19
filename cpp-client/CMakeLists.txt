cmake_minimum_required(VERSION 3.16)
project(EpicSecureMessengerClient LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_path(CURL_INCLUDE_DIR curl/curl.h)
find_library(CURL_LIBRARY curl)
find_path(SODIUM_INCLUDE_DIR sodium.h)
find_library(SODIUM_LIBRARY sodium)

if(NOT CURL_INCLUDE_DIR OR NOT CURL_LIBRARY)
  message(FATAL_ERROR "Could not find libcurl. Install libcurl-dev.")
endif()

if(NOT SODIUM_INCLUDE_DIR OR NOT SODIUM_LIBRARY)
  message(FATAL_ERROR "Could not find libsodium. Install libsodium-dev.")
endif()

set(CURL_INCLUDE_DIRS   ${CURL_INCLUDE_DIR})
set(CURL_LIBRARIES      ${CURL_LIBRARY})
set(SODIUM_INCLUDE_DIRS ${SODIUM_INCLUDE_DIR})
set(SODIUM_LIBRARIES    ${SODIUM_LIBRARY})

find_package(nlohmann_json 3.2.0 REQUIRED)

if(DEFINED SODIUM_LIBRARY_DIRS)
  link_directories(${SODIUM_LIBRARY_DIRS})
endif()

add_library(client_lib
  src/HttpClient.cpp
  src/JsonHelpers.cpp
  src/CryptoHelpers.cpp
  src/ApiClient.cpp
  src/Models.cpp
)

target_include_directories(client_lib
    PUBLIC  ${PROJECT_SOURCE_DIR}/include
    PRIVATE ${CURL_INCLUDE_DIRS} ${SODIUM_INCLUDE_DIRS}
)

target_link_libraries(client_lib PRIVATE
    ${SODIUM_LIBRARIES}
    nlohmann_json::nlohmann_json
    ${CURL_LIBRARIES}
)

add_executable(epic_client src/main.cpp)

target_include_directories(epic_client PRIVATE
    ${CURL_INCLUDE_DIRS}
    ${SODIUM_INCLUDE_DIRS}
)

target_link_libraries(epic_client PRIVATE client_lib)

install(TARGETS epic_client client_lib
  RUNTIME DESTINATION bin
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
)
