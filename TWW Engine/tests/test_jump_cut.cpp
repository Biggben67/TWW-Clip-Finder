// test_jump_cut.cpp - the jump slash and its landing against the console, and the controls.
//
// The sword capture's other 70 frames, driven by jump_land_replay. procJumpCut calls
// procJumpCutLand_init from its own body, so a slash is followed across the proc change with no
// seed in between, as a backflip is.
//
//   * procJumpCut lands on `ChkGroundHit()` alone (procBackJump also needs `getRate() < 0.01f`).
//     This jump launches at 27.0, steps by -3.0 and passes through exactly 0.0 at its apex, so the
//     delivered ground hit is a zero in speed_y that gravity alone cannot explain.
//   * `mProcVar0.m34D0 = mCutJump.field_0x4` = 2 is spent by the clock-expired arm before it
//     dispatches, so the landing outlives its animation by two frames (14 = 12 + clamped + 1).
//   * `changeCutReverseProc(ANM_JATTACK)` (the sword bounce) is guarded by
//     `current.angle.y == shape_angle.y`, which procJumpCut_init writes, so it is asked on every
//     airborne body frame and the capture answers no on all 54 rows. procJumpCutLand asks once
//     more per run with ANM_CUTRER.
//   * The landing's first line is a fall-damage test on commonProcInit's m35F0.
//
// Not claimed: position and speed.y on and after the console's ground clamp (the rig has no
// collision world), ground contact (delivered, not computed), the frames between runs, the BOKO
// and hammer arms, and the init's midair half.

#include <cstring>
#include <string>
#include <vector>

#include "jump_land_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::f32_bits;
using tww_engine::testing::Json;
using tww_engine::testing::JumpLandFrame;
using tww_engine::testing::JumpLandPair;
using tww_engine::testing::JumpLandReplayOptions;
using tww_engine::testing::JumpLandRun;

const char* kGolden = "setup_finder_sword_live.json";

/// The jump slash's row of the shared replay's pair table.
const JumpLandPair& pair() {
    return tww_engine::testing::jump_land_pair(tww_engine::testing::kPairJumpCut);
}

