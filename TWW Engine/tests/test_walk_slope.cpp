// test_walk_slope.cpp - a walk up a steep slope takes ANM_WALKSLOPE (setBlendMoveAnime picks it
// when m34E2 is below -0x11C7) and keeps both under clocks finite. An animation loaded with
// frameMax 0 runs the clocks at +infinity and hangs `J3DFrameCtrl::update`'s wrap loop.
//
// The world is the slab `y = z / 2` (0x12E4 on the 65536 circle); power-of-two vertices keep the
// plane exact. Link faces up the slope (facing 0 travels +z) with the stick held forward.

#include <cmath>
#include <string>

#include "framework/require_bits.h"
#include "framework/runner.h"

#include "d/actor/d_a_player_main.h"
#include "engine/room.h"
#include "engine/session.h"

namespace {

tww_engine::RoomDzb slope_dzb() {
    tww_engine::RoomDzb d = tww_engine::flat_floor_dzb(0.0f);
    for (size_t i = 0; i < d.v_tbl.size(); ++i) {
        d.v_tbl[i].y = d.v_tbl[i].z * 0.5f;
    }
    return d;
}

struct Walked {
    int frames = 0;
    int stopped = -1;             // the frame a step came back not Ok, or -1
    tww_engine::StepResult why = tww_engine::StepResult::Ok;
    bool slope_walk = false;      // ANM_WALKSLOPE's .bck was the MOVE0 slot on some frame
    bool finite = true;           // every under clock's rate and frame stayed finite
    s16 steepest = 0;             // the most negative m34E2 seen
};

Walked walk_up(int frames) {
    const tww_engine::RoomDzb dzb = slope_dzb();
    tww_engine::Init init;
    init.pos.set(0.0f, 0.0f, 0.0f);
    init.shape_angle_y = 0;
    init.travel_angle_y = 0;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    tww_engine::Session::boundary_reset();
    tww_engine::Session session(init, &dzb, tww_engine::RunOptions());
    tww_engine::Pad pad;
    pad.stick_angle_raw = 0;
    pad.target_angle = 0;
    pad.stick_distance = 1.0f;
    Walked w;
    for (int i = 1; i <= frames; ++i) {
        const tww_engine::StepResult r = session.step(pad);
        daPy_lk_c& lk = session.lk;
        if (r != tww_engine::StepResult::Ok) {
            w.stopped = i;
            w.why = r;
            break;
        }
        ++w.frames;
        if (lk.m34E2 < w.steepest) w.steepest = lk.m34E2;
        if (lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx ==
            dRes_INDEX_LKANM_BCK_WALKSLOPE_e) {
            w.slope_walk = true;
        }
        for (int k = 0; k < 2; ++k) {
            const J3DFrameCtrl& f = lk.mFrameCtrlUnder[k];
            if (!std::isfinite(f.getRate()) || !std::isfinite(f.getFrame())) w.finite = false;
        }
    }
    return w;
}

}  // namespace

TWWE_TEST(a_walk_up_a_steep_slope_runs_with_finite_clocks,
          "with no length for ANM_WALKSLOPE, the slope walk's blend runs both under clocks at "
          "+infinity and the frame never ends - a hung thread, not a wrong number") {
    const Walked w = walk_up(60);
    REQUIRE_INT(c, w.stopped, -1, "a step came back not Ok");
    REQUIRE_INT(c, w.frames, 60, "the walk did not run its sixty frames");
    REQUIRE_TRUE(c, w.steepest <= -0x11C7,
                 "the slab never read as steep enough for the slope walk (m34E2 " +
                     std::to_string(w.steepest) + ") - the case would not reach what it guards");
    REQUIRE_TRUE(c, w.slope_walk, "the walk never took ANM_WALKSLOPE");
    REQUIRE_TRUE(c, w.finite, "an under clock's rate or frame left the finite numbers");
    c.note("m34E2 down to " + std::to_string(w.steepest) + ", ANM_WALKSLOPE reached, 60 frames");
}
