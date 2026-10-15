// test_cut_turn_move.cpp - procCutTurnMove (the spin's steered hold) against the console capture
// setup_finder_sword_live.json: 22 frames in two runs (rows 238-249 and 312-321), both entered
// from CUT_TURN_CHARGE and both leaving for CUT_TURN.
//
// Not claimed: frames outside the runs; the hurricane fork (47-frame countdown vs -1, longer than
// either run, driven both ways below); mMaxNormalSpeed's value beyond being nonzero.

#include <cstring>
#include <string>
#include <vector>

#include "cut_turn_move_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CutTurnMoveFrame;
using tww_engine::testing::CutTurnMoveReplayOptions;
using tww_engine::testing::CutTurnMoveRun;
using tww_engine::testing::Json;

const char* kGolden = "setup_finder_sword_live.json";

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's, over both runs.
///
/// `perturb_frame` moves the expected blend_move by one ULP on that frame (the comparator's red
/// control); the other float columns are 0.0 here, where one ULP is a denormal.
void compare(Case& c, const Json& g, const std::vector<CutTurnMoveRun>& runs,
             int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
    // The runner suppresses a red case's failure log, so note where it first disagreed.
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
    for (const CutTurnMoveRun& run : runs) {
        for (const CutTurnMoveFrame& row : run.rows) {
            const Json& want = g[size_t(row.frame)];
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_blend = want["blend_move"].as_f32_bits();
            if (row.frame == perturb_frame) {
                want_blend += 1;   // red control: one ULP, on one frame
            }
            REQUIRE_BITS_RAW(c, row.blend_bits, want_blend, at(row.frame, "blend_move"));
            watch(row.blend_bits == want_blend, at(row.frame, "blend_move"));
            REQUIRE_BITS_RAW(c, row.anim_bits, want["anim_frame"].as_f32_bits(),
                             at(row.frame, "anim_frame"));
            watch(row.anim_bits == want["anim_frame"].as_f32_bits(), at(row.frame, "anim_frame"));
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

            tww_engine::testing::ledger_record(want_proc, tier, 4, 4);
            compared++;
        }

        // The exit, against the capture's first frame that is not CUT_TURN_MOVE.
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left CUT_TURN_MOVE for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left CUT_TURN_MOVE for"));
    }
    c.note("compared " + std::to_string(compared) + " CUT_TURN_MOVE frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. the entries

TWWE_TEST(every_steered_hold_is_entered_from_the_one_proc_the_decomp_calls_it_from,
          "a run would be entered by a route this port has not read") {
    const Json& g = tww_engine::testing::golden(kGolden);

    // The decomp's one live call site is procCutTurnCharge (d_a_player_sword.inc:1681).
    std::vector<int> entries = tww_engine::testing::cut_turn_move_entry_frames(
        g, tww_engine::testing::kTurnMoveFirstFrame, tww_engine::testing::kTurnMoveLastFrame);
    REQUIRE_INT(c, (long long)entries.size(), tww_engine::testing::kTurnMoveRuns,
                "CUT_TURN_MOVE runs the capture's own proc column holds");

    for (int e : entries) {
        const int from = int(g[size_t(e - 1)]["proc"].as_int());
        REQUIRE_TRUE(c, tww_engine::testing::cut_turn_move_entry_is_known(from),
                     "the proc before the hold at " + std::to_string(e) + " (" +
                         std::to_string(from) + ") is the one the decomp calls "
                         "procCutTurnMove_init from");
        REQUIRE_INT(c, from, daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e,
                    "...and it is CUT_TURN_CHARGE by name");
    }

    // The exit is the call site cut_turn_replay's kTurnEntries lists with FALSE.
    for (int e : entries) {
        int f = e;
        while (g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_MOVE_e) {
            f++;
        }
        REQUIRE_INT(c, g[size_t(f)]["proc"].as_int(), daPy_lk_c::daPyProc_CUT_TURN_e,
                    at(f, "the proc the console left the hold for"));
    }
    c.note("2 holds, both from CUT_TURN_CHARGE and both into CUT_TURN - which is the call site "
           "cut_turn_replay's predecessor table names for its FALSE arm");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(cut_turn_move_is_bit_exact_against_the_console,
          "the ported steered hold no longer reproduces the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnMoveRun> runs =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});

    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kTurnMoveRuns, "runs replayed");

    int frames = 0;
    for (const CutTurnMoveRun& run : runs) {
        REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                    "frames replayed in the run entered at " + std::to_string(run.entry));
        frames += int(run.rows.size());

        REQUIRE_INT(c, run.unreached_called, 0,
                    "UNREACHED stubs called in the run entered at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.precondition_broken, 0,
                    "stubs called outside their proof's regime, run at " +
                        std::to_string(run.entry));
        REQUIRE_INT(c, run.rnd_draws_compared, 0,
                    "RNG draws over the compared frames of the run entered at " +
                        std::to_string(run.entry));
        // The exit runs procCutTurn_init, which draws nothing either.
        REQUIRE_INT(c, run.rnd_draws, 0,
                    "RNG draws including the exit of the run entered at " +
                        std::to_string(run.entry));

        // procCutTurnMove_init's boundary, read at the init.
        REQUIRE_INT(c, run.anim_idx, dRes_INDEX_LKANM_BCK_CUTTURNPWFB_e,
                    "the .bck the init asked for, run at " + std::to_string(run.entry));
        REQUIRE_INT(c, (long long)run.player_status0, daPyStts0_SPIN_ATTACK_e,
                    "the player-status bit the init raised");
        // Hurricane fork shut: -1 silences the body's `if (m34D0 != -1) seStartSystem(...)` and
        // makes its `else if (m34D0 == 0)` exit arm unreachable.
        REQUIRE_INT(c, run.charge_countdown, -1,
                    "the charge countdown the init left, run at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.particle_ids[0], -1, "no left-hand charge emitter was spawned");
        REQUIRE_INT(c, run.particle_ids[1], -1, "...and neither was its twin");
        REQUIRE_INT(c, run.system_se_calls, 0,
                    "frames that restarted the charge hum, run at " + std::to_string(run.entry));

        // initSeAnime is the B-held arm's last call before the BOKO tail, so this counts frames
        // that ran that arm to its end.
        REQUIRE_INT(c, run.se_anime_inits, int(run.rows.size()) - 1,
                    "frames that ran the B-held arm to its end, run at " +
                        std::to_string(run.entry));
        // The exit frame (B released) runs the third arm instead, hence the -1 above.
        REQUIRE_INT(c, (long long)run.player_status1, 0,
                    "the hurricane's own status bit, which needs a countdown that never ran");
    }

    REQUIRE_INT(c, frames, tww_engine::testing::kTurnMoveFrames,
                "CUT_TURN_MOVE frames held to the console");
    compare(c, g, runs);
}

TWWE_TEST(the_hold_stands_still_because_its_anim_rate_is_a_speed_ratio,
          "the degenerate end of setRate's expression would be read as a constant") {
    // The animation is started (fc_end 10 is ANM_CUTTURNPWFB's frameMax) but its rate,
    // `(mNormalSpeed / mMaxNormalSpeed) * mCutTurnR.field_0x18`, has a zero numerator.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnMoveRun> runs =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});

    for (const CutTurnMoveRun& run : runs) {
        for (const CutTurnMoveFrame& row : run.rows) {
            const Json& want = g[size_t(row.frame)];
            REQUIRE_BITS_RAW(c, want["potential_speed"].as_f32_bits(),
                             tww_engine::testing::f32_bits(0.0f),
                             at(row.frame, "the console's mNormalSpeed"));
            REQUIRE_BITS_RAW(c, want["fc_rate"].as_f32_bits(),
                             tww_engine::testing::f32_bits(0.0f),
                             at(row.frame, "the console's fc_rate"));
            REQUIRE_INT(c, want["fc_end"].as_int(), 10,
                        at(row.frame, "the console's fc_end - ANM_CUTTURNPWFB's frameMax"));
        }
        // The init sets DIR_FORWARD and only `mStickDistance > 0.05f` changes it; it also picks
        // `+field_0x18` over `-field_0x18` for the rate.
        for (const CutTurnMoveFrame& row : run.rows) {
            REQUIRE_INT(c, row.direction, daPy_lk_c::DIR_FORWARD, at(row.frame, "mDirection"));
        }
    }
    c.note("22 frames at rate 0.0 - the numerator, not the expression");
}

TWWE_TEST(the_stopped_flag_and_the_blend_are_written_by_the_same_line,
          "the mode flag that rides on m3598 would be unobserved") {
    // `if (mNormalSpeed <= 0.001f) { onModeFlg(ModeFlg_00000001); m3598 = 0.0f; }` writes a
    // compared column and the standstill flag, which has no column. The entry frame is the
    // init's: mModeFlg comes from mProcInitTable[CUT_TURN_MOVE] and m3598 is 1.0.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnMoveRun> runs =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});

    for (const CutTurnMoveRun& run : runs) {
        bool first = true;
        for (const CutTurnMoveFrame& row : run.rows) {
            if (first) {
                REQUIRE_BITS_RAW(c, row.blend_bits, tww_engine::testing::f32_bits(1.0f),
                                 at(row.frame, "the init's own blend"));
                first = false;
                continue;
            }
            REQUIRE_BITS_RAW(c, row.blend_bits, tww_engine::testing::f32_bits(0.0f),
                             at(row.frame, "the body's blend"));
            REQUIRE_INT(c, row.mode_flg_bit0, 1,
                        at(row.frame, "ModeFlg_00000001, raised by the same arm"));
        }
    }
    c.note("both runs: blend_move 1.0 on the init's frame, 0.0 and the standstill flag on every "
           "frame after");
}

TWWE_TEST(the_hurricane_fork_cannot_reach_a_compared_column_and_the_gate_says_which_way,
          "a fork this gate says is invisible would have become live without the gate noticing") {
    // Not a red control. procCutTurnMove_init's save-flag and magic-meter chain picks a 47-frame
    // countdown (to a dizzy CUT_ROLL) or -1; the runs are 12 and 10 frames, so compared columns
    // must match both ways while the boundary differs.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions on;
    on.hurricane = true;
    std::vector<CutTurnMoveRun> off =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});
    std::vector<CutTurnMoveRun> with = tww_engine::testing::run_cut_turn_move_replay(g, on);

    REQUIRE_INT(c, (long long)with.size(), (long long)off.size(), "runs replayed either way");
    for (size_t r = 0; r < off.size(); r++) {
        REQUIRE_INT(c, (long long)with[r].rows.size(), (long long)off[r].rows.size(),
                    "frames in the run entered at " + std::to_string(off[r].entry));
        for (size_t i = 0; i < off[r].rows.size(); i++) {
            REQUIRE_BITS_RAW(c, with[r].rows[i].blend_bits, off[r].rows[i].blend_bits,
                             at(off[r].rows[i].frame, "blend_move with the charge live"));
            REQUIRE_BITS_RAW(c, with[r].rows[i].anim_bits, off[r].rows[i].anim_bits,
                             at(off[r].rows[i].frame, "anim_frame with the charge live"));
            REQUIRE_BITS_RAW(c, with[r].rows[i].rate_bits, off[r].rows[i].rate_bits,
                             at(off[r].rows[i].frame, "fc_rate with the charge live"));
            REQUIRE_INT(c, with[r].rows[i].proc, off[r].rows[i].proc,
                        at(off[r].rows[i].frame, "proc with the charge live"));
        }
        REQUIRE_INT(c, with[r].exit_proc, off[r].exit_proc,
                    "the exit of the run entered at " + std::to_string(off[r].entry));

        // The boundary must differ, or the option drove nothing.
        REQUIRE_INT(c, with[r].charge_countdown, 47,
                    "the countdown the init seeds when the charge is live");
        REQUIRE_INT(c, with[r].particle_ids[0], dPa_name::ID_AK_JN_CHARGEPOWER00,
                    "the first left-hand emitter the charge spawns");
        REQUIRE_INT(c, with[r].particle_ids[1], dPa_name::ID_AK_JN_CHARGEPOWER01,
                    "...and the second");
        REQUIRE_INT(c, with[r].particle_joint, CL_JNT_CL_LHANDA_e,
                    "...and the joint both of them were handed");
        REQUIRE_INT(c, with[r].system_se, JA_SE_LK_SWORD_CHARGE,
                    "the hum the live countdown restarts");
        REQUIRE_INT(c, with[r].system_se_calls, int(with[r].rows.size()),
                    "frames that restarted it - every frame of the run, including the exit's");
        REQUIRE_INT(c, (long long)with[r].player_status1, 0,
                    "the bit the countdown would raise at 0, which 47 frames cannot reach here");
    }
    c.note("the hurricane fork moves 6 boundary observables and 0 compared columns - 47 frames "
           "of countdown against runs of 12 and 10");
}