std::vector<JumpLandRun> replay(const Json& g, const JumpLandReplayOptions& opt) {
    return tww_engine::testing::run_jump_land_replay(g, tww_engine::testing::kPairJumpCut, opt);
}

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's, over every run: the backflip gate's eight columns.
///
/// `perturb_frame` moves the expected anim_frame by one ULP on that frame - the comparator's own
/// red control.
void compare(Case& c, const Json& g, const std::vector<JumpLandRun>& runs,
             int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
    int integrated = 0;
    // Where the comparison first disagreed: the runner suppresses a red case's failure log.
    std::string first_bad;
    int bad = 0;
    auto watch = [&](bool ok, const std::string& where) {
        if (!ok) {
            bad++;
            if (first_bad.empty()) {
                first_bad = where;
            }
        }
    };
    for (const JumpLandRun& run : runs) {
        for (const JumpLandFrame& row : run.rows) {
            const Json& want = g[size_t(row.frame)];
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_anim = want["anim_frame"].as_f32_bits();
            if (row.frame == perturb_frame) {
                want_anim += 1;   // the red control: one ULP, on one frame
            }
            REQUIRE_BITS_RAW(c, row.anim_bits, want_anim, at(row.frame, "anim_frame"));
            watch(row.anim_bits == want_anim, at(row.frame, "anim_frame"));
            REQUIRE_BITS_RAW(c, row.rate_bits, want["fc_rate"].as_f32_bits(),
                             at(row.frame, "fc_rate"));
            watch(row.rate_bits == want["fc_rate"].as_f32_bits(), at(row.frame, "fc_rate"));
            REQUIRE_BITS_RAW(c, row.nspeed_bits, want["potential_speed"].as_f32_bits(),
                             at(row.frame, "mNormalSpeed"));
            watch(row.nspeed_bits == want["potential_speed"].as_f32_bits(),
                  at(row.frame, "mNormalSpeed"));
            REQUIRE_BITS_RAW(c, row.gravity_bits, want["gravity"].as_f32_bits(),
                             at(row.frame, "gravity"));
            watch(row.gravity_bits == want["gravity"].as_f32_bits(), at(row.frame, "gravity"));
            REQUIRE_INT(c, row.end, want["fc_end"].as_int(), at(row.frame, "fc_end"));
            watch(row.end == want["fc_end"].as_int(), at(row.frame, "fc_end"));
            REQUIRE_INT(c, row.proc, want_proc, at(row.frame, "proc"));
            watch(row.proc == want_proc, at(row.frame, "proc"));
            REQUIRE_INT(c, row.shape_angle_y, want["shape_angle_y"].as_int(),
                        at(row.frame, "shape_angle_y"));
            watch(row.shape_angle_y == want["shape_angle_y"].as_int(),
                  at(row.frame, "shape_angle_y"));
            REQUIRE_INT(c, row.travel_angle, want["travel_angle"].as_int(),
                        at(row.frame, "travel_angle"));
            watch(row.travel_angle == want["travel_angle"].as_int(),
                  at(row.frame, "travel_angle"));

            // The integration's columns, on every airborne frame but the last. dBgS_Acch::CrrPos
            // (execute():11406) clamps Link onto the floor from that row on, and the rig's dBgS is
            // empty, so those rows are not compared.
            //
            // m3598, the multiplier on the whole foot delta, is asserted 0 on every compared frame;
            // `foot_delta` from the empty skeleton is recorded, not compared.
            const bool console_clamped = run.console_land >= 0 && row.frame >= run.console_land - 1;
            if (!console_clamped) {
                REQUIRE_BITS_RAW(c, row.blend_bits, f32_bits(0.0f), at(row.frame, "m3598"));
                watch(row.blend_bits == f32_bits(0.0f), at(row.frame, "m3598"));
                REQUIRE_BITS_RAW(c, row.speed_y_bits, want["speed_y"].as_f32_bits(),
                                 at(row.frame, "speed.y"));
                watch(row.speed_y_bits == want["speed_y"].as_f32_bits(), at(row.frame, "speed.y"));
                REQUIRE_BITS_RAW(c, row.pos_x_bits, want["pos_x"].as_f32_bits(),
                                 at(row.frame, "pos.x"));
                watch(row.pos_x_bits == want["pos_x"].as_f32_bits(), at(row.frame, "pos.x"));
                REQUIRE_BITS_RAW(c, row.pos_y_bits, want["pos_y"].as_f32_bits(),
                                 at(row.frame, "pos.y"));
                watch(row.pos_y_bits == want["pos_y"].as_f32_bits(), at(row.frame, "pos.y"));
                REQUIRE_BITS_RAW(c, row.pos_z_bits, want["pos_z"].as_f32_bits(),
                                 at(row.frame, "pos.z"));
                watch(row.pos_z_bits == want["pos_z"].as_f32_bits(), at(row.frame, "pos.z"));
                integrated++;
            }

            // 4 bit comparisons and 4 integer ones per frame, plus the integration's 5 bit
            // comparisons on the frames it is held to.
            tww_engine::testing::ledger_record(want_proc, tier, console_clamped ? 4 : 9, 4);
            compared++;
        }

        // The exit, against the capture's proc on the first frame outside the pair. Two runs
        // quickspin (0x55).
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left the landing for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left the landing for"));
    }
    c.note("compared " + std::to_string(compared) + " JUMP_CUT / JUMP_CUT_LAND frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    c.note("of those, " + std::to_string(integrated) +
           " hold current.pos and speed.y - the frames before the console's own ground clamp");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. what is in there

TWWE_TEST(the_capture_holds_three_jump_slashes_and_both_of_the_landings_two_exits,
          "the gate could pass on three runs that all left the landing the same way") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<int> entries = tww_engine::testing::jump_land_entry_frames(g, pair());
    REQUIRE_INT(c, (long long)entries.size(), pair().runs,
                "JUMP_CUT runs the capture's own proc column holds");

    int jump_frames = 0, land_frames = 0, to_spin = 0, to_other = 0;
    for (int e : entries) {
        int f = e;
        while (f < int(g.size()) && g[size_t(f)]["proc"].as_int() == pair().jump_proc) {
            jump_frames++;
            f++;
        }
        while (f < int(g.size()) && g[size_t(f)]["proc"].as_int() == pair().land_proc) {
            land_frames++;
            f++;
        }
        if (g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e) {
            to_spin++;
        } else {
            to_other++;
        }
    }
    REQUIRE_INT(c, jump_frames, pair().jump_frames, "JUMP_CUT frames");
    REQUIRE_INT(c, land_frames, pair().land_frames, "JUMP_CUT_LAND frames");
    // Both exits occurred.
    REQUIRE_TRUE(c, to_spin > 0, "no slash left the landing for CUT_TURN - the quickspin is unrun");
    REQUIRE_TRUE(c, to_other > 0,
                 "every slash took the quickspin - the countdown arm is unrun");
    c.note("jump slashes: " + std::to_string(to_spin) + " into CUT_TURN (the quickspin), " +
           std::to_string(to_other) + " out through the landing's own countdown");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(the_jump_slash_and_its_landing_are_bit_exact_against_the_console,
          "the ported pair no longer reproduces the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    REQUIRE_INT(c, (long long)runs.size(), pair().runs, "runs replayed");

    int frames = 0;
    for (const JumpLandRun& run : runs) {
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry, "frames replayed" + where);
        frames += int(run.rows.size());

        REQUIRE_INT(c, run.unreached_called, 0, "UNREACHED stubs called" + where);
        REQUIRE_INT(c, run.precondition_broken, 0,
                    "stubs called outside their proof's regime" + where);
        REQUIRE_INT(c, run.rnd_draws_compared, 0, "RNG draws over the compared frames" + where);
        // ...and including the exit: procCutTurn_init draws nothing, procWait_init draws once for
        // its idle timer.
        const bool spun = g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        REQUIRE_INT(c, run.rnd_draws, spun ? 0 : 1, "RNG draws including the exit" + where);

        // The landing frame. procJumpCut has no rate term, so this is the ground-hit delivery.
        REQUIRE_INT(c, run.land, run.console_land,
                    "the frame the port entered the landing on" + where);

        // procJumpCut_init's boundary.
        REQUIRE_INT(c, run.voice_id, pair().voice, "the voice cue the init fired" + where);
        // The two arms this pair does not have: zero because the body has no call site.
        REQUIRE_TRUE(c, !pair().has_fan_and_fall,
                     "the pair table says the jump slash has no fan and no drop arm");
        REQUIRE_INT(c, run.fan_glide_calls, 0,
                    "checkFanGlideProc asks - procJumpCut has no call site" + where);
        REQUIRE_INT(c, run.fall_init_calls, 0,
                    "procFall_init calls - procJumpCut has no drop arm" + where);
        // ...and the one it has that the backflip does not.
        REQUIRE_TRUE(c, pair().asks_cut_reverse,
                     "the pair table says the jump slash asks for the sword bounce");
        // Two call sites, stated as a sum: procJumpCut on `land - entry - 1` frames (the entry
        // runs the init, the landing returns at the ground-hit test first), and procJumpCutLand
        // once, behind the mProcVar6.m3570 one-shot the quickspin spends.
        REQUIRE_INT(c, run.cut_reverse_calls, (run.land - run.entry - 1) + 1,
                    "changeCutReverseProc asks - one per airborne body frame, plus the landing's "
                    "own m3570-guarded arm" + where);
        REQUIRE_INT(c, run.evmng_cut_end_calls, 0,
                    "event-cut-end calls - dComIfGp_event_runCheck is false" + where);
        REQUIRE_INT(c, run.shock_calls, 0,
                    "rumble calls - checkHeavyStateOn is false, so the landing's heavy arm is "
                    "shut" + where);
        REQUIRE_INT(c, run.hammer_quake_calls, 0,
                    "hammer-quake calls - the landing's other equip arm, and a sword is "
                    "equipped" + where);

        // procJumpCutLand_init's, read at the init.
        REQUIRE_INT(c, run.foot_effect_type, 3,
                    "the foot-effect type the landing's init set" + where);
        REQUIRE_INT(c, (long long)(run.reset_flg0 & (daPyRFlg0_RIGHT_FOOT_ON_GROUND |
                                                     daPyRFlg0_LEFT_FOOT_ON_GROUND)),
                    (long long)(daPyRFlg0_RIGHT_FOOT_ON_GROUND | daPyRFlg0_LEFT_FOOT_ON_GROUND),
                    "the two foot-on-ground bits the landing's init raised" + where);
        // The quickspin one-shot, armed by `mEquipItem != daPyItem_NONE_e` (the backflip tests
        // `== daPyItem_SWORD_e`; same effect under a sword).
        REQUIRE_INT(c, run.m3570_at_land, 1,
                    "mProcVar6.m3570 as the landing's init left it - the equipped arm" + where);
        // setJumpCutAtParam's fork; both inits call it, so this is the landing's answer.
        REQUIRE_INT(c, run.cut_at_param_type, daPy_lk_c::CUT_TYPE_JUMPCUT_SWORD,
                    "the cut type setJumpCutAtParam recorded" + where);

        // The fall damage, m35F0's reader; fires on nothing here.
        REQUIRE_INT(c, run.damage_calls, 0,
                    "setDamagePoint calls - the drop is 0.0 against thresholds of 6000 and "
                    "2000" + where);

        // The sword trail: 10.0 * mCutJump.field_0x48 the length, getBlurTopRate() the taper,
        // getSwordBlurColor() the palette. The call is a stub; the arguments are the decomp's.
        REQUIRE_INT(c, run.sw_blur_calls, 1, "initSwBlur calls - once per landing" + where);
        REQUIRE_INT(c, run.sw_blur_frames, 130,
                    "the trail's length - 10.0 * mCutJump.field_0x48 (13.0)" + where);
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(run.sw_blur_top_rate),
                         tww_engine::testing::f32_bits(0.5f),
                         "getBlurTopRate - the normal sword's arm, not the Master Sword's" + where);
        REQUIRE_INT(c, run.sw_blur_color, 0,
                    "getSwordBlurColor - no parry window and no soup" + where);
        REQUIRE_INT(c, run.base_tr_mtx_calls, 1,
                    "the base matrix that call asked J3DModel for" + where);
    }

    REQUIRE_INT(c, frames, pair().jump_frames + pair().land_frames,
                "jump-slash frames held to the console");
    compare(c, g, runs);
}

