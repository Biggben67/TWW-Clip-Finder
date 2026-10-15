// sha256.h - the loader checks each golden against its recorded digest, so an edited golden fails
// at load.

#ifndef TWW_ENGINE_TESTS_SHA256_H
#define TWW_ENGINE_TESTS_SHA256_H

#include <string>

namespace tww_engine {
namespace testing {

/// Lowercase hex digest of `data`.
std::string sha256_hex(const std::string& data);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_SHA256_H
