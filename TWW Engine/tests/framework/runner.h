// runner.h - the suite: registration and the run. Hand-rolled rather than doctest/Catch2 because
// both ship `Approx`, which this suite bans.
//
// A run prints every failure by name with its row and column, and the golden tier split (console
// captures vs the old sim's output). A red control (`Expect::Red`) fails the suite if it passes.

#ifndef TWW_ENGINE_TESTS_RUNNER_H
#define TWW_ENGINE_TESTS_RUNNER_H

#include <functional>
#include <string>
#include <vector>

#include "framework/require_bits.h"

namespace tww_engine {
namespace testing {

enum class Expect {
    Green,  //: must pass
    Red,    //: must fail - a deliberately wrong value, a twin, a misaligned input
};

struct Registration {
    const char* name;
    const char* what;  //: one line: what a failure here would mean
    Expect expect;
    std::function<void(Case&)> body;
};

/// The registry. A test registers itself at static-init time; nothing has to list them.
std::vector<Registration>& registry();

struct Register {
    Register(const char* name, const char* what, Expect expect, std::function<void(Case&)> body) {
        registry().push_back(Registration{name, what, expect, std::move(body)});
    }
};

/// Runs everything (or only names containing `filter`), prints, and returns a process exit code.
int run_all(const char* filter);

}  // namespace testing
}  // namespace tww_engine

//: Define a case that must pass.
#define TWWE_TEST(ident, what)                                                                  \
    static void ident(::tww_engine::testing::Case&);                                            \
    static ::tww_engine::testing::Register ident##_reg(                                         \
        #ident, what, ::tww_engine::testing::Expect::Green, ident);                             \
    static void ident(::tww_engine::testing::Case& c)

//: Define a red control: a case that must fail. `what` names the wrong value it injects.
#define TWWE_RED_CONTROL(ident, what)                                                           \
    static void ident(::tww_engine::testing::Case&);                                            \
    static ::tww_engine::testing::Register ident##_reg(                                         \
        #ident, what, ::tww_engine::testing::Expect::Red, ident);                               \
    static void ident(::tww_engine::testing::Case& c)

#endif  // TWW_ENGINE_TESTS_RUNNER_H
