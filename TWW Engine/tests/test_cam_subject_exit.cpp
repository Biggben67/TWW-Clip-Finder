// test_cam_subject_exit.cpp - properties of the console's first-person-exit capture,
// `cup_turn_camera_live.json` (`exits`, and the `exit_series` in `turns`), a live GZLJ01 read.
// No port runs here; `tests/cam_exit_probe.cpp` runs the `followCamera` frames after the view.
// The properties any model of the exit must survive:
//   1. Some turns are still moving at the end of their captured series, and `csangle_after_exit`
//      is read past it, so the column depends on the wait before the next press.
//   2. B and C-down agree on some turns and differ on others, so neither is the other plus a
//      constant.
// Row counts are asserted first, so an empty capture cannot pass.

#include "framework/golden.h"
#include "framework/runner.h"

#include <string>

namespace {

using tww_engine::testing::Json;

const char* const kGolden = "cup_turn_camera_live.json";

/// The signed short way round.
int signed_delta(int a, int b) {
    int d = (a - b) & 0xFFFF;
    return d > 0x8000 ? d - 0x10000 : d;
}

TWWE_TEST(the_exit_is_not_a_function_of_the_turn_alone,
          "the console's exit capture lets a single offset per turn be fitted to it - which it "
          "does not, because ten of its turns are still moving when the capture ends") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& turns = g["turns"];

    REQUIRE_TRUE(c, turns.size() > 0, "the capture has no turn rows at all");

    size_t settled = 0;
    size_t moving = 0;
    size_t read_past_the_series = 0;
    int furthest_past = 0;
    for (size_t i = 0; i < turns.size(); ++i) {
        const Json& r = turns[i];
        const int facing = static_cast<int>(r["facing_after"].as_int());
        const Json& series = r["exit_series"];
        REQUIRE_TRUE(c, series.size() > 1,
                     "a turn row carries no exit series to say whether it settled");

        // Settled is flat from frame two; frame one is the press frame and reads the view's angle.
        bool flat = true;
        for (size_t k = 2; k < series.size(); ++k) {
            if (series[k].as_int() != series[1].as_int()) {
                flat = false;
                break;
            }
        }
        if (flat) {
            ++settled;
        } else {
            ++moving;
        }

        const int at_twenty = signed_delta(static_cast<int>(series[series.size() - 1].as_int()),
                                           facing);
        const int when_read =
            signed_delta(static_cast<int>(r["csangle_after_exit"].as_int()), facing);
        if (at_twenty != when_read) {
            ++read_past_the_series;
            const int past = when_read - at_twenty;
            if ((past < 0 ? -past : past) > (furthest_past < 0 ? -furthest_past : furthest_past)) {
                furthest_past = past;
            }
        }
    }

    c.note("turns: " + std::to_string(turns.size()) + ", settled by frame two: " +
           std::to_string(settled) + ", still moving at frame twenty: " + std::to_string(moving));
    c.note("rows whose reading is past the end of their own series: " +
           std::to_string(read_past_the_series) + ", furthest by " +
           std::to_string(furthest_past) + " unit(s)");

    REQUIRE_TRUE(c, settled > 0, "no turn in this capture settles - the split this case is about "
                                 "is not in the data any more");
    REQUIRE_TRUE(c, moving > 0,
                 "every turn in this capture settles, so nothing here would catch a model that "
                 "reads csangle_after_exit as a property of the turn");

    REQUIRE_TRUE(c, read_past_the_series > 0,
                 "no row is read past the end of its own series, so the capture no longer says "
                 "that how long you wait changes the answer");
}

TWWE_TEST(the_two_exits_are_not_one_exit_plus_an_offset,
          "the two exit modes differ by a constant, so a model of one would be a model of both") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& exits = g["exits"];

    REQUIRE_TRUE(c, exits.size() > 0, "the capture has no exit rows at all");

    // Paired by turn: the same turn left both ways.
    size_t paired = 0;
    size_t agreeing = 0;
    int widest = 0;
    for (size_t i = 0; i < exits.size(); ++i) {
        if (exits[i]["mode"].str != "lb") continue;
        const int steps = static_cast<int>(exits[i]["steps"].as_int());
        for (size_t k = 0; k < exits.size(); ++k) {
            if (exits[k]["mode"].str != "cdown") continue;
            if (static_cast<int>(exits[k]["steps"].as_int()) != steps) continue;
            ++paired;
            const int b = signed_delta(static_cast<int>(exits[i]["csangle_after_exit"].as_int()),
                                       static_cast<int>(exits[i]["facing_after"].as_int()));
            const int cd = signed_delta(static_cast<int>(exits[k]["csangle_after_exit"].as_int()),
                                        static_cast<int>(exits[k]["facing_after"].as_int()));
            const int apart = b - cd;
            if (apart == 0) ++agreeing;
            if ((apart < 0 ? -apart : apart) > (widest < 0 ? -widest : widest)) widest = apart;
        }
    }

    c.note("turns left both ways: " + std::to_string(paired) + ", of them agreeing exactly: " +
           std::to_string(agreeing) + ", widest disagreement: " + std::to_string(widest) +
           " unit(s)");

    REQUIRE_TRUE(c, paired > 0,
                 "no turn in this capture was left both ways, so nothing here compares the two "
                 "exits at all");
    // An agreeing row rules out a per-mode constant offset.
    REQUIRE_TRUE(c, agreeing > 0,
                 "no turn has the two exits landing on the same angle, so the capture no longer "
                 "refutes a model that reads one exit as the other plus a constant");
    REQUIRE_TRUE(c, agreeing < paired,
                 "the two exits agree on every turn in this capture, which would make them one "
                 "exit - and the whole reason the search carries a choice of exit would be gone");
}

}  // namespace
