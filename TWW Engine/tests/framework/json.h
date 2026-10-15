// json.h - just enough JSON to read a golden: what Python's `json.dump` writes (objects, arrays,
// strings, numbers, the three literals). No writer: goldens are produced elsewhere.
//
// A golden's floats are f32 widened to f64 and printed by Python's repr, which round-trips, so
// `strtod` and the f32 cast in `as_f32()` are bit-exact. It is the only way a float leaves this
// file, so a caller cannot compare doubles by accident.

#ifndef TWW_ENGINE_TESTS_JSON_H
#define TWW_ENGINE_TESTS_JSON_H

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace tww_engine {
namespace testing {

class Json {
public:
    enum class Kind { Null, Bool, Number, String, Array, Object };

    Kind kind = Kind::Null;
    bool boolean = false;
    double number = 0.0;
    std::string str;
    std::vector<Json> array;
    std::map<std::string, Json> object;

    bool is_null() const { return kind == Kind::Null; }

    /// Parse `text`. On failure returns false and puts a line/column message in `error`.
    static bool parse(const std::string& text, Json* out, std::string* error);
    /// Read and parse a file. Failure message names the path.
    static bool load(const std::string& path, Json* out, std::string* error);

    /// Member of an object, or a null Json if absent (some columns are absent on some rows).
    const Json& operator[](const std::string& key) const;
    const Json& operator[](size_t i) const;
    size_t size() const;
    bool has(const std::string& key) const;

    /// The f32 this number is. Exact: see the header comment.
    float as_f32() const { return static_cast<float>(number); }
    /// Its bit pattern.
    uint32_t as_f32_bits() const;
    long long as_int() const { return static_cast<long long>(number); }
};

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_JSON_H
