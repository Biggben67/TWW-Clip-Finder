// test_cam_l_held.cpp - L held with nothing to target, in `dCamera_c::followCamera` Field mode 1.
// `nextMode`'s `setFlag(0x100000)` arms the tail that raises `m3B8`, the weight the yaw is chased
// behind the player by; the decomp's condition on `m392` makes that arm unreachable, and the port
// corrects it to the DOL.
//
// Tape: the player stands on facing 9170, enters the C up view and leaves by B, then holds L for
// 30 frames from the second frame after the view ends. His facing and view status are fed.
//
// Expected values are a hand reading on GZLJ01: 9182 for L's first three frames, 9177 while held,
// then a climb to 9206. The climb's frame counts were not read, so only its ends and direction
// are held.

#include <string>
#include <vector>

#include "framework/runner.h"

#include "boundary/game_boundary.h"
#include "d/actor/d_a_player_main.h"
#include "engine/session.h"
#include "m_Do/m_Do_controller_pad.h"

namespace {

const int kFacing = 9170;

struct Frame {
    bool l;
    bool view;
};

/// The camera's yaw after each frame of the tape.
std::vector<int> run(const std::vector<Frame>& tape) {
    tww_engine::Init init;
    init.pos.set(0.0f, 0.0f, 0.0f);
    init.shape_angle_y = static_cast<s16>(kFacing);
    init.travel_angle_y = static_cast<s16>(kFacing);
    init.normal_speed = 0.0f;
    init.speed_f = 0.0f;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    tww_engine::RunOptions opts;
    opts.ground = tww_engine::RunOptions::Ground::Supplied;
    opts.floor_y = 0.0f;
    opts.camera = true;
    opts.camera_yaw = static_cast<s16>(kFacing);
    tww_engine::Session session(init, NULL, opts);
    session.bind();
    std::vector<int> yaw;
    for (const Frame& f : tape) {
        session.lk.shape_angle.y = static_cast<s16>(kFacing);
        session.lk.current.angle.y = static_cast<s16>(kFacing);
        g_mDoCPd_cpadInfo[PAD_1].mMainStickPosX = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mCStickPosX = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mCStickPosY = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mCStickValue = 0.0f;
        g_mDoCPd_cpadInfo[PAD_1].mTriggerLeft = f.l ? 1.0f : 0.0f;
        cam_stub_lockon = f.l;
        if (f.view) {
            session.lk.stub_player_status0 |= daPyStts0_SUBJECT_e;
        } else {
            session.lk.stub_player_status0 &= ~daPyStts0_SUBJECT_e;
        }
        session.runCamera(1);
        yaw.push_back(session.cameraFacts().yaw & 0xFFFF);
    }
    cam_stub_lockon = false;
    g_mDoCPd_cpadInfo[PAD_1].mTriggerLeft = 0.0f;
    return yaw;
}

void add(std::vector<Frame>* t, int n, bool l, bool view) {
    for (int i = 0; i < n; ++i) t->push_back({l, view});
}

}  // namespace

TWWE_TEST(l_held_turns_the_follow_camera_back_onto_the_facing,
          "the follow camera's tail never raises m3B8 in Field mode 1, so L held with nothing to "
          "target leaves the camera creeping up its ladder instead of turning it behind the "
          "player, and every turnaround read off an L press is a value the console never shows") {
    const int kHold = 30;
    std::vector<Frame> tape;
    add(&tape, 11, false, false);  // standing
    add(&tape, 3, false, false);   // the C up press, before its status is up
    add(&tape, 20, false, true);   // in the view; B is its second-last frame
    add(&tape, 1, false, false);   // the view has ended
    const int l_at = static_cast<int>(tape.size());
    add(&tape, kHold, true, false);
    const int let_go = static_cast<int>(tape.size());
    add(&tape, 60, false, false);

    const std::vector<int> y = run(tape);
    REQUIRE_INT(c, static_cast<long long>(y.size()), static_cast<long long>(tape.size()),
                "the tape did not run to its end");

    for (int i = 0; i < 3; ++i) {
        REQUIRE_INT(c, y[l_at + i], 9182,
                    "L's frame " + std::to_string(i) + " is not the console's 9182");
    }
    for (int i = l_at + 3; i < let_go; ++i) {
        REQUIRE_INT(c, y[i], 9177,
                    "L held, frame " + std::to_string(i - l_at) + ", is not the console's 9177");
    }
    int lowest = y[let_go];
    for (size_t i = static_cast<size_t>(let_go) + 1; i < y.size(); ++i) {
        REQUIRE_TRUE(c, y[i] >= y[i - 1],
                     "after letting go the camera moved back down at frame " +
                         std::to_string(static_cast<int>(i) - let_go));
        if (y[i] < lowest) lowest = y[i];
    }
    REQUIRE_TRUE(c, lowest >= 9177, "after letting go the camera went below 9177");
    REQUIRE_INT(c, y.back(), 9206, "the climb after letting go does not end on the console's 9206");
    c.note("L held " + std::to_string(kHold) + " frames: 9182 x3, 9177 x" +
           std::to_string(let_go - l_at - 3) + ", then " + std::to_string(y[let_go]) +
           " rising to " + std::to_string(y.back()));
}
