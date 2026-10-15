// test_seed_by_a_wall.cpp - a standstill seeded where the console stood stays there, and a crawl
// from it ends where the console put it.
//
// `Session::seed`'s collision pass: `dBgS_Acch::GetWallAddY` lifts each wall cut by the floor the
// previous frame found, so the seed must find the floor before its wall pass or, on sea r11's
// slope, the rock face pushes the standstill 0.2 units off.
//
// Expected values are console readings (GZLJ01, the setup finder's plan on sea room 11):
//   * standstill before its crawl: current.pos -938.387878, 16.5026398, -197951.781
//     (c46a98d3 41840568 c8414ff2), old.pos the same, facing 4499; the three wall cylinders hit
//     polygon 3477 at 47895, polygon 2861 at 3159, and nothing. The console was in proc 1 (first
//     person); the seed is WAIT, and both use the same 35-unit radius and three heights
//     (setBgCheckParam's default arm).
//   * the crawl's end: x -933.923645, y 16.0741272, z -197940.812.
//
// The press is the setup finder's crawl: R on a centred stick for ten frames, full stick on the
// facing with R for four, R alone for fourteen, then neutral until he is at rest.

#include <string>

#include "framework/golden.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "room_dzb.h"

#include "d/actor/d_a_player_main.h"
#include "engine/session.h"

namespace {

const s16 kFacing = static_cast<s16>(4499);

tww_engine::Init standing() {
    tww_engine::Init init;
    init.pos.set(-938.387878f, 16.5026398f, -197951.781f);
    init.shape_angle_y = kFacing;
    init.travel_angle_y = kFacing;
    init.equip_item = daPyItem_NONE_e;
    init.pad.stick_angle_raw = kFacing;
    init.pad.target_angle = kFacing;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    return init;
}

const tww_engine::RoomDzb& sea_r11() {
    static const tww_engine::RoomDzb dzb =
        tww_engine::testing::read_room_dzb(tww_engine::testing::golden("sea_r11_bgd.json"));
    return dzb;
}

struct Crawled {
    int frames = 0;
    int stopped = -1;
    bool rested = false;
    bool crawled = false;  // CRAWL_START was reached
    cXyz end{0.0f, 0.0f, 0.0f};
};

Crawled crawl() {
    tww_engine::Session::boundary_reset();
    tww_engine::Session session(standing(), &sea_r11(), tww_engine::RunOptions());

    Crawled r;
    tww_engine::Pad pad;
    pad.stick_angle_raw = kFacing;
    pad.target_angle = kFacing;
    const int kSettle = 10, kPush = 4, kHold = 14;
    u8 held = 0;
    for (int i = 1; i <= kSettle + kPush + kHold + 96; ++i) {
        const bool pressing = i <= kSettle + kPush + kHold;
        const daPy_lk_c& before = session.lk;
        if (!pressing && (before.mCurProc == daPy_lk_c::daPyProc_WAIT_e ||
                          before.mCurProc == daPy_lk_c::daPyProc_FREE_WAIT_e) &&
            before.mNormalSpeed == 0.0f) {
            r.rested = true;
            break;
        }
        const u8 buttons = pressing ? static_cast<u8>(daPy_lk_c::BTN_R) : 0;
        pad.item_button = buttons;
        pad.item_trigger = static_cast<u8>(buttons & ~held);
        held = buttons;
        pad.attention_lock = FALSE;
        pad.stick_distance = (i > kSettle && i <= kSettle + kPush) ? 1.0f : 0.0f;
        if (session.step(pad) != tww_engine::StepResult::Ok) {
            r.stopped = i;
            break;
        }
        ++r.frames;
        if (session.lk.mCurProc == daPy_lk_c::daPyProc_CRAWL_START_e) r.crawled = true;
    }
    r.end = session.lk.current.pos;
    return r;
}

}  // namespace

TWWE_TEST(a_standstill_by_a_wall_on_a_slope_stays_where_the_console_stood,
          "with the walls cut before the floor is found, the seed is pushed 0.2 units off sea "
          "r11's rock face") {
    tww_engine::Session session(standing(), &sea_r11(), tww_engine::RunOptions());
    daPy_lk_c& lk = session.lk;
    REQUIRE_BITS(c, lk.current.pos.x, -938.387878f, "the seed's x, against the console");
    REQUIRE_BITS(c, lk.current.pos.y, 16.5026398f, "the seed's y, against the console");
    REQUIRE_BITS(c, lk.current.pos.z, -197951.781f, "the seed's z, against the console");
    REQUIRE_INT(c, lk.mAcchCir[0].GetPolyIndex(), 3477, "the low cylinder's wall, as the console hit");
    REQUIRE_INT(c, lk.mAcchCir[0].GetWallAngleY() & 0xFFFF, 47895, "and its angle");
    REQUIRE_INT(c, lk.mAcchCir[1].GetPolyIndex(), 2861, "the middle cylinder's wall");
    REQUIRE_INT(c, lk.mAcchCir[1].GetWallAngleY() & 0xFFFF, 3159, "and its angle");
    REQUIRE_TRUE(c, !lk.mAcchCir[2].ChkWallHit(), "the top cylinder hits nothing on the console");

    tww_engine::Pad pad;
    pad.stick_angle_raw = kFacing;
    pad.target_angle = kFacing;
    REQUIRE_TRUE(c, session.step(pad) == tww_engine::StepResult::Ok, "a standing frame ran");
    REQUIRE_BITS(c, session.lk.current.pos.x, -938.387878f, "and a frame later he is still there");
    REQUIRE_BITS(c, session.lk.current.pos.z, -197951.781f, "in both axes");
}

TWWE_TEST(a_crawl_by_a_wall_on_a_slope_ends_where_the_console_put_it,
          "seeded 0.2 units off the console's standstill, the crawl ends 0.26 units from its "
          "landing") {
    const Crawled r = crawl();
    REQUIRE_INT(c, r.stopped, -1, "a step came back not Ok");
    REQUIRE_TRUE(c, r.crawled, "the press never reached CRAWL_START");
    REQUIRE_TRUE(c, r.rested, "the crawl did not come back to a standstill");
    REQUIRE_BITS(c, r.end.x, -933.923645f, "the crawl's end x, against the console");
    REQUIRE_BITS(c, r.end.y, 16.0741272f, "the crawl's end y, against the console");
    REQUIRE_BITS(c, r.end.z, -197940.812f, "the crawl's end z, against the console");
    c.note("ended at " + std::to_string(r.end.x) + ", " + std::to_string(r.end.y) + ", " +
           std::to_string(r.end.z) + " after " + std::to_string(r.frames) + " frames");
}
