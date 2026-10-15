// test_back_jump.cpp - the backflip and its landing against the console, with red controls.
//
// procBackJump calls procBackJumpLand_init from its own body, so a flip is replayed as one run
// across the proc change, with no seed in between.
//
//   * procBackJumpLand's third arm turns the accumulated stick rotation into
//     procCutTurn_init(TRUE) when `abs(m3578) > 0xF800`. m3578 has no column; the capture's
//     `proc` column says which two of the four flips spin.
//   * gravity: -2.5 on the seed row (commonProcInit), -3.0 airborne (procBackJump_init), -2.5
//     on the landing (not overwritten).
//   * `getRate() < 0.01f` is half the landing test, so ANM_ROLLB's attribute is load-bearing:
//     EMode_LOOP wraps at 11 and the flip never lands.
//
// Not claimed:
//   * position and speed.y on the frame dBgS_Acch::CrrPos clamps and after; the rig has no
//     collision world.
//   * ground contact is delivered from the capture's `speed_y` column, never its `proc` column.
//   * the frames between runs, and the BOKO arm.

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

/// The backflip's row of the shared replay's pair table (jump_land_replay.h).
const JumpLandPair& pair() {
    return tww_engine::testing::jump_land_pair(tww_engine::testing::kPairBackJump);
}

std::vector<JumpLandRun> replay(const Json& g, const JumpLandReplayOptions& opt) {
    return tww_engine::testing::run_jump_land_replay(g, tww_engine::testing::kPairBackJump, opt);
}

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's, over every run.
/// The port's frames against the capture's, over every run.
/// `perturb_frame` moves the expected anim_frame by one ULP on that frame.
void compare(Case& c, const Json& g, const std::vector<JumpLandRun>& runs,
             int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
    int integrated = 0;
    // The runner suppresses a red case's log, so record where it first disagreed.
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
                want_anim += 1;   // the red control
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

            // The integration's columns, on frames before the console's CrrPos (execute():11406)
            // clamps Link to the floor and zeroes speed.y; the rig has no collision world. m3598,
            // the foot-delta multiplier, is asserted 0 there.
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

            // 4 bit and 4 integer comparisons per frame, plus 5 bit comparisons while integrated.
            tww_engine::testing::ledger_record(want_proc, tier, console_clamped ? 4 : 9, 4);
            compared++;
        }

        // The exit: two runs must read 0x55 (CUT_TURN).
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left the landing for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left the landing for"));
    }
    c.note("compared " + std::to_string(compared) + " BACK_JUMP / BACK_JUMP_LAND frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    c.note("of those, " + std::to_string(integrated) +
           " hold current.pos and speed.y - the frames before the console's own ground clamp");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. what is in there

