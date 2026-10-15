// test_session_camera.cpp - `Session::seatCamera` and the `RunOptions::camera` arm: the wiring of
// `dCamera_c::Run` into `Session`. What the camera computes is gated in `test_cam_csangle.cpp`.
// Held here: the seated yaw reads back (the globe stores an inclination and `mAngleY` is
// `mDirection.U().Inv()`, a half circle apart); `Run` is entered every `step`; both constructors
// read the arm; and a session with no camera steps bit-identically to one with it.
// These are claims about the library's own interface, so there is no golden.

#include <string>
#include <vector>

#include "framework/manifest.h"
#include "framework/runner.h"

#include "player_rig.h"

#include "boundary/game_boundary.h"
#include "d/d_camera.h"
#include "m_Do/m_Do_controller_pad.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Rig;

/// 0 and 0x8000 map onto each other through the half circle; 0xFFFF is one below the wrap.
const int kYaws[] = {0, 0x4000, 0x8000, 0xC000, 7018, 0xFFFF, 21422, 2392};

/// `Run` begins with `updatePad`, which copies the global pad block; clear it so no earlier case
/// leaks in.
void pad_at_rest() {
    std::memset(&g_mDoCPd_cpadInfo[0], 0, sizeof(g_mDoCPd_cpadInfo[0]));
}

/// Stick centred, nothing pressed.
tww_engine::Pad resting_pad(int facing) {
    tww_engine::Pad pad;
    pad.stick_angle_raw = static_cast<s16>(facing);
    pad.target_angle = static_cast<s16>(facing);
    pad.stick_distance = 0.0f;
    return pad;
}

tww_engine::Init standing_at(int facing) {
    tww_engine::Init init;
    init.pos.set(209.62948608398438f, 0.0f, 549.9795532226562f);
    init.shape_angle_y = static_cast<s16>(facing);
    init.travel_angle_y = static_cast<s16>(facing);
    init.pad = resting_pad(facing);
    return init;
}

}  // namespace

TWWE_TEST(a_seated_camera_answers_the_yaw_it_was_seated_at,
          "Session::seatCamera stores the yaw through the view globe's inclination and reads it "
          "back through mAngleY = U().Inv(), so a seat that loses the half-circle between them "
          "answers a wrong yaw at every angle that is not its own opposite") {
    for (size_t i = 0; i < sizeof(kYaws) / sizeof(kYaws[0]); i++) {
        const int yaw = kYaws[i];
        tww_engine::Session s;
        REQUIRE_TRUE(c, !s.hasCamera(), "a fresh Session already has a camera");
        s.seatCamera(static_cast<s16>(yaw));
        REQUIRE_TRUE(c, s.hasCamera(), "seatCamera left hasCamera() false");
        REQUIRE_INT(c, s.cameraYaw() & 0xFFFF, yaw & 0xFFFF,
                    "the yaw seated at " + std::to_string(yaw) + " did not read back");
    }
    c.note("yaws swept: " + std::to_string(sizeof(kYaws) / sizeof(kYaws[0])));
}

TWWE_TEST(the_options_arm_is_what_seats_the_camera_through_either_constructor,
          "RunOptions::camera is the switch a caller reaches for and the constructors are what "
          "read it, so an arm that is raised and not read leaves a session with no camera while "
          "every option says it has one - and the Init constructor delegating to the other makes "
          "that two places to miss it rather than one") {
    const int facing = 7018;
    const int yaw = 21422;

    // Off by default.
    tww_engine::RunOptions plain;
    REQUIRE_TRUE(c, !plain.camera, "RunOptions::camera does not default to off");

    tww_engine::RunOptions watched;
    watched.camera = true;
    watched.camera_yaw = static_cast<s16>(yaw);

    // No Init: the camera watches the origin.
    tww_engine::Session bare(NULL, watched);
    REQUIRE_TRUE(c, bare.hasCamera(), "the arm was raised and the bare constructor seated nothing");
    REQUIRE_INT(c, bare.cameraYaw() & 0xFFFF, yaw, "the bare constructor's camera is at a yaw "
                                                   "nobody asked for");

    // The Init constructor delegates to the bare one and re-seats; the yaw must survive it.
    tww_engine::Session seeded(standing_at(facing), NULL, watched);
    REQUIRE_TRUE(c, seeded.hasCamera(), "the arm was raised and the Init constructor seated "
                                        "nothing");
    REQUIRE_INT(c, seeded.cameraYaw() & 0xFFFF, yaw,
                "the Init constructor's re-seat lost the yaw the options named");

    tww_engine::Session bare_off(NULL, plain);
    tww_engine::Session seeded_off(standing_at(facing), NULL, plain);
    REQUIRE_TRUE(c, !bare_off.hasCamera(), "a session with the arm down has a camera anyway");
    REQUIRE_TRUE(c, !seeded_off.hasCamera(),
                 "a seeded session with the arm down has a camera anyway");
}