TWWE_TEST(the_walk_cap_this_replay_seeds_cannot_reach_a_compared_column_unless_it_is_zero,
          "an unchecked harness seed would look checked because the gate is green") {
    // No proc in the run writes mMaxNormalSpeed (setSpeedAndAngleNormal does), so the replay
    // seeds daPy_lk_c::create's boot value. With a 0.0 numerator any nonzero value gives the same
    // columns; zero is red_the_walk_cap_left_at_zero.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions atn;
    atn.atn_max_speed = true;
    std::vector<CutTurnMoveRun> base =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});
    std::vector<CutTurnMoveRun> other = tww_engine::testing::run_cut_turn_move_replay(g, atn);

    REQUIRE_INT(c, (long long)other.size(), (long long)base.size(), "runs replayed either way");
    for (size_t r = 0; r < base.size(); r++) {
        for (size_t i = 0; i < base[r].rows.size(); i++) {
            REQUIRE_BITS_RAW(c, other[r].rows[i].rate_bits, base[r].rows[i].rate_bits,
                             at(base[r].rows[i].frame, "fc_rate under the other walk cap"));
            REQUIRE_BITS_RAW(c, other[r].rows[i].anim_bits, base[r].rows[i].anim_bits,
                             at(base[r].rows[i].frame, "anim_frame under the other walk cap"));
        }
    }
    c.note("the free cap and the attention cap give identical columns - what the capture can see "
           "about this seed is that it is not zero, and red_the_walk_cap_left_at_zero is that");
}