TWWE_TEST(the_capture_holds_four_flips_and_both_of_the_landings_two_exits,
          "the gate could pass on four runs that all left the landing the same way") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<int> entries = tww_engine::testing::jump_land_entry_frames(g, pair());
    REQUIRE_INT(c, (long long)entries.size(), pair().runs,
                "BACK_JUMP runs the capture's own proc column holds");

    int jump_frames = 0, land_frames = 0, to_spin = 0, to_other = 0;
    for (int e : entries) {
        int f = e;
        while (f < int(g.size()) &&
               g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_BACK_JUMP_e) {
            jump_frames++;
            f++;
        }
        while (f < int(g.size()) &&
               g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_BACK_JUMP_LAND_e) {
            land_frames++;
            f++;
        }
        if (g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e) {
            to_spin++;
        } else {
            to_other++;
        }
    }
    REQUIRE_INT(c, jump_frames, pair().jump_frames, "BACK_JUMP frames");
    REQUIRE_INT(c, land_frames, pair().land_frames, "BACK_JUMP_LAND frames");
    // Both exits occurred, so the quickspin arm is exercised.
    REQUIRE_TRUE(c, to_spin > 0, "no flip left the landing for CUT_TURN - the quickspin is unrun");
    REQUIRE_TRUE(c, to_other > 0,
                 "every flip took the quickspin - the clock-expired arm is unrun");
    c.note("flips: " + std::to_string(to_spin) + " into CUT_TURN (the quickspin), " +
           std::to_string(to_other) + " out through the landing's own clock");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(the_backflip_and_its_landing_are_bit_exact_against_the_console,
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
        // A quickspin leaves through procCutTurn_init (no draw); a clock-expired landing through
        // procWait_init (one draw for its idle countdown).
        const bool spun = g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        REQUIRE_INT(c, run.rnd_draws, spun ? 0 : 1, "RNG draws including the exit" + where);

        // The landing frame, port against console: the ground-hit delivery's own claim.
        REQUIRE_INT(c, run.land, run.console_land, "the frame the port entered the landing on" +
                                                       where);

        // procBackJump_init's boundary, and the arms it did not take.
        REQUIRE_INT(c, run.voice_id, 7, "the voice cue the init fired" + where);
        REQUIRE_INT(c, run.fall_init_calls, 0,
                    "procFall_init calls - the drop arm, which says m3688 was written" + where);
        REQUIRE_INT(c, run.shock_calls, 0,
                    "rumble calls - checkHeavyStateOn is false, so the landing's heavy arm is "
                    "shut" + where);
        REQUIRE_INT(c, run.evmng_cut_end_calls, 0,
                    "event-cut-end calls - dComIfGp_event_runCheck is false" + where);
        // Asked every airborne frame that did not land: the entry frame runs the init, the landing
        // frame the other arm.
        REQUIRE_INT(c, run.fan_glide_calls, run.land - run.entry - 1,
                    "checkFanGlideProc asks - one per airborne frame that did not land" + where);
        // procBackJump never calls changeCutReverseProc (procJumpCut asks it every airborne frame).
        REQUIRE_TRUE(c, !pair().asks_cut_reverse, "the pair table says the backflip has no "
                                                  "sword-bounce arm");
        REQUIRE_INT(c, run.cut_reverse_calls, 0,
                    "changeCutReverseProc asks - the backflip's body has no call site" + where);

        // procBackJumpLand_init's, read at the init.
        REQUIRE_INT(c, run.foot_effect_type, 3, "the foot-effect type the landing's init set" + where);
        REQUIRE_INT(c, (long long)(run.reset_flg0 & (daPyRFlg0_RIGHT_FOOT_ON_GROUND |
                                                     daPyRFlg0_LEFT_FOOT_ON_GROUND)),
                    (long long)(daPyRFlg0_RIGHT_FOOT_ON_GROUND | daPyRFlg0_LEFT_FOOT_ON_GROUND),
                    "the two foot-on-ground bits the landing's init raised" + where);
        // The quickspin one-shot, armed because a sword is equipped; 1 on every run.
        REQUIRE_INT(c, run.m3570_at_land, 1,
                    "mProcVar6.m3570 as the landing's init left it - the sword arm" + where);
    }

    REQUIRE_INT(c, frames, pair().jump_frames + pair().land_frames,
                "flip frames held to the console");
    compare(c, g, runs);
}

