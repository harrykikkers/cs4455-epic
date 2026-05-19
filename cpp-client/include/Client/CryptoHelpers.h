#pragma once

#include <string>
#include <vector>

namespace Client {

class CryptoHelpers {
public:
    static std::string generateBase64Nonce();
    static std::string encryptMessage(const std::string& plaintext,
                                      const std::string& recipientPublicKeyBase64,
                                      const std::string& senderSecretKeyBase64,
                                      std::string& outNonceBase64);
    static std::string generateKeypairPublicBase64(std::string& outSecretKeyBase64);
    static std::string toBase64(const std::vector<unsigned char>& data);
    static std::vector<unsigned char> fromBase64(const std::string& text);
};

} // namespace Client
