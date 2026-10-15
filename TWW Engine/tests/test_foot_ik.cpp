// test_foot_ik.cpp - Roll R on a slope against a console capture: the foot IK and the grounded
// tail that feeds it.
//
// Under test: footBgCheck, setLegAngle, setWaistAngle and the three joint callbacks
// (`RunOptions::foot_ik`), and execute()'s grounded-tail `m34E2` and `setStepsOffset`
// (`ground_tail` in engine/session.cpp). Sea r11 is a slope, and posMoveFromFootPos reads the
// planted toe from the bent pose, so the last frame's speedF depends on the IK.
//
// The tape is roll_r_sea11_live.json, from savestate 10: L+A three frames, L+R twenty-two, then
// neutral. Engine frame k gets the console's pad of input k and is compared with the actor after
// input k+1. Position and speedF are held on every frame; the IK columns from frame 8, because the
// console starts from a settled standstill whose leg bends decay over frames 1-7 and a Session
// seeded from `Init` has none. Nothing downstream reads those frames (m3598 is 0).

#include <cstring>
#include <string>

#include "framework/golden.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "room_dzb.h"

#include "d/actor/d_a_player_main.h"
#include "engine/session.h"

namespace {

using tww_engine::testing::Json;
using tww_engine::testing::golden;

const int kFirstIkFrame = 8;

uint32_t hex(const Json& j) {
    return static_cast<uint32_t>(std::stoul(j.str, nullptr, 16));
}

/// Runs the tape, and at each frame hands the Session to `check` with the console's row.
template <class Check>
void run(bool foot_ik, Check check) {
    const Json& g = golden("roll_r_sea11_live.json");
    const tww_engine::RoomDzb dzb = tww_engine::testing::read_room_dzb(golden("sea_r11_bgd.json"));
    const Json& seed = g["seed"];
    tww_engine::Init init;
    f32 x, y, z;
    uint32_t b;
    b = hex(seed["x"]);
    std::memcpy(&x, &b, 4);
    b = hex(seed["y"]);
    std::memcpy(&y, &b, 4);
    b = hex(seed["z"]);
    std::memcpy(&z, &b, 4);
    init.pos.set(x, y, z);
    const s16 facing = static_cast<s16>(seed["facing"].as_int());
    init.shape_angle_y = facing;
    init.travel_angle_y = facing;
    init.normal_speed = 0.0f;
    init.speed_f = 0.0f;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    init.pad.stick_angle_raw = facing;
    init.pad.target_angle = facing;
    tww_engine::RunOptions opts;
    opts.foot_ik = foot_ik;
    tww_engine::Session::boundary_reset();
    tww_engine::Session session(init, &dzb, opts);

    u8 held = 0;
    const Json& frames = g["frames"];
    for (size_t i = 0; i < frames.size(); ++i) {
        const Json& f = frames[i];
        // The GameCube pad word: A 0x100, L 0x40, R 0x20. L held is the lock.
        const int pad = static_cast<int>(f["buttons"].as_int());
        u8 buttons = 0;
        if (pad & 0x100) buttons |= daPy_lk_c::BTN_A;
        if (pad & 0x40) buttons |= daPy_lk_c::BTN_L;
        if (pad & 0x20) buttons |= daPy_lk_c::BTN_R;
        tww_engine::Pad p;
        p.stick_angle_raw = facing;
        p.target_angle = facing;
        p.stick_distance = 0.0f;
        p.item_button = buttons;
        p.item_trigger = static_cast<u8>(buttons & ~held);
        p.attention_lock = (pad & 0x40) ? TRUE : FALSE;
        held = buttons;
        session.step(p);
        check(static_cast<int>(f["frame"].as_int()), session.state(), f["console"]);
    }
}

void hold_feet(tww_engine::testing::Case& c, int frame, const daPy_lk_c& lk, const Json& con) {
    const std::string at = "frame " + std::to_string(frame);
    REQUIRE_INT(c, lk.m34E0, con["m34E0"].as_int(), at + " m34E0");
    REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.m35B8), hex(con["m35B8"]), at + " m35B8");
    for (int i = 0; i < 2; ++i) {
        const daPy_footData_c& foot = lk.mFootData[i];
        const Json& cf = con["feet"][i];
        const std::string ft = at + " foot " + std::to_string(i);
        const s16 angles[5] = {foot.field_0x002, foot.field_0x004, foot.field_0x006,
                               foot.field_0x008, foot.field_0x00A};
        for (int k = 0; k < 5; ++k) {
            REQUIRE_INT(c, angles[k], cf["angles"][k].as_int(),
                        ft + " angle " + std::to_string(k));
        }
        const f32 toe[3] = {foot.field_0x00C.x, foot.field_0x00C.y, foot.field_0x00C.z};
        const f32 heel[3] = {foot.field_0x018.x, foot.field_0x018.y, foot.field_0x018.z};
        for (int k = 0; k < 3; ++k) {
            REQUIRE_BITS_RAW(c, tww_engine::f32_bits(toe[k]), hex(cf["toe"][k]), ft + " toe");
            REQUIRE_BITS_RAW(c, tww_engine::f32_bits(heel[k]), hex(cf["heel"][k]), ft + " heel");
        }
    }
}

}  // namespace

TWWE_TEST(roll_r_on_a_slope_lands_where_the_console_does,
          "without the foot IK, the planted toe posMoveFromFootPos reads on a sloped walk frame "
          "is an unbent leg's, and Roll R on sea r11 ends 0.051 units from where the console "
          "puts it") {
    int held = 0;
    run(true, [&](int frame, const daPy_lk_c& lk, const Json& con) {
        const std::string at = "frame " + std::to_string(frame);
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.current.pos.x), hex(con["x"]), at + " x");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.current.pos.y), hex(con["y"]), at + " y");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.current.pos.z), hex(con["z"]), at + " z");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.speedF), hex(con["speedF"]), at + " speedF");
        REQUIRE_INT(c, lk.m34E2, con["m34E2"].as_int(), at + " m34E2");
        if (frame >= kFirstIkFrame) {
            hold_feet(c, frame, lk, con);
        }
        ++held;
    });
    REQUIRE_INT(c, held, 30, "the tape did not run to its end");
    c.note("30 frames, position and speedF on all of them, the foot IK from frame " +
           std::to_string(kFirstIkFrame));
}

TWWE_RED_CONTROL(roll_r_on_a_slope_red_without_the_foot_ik,
                 "RunOptions::foot_ik off: no leg bends, no body lowering and no waist tilt, so "
                 "the last ATN_MOVE frame's speedF comes from an unbent leg's toe") {
    run(false, [&](int frame, const daPy_lk_c& lk, const Json& con) {
        const std::string at = "frame " + std::to_string(frame);
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.current.pos.x), hex(con["x"]), at + " x");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.current.pos.z), hex(con["z"]), at + " z");
        REQUIRE_BITS_RAW(c, tww_engine::f32_bits(lk.speedF), hex(con["speedF"]), at + " speedF");
    });
}
