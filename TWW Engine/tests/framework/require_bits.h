// require_bits.h - the only float assertion this suite has.
//
// REQUIRE_BITS compares the two 32-bit patterns; there is no epsilon parameter and no other float
// assertion, so every comparison is 0 ULP. Comparing patterns means -0.0f and +0.0f differ and a
// NaN equals only the same NaN, which is what a bit-exactness claim wants.
//
// EXPECT_KNOWN_GAP must fail, so the suite goes red the day a marked gap starts passing.

#ifndef TWW_ENGINE_TESTS_REQUIRE_BITS_H
#define TWW_ENGINE_TESTS_REQUIRE_BITS_H

#include <cstdint>
#include <cstring>
#include <string>

namespace tww_engine {
namespace testing {

inline uint32_t bits(float f) {
    uint32_t u;
    std::memcpy(&u, &f, 4);
    return u;
}

inline float from_bits(uint32_t u) {
    float f;
    std::memcpy(&f, &u, 4);
    return f;
}

/// One running test. Failures accumulate rather than abort, because a replay that stops at its
/// first bad frame hides whether the rest of the run diverged or the one frame did.
class Case {
public:
    explicit Case(const char* name) : name_(name) {}

    const char* name() const { return name_; }
    int failures() const { return failures_; }
    int checks() const { return checks_; }
    //: Of those, the ones that compared two f32 bit patterns, reported apart from integer and
    //: boolean assertions.
    int bit_checks() const { return bit_checks_; }
    const std::string& log() const { return log_; }
    const std::string& notes() const { return notes_; }

    /// A measurement the case made, printed whether it passes or fails.
    void note(const std::string& line) { notes_ += "  " + line + "\n"; }

    void check_bits(uint32_t got, uint32_t want, const std::string& where);
    void check_int(long long got, long long want, const std::string& where);
    void fail(const std::string& why);
    /// A claim this suite makes that is not a comparison - "this ran", "this was reached".
    void require(bool ok, const std::string& why) {
        checks_++;
        if (!ok) {
            fail(why);
        }
    }
    /// Must not hold. If it starts holding, the suite goes red and says to unmark it.
    void known_gap(bool ok, const std::string& what);

private:
    const char* name_;
    int failures_ = 0;
    int checks_ = 0;
    int bit_checks_ = 0;
    std::string log_;
    std::string notes_;
};

}  // namespace testing
}  // namespace tww_engine

//: The float comparison. `where` names the row and column, so a failure reads as a place in the
//: data.
#define REQUIRE_BITS(c, actual, expected, where) \
    (c).check_bits(::tww_engine::testing::bits(actual), ::tww_engine::testing::bits(expected), (where))

//: The same, for a value that is already a bit pattern, so no float is converted on the way in.
#define REQUIRE_BITS_RAW(c, actual_bits, expected_bits, where) \
    (c).check_bits((actual_bits), (expected_bits), (where))

#define REQUIRE_INT(c, actual, expected, where) \
    (c).check_int((actual), (expected), (where))

#define REQUIRE_TRUE(c, cond, why) (c).require((cond), (why))

#define EXPECT_KNOWN_GAP(c, cond, what) (c).known_gap((cond), (what))

#endif  // TWW_ENGINE_TESTS_REQUIRE_BITS_H