// ------------------------------------------------------------------------ 2. the red controls

TWWE_RED_CONTROL(red_turn_move_the_comparator_itself,
                 "the expected blend_move moved by one ULP on the first hold frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnMoveRun> runs =
        tww_engine::testing::run_cut_turn_move_replay(g, CutTurnMoveReplayOptions{});
    compare(c, g, runs, tww_engine::testing::kTurnMoveFirstFrame);
}

TWWE_RED_CONTROL(red_the_B_hold_dropped,
                 "B released, which is the whole of procCutTurnMove's body behind swordButton()") {
    // The body is `else if (swordButton())`, so dropping B exits to CUT_TURN on the first body
    // frame.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions opt;
    opt.no_b_hold = true;
    compare(c, g, tww_engine::testing::run_cut_turn_move_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_pad_alignment_one_frame_late,
                 "the harness: pad_lead 0, checked here by a B release rather than an R latch") {
    // btn_hold drops B on rows 249 and 321, so the wrong alignment leaves the hold a frame early.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions opt;
    opt.pad_lead = 0;
    compare(c, g, tww_engine::testing::run_cut_turn_move_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_init_blend_dropped,
                 "m3598 zeroed after the init - the `m3598 = 1.0f` line read as 0") {
    // Moves only each run's entry frame; the body overwrites m3598 on every frame after.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions opt;
    opt.no_init_blend = true;
    compare(c, g, tww_engine::testing::run_cut_turn_move_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_walk_cap_left_at_zero,
                 "mMaxNormalSpeed never seeded, so the anim rate is 0/0") {
    // 0/0 makes the rate NaN; the console's fc_rate is 0.0.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnMoveReplayOptions opt;
    opt.zero_max_speed = true;
    compare(c, g, tww_engine::testing::run_cut_turn_move_replay(g, opt));
}

}  // namespace