TWWE_TEST(the_camera_runs_once_per_frame_and_not_once_per_session,
          "dCamera_c::Run is entered once per Session::step, measured by the camera boundary's "
          "own counter - a camera seated and never run would answer its seat forever and read "
          "exactly like one that is watching") {
    const int facing = 7018;
    tww_engine::RunOptions watched;
    watched.camera = true;
    watched.camera_yaw = static_cast<s16>(facing);
    tww_engine::Session s(standing_at(facing), NULL, watched);
    pad_at_rest();

    const int frames = 12;
    cam_boundary_reset();
    const int before = cam_boundary_hits;
    REQUIRE_INT(c, before, 0, "the camera boundary counter did not reset");

    const tww_engine::Pad pad = resting_pad(facing);
    int reached_at_least_once = 0;
    for (int f = 0; f < frames; f++) {
        const int was = cam_boundary_hits;
        pad_at_rest();
        s.step(pad);
        if (cam_boundary_hits > was) reached_at_least_once++;
    }
    // Every frame, not only the first.
    REQUIRE_INT(c, reached_at_least_once, frames,
                "some frame ran without the camera entering a single one of its own definitions");
    c.note("camera boundary definitions reached over " + std::to_string(frames) +
           " frame(s): " + std::to_string(cam_boundary_hits));
    c.note("csangle after the run: " + std::to_string(s.cameraYaw() & 0xFFFF));
}

TWWE_TEST(a_session_with_no_camera_steps_exactly_as_it_did_before_there_was_one,
          "a seated camera writes into the player, so the cases in this suite that seat none "
          "are passing for a reason that has stopped being true") {
    const int facing = 7018;
    const int frames = 20;
    const tww_engine::Pad pad = resting_pad(facing);

    tww_engine::RunOptions with_camera;
    with_camera.camera = true;
    with_camera.camera_yaw = static_cast<s16>(facing);
    tww_engine::Session plain(standing_at(facing), NULL);
    tww_engine::Session watched(standing_at(facing), NULL, with_camera);

    // Stepped alternately: `step` calls `bind()` over process-wide globals, so a camera writing
    // through a global would land on the plain session.
    for (int f = 0; f < frames; f++) {
        pad_at_rest();
        watched.step(pad);
        plain.step(pad);

        const daPy_lk_c& a = plain.state();
        const daPy_lk_c& b = watched.state();
        const std::string at = "frame " + std::to_string(f) + ": ";
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(a.current.pos.x),
                         tww_engine::f32_bits(b.current.pos.x), at + "current.pos.x");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(a.current.pos.y),
                         tww_engine::f32_bits(b.current.pos.y), at + "current.pos.y");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(a.current.pos.z),
                         tww_engine::f32_bits(b.current.pos.z), at + "current.pos.z");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(a.speedF), tww_engine::f32_bits(b.speedF),
                         at + "speedF");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(a.mNormalSpeed),
                         tww_engine::f32_bits(b.mNormalSpeed), at + "mNormalSpeed");
        REQUIRE_INT(c, a.shape_angle.y, b.shape_angle.y, at + "shape_angle.y");
        REQUIRE_INT(c, a.current.angle.y, b.current.angle.y, at + "current.angle.y");
        REQUIRE_INT(c, a.mCurProc, b.mCurProc, at + "mCurProc");
        REQUIRE_INT(c, a.m34E8, b.m34E8, at + "m34E8");
    }
    c.note("frames compared: " + std::to_string(frames));
}

TWWE_RED_CONTROL(the_seat_is_read_back_through_a_half_circle_and_this_control_drops_it,
                 "INJECTED: the yaw read back is compared against the view globe's inclination - "
                 "the same number plus the half-circle Inv() takes off - which is what a seat that "
                 "forgot the 0x8000 would answer. It must be red at every yaw, and it is the only "
                 "thing that says the half-circle in seatCamera is load-bearing rather than two "
                 "constants that happen to cancel") {
    for (size_t i = 0; i < sizeof(kYaws) / sizeof(kYaws[0]); i++) {
        const int yaw = kYaws[i];
        tww_engine::Session s;
        s.seatCamera(static_cast<s16>(yaw));
        REQUIRE_INT(c, s.cameraYaw() & 0xFFFF, (yaw + 0x8000) & 0xFFFF,
                    "the yaw at " + std::to_string(yaw) + " is not the inclination");
    }
}
