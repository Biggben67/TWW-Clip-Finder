// test_stairs_roll.cpp - a roll up sea r11's stairs keeps its flat speed and ends where the
// console put it.
//
// `ground_tail` and `Session::seed` write the ground code into `m3580`. Code 8 is stairs, where
// posMoveFromFootPos skips the slope's cosine; with `m3580` at 0 the stairs run as a ramp.
//
// The expected landing is a console reading on GZLJ01: a plan on these stairs (a C-up turn, a
// crawl and this roll from 5.3983803, 704.59882, -203773.94) ended the roll at x -90.2980652,
// z -203738.188. The roll starts where the engine's crawl of that plan ended, at a standstill;
// the crawl is not replayed.
//
// The press is the setup finder's dry roll: L + A on a centred stick, sheathed, for three frames,
// then a neutral pad until Link is at rest.

#include <string>

#include "framework/golden.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "room_dzb.h"

#include "d/actor/d_a_player_main.h"
#include "engine/session.h"

namespace {

const s16 kFacing = static_cast<s16>(52880);

struct Rolled {
    int frames = 0;
    int stopped = -1;          // the frame a step came back not Ok, or -1
    bool rested = false;
    bool on_stairs = false;    // m3580 read 8 on some frame
    bool slowed = false;       // speedF fell below the roll's normal speed on some rolling frame
    cXyz end{0.0f, 0.0f, 0.0f};
};

Rolled roll_up_the_stairs() {
    const tww_engine::RoomDzb dzb =
        tww_engine::testing::read_room_dzb(tww_engine::testing::golden("sea_r11_bgd.json"));
    tww_engine::Init init;
    init.pos.set(-5.9857378f, 710.006653f, -203769.688f);
    init.shape_angle_y = kFacing;
    init.travel_angle_y = kFacing;
    init.equip_item = daPyItem_NONE_e;
    init.pad.stick_angle_raw = kFacing;
    init.pad.target_angle = kFacing;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    tww_engine::Session::boundary_reset();
    tww_engine::Session session(init, &dzb, tww_engine::RunOptions());

    Rolled r;
    tww_engine::Pad pad;
    pad.stick_angle_raw = kFacing;
    pad.target_angle = kFacing;
    u8 held = 0;
    for (int i = 1; i <= 3 + 96; ++i) {
        const bool pressing = i <= 3;
        const daPy_lk_c& before = session.lk;
        if (!pressing && (before.mCurProc == daPy_lk_c::daPyProc_WAIT_e ||
                          before.mCurProc == daPy_lk_c::daPyProc_FREE_WAIT_e) &&
            before.mNormalSpeed == 0.0f) {
            r.rested = true;
            break;
        }
        const u8 buttons = pressing ? static_cast<u8>(daPy_lk_c::BTN_L | daPy_lk_c::BTN_A) : 0;
        pad.item_button = buttons;
        pad.item_trigger = static_cast<u8>(buttons & ~held);
        held = buttons;
        pad.attention_lock = pressing ? TRUE : FALSE;
        pad.stick_distance = 0.0f;
        if (session.step(pad) != tww_engine::StepResult::Ok) {
            r.stopped = i;
            break;
        }
        ++r.frames;
        const daPy_lk_c& lk = session.lk;
        if (lk.m3580 == 8) r.on_stairs = true;
        if (lk.mCurProc == daPy_lk_c::daPyProc_FRONT_ROLL_e && lk.speedF < lk.mNormalSpeed) {
            r.slowed = true;
        }
    }
    r.end = session.lk.current.pos;
    return r;
}

}  // namespace

TWWE_TEST(a_roll_up_the_stairs_keeps_its_flat_speed,
          "with the ground code unread, stairs are a ramp and the roll ends 20 units short of the "
          "console's landing") {
    const Rolled r = roll_up_the_stairs();
    REQUIRE_INT(c, r.stopped, -1, "a step came back not Ok");
    REQUIRE_TRUE(c, r.rested, "the roll did not come back to a standstill");
    REQUIRE_TRUE(c, r.on_stairs,
                 "no frame stood on ground code 8 - the case would not reach what it guards");
    REQUIRE_TRUE(c, !r.slowed, "the roll's speedF fell below its normal speed on the stairs");
    REQUIRE_BITS(c, r.end.x, -90.2980652f, "the roll's end x, against the console");
    REQUIRE_BITS(c, r.end.z, -203738.188f, "the roll's end z, against the console");
    c.note("ended at " + std::to_string(r.end.x) + ", " + std::to_string(r.end.z) + " after " +
           std::to_string(r.frames) + " frames");
}
