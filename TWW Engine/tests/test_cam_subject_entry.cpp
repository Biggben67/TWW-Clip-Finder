// test_cam_subject_entry.cpp - `dCamera_c::subjectCamera`'s entry arm against the console, run
// through `Session::runFirstPersonCamera` (raises `daPyStts0_SUBJECT_e`, lets `Run`'s sequencer pick
// mode 4, runs `Run` until the entry raises `m100`).
//
// `cup_turn_camera_live.json` `entry` is a GZLJ01 per-frame read that swings the csangle 10206 BAM
// off the facing before pressing C-up:
//     10206, 10206, 10206, 8748, 7290, 5832, 4374, 2916, 1458, 0, 0, 0, 0, 0
// i.e. `1 / (end - m108)` with `end == 7`, the arm `check_owner_action(mPadId,
// daPyStts0_SUBJECT_e)` picks. The three holding frames are the press being taken and are not
// compared (the port starts at the mode change); the landing `csangle_after_entry` is.

#include "framework/golden.h"
#include "framework/runner.h"

#include "engine/session.h"

#include "d/actor/d_a_player_main.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;

const char* const kGolden = "cup_turn_camera_live.json";

/// A flat floor: `Run`'s tail clamps the camera centre against the floor margin, so the entry
/// needs ground under it, and the console capture was taken on flat ground.
tww_engine::RunOptions flat_options() {
    tww_engine::RunOptions opts;
    opts.ground = tww_engine::RunOptions::Ground::Supplied;
    opts.floor_y = 0.0f;
    opts.camera = true;
    return opts;
}

TWWE_TEST(the_first_person_entry_lands_on_the_facing_like_the_console,
          "dCamera_c::subjectCamera's entry - composed through Run and the mode sequencer - "
          "leaves the camera somewhere other than where GZLJ01 left it, on a capture that swings "
          "the csangle 10206 BAM off the facing before the view starts") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["entry"];

    REQUIRE_TRUE(c, rows.size() > 0, "the capture has no entry rows at all");

    // A row already on the facing passes a body that does nothing; require some that move.
    size_t moved = 0;
    for (size_t i = 0; i < rows.size(); ++i) {
        if (rows[i]["csangle_before"].as_int() != rows[i]["csangle_after_entry"].as_int()) {
            ++moved;
        }
    }
    REQUIRE_TRUE(c, moved > 0,
                 "every row in this capture starts with the camera already on the facing - "
                 "nothing here would notice a view that never ran");
    c.note("rows: " + std::to_string(rows.size()) + ", of them moving the camera: " +
           std::to_string(moved));

    for (size_t i = 0; i < rows.size(); ++i) {
        const Json& r = rows[i];
        const int facing = static_cast<int>(r["facing"].as_int());
        const int before = static_cast<int>(r["csangle_before"].as_int());
        const int after = static_cast<int>(r["csangle_after_entry"].as_int());
        const std::string name = r["case"].str;

        tww_engine::Init init;
        init.pos.set(0.0f, 0.0f, 0.0f);
        init.shape_angle_y = static_cast<s16>(facing);
        init.travel_angle_y = static_cast<s16>(facing);
        init.normal_speed = 0.0f;
        init.speed_f = 0.0f;
        init.proc = daPy_lk_c::daPyProc_WAIT_e;

        tww_engine::RunOptions opts = flat_options();
        opts.camera_yaw = static_cast<s16>(before);

        tww_engine::Session session(init, NULL, opts);
        // The camera must start at the row's `csangle_before`.
        REQUIRE_INT(c, session.cameraYaw() & 0xFFFF, before & 0xFFFF,
                    name + ": the camera was not seated where the capture says the view started");

        // A ceiling, not a count: twenty is past any `end` the body has.
        const int ran = session.runFirstPersonCamera(20);
        REQUIRE_TRUE(c, ran < 20, name + ": the view never finished entering");
        c.note(name + ": the entry took " + std::to_string(ran) + " frame(s)");

        REQUIRE_INT(c, session.cameraYaw() & 0xFFFF, after & 0xFFFF,
                    name + ": the first-person entry left the camera somewhere other than where "
                           "the console left it");
    }
}

}  // namespace