TWWE_TEST(the_sword_bounce_is_asked_on_every_airborne_frame_and_the_console_says_no,
          "the reverse arm could be unreached and its false would look identical") {
    // procJumpCut's changeCutReverseProc is behind `current.angle.y == shape_angle.y`, which its
    // init writes, so it is asked on every airborne body frame (17 a run); procJumpCutLand asks
    // once more with ANM_CUTRER. A bounce would flip current.angle.y by 0x8000 and write
    // mNormalSpeed = 27.0; the capture reads travel_angle == shape_angle_y and 18.0 on all 54
    // airborne rows, so `stub_cut_reverse`'s false is measured.
    //
    // The `else if (current.angle.y != shape_angle.y)` cLib_addCalc beside it is therefore
    // unreachable with a sword; `red_the_sword_bounced` runs it.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    int asks = 0, airborne = 0;
    for (const JumpLandRun& run : runs) {
        asks += run.cut_reverse_calls;
        airborne += run.land - run.entry - 1;
        for (const JumpLandFrame& row : run.rows) {
            if (row.proc != pair().jump_proc) {
                continue;
            }
            REQUIRE_INT(c, row.travel_angle, row.shape_angle_y,
                        at(row.frame, "travel_angle against shape_angle_y - the arm's own guard"));
            REQUIRE_BITS_RAW(c, row.nspeed_bits,
                             g[size_t(row.frame)]["potential_speed"].as_f32_bits(),
                             at(row.frame, "mNormalSpeed - 27.0 here would be the bounce"));
        }
    }
    REQUIRE_TRUE(c, asks > 0, "the bounce arm was never reached, so its false says nothing");
    REQUIRE_INT(c, asks, airborne + pair().runs,
                "the asks, as airborne body frames plus one landing arm per run");
    c.note("changeCutReverseProc asked " + std::to_string(asks) + " time(s) - " +
           std::to_string(airborne) + " from procJumpCut and " + std::to_string(pair().runs) +
           " from procJumpCutLand's own arm - and answered false every time; the cLib_addCalc arm "
           "beside the first is copied and unreachable with a sword equipped");
}

