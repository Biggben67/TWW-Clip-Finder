// test_cut_turn.cpp - procCutTurn against setup_finder_sword_live.json, with red controls.
//
// procCutTurn's rate-expired arm counts down before it exits:
//
//     if (frameCtrl.getRate() < 0.01f) {
//         if (mProcVar0.m34D0 > 0) { mProcVar0.m34D0--; }      // ...one more frame
//         else { mDirection = DIR_RIGHT; checkNextMode(0); return true; }
//     }
//
// mCutTurn.field_0x2 is 1, so all six runs leave on the frame after the clock clamps, and the
// console's `proc` reads 85 on the clamping frame. That frame reads 20.999001 = mEnd - 0.001,
// which is EMode_NONE's clamp and no other attribute's.
//
// Not claimed:
//   * anything between the runs (WAIT with the lock held, BACK_JUMP, BACK_JUMP_LAND, JUMP_CUT,
//     JUMP_CUT_LAND are not ported); each run replays from its own seed row.
//   * the attack cylinder's radius and the blur ribbons' alpha: no capture column, so they are
//     held against the decomp's closed form (the PORT-INTERNAL cases).
//   * procCutTurn_init's BOKO arm (a Bokoblin's weapon): copied, and `unreached_called` shows it
//     unreached.

#include <algorithm>
#include <cstring>
#include <string>
#include <vector>

#include "cut_turn_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CutTurnFrame;
using tww_engine::testing::CutTurnReplayOptions;
using tww_engine::testing::CutTurnRun;
using tww_engine::testing::Json;

const char* kGolden = "setup_finder_sword_live.json";

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

f32 f32_of(uint32_t bits) {
    f32 f;
    std::memcpy(&f, &bits, 4);
    return f;
}