TWWE_TEST(the_quickspin_fires_on_exactly_one_landing_frame_and_only_past_0xF800,
          "the one-shot could be spent on every frame, or on none, and the exits would still "
          "look right on two of the four runs") {
    // The arms are tested in order, so the m3570 arm is reached only while the clock is alive and
    // below field_0x30 (2.0): the landing's first body frame. Two runs arrive past 0xF800 and spin;
    // two do not and run the clock out.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    int spun = 0, did_not = 0;
    for (const JumpLandRun& run : runs) {
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        // The rotation at the one frame the arm is reached, taken off the run: on a spin that frame
        // is the exit and emits no row.
        REQUIRE_TRUE(c, run.polled,
                     "the landing's quickspin arm was reached at all" + where);
        const int mag = run.rotation_at_poll < 0 ? -run.rotation_at_poll : run.rotation_at_poll;
        const bool console_spun =
            g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        if (console_spun) {
            spun++;
            REQUIRE_TRUE(c, mag > 0xF800,
                         "the console spun out of this landing, so the port's own accumulated "
                         "rotation " + std::to_string(mag) + " must be past 0xF800" + where);
            // ...and it left on the first body frame.
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
    REQUIRE_INT(c, did_not, 2, "runs whose landing ran its own clock out");
    c.note("the accumulator the harness carries agrees with the console on all four exits");
}

TWWE_TEST(the_landings_clock_expired_arm_runs_the_full_field_0x2_frames,
          "the landing's own duration would rest on the exit column alone") {
    // mBackJump.field_0x2 is 5, so ROLLBLAND runs 0.0 -> 4.8 at rate 0.8 and clamps on the seventh
    // body frame. Reading the end from field_0x0 (11) would give the same exit, 15 frames long.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    for (const JumpLandRun& run : runs) {
        if (g[size_t(run.exit)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e) {
            continue;
        }
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_INT(c, run.exit - run.land, 7, "landing frames before the clock-expired exit" + where);
        for (const JumpLandFrame& row : run.rows) {
            if (row.frame >= run.land) {
                REQUIRE_INT(c, row.end, 5, at(row.frame, "the landing clock's end - field_0x2"));
            }
        }
    }
}

TWWE_TEST(the_backflips_launch_and_its_first_gravity_step_are_one_frame,
          "the launch, the gravity step and the move would stop being one frame's work") {
    // procBackJump_init writes `speed.y = mBackJump.field_0x14 = 19.0`; the console's first row
    // reads 16.0, one gravity step later (execute() runs posMove after the proc). Asserted as the
    // launch without integration, the console's row, and the port's row with it.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    JumpLandReplayOptions no_move;
    no_move.no_pos_move = true;
    std::vector<JumpLandRun> unmoved = replay(g, no_move);
    REQUIRE_INT(c, (long long)unmoved.size(), (long long)runs.size(), "runs replayed both ways");

    for (size_t i = 0; i < runs.size(); i++) {
        const JumpLandRun& run = runs[i];
        const std::string where = " in the run entered at " + std::to_string(run.entry);
        REQUIRE_BITS_RAW(c, unmoved[i].rows.front().speed_y_bits, f32_bits(19.0f),
                         "speed.y as the init wrote it, integration removed - mBackJump.field_0x14" + where);
        REQUIRE_BITS_RAW(c, g[size_t(run.entry)]["speed_y"].as_f32_bits(),
                         f32_bits(19.0f + -3.0f),
                         "the console's own first row - one gravity step below the launch" + where);
        REQUIRE_BITS_RAW(c, run.rows.front().speed_y_bits,
                         g[size_t(run.entry)]["speed_y"].as_f32_bits(),
                         "...and the port's entry row, integration included" + where);
    }
    c.note("the launch, the gravity step and the console's first row are one frame's arithmetic; "
           "`compare` holds current.pos with them");
}
TWWE_TEST(the_two_rollb_animations_have_measured_metadata_and_not_a_default,
          "ANM_ROLLB's attribute would be resting on getAnimeResource's default") {
    // ANM_ROLLB's attribute is load-bearing (`getRate() < 0.01f`), so both rollb anims need
    // anm_meta.inc rows; this goes red if one is dropped.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});

    for (const JumpLandRun& run : runs) {
        REQUIRE_INT(c, run.anm_meta_missing, 0,
                    "UNDER-slot anims with no measured metadata in the run entered at " +
                        std::to_string(run.entry));
    }
    c.note("rollb (frameMax 11, EMode_NONE) and rollbland (6, EMode_NONE) are measured rows; the "
           "control that says the parse reproduces a known answer is in the generator that writes "
           "anm_meta.inc");
}

// ------------------------------------------------------------------------ 2. the red controls

TWWE_RED_CONTROL(red_flip_the_comparator_itself,
                 "the expected anim_frame moved by one ULP on the first flip's entry frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<JumpLandRun> runs = replay(g, JumpLandReplayOptions{});
    compare(c, g, runs, runs.empty() ? -1 : runs.front().entry);
}

TWWE_RED_CONTROL(red_the_ground_hit_delivered_one_frame_late,
                 "the collision flag this replay delivers, shifted by one frame") {
    // procBackJump lands on `ChkGroundHit() && rate < 0.01f`, so a shift moves every landing.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.late_ground_hit = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_ground_hit_never_delivered,
                 "the collision flag held false, so the flip never lands") {
    // The port stays in BACK_JUMP past the console's proc change. A port that ignored the flag
    // would pass the shift control and fail this one.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_ground_hit = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_launch_position_zeroed,
                 "m3688 dropped, which is commonProcInit's ground-to-midair line removed") {
    // The console's floor is at y = -6534, so with m3688 at the origin the drop arm fires on every
    // airborne frame. procFall_init is a stub that records the dispatch, so this goes red at
    // `fall_init_calls`, not in a column.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_launch_pos = true;
    std::vector<JumpLandRun> runs = replay(g, opt);
    for (const JumpLandRun& run : runs) {
        REQUIRE_INT(c, run.fall_init_calls, 0,
                    "procFall_init calls in the run entered at " + std::to_string(run.entry));
    }
    compare(c, g, runs);
}

TWWE_RED_CONTROL(red_the_integration_not_run,
                 "posMoveFromFootPos skipped after the proc - the replay's integration step") {
    // execute():11400 removed: pos keeps the seed row and speed.y the launch, so the integration's
    // columns go wrong on the first compared frame.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_pos_move = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_skeleton_is_not_ready,
                 "m_old_fdata->getOldFrameFlg() driven false - the copy's own first arm") {
    // posMoveFromFootPos's `if (m_old_fdata->getOldFrameFlg() == false)` arm seeds the feet,
    // writes speedF = 0 and returns; the game takes it once, after Link's model is built.
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
                 "the accumulator the harness carries removed, so no flip can quickspin") {
    // m3578 held at 0: all four runs leave through the clock, and the two spins read proc 4.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_stick_rotation = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_no_sword_equipped,
                 "the quickspin's other gate - the init's arming test - removed") {
    // No sword: procBackJumpLand_init's `#if VERSION > VERSION_DEMO` else leaves m3570 at 0, so the
    // arm is never reached. Paired with the rotation control, each catches a hardcoded other half.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.no_sword = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_heavy_state_on,
                 "procBackJump_init's heavy fork taken - half the speed and 1.2x the anim rate") {
    // mNormalSpeed 0.5 * 22.5 = 11.25 and the ROLLB rate 1.5 * 0.8 = 1.2, so the flip is shorter.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.heavy_state = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_anim_clock_set_to_loop,
                 "ANM_ROLLB's measured EMode_NONE replaced by EMode_LOOP") {
    // A looping clock never drops its rate to 0, so the flip never lands.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.loop_jump_anim = true;
    compare(c, g, replay(g, opt));
}

TWWE_RED_CONTROL(red_the_facing_seeded_from_the_travel_angle,
                 "shape_angle.y seeded from the previous row's travel_angle") {
    // Both inits write current.angle.y from shape_angle.y, so a seed from travel_angle makes them
    // no-ops; the rows before the entries have the two apart.
    const Json& g = tww_engine::testing::golden(kGolden);
    JumpLandReplayOptions opt;
    opt.wrong_seed_shape_angle = true;
    compare(c, g, replay(g, opt));
}

}  // namespace