TWWE_TEST(the_landings_countdown_outlives_its_own_animation_by_two_frames,
          "the landing's duration would rest on the exit column alone") {
    // `mProcVar0.m34D0 = mCutJump.field_0x4` = 2, decremented by procJumpCutLand's clock-expired
    // arm before it dispatches, so the landing stays two frames after JATTACKLAND's clock clamps.
    // The console's non-quickspin run spends 14 landing frames, the last two at fc_rate 0.0 and
    // anim_frame 13.999.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    int checked = 0;
    for (const JumpLandRun& run : runs) {
        if (g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e) {
            continue;
        }
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_INT(c, run.exit - run.land, 14,
                    "landing frames before the countdown-expired exit" + where);
        // The two frames the clock is dead and the proc is not, read off the port's rows.
        int clamped = 0;
        for (const JumpLandFrame& row : run.rows) {
            if (row.frame >= run.land) {
                REQUIRE_INT(c, row.end, 14, at(row.frame, "the landing clock's end - field_0x2"));
                if (row.rate_bits == tww_engine::testing::f32_bits(0.0f)) {
                    clamped++;
                }
            }
        }
        REQUIRE_INT(c, clamped, 2,
                    "landing frames spent with the animation already over - field_0x4" + where);
        checked++;
    }
    REQUIRE_TRUE(c, checked > 0, "no run reached the countdown arm, so field_0x4 is unexercised");
}