/// The port's frames against the capture's, over every run.
///
/// `perturb_frame` moves the expected anim_frame by one ULP on that frame: the comparator's own
/// red control. Not mNormalSpeed, which is 0.0 on every spin frame.
void compare(Case& c, const Json& g, const std::vector<CutTurnRun>& runs, int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
    // Where the comparison first disagreed; the runner suppresses a red case's failure log.
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
    for (const CutTurnRun& run : runs) {
        for (const CutTurnFrame& row : run.rows) {
            const Json& want = g[size_t(row.frame)];
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_anim = want["anim_frame"].as_f32_bits();
            if (row.frame == perturb_frame) {
                want_anim += 1;   // the red control: one ULP, on one frame
            }
            REQUIRE_BITS_RAW(c, row.anim_bits, want_anim, at(row.frame, "anim_frame"));
            watch(row.anim_bits == want_anim, at(row.frame, "anim_frame"));
            REQUIRE_BITS_RAW(c, row.nspeed_bits, want["potential_speed"].as_f32_bits(),
                             at(row.frame, "mNormalSpeed"));
            watch(row.nspeed_bits == want["potential_speed"].as_f32_bits(),
                  at(row.frame, "mNormalSpeed"));
            REQUIRE_BITS_RAW(c, row.rate_bits, want["fc_rate"].as_f32_bits(),
                             at(row.frame, "fc_rate"));
            watch(row.rate_bits == want["fc_rate"].as_f32_bits(), at(row.frame, "fc_rate"));
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
            watch(row.travel_angle == want["travel_angle"].as_int(), at(row.frame, "travel_angle"));

            // 3 bit comparisons and 4 integer ones per frame.
            tww_engine::testing::ledger_record(want_proc, tier, 3, 4);
            compared++;
        }

        // The exit, against the capture's proc on the first frame that is not CUT_TURN.
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left CUT_TURN for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left CUT_TURN for"));
    }
    c.note("compared " + std::to_string(compared) + " CUT_TURN frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. the entries

TWWE_TEST(every_spin_is_entered_from_a_proc_the_decomp_has_a_call_site_for,
          "a run would be entered with an init argument nothing in the decomp justifies") {
    const Json& g = tww_engine::testing::golden(kGolden);

    // procCutTurn_init's one argument picks the start frame, 5.0 or 2.0, by call site, so it is
    // read off the capture's proc on the row before each entry.
    std::vector<int> entries = tww_engine::testing::cut_turn_entry_frames(
        g, tww_engine::testing::kTurnFirstFrame, tww_engine::testing::kTurnLastFrame);
    REQUIRE_INT(c, (long long)entries.size(), tww_engine::testing::kTurnRuns,
                "CUT_TURN runs the capture's own proc column holds");

    int from_move = 0, from_landing = 0;
    for (int e : entries) {
        const int from = int(g[size_t(e - 1)]["proc"].as_int());
        const int arg = tww_engine::testing::cut_turn_init_arg(from);
        REQUIRE_TRUE(c, arg >= 0,
                     "the proc before the spin at " + std::to_string(e) + " (" +
                         std::to_string(from) + ") is a proc the decomp calls procCutTurn_init "
                         "from - a predecessor not in that table is a route this port has not read");
        if (arg == 0) {
            from_move++;
        } else {
            from_landing++;
        }
    }
    // Both arms must occur, or the argument is held for one value only.
    REQUIRE_TRUE(c, from_move > 0, "no spin entered from CUT_TURN_MOVE - the FALSE arm is unrun");
    REQUIRE_TRUE(c, from_landing > 0, "no spin entered from a landing - the TRUE arm is unrun");
    c.note("spins: " + std::to_string(from_move) + " from CUT_TURN_MOVE (start 2.0), " +
           std::to_string(from_landing) + " from a landing (start 5.0)");
}

TWWE_TEST(the_clamped_anim_frame_settles_which_attribute_ANM_CUTTURN_has,
          "the capture's own clamp value would no longer rule out RESET and LOOP") {
    // The spin's last frame reads 20.999001 with the rate at 0, and each of J3DFrameCtrl::update's
    // three arms leaves a different number there:
    //
    //     EMode_NONE    mFrame = mEnd - 0.001    = 20.999001   <- the capture
    //     EMode_RESET   mFrame = mStart          = 5.0 (or 2.0)
    //     EMode_LOOP    mFrame -= mEnd - mLoop   (wraps; the rate never drops and the spin never
    //                                             ends, so the proc column could not read 4)
    //
    // Driven directly because the body that reads it is a copy.
    const f32 kEnd = 21.0f, kStart = 5.0f, kRate = 1.2f;
    const J3DFrameCtrl::Attribute_e modes[] = {
        J3DFrameCtrl::EMode_NONE, J3DFrameCtrl::EMode_RESET, J3DFrameCtrl::EMode_LOOP};
    const char* names[] = {"EMode_NONE", "EMode_RESET", "EMode_LOOP"};

    const Json& g = tww_engine::testing::golden(kGolden);
    const uint32_t want = g[size_t(800)]["anim_frame"].as_f32_bits();   // the last spin's last row

    for (int m = 0; m < 3; m++) {
        J3DFrameCtrl fc;
        fc.init((s16)kEnd);
        fc.setAttribute((u8)modes[m]);
        fc.setStart((s16)kStart);
        fc.setRate(kRate);
        fc.setFrame(20.6f);     // the capture's own second-to-last row
        fc.update();
        uint32_t got;
        f32 frame = fc.getFrame();
        std::memcpy(&got, &frame, 4);
        if (modes[m] == J3DFrameCtrl::EMode_NONE) {
            REQUIRE_BITS_RAW(c, got, want,
                             "EMode_NONE's clamp is the console's last spin frame");
        } else {
            REQUIRE_TRUE(c, got != want,
                         std::string(names[m]) + " leaves a different frame than the console's - "
                         "which is what rules it out");
        }
    }
    c.note("ANM_CUTTURN's attribute is MEASURED as EMode_NONE by the clamp value, not defaulted");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(cut_turn_is_bit_exact_against_the_console,
          "the ported spin no longer reproduces the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});

    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kTurnRuns, "runs replayed");

    int frames = 0;
    for (const CutTurnRun& run : runs) {
        REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                    "frames replayed in the run entered at " + std::to_string(run.entry));
        frames += int(run.rows.size());

        REQUIRE_INT(c, run.unreached_called, 0,
                    "UNREACHED stubs called in the run entered at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.precondition_broken, 0,
                    "stubs called outside their proof's regime, run at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.rnd_draws_compared, 0,
                    "RNG draws over the compared frames of the run entered at " +
                        std::to_string(run.entry));
        // ...and the exit frame's: all six leave into WAIT, whose init draws once.
        REQUIRE_INT(c, run.rnd_draws, 1,
                    "RNG draws including the exit of the run entered at " +
                        std::to_string(run.entry));

        // procCutTurn_init's boundary: the turn writes no speed or angle after entry, so these
        // arguments are most of what its init can be held to.
        REQUIRE_INT(c, run.sword_anim_idx, dRes_INDEX_LKANM_BCK_CUTTURNA_e,
                    "the .bck checkNormalSwordEquip's fork asked for, run at " +
                        std::to_string(run.entry));
        REQUIRE_INT(c, run.blur_pos_idx, dRes_INDEX_LKANM__CUTTURN_POS_e,
                    "the blur position buffer the init loaded");
        REQUIRE_INT(c, run.at_atp, 2,
                    "the attack power SetAtAtp was handed - the normal sword without the soup");
        REQUIRE_BITS_RAW(c, run.at_target_bits, tww_engine::testing::f32_bits(180.0f),
                         "m35A4, the radius the at-window's chase walks toward");
        // The ground fork: the courtyard stone is neither GRASS nor WATER, so the default arm
        // spawns the smoke and sets m35A0 = 21.0, which the clamped clock (20.999001) never
        // exceeds; hence `smoke_removes` is 0.
        REQUIRE_INT(c, run.particle_ground_id, dPa_name::ID_AK_JT_ROUNDATTACKSMOKE,
                    "the ground plume the attribute fork spawned, run at " +
                        std::to_string(run.entry));
        // m35A0 is read at the init: procWait_init, which the exit frame runs, writes the same
        // word.
        REQUIRE_BITS_RAW(c, run.plume_end_bits, tww_engine::testing::f32_bits(21.0f),
                         "m35A0, the frame past which that plume would be ended");
        REQUIRE_INT(c, run.particle_toe_id, dPa_name::ID_AK_JN_ROUNDATTACKTOE,
                    "the toe plume, which is spawned on every arm");
        REQUIRE_INT(c, run.particle_toe_joint, CL_JNT_RTOE_JNT_e,
                    "...and the joint its matrix was asked for");
        REQUIRE_INT(c, (long long)run.player_status0, daPyStts0_SWORD_SWING_e,
                    "the player-status bit the init raised");
        REQUIRE_INT(c, run.sword_cut_se, JA_SE_LK_KAITENGIRI,
                    "the spin cue the at-window fired, run at " + std::to_string(run.entry));
        // The toe plume ends on `frame > 17.0`, the ground plume on `frame > m35A0` (never here),
        // so these two counters show which lines ran.
        REQUIRE_INT(c, run.particle_ends, 3,
                    "toe-plume end() calls - the frames whose clock is past 17.0 with the rate "
                    "still live, run at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.smoke_removes, 0,
                    "smoke removals - m35A0 is 21.0 and the clock never reaches it");
    }

    REQUIRE_INT(c, frames, tww_engine::testing::kTurnFrames,
                "CUT_TURN frames held to the console");
    compare(c, g, runs);
}

TWWE_TEST(the_exit_is_one_frame_later_than_the_animation_and_the_capture_says_so,
          "the countdown that keeps the spin alive past its own clock would be untested") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});

    // Read off the capture: on every run's last frame the rate is already 0 and the proc is still
    // CUT_TURN. procCutA's rate-expired arm, by contrast, dispatches on the same frame.
    for (const CutTurnRun& run : runs) {
        const Json& last = g[size_t(run.exit - 1)];
        REQUIRE_BITS_RAW(c, last["fc_rate"].as_f32_bits(), tww_engine::testing::f32_bits(0.0f),
                         at(run.exit - 1, "the console's rate on the last spin frame"));
        REQUIRE_INT(c, last["proc"].as_int(), daPy_lk_c::daPyProc_CUT_TURN_e,
                    at(run.exit - 1, "...and the console's proc there, with the rate already 0"));
        REQUIRE_INT(c, g[size_t(run.exit)]["proc"].as_int(), daPy_lk_c::daPyProc_WAIT_e,
                    at(run.exit, "the proc one frame later"));
    }
    c.note("all " + std::to_string(runs.size()) +
           " runs spend one frame in CUT_TURN with the rate at 0 - field_0x2 is 1");
}

