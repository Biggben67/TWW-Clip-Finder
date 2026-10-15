// test_cam_turnarounds.cpp - what a turnaround does to the follow camera, held to the console.
//
// `dCamera_c::followCamera` on the Room camera (type 57, follow style FN09, as Kaisen's stage
// names it) while Link pivots, in particular the radius clamp on `m398` (a DOL correction to the
// decomp): without it any radius over the style's minimum is pulled down to it.
//
// Inside its limits the follow camera does not pull its radius, so entering the C up view and
// leaving it by B first puts the radius on the style's minimum whatever it was (third case).
//
// The tape: Link at (209.62948608398438, 0, 549.9795532226562) on flat ground at y 0 (the room's
// collision agrees to the bit), facing 7018, the camera behind him. 12 frames in the C up view,
// out; a wait; the stick 3 frames at the camera cardinal that reverses him; a wait.
//
// Console tier: read live on GZLJ01 off the camera (`mCenter` +0x10, `mEye` +0x1C) after the same
// input at that spot, once the camera stopped.

#include <string>

#include "framework/require_bits.h"
#include "framework/runner.h"

#include "boundary/game_boundary.h"
#include "d/actor/d_a_player_main.h"
#include "engine/session.h"
#include "m_Do/m_Do_controller_pad.h"

namespace {

int s16_of(int v) { return static_cast<int16_t>(static_cast<uint16_t>(v)); }

struct After {
    int facing = 0;
    int camera = 0;
    float center[3] = {0.0f, 0.0f, 0.0f};
    float eye[3] = {0.0f, 0.0f, 0.0f};
};

/// The camera after one turnaround, the C up view left `wait` frames before it and `gap` after.
After run(int wait, int gap, float seat_radius) {
    const int facing = 7018;
    tww_engine::Init init;
    init.pos.set(209.62948608398438f, 0.0f, 549.9795532226562f);
    init.shape_angle_y = static_cast<s16>(facing);
    init.travel_angle_y = static_cast<s16>(facing);
    init.normal_speed = 0.0f;
    init.speed_f = 0.0f;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    init.pad.stick_angle_raw = static_cast<s16>(facing);
    init.pad.target_angle = static_cast<s16>(facing);
    tww_engine::RunOptions opts;
    opts.ground = tww_engine::RunOptions::Ground::Supplied;
    opts.floor_y = 0.0f;
    opts.camera = true;
    opts.camera_yaw = static_cast<s16>(facing);
    opts.camera_type = 57;
    opts.camera_radius = seat_radius;
    tww_engine::Session session(init, NULL, opts);
    session.bind();
    tww_engine::Pad pad;
    pad.stick_angle_raw = static_cast<s16>(facing);
    pad.target_angle = static_cast<s16>(facing);
    auto one = [&](bool view, float stick_y) {
        g_mDoCPd_cpadInfo[PAD_1].mMainStickPosX = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mMainStickPosY = stick_y;
        g_mDoCPd_cpadInfo[PAD_1].mMainStickValue = stick_y < 0.0f ? -stick_y : stick_y;
        g_mDoCPd_cpadInfo[PAD_1].mCStickPosX = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mCStickPosY = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mCStickValue = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mTriggerLeft = 0.0f;
        cam_stub_lockon = false;
        pad.attention_lock = FALSE;
        if (view) {
            session.lk.stub_player_status0 |= daPyStts0_SUBJECT_e;
        } else {
            session.lk.stub_player_status0 &= ~daPyStts0_SUBJECT_e;
        }
        session.step(pad);
    };
    for (int i = 0; i < 12; ++i) one(true, 0.0f);
    for (int i = 0; i < wait; ++i) one(false, 0.0f);
    const int now = session.state().shape_angle.y & 0xFFFF;
    const int cam = session.cameraFacts().yaw & 0xFFFF;
    // The cardinal that reverses him: toward the camera when it is behind him, away when in front.
    const bool behind = s16_of(now - cam) > -0x4000 && s16_of(now - cam) < 0x4000;
    const int world = behind ? (cam + 0x8000) & 0xFFFF : cam;
    pad.stick_angle_raw = static_cast<s16>(world);
    pad.target_angle = static_cast<s16>(world);
    pad.stick_distance = 1.0f;
    for (int i = 0; i < 3; ++i) one(false, behind ? -1.0f : 1.0f);
    pad.stick_distance = 0.0f;
    for (int i = 0; i < gap; ++i) one(false, 0.0f);
    After out;
    const tww_engine::Session::CameraFacts f = session.cameraFacts();
    out.facing = session.state().shape_angle.y & 0xFFFF;
    out.camera = f.yaw & 0xFFFF;
    for (int k = 0; k < 3; ++k) {
        out.center[k] = f.center[k];
        out.eye[k] = f.eye[k];
    }
    g_mDoCPd_cpadInfo[PAD_1].mMainStickPosY = 0.0f;
    g_mDoCPd_cpadInfo[PAD_1].mMainStickValue = 0.0f;
    return out;
}

}  // namespace

TWWE_TEST(a_turnaround_moves_the_follow_camera_as_the_console_does,
          "the follow camera pulls any radius over its style's minimum down to it, so every "
          "settled eye is a unit off the console's and the turnarounds after it land elsewhere") {
    const After a = run(300, 300, 0.0f);
    REQUIRE_INT(c, a.facing, 39786, "his facing after the turnaround");
    REQUIRE_INT(c, a.camera, 6993, "the camera after the turnaround");
    // Read off the console, f32 for f32.
    const float center[3] = {209.31912231445312f, 82.49990844726562f, 549.590087890625f};
    const float eye[3] = {83.02422332763672f, 135.26202392578125f, 390.32379150390625f};
    const char* axis[3] = {"x", "y", "z"};
    for (int k = 0; k < 3; ++k) {
        REQUIRE_BITS(c, a.center[k], center[k], std::string("the centre's ") + axis[k]);
        REQUIRE_BITS(c, a.eye[k], eye[k], std::string("the eye's ") + axis[k]);
    }
}

TWWE_TEST(the_reading_after_the_c_up_view_needs_no_timing,
          "a setup whose reading moves with how long a person waits is not one a person can do") {
    // Two seconds after B and a second and a half after the turnaround are the shortest waits the
    // engine gives one answer from; any longer is the same answer.
    const int waits[] = {60, 120, 300, 900};
    const int gaps[] = {40, 120, 300};
    for (int w : waits) {
        for (int g : gaps) {
            const After a = run(w, g, 0.0f);
            const std::string at = "wait " + std::to_string(w) + ", gap " + std::to_string(g);
            REQUIRE_INT(c, a.facing, 39786, at + ": his facing");
            REQUIRE_INT(c, a.camera, 6993, at + ": the camera");
        }
    }
}

TWWE_TEST(the_c_up_view_left_by_b_forgets_the_cameras_distance,
          "a camera whose distance survives the view carries a history nobody can see into every "
          "turnaround after it") {
    const After ref = run(300, 300, 0.0f);
    const float seats[] = {205.0f, 211.617f, 260.0f, 450.0f};
    for (float r : seats) {
        const After a = run(300, 300, r);
        const std::string at = "seated at radius " + std::to_string(r);
        REQUIRE_INT(c, a.camera, ref.camera, at + ": the camera");
        for (int k = 0; k < 3; ++k) {
            REQUIRE_BITS(c, a.eye[k], ref.eye[k], at + ": the eye");
        }
    }
}