TWWE_TEST(the_quickspin_fires_on_exactly_one_landing_frame_and_only_past_0xF800,
          "the one-shot could be spent on every frame, or on none, and the exits would still "
          "look right on two of the three runs") {
    // procJumpCutLand's arms are tested in order, so the m3570 arm is reached only while the
    // clock is alive and below field_0x44 - the landing's first body frame. Two runs arrive with
    // |m3578| past 0xF800 and leave for CUT_TURN; one arrives under it and runs the countdown out.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    int spun = 0, did_not = 0;
    for (const JumpLandRun& run : runs) {
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_TRUE(c, run.polled, "the landing's quickspin arm was reached at all" + where);
        const int mag = run.rotation_at_poll < 0 ? -run.rotation_at_poll : run.rotation_at_poll;
        const bool console_spun =
            g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        if (console_spun) {
            spun++;
            REQUIRE_TRUE(c, mag > 0xF800,
                         "the console spun out of this landing, so the port's own accumulated "
                         "rotation " + std::to_string(mag) + " must be past 0xF800" + where);
            REQUIRE_INT(c, run.exit, run.land + 1,
                        "the landing lasted one body frame before the spin" + where);
        } else {
            did_not++;
            REQUIRE_TRUE(c, mag <= 0xF800,
                         "the console did not spin out of this landing, so the port's rotation " +
                             std::to_string(mag) + " must not be past 0xF800" + where);
        }
    }
    REQUIRE_INT(c, spun, 2, "runs whose landing the console left for CUT_TURN");
    REQUIRE_INT(c, did_not, 1, "runs whose landing ran its own countdown out");
}

TWWE_TEST(the_jump_slashs_launch_and_its_first_gravity_step_are_one_frame,
          "the launch, the gravity step and the move would stop being one frame's work") {
    // procJumpCut_init writes `speed.y = mCutJump.field_0x18 = 27.0`; the console's first
    // JUMP_CUT row reads 24.0 because execute() runs posMove after the proc and before the sample.
    // With `no_pos_move` the port holds the launch; with the integration its entry row is the
    // console's.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    JumpLandReplayOptions no_move;
    no_move.no_pos_move = true;
    std::vector<JumpLandRun> unmoved = replay(g, no_move);
    REQUIRE_INT(c, (long long)unmoved.size(), (long long)runs.size(), "runs replayed both ways");

    for (size_t i = 0; i < runs.size(); i++) {
        const JumpLandRun& run = runs[i];
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_BITS_RAW(c, unmoved[i].rows.front().speed_y_bits, f32_bits(27.0f),
                         "speed.y as the init wrote it, integration removed - mCutJump.field_0x18" + where);
        REQUIRE_BITS_RAW(c, g[size_t(run.entry)]["speed_y"].as_f32_bits(),
                         f32_bits(27.0f + -3.0f),
                         "the console's own first row - one gravity step below the launch" + where);
        REQUIRE_BITS_RAW(c, run.rows.front().speed_y_bits,
                         g[size_t(run.entry)]["speed_y"].as_f32_bits(),
                         "...and the port's entry row, integration included" + where);
    }
    c.note("the launch, the gravity step and the console's first row are one frame's arithmetic; "
           "`compare` holds current.pos with them");
}
TWWE_TEST(the_two_jattack_animations_have_measured_metadata_and_not_a_default,
          "JATTACKLAND's attribute would be resting on getAnimeResource's default") {
    // jattack (frameMax 15) and jattackland (14), parsed from LkAnm.arc. jattackland's attribute
    // matters: `getRate() < 0.01f` is procJumpCutLand's first arm, so EMode_LOOP never ends the
    // landing. JATTACK's clock runs 2.0 to 14.58 and the landing re-inits the controller before it
    // would reach frameMax, so its attribute is unexercised (see the loop_jump_anim case).
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    for (const JumpLandRun& run : runs) {
        REQUIRE_INT(c, run.anm_meta_missing, 0,
                    "UNDER-slot anims with no measured metadata in the run entered at " +
                        std::to_string(run.entry));
    }
    c.note("jattack (frameMax 15, EMode_NONE) and jattackland (14, EMode_NONE) are measured rows; "
           "the control that says the parse reproduces a known answer is in the generator that "
           "writes anm_meta.inc");
}

TWWE_TEST(the_init_argument_is_the_ground_route_and_the_other_half_of_the_row_is_unexercised,
          "the half of mCutJump the capture never reads would look tested") {
    // procJumpCut_init's int picks one half of its HIO row (anim rate, start, morf, mNormalSpeed,
    // speed.y, gravity). All runs enter from proc 4 via checkNextActionFromButton's do-status arm
    // (d_a_player_main.cpp:4176), which passes 0. The capture settles rate 0.74 (field_0x8, not
    // field_0x20's 0.8), start 2.0 (field_0xC, not field_0x24's 1.0), end 15 (field_0x0) and
    // mNormalSpeed 18.0 (field_0x14, not field_0x2C's 9.0). The midair half,
    // checkJumpCutFromButton's route, has no call site in this port.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    for (const JumpLandRun& run : runs) {
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_INT(c, run.from_proc, daPy_lk_c::daPyProc_WAIT_e,
                    "the proc the console was in on the row before the entry" + where);
        const JumpLandFrame& first = run.rows.front();
        REQUIRE_BITS_RAW(c, first.rate_bits, tww_engine::testing::f32_bits(0.74f),
                         "the anim rate - field_0x8, the ground half" + where);
        REQUIRE_BITS_RAW(c, first.anim_bits, tww_engine::testing::f32_bits(2.0f),
                         "the anim start - field_0xC, the ground half" + where);
        REQUIRE_BITS_RAW(c, first.nspeed_bits, tww_engine::testing::f32_bits(18.0f),
                         "mNormalSpeed - field_0x14, the ground half" + where);
    }
    c.note("GAP: mCutJump.field_0x20..0x34 is the midair route's half of the row and no banked "
           "frame reads it; checkJumpCutFromButton is not in this port");
}