TWWE_TEST(the_at_window_chase_walks_the_cylinder_out_in_eighteens,
          "PORT-INTERNAL, no console column: cLib_chaseF's per-frame walk would be unchecked") {
    // No capture column: held against the decomp's closed form, so this is not evidence about
    // the console.
    //
    //     mAtCyl.SetR(m35A4 * 0.5f);                          // procCutTurn_init, twice
    //     if (frame >= field_0x30 (3.0) && frame < field_0x34 (18.5))
    //         cLib_chaseF(mAtCyl.GetRP(), m35A4 (180.0), 18.0f);
    //
    // The init starts it at half, so the chase takes five steps of 18.0 from 90.0.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});

    int saturated_runs = 0;
    for (const CutTurnRun& run : runs) {
        const f32 target = f32_of(run.at_target_bits);
        f32 want = target * 0.5f;
        // The entry frame is the init's: no step yet, the radius is what SetR left.
        REQUIRE_BITS_RAW(c, run.rows.front().at_radius_bits, tww_engine::testing::f32_bits(want),
                         at(run.entry, "the radius the init left, m35A4 * 0.5"));
        bool first = true;
        int steps = 0;
        for (const CutTurnFrame& row : run.rows) {
            if (!first) {
                const f32 clock = f32_of(row.anim_bits);
                if (clock >= 3.0f && clock < 18.5f) {
                    if (want < target) {
                        steps++;
                    }
                    want += 18.0f;
                    if (want > target) {
                        want = target;
                    }
                }
            }
            first = false;
            REQUIRE_BITS_RAW(c, row.at_radius_bits, tww_engine::testing::f32_bits(want),
                             at(row.frame, "the attack cylinder's radius"));
        }
        REQUIRE_INT(c, steps, 5,
                    "steps the chase takes before it saturates, run at " +
                        std::to_string(run.entry));
        if (want == target) {
            saturated_runs++;
        }
    }
    REQUIRE_INT(c, saturated_runs, tww_engine::testing::kTurnRuns,
                "runs whose at-window is long enough for the chase to reach 180.0 - five steps "
                "of 18.0 from the init's 90.0, which every one of the six has room for");
}