// ------------------------------------------------ 2. the forks that move no column, run anyway

TWWE_TEST(the_landings_heavy_fork_reaches_the_rumble_and_no_column,
          "the heavy arm would be untested, or would be registered as a control that cannot go "
          "red") {
    // procJumpCut_init has no heavy fork; the only reader is procJumpCutLand_init's
    // `else if (checkHeavyStateOn())`, which starts a rumble. It moves a boundary count and no
    // column, so it is a positive case, not a red control.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.heavy_state = true;
    std::vector<JumpLandRun> heavy = replay(g, opt);
    std::vector<JumpLandRun> normal = replay(g, JumpLandReplayOptions{});

    REQUIRE_INT(c, (long long)heavy.size(), (long long)normal.size(), "runs replayed both ways");
    for (size_t i = 0; i < heavy.size(); i++) {
        const std::string where = " in the run entered at " + std::to_string(heavy[i].entry);
        REQUIRE_INT(c, heavy[i].shock_calls, 1, "rumble calls with the heavy state on" + where);
        REQUIRE_INT(c, normal[i].shock_calls, 0, "...and with it off" + where);
        REQUIRE_INT(c, (long long)heavy[i].rows.size(), (long long)normal[i].rows.size(),
                    "frames replayed" + where);
        for (size_t k = 0; k < heavy[i].rows.size(); k++) {
            REQUIRE_BITS_RAW(c, heavy[i].rows[k].nspeed_bits, normal[i].rows[k].nspeed_bits,
                             at(heavy[i].rows[k].frame, "mNormalSpeed, heavy against normal"));
            REQUIRE_BITS_RAW(c, heavy[i].rows[k].rate_bits, normal[i].rows[k].rate_bits,
                             at(heavy[i].rows[k].frame, "fc_rate, heavy against normal"));
        }
    }
    c.note("the heavy state moves shock_calls 0 -> 1 and no compared column; procJumpCut_init has "
           "no heavy fork, unlike procBackJump_init");
}

TWWE_TEST(the_airborne_anims_attribute_moves_nothing_and_the_landings_moves_everything,
          "loop_jump_anim would be registered as a red control and would come back green") {
    // JATTACK's clock never reaches its frameMax inside a run, so EMode_LOOP and EMode_NONE give
    // identical rows. `red_the_landing_anim_clock_set_to_loop` is the counterpart that bites.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.loop_jump_anim = true;
    std::vector<JumpLandRun> looped = replay(g, opt);
    std::vector<JumpLandRun> normal = replay(g, JumpLandReplayOptions{});

    REQUIRE_INT(c, (long long)looped.size(), (long long)normal.size(), "runs replayed both ways");
    for (size_t i = 0; i < looped.size(); i++) {
        REQUIRE_INT(c, (long long)looped[i].rows.size(), (long long)normal[i].rows.size(),
                    "frames replayed in the run entered at " + std::to_string(looped[i].entry));
        for (size_t k = 0; k < looped[i].rows.size() && k < normal[i].rows.size(); k++) {
            REQUIRE_BITS_RAW(c, looped[i].rows[k].anim_bits, normal[i].rows[k].anim_bits,
                             at(looped[i].rows[k].frame, "anim_frame, LOOP against NONE"));
        }
    }
    c.note("UNGATED: JATTACK's attribute is measured, carried and unexercised - the clock runs "
           "2.0 to 14.58 against a frameMax of 15 and the landing re-inits the controller before "
           "the one frame that would have clamped it emits");
}

TWWE_TEST(the_gravity_term_in_the_ground_hit_rule_changes_nothing_on_the_backflip,
          "the harness rule this pair needs could have moved the backflip pair") {
    // The other half of `red_the_naive_ground_hit_rule`: a zero in `speed_y` that gravity alone
    // explains is the apex, not the clamp. On the backflip (19.0 stepped by -3.0 never hits zero)
    // both rules must give bit-identical rows.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions naive;
    naive.naive_ground_hit = true;
    std::vector<JumpLandRun> old_rule =
        tww_engine::testing::run_jump_land_replay(g, tww_engine::testing::kPairBackJump, naive);
    std::vector<JumpLandRun> new_rule = tww_engine::testing::run_jump_land_replay(
        g, tww_engine::testing::kPairBackJump, JumpLandReplayOptions{});

    REQUIRE_INT(c, (long long)old_rule.size(), (long long)new_rule.size(), "flips replayed");
    int rows = 0;
    for (size_t i = 0; i < old_rule.size() && i < new_rule.size(); i++) {
        const std::string where = " in the flip entered at " + std::to_string(new_rule[i].entry);
        REQUIRE_INT(c, old_rule[i].land, new_rule[i].land, "the landing frame" + where);
        REQUIRE_INT(c, (long long)old_rule[i].rows.size(), (long long)new_rule[i].rows.size(),
                    "frames replayed" + where);
        for (size_t k = 0; k < old_rule[i].rows.size() && k < new_rule[i].rows.size(); k++) {
            REQUIRE_BITS_RAW(c, old_rule[i].rows[k].anim_bits, new_rule[i].rows[k].anim_bits,
                             at(new_rule[i].rows[k].frame, "anim_frame, old rule against new"));
            REQUIRE_INT(c, old_rule[i].rows[k].proc, new_rule[i].rows[k].proc,
                        at(new_rule[i].rows[k].frame, "proc, old rule against new"));
            rows++;
        }
    }
    c.note("the gravity term leaves all " + std::to_string(rows) +
           " backflip rows bit-identical; over the whole capture it removes exactly three frames "
           "and all three are jump-slash apexes");
}

// ------------------------------------------------------------------------ 3. the red controls

TWWE_RED_CONTROL(red_flip_the_comparator_itself,
                 "the expected anim_frame moved by one ULP on the first slash's entry frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});
    compare(c, g, runs, runs.empty() ? -1 : runs.front().entry);
}

TWWE_RED_CONTROL(red_the_naive_ground_hit_rule,
                 "the delivery rule with its gravity term removed - a bare `speed_y == 0`") {
    // procJumpCut lands on `ChkGroundHit()` alone, and speed.y is exactly 0.0 at the apex, so the
    // naive rule lands all three runs nine frames early.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.naive_ground_hit = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_ground_hit_delivered_one_frame_late,
                 "the collision flag this replay delivers, shifted by one frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.late_ground_hit = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_ground_hit_never_delivered,
                 "the collision flag held false, so the slash never lands") {
    // The port stays in JUMP_CUT past the console's proc change; catches a port that ignores the
    // flag entirely.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_ground_hit = true;
    compare(c, g, replay(g, opt));
}