TWWE_TEST(the_blur_ribbons_are_alpha_d_on_for_exactly_one_frame,
          "PORT-INTERNAL, no console column: checkPass's second reader would be unchecked") {
    // procCutTurn's last fork is `frameCtrl.checkPass(field_0x34)`, the forward-looking predicate
    // the slash's lunge uses, against 18.5. Its only observable is the ribbons' alpha (inline
    // stores in the decomp too), which has no capture column. checkPass fires on the one frame
    // whose [frame, frame+rate) contains 18.5, and the next frame's `getAlpha() == 0x80` else-arm
    // clears it; a `frame >= pass` reading would hold it on for the rest of the run.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});

    for (const CutTurnRun& run : runs) {
        int on = 0, on_frame = -1;
        f32 on_clock = 0.0f;
        for (const CutTurnFrame& row : run.rows) {
            if (row.ribbon_alpha == 0x80) {
                on++;
                on_frame = row.frame;
                on_clock = f32_of(row.anim_bits);
            }
        }
        REQUIRE_INT(c, on, 1,
                    "frames with the ribbons lit in the run entered at " +
                        std::to_string(run.entry));
        // ...and it is the last frame below 18.5, not the first above it.
        REQUIRE_TRUE(c, on_clock < 18.5f && on_clock + 1.2f >= 18.5f,
                     "the lit frame's clock " + std::to_string(on_clock) + " at " +
                         std::to_string(on_frame) + " straddles 18.5 from below");
    }
}