TWWE_TEST(the_launch_height_latch_is_redundant_once_the_integration_runs,
          "a control that stopped biting would look exactly like a control that never bit") {
    // m35F0, commonProcInit's launch-height latch, zeroed after the init. procJumpCutLand_init
    // tests the drop `m35F0 - current.pos.y` against 100.0 * mFall.field_0x10; at the floor
    // (y = -6534) a zero latch would read 6534 against 6000 and deal fall damage. But
    // posMoveFromFootPos re-latches `if (speed.y <= 0.0f && f1 > 0.0f) m35F0 = current.pos.y;`
    // at the apex, so fall damage is measured from the apex and the injection is inert.
    // With `no_pos_move` as well, nothing re-latches and the injection deals damage.
    const Json& g = tww_engine::testing::golden(kGolden);

    JumpLandReplayOptions opt;
    opt.no_launch_height = true;
    std::vector<JumpLandRun> zeroed = replay(g, opt);
    std::vector<JumpLandRun> plain = replay(g, JumpLandReplayOptions{});
    REQUIRE_INT(c, (long long)zeroed.size(), (long long)plain.size(), "runs replayed both ways");

    for (size_t i = 0; i < zeroed.size(); i++) {
        const std::string where = " in the run entered at " + std::to_string(plain[i].entry);
        REQUIRE_INT(c, zeroed[i].damage_calls, 0, "setDamagePoint calls with m35F0 zeroed" + where);
        REQUIRE_INT(c, (long long)zeroed[i].rows.size(), (long long)plain[i].rows.size(),
                    "frames replayed" + where);
        for (size_t r = 0; r < zeroed[i].rows.size(); r++) {
            const JumpLandFrame& a = zeroed[i].rows[r];
            const JumpLandFrame& b = plain[i].rows[r];
            REQUIRE_BITS_RAW(c, a.pos_y_bits, b.pos_y_bits, at(a.frame, "pos.y with m35F0 zeroed"));
            REQUIRE_BITS_RAW(c, a.speed_y_bits, b.speed_y_bits,
                             at(a.frame, "speed.y with m35F0 zeroed"));
        }
    }

    // ...and the counterfactual: the same injection with the integration removed.
    JumpLandReplayOptions both;
    both.no_launch_height = true;
    both.no_pos_move = true;
    int bit = 0;
    for (const JumpLandRun& run : replay(g, both)) {
        bit += run.damage_calls;
    }
    REQUIRE_TRUE(c, bit > 0,
                 "with the integration removed the m35F0 injection must reach the fall damage - "
                 "otherwise the apex latch is not what made it inert");
    c.note("the apex latch absorbs the injection on all " + std::to_string(plain.size()) +
           " run(s); with the integration removed it lands " + std::to_string(bit) +
           " fall-damage call(s)");
}
TWWE_RED_CONTROL(red_the_sword_bounced,
                 "changeCutReverseProc answered true - the stub whose false the console measured") {
    // The bounce flips current.angle.y by 0x8000 and writes mNormalSpeed = 27.0 against the
    // console's 18.0; every later frame takes the `!=` cLib_addCalc arm toward 5.0.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.cut_reverse_true = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_integration_not_run,
                 "posMoveFromFootPos skipped after the proc - the replay's integration step") {
    // execute():11400 removed: current.pos holds the seed and speed.y the launch, so the
    // integration's columns go wrong on the first compared frame of every run.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_pos_move = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_skeleton_is_not_ready,
                 "m_old_fdata->getOldFrameFlg() driven false - the copy's own first arm") {
    // posMoveFromFootPos's first statement, `if (m_old_fdata->getOldFrameFlg() == false)`, seeds
    // the feet's offsets, writes speedF = 0 and returns. The game takes it for one frame after
    // Link's model is built.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.skeleton_not_ready = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_position_integrated_before_gravity,
                 "`current.pos += speed` moved ahead of the `speed.y += gravity` above it") {
    // An order, not a presence: every pos.y is one gravity step (3.0) out and nothing else moves.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.integrate_before_gravity = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_stick_rotation_frozen_at_zero,
                 "the accumulator the harness carries removed, so no slash can quickspin") {
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_stick_rotation = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_no_sword_equipped,
                 "the quickspin's other gate - the landing init's arming test - removed") {
    // With nothing equipped, procJumpCutLand_init's `mEquipItem == daPyItem_NONE_e` arm leaves
    // m3570 at 0, so the quickspin is never reached; procJumpCut's cut-sound window also shuts.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_sword = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_landing_anim_clock_set_to_loop,
                 "JATTACKLAND's measured EMode_NONE replaced by EMode_LOOP") {
    // The landing's clock looping: `getRate() < 0.01f` never holds, the countdown is never spent
    // and the non-quickspin run never ends.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.loop_land_anim = true;
    compare(c, g, replay(g, opt));
}

TWWE_TEST(no_seed_control_over_the_facing_can_bite_on_this_pair,
          "an ACCEPTED red control would say the seed is tested when it is not") {
    // Which column seeds the facing cannot be gated here: all three seed rows read
    // shape_angle_y == travel_angle. test_back_jump.cpp holds it on seed rows that differ. The
    // inits' writes (`current.angle.y = shape_angle.y`, then `shape_angle.y + 0x8000` on the
    // landing: travel_angle 18377 against a facing of 51145) are gated by travel_angle.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<int> entries = tww_engine::testing::jump_land_entry_frames(g, pair());
    for (int e : entries) {
        REQUIRE_INT(c, g[size_t(e - 1)]["shape_angle_y"].as_int(),
                    g[size_t(e - 1)]["travel_angle"].as_int(),
                    at(e - 1, "shape_angle_y against travel_angle on the seed row"));
    }
    // ...and the run confirms the swap is inert.
    JumpLandReplayOptions opt;
    opt.wrong_seed_shape_angle = true;
    std::vector<JumpLandRun> swapped = replay(g, opt);
    std::vector<JumpLandRun> normal = replay(g, JumpLandReplayOptions{});
    for (size_t i = 0; i < swapped.size() && i < normal.size(); i++) {
        for (size_t k = 0; k < swapped[i].rows.size() && k < normal[i].rows.size(); k++) {
            REQUIRE_INT(c, swapped[i].rows[k].travel_angle, normal[i].rows[k].travel_angle,
                        at(normal[i].rows[k].frame, "travel_angle, swapped seed against normal"));
        }
    }
    c.note("UNGATED: which column seeds shape_angle.y - the capture's three seed rows hold the "
           "two equal, so no control over it can move a column on this pair");
}

}  // namespace