TWWE_TEST(the_spins_missing_animation_metadata_cannot_move_a_compared_column,
          "ANM_CUTTURN's frameMax would be resting on a measurement nobody made") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});

    // ANM_CUTTURN's metadata is parsed from the shipped LkAnm.arc into anm_meta.inc. frameMax is
    // not read: setSingleMoveAnime takes `end` explicitly (mCutTurn.field_0x0 = 21) and reads
    // getFrameMax() only when end < 0. The attribute the .bck gives agrees with the clamp case
    // above, which measures it off the console.
    for (const CutTurnRun& run : runs) {
        REQUIRE_INT(c, run.anm_meta_missing, 0,
                    "the run at " + std::to_string(run.entry) +
                        " still reports ANM_CUTTURN as unmeasured - anm_meta.inc has its row, so "
                        "this is the table going stale");
    }
    c.note("ANM_CUTTURN's row is parsed from the shipped .bck (frameMax 21, EMode_NONE); "
           "frameMax is unread here, and the clamp measures the attribute off the console");
}

TWWE_TEST(the_B_hold_cannot_reach_a_compared_column_in_the_spin,
          "an input this gate says is inert would have become live without the gate noticing") {
    // Not a red control. procCutTurn reads swordButton() behind `mProcVar6.m3570 != 0`, set only
    // when procCutTurn_init found m34C4 == 6 (a combo's sixth link); it is 0 on every run. B is
    // driven both ways and the output must be identical.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnReplayOptions off;
    off.no_b_hold = true;
    std::vector<CutTurnRun> with = tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});
    std::vector<CutTurnRun> without = tww_engine::testing::run_cut_turn_replay(g, off);

    REQUIRE_INT(c, (long long)without.size(), (long long)with.size(), "runs replayed either way");
    for (size_t r = 0; r < with.size(); r++) {
        REQUIRE_INT(c, (long long)without[r].rows.size(), (long long)with[r].rows.size(),
                    "frames in the run entered at " + std::to_string(with[r].entry));
        for (size_t i = 0; i < with[r].rows.size(); i++) {
            REQUIRE_BITS_RAW(c, without[r].rows[i].anim_bits, with[r].rows[i].anim_bits,
                             at(with[r].rows[i].frame, "anim_frame with B dropped"));
            REQUIRE_INT(c, without[r].rows[i].proc, with[r].rows[i].proc,
                        at(with[r].rows[i].frame, "proc with B dropped"));
        }
        REQUIRE_INT(c, without[r].exit_proc, with[r].exit_proc,
                    "the exit of the run entered at " + std::to_string(with[r].entry));
    }
    c.note("B is held on 60 of the 94 spin frames and moves nothing - m34C4 is never 6, so "
           "mProcVar6.m3570 is 0 and the swordButton() arm is shut");
}

// ------------------------------------------------------------------------ 2. the red controls

TWWE_RED_CONTROL(red_turn_the_comparator_itself,
                 "the expected anim_frame moved by one ULP on the first spin frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnRun> runs =
        tww_engine::testing::run_cut_turn_replay(g, CutTurnReplayOptions{});
    compare(c, g, runs, tww_engine::testing::kTurnFirstFrame);
}

TWWE_RED_CONTROL(red_the_init_argument_flipped,
                 "procCutTurn_init handed the other start frame - 5.0 where the decomp says 2.0") {
    // Both arms move (the CUT_TURN_MOVE runs start at 5.0, the landing runs at 2.0), so this
    // cannot pass by getting one group right; the clock never resynchronises.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnReplayOptions opt;
    opt.wrong_init_arg = true;
    compare(c, g, tww_engine::testing::run_cut_turn_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_exit_countdown_zeroed,
                 "mProcVar0.m34D0 read as 0 instead of mCutTurn.field_0x2's 1") {
    // With the countdown at 0 the port dispatches on the clamping frame, so each run's last frame
    // reads WAIT where the console reads 85. One frame per run moves.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnReplayOptions opt;
    opt.no_exit_countdown = true;
    compare(c, g, tww_engine::testing::run_cut_turn_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_facing_seeded_from_the_travel_angle,
                 "shape_angle.y seeded from the previous row's travel_angle") {
    // `current.angle.y = shape_angle.y`: before the two spins entered from JUMP_CUT_LAND,
    // shape_angle_y is 51145 and travel_angle 18377, and the console's entry row reads 51145.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnReplayOptions opt;
    opt.wrong_seed_shape_angle = true;
    compare(c, g, tww_engine::testing::run_cut_turn_replay(g, opt));
}

}  // namespace
