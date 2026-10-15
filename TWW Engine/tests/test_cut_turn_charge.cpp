// test_cut_turn_charge.cpp - procCutTurnCharge, the spin's wind-up, against the console, with
// red controls.
//
// 20 frames of the sword capture in two runs (rows 228-237 and 302-311), both from CUT_A into
// CUT_TURN_MOVE.
//
//   * The body has no arithmetic (`!swordButton() || checkCurse()` and `getRate() < 0.01f`), so
//     the console holds when the wind-up ends: `start + n*rate >= end` over ANM_CUTTURNP's
//     EMode_NONE clock, (9 - 1) / 0.8 = ten frames.
//   * Reading the rate before animeUpdate leaves the port in CUT_TURN_CHARGE on the frame the
//     console reads 89.
//   * Dropping B leaves the proc outright, costing nine of each run's ten rows.
//
// Not claimed:
//   * the init's `mNormalSpeed = 0.0f` and `current.angle.y = shape_angle.y`: the seed rows
//     already hold both values (asserted below).
//   * whether the clock took `end` or `frameMax`: both are 9.
//   * the morf (mCutTurnR.field_0x14, 3.0f): no column.
//   * PAD_LEAD: the pad is constant across both wind-ups (asserted below).

#include <cstring>
#include <string>
#include <vector>

#include "cut_turn_charge_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CutTurnChargeFrame;
using tww_engine::testing::CutTurnChargeReplayOptions;
using tww_engine::testing::CutTurnChargeRun;
using tww_engine::testing::Json;

const char* kGolden = "setup_finder_sword_live.json";

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's, over both runs.
/// `perturb_frame` moves the expected anim_frame (1.0 there) by one ULP on that frame;
/// mNormalSpeed and blend_move are 0.0 throughout.
void compare(Case& c, const Json& g, const std::vector<CutTurnChargeRun>& runs,
             int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
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
    for (const CutTurnChargeRun& run : runs) {
        for (const CutTurnChargeFrame& row : run.rows) {
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
            REQUIRE_BITS_RAW(c, row.blend_bits, want["blend_move"].as_f32_bits(),
                             at(row.frame, "blend_move"));
            watch(row.blend_bits == want["blend_move"].as_f32_bits(), at(row.frame, "blend_move"));
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

            // 4 bit and 4 integer comparisons per frame.
            tww_engine::testing::ledger_record(want_proc, tier, 4, 4);
            compared++;
        }

        // The exit: the one column `proc_before_anim` can move.
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left CUT_TURN_CHARGE for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left CUT_TURN_CHARGE for"));
    }
    c.note("compared " + std::to_string(compared) + " CUT_TURN_CHARGE frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. the entries

TWWE_TEST(every_wind_up_is_entered_from_a_proc_this_port_has_read_end_to_end,
          "a run would be entered by a route this port has only been told about") {
    const Json& g = tww_engine::testing::golden(kGolden);

    // procCutTurnCharge_init's call sites are the sword and BOKO arms of one `if` in
    // checkNextActionFromButton (d_a_player_main.cpp:4188, :4198), reached from any proc that ends
    // in checkNextMode, so the check is that the predecessor is a ported proc: CUT_A.
    std::vector<int> entries = tww_engine::testing::cut_turn_charge_entry_frames(
        g, tww_engine::testing::kChargeFirstFrame, tww_engine::testing::kChargeLastFrame);
    REQUIRE_INT(c, (long long)entries.size(), tww_engine::testing::kChargeRuns,
                "CUT_TURN_CHARGE runs the capture's own proc column holds");

    for (int e : entries) {
        const int from = int(g[size_t(e - 1)]["proc"].as_int());
        REQUIRE_TRUE(c, tww_engine::testing::cut_turn_charge_entry_is_known(from),
                     "the proc before the wind-up at " + std::to_string(e) + " (" +
                         std::to_string(from) + ") is one this port has a body for");
        REQUIRE_INT(c, from, daPy_lk_c::daPyProc_CUT_A_e, "...and it is CUT_A by name");
    }

    // The exit is CUT_TURN_MOVE, whose gate reads its predecessor table off this transition.
    for (int e : entries) {
        int f = e;
        while (g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e) {
            f++;
        }
        REQUIRE_INT(c, g[size_t(f)]["proc"].as_int(), daPy_lk_c::daPyProc_CUT_TURN_MOVE_e,
                    at(f, "the proc the console left the wind-up for"));
    }
    c.note("2 wind-ups, both from CUT_A and both into CUT_TURN_MOVE - four consecutive procs this "
           "port has a body for, over capture rows 217-266 and 291-338");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(cut_turn_charge_is_bit_exact_against_the_console,
          "the ported wind-up no longer reproduces the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnChargeRun> runs =
        tww_engine::testing::run_cut_turn_charge_replay(g, CutTurnChargeReplayOptions{});

    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kChargeRuns, "runs replayed");

    int frames = 0;
    for (const CutTurnChargeRun& run : runs) {
        REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                    "frames replayed in the run entered at " + std::to_string(run.entry));
        frames += int(run.rows.size());

        REQUIRE_INT(c, run.unreached_called, 0,
                    "UNREACHED stubs called in the run entered at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.precondition_broken, 0,
                    "stubs called outside their proof's regime, run at " +
                        std::to_string(run.entry));
        REQUIRE_INT(c, run.anm_meta_missing, 0,
                    "animations with no measured frameMax, run at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.rnd_draws_compared, 0,
                    "RNG draws over the compared frames of the run entered at " +
                        std::to_string(run.entry));
        // ...and including the exit, procCutTurnMove_init, which draws nothing either.
        REQUIRE_INT(c, run.rnd_draws, 0,
                    "RNG draws including the exit of the run entered at " +
                        std::to_string(run.entry));
        // No proc-init stub fired: entry and exit are both ported.
        REQUIRE_INT(c, run.next_init_calls, 0,
                    "proc-init stubs reached in the run entered at " + std::to_string(run.entry));
        REQUIRE_TRUE(c, !run.exit_was_named,
                     "the exit of the run entered at " + std::to_string(run.entry) +
                         " was entered rather than named");

        // procCutTurnCharge_init's boundary, read at the init. The .bck separates ANM_CUTTURNP from
        // any other anim whose frameMax is 9.
        REQUIRE_INT(c, run.anim_idx, dRes_INDEX_LKANM_BCK_CUTTURNP_e,
                    "the .bck the init asked for, run at " + std::to_string(run.entry));
        // The wind-up's init raises no status bit (procCutTurnMove_init raises SPIN_ATTACK,
        // procCutA's SWORD_SWING).
        REQUIRE_INT(c, (long long)run.player_status0, 0,
                    "player-status bits the wind-up's init raised, run at " +
                        std::to_string(run.entry));
    }

    REQUIRE_INT(c, frames, tww_engine::testing::kChargeFrames,
                "CUT_TURN_CHARGE frames held to the console");
    compare(c, g, runs);
}

/// The wind-up's length: the port's `port_exit_frame` against the console's entry row stepped
/// through J3DFrameCtrl's EMode_NONE clamp, so a port regression can turn it red.
void check_length(Case& c, const Json& g, const CutTurnChargeReplayOptions& opt) {
    std::vector<CutTurnChargeRun> runs = tww_engine::testing::run_cut_turn_charge_replay(g, opt);
    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kChargeRuns, "runs replayed");

    for (const CutTurnChargeRun& run : runs) {
        const int e = run.entry;
        const f32 start = g[size_t(e)]["anim_frame"].as_f32();
        const f32 rate = g[size_t(e)]["fc_rate"].as_f32();
        const f32 end = f32(g[size_t(e)]["fc_end"].as_int());

        // J3DFrameCtrl::update, EMode_NONE (J3DAnimation.cpp:147-162), stepped until the clamp.
        int steps = 1;
        f32 frame = start;
        while (frame + rate < end) {
            frame += rate;
            steps++;
        }

        REQUIRE_INT(c, run.port_exit_frame - e, steps,
                    "frames the port spent in the wind-up at " + std::to_string(e) +
                        ", against (end - start) / rate off the console's own columns");
        // ...and the console agrees with the same arithmetic.
        REQUIRE_INT(c, run.exit - e, steps,
                    "rows of proc 88 from " + std::to_string(e) + ", against the same quotient");
        // The three terms are the HIO fields the init hands setSingleMoveAnime.
        REQUIRE_BITS(c, start, 1.0f, at(e, "the start - mCutTurnR.field_0x10"));
        REQUIRE_BITS(c, rate, 0.8f, at(e, "the rate - mCutTurnR.field_0xC"));
        REQUIRE_INT(c, g[size_t(e)]["fc_end"].as_int(), 9, at(e, "the end - mCutTurnR.field_0x4"));
    }
}

TWWE_TEST(the_wind_ups_length_is_the_inits_three_anim_arguments,
          "a run of the right length for the wrong reason would read as a pass") {
    // procCutTurnCharge leaves when the MOVE0 rate falls under 0.01, which EMode_NONE does on the
    // update where `frame + rate >= end`, so the length is fixed by the entry row's anim_frame,
    // fc_rate and fc_end.
    check_length(c, tww_engine::testing::golden(kGolden), CutTurnChargeReplayOptions{});
    c.note("both wind-ups are 10 frames in the port and 10 rows in the capture, which is "
           "(9 - 1) / 0.8 stepped through EMode_NONE's clamp");
}

TWWE_TEST(the_inits_other_two_lines_cannot_be_seen_by_this_capture,
          "an unobservable init write would be reported as a held one") {
    // procCutTurnCharge_init's other two lines write values the seed rows already hold. This
    // asserts those equalities on the capture, so a capture entering from a moving slash turns it
    // red.
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<int> entries = tww_engine::testing::cut_turn_charge_entry_frames(
        g, tww_engine::testing::kChargeFirstFrame, tww_engine::testing::kChargeLastFrame);

    for (int e : entries) {
        const Json& seed = g[size_t(e - 1)];
        REQUIRE_BITS_RAW(c, seed["potential_speed"].as_f32_bits(),
                         tww_engine::testing::f32_bits(0.0f),
                         at(e - 1, "the seed's mNormalSpeed, which the init sets to 0.0"));
        REQUIRE_INT(c, seed["travel_angle"].as_int(), seed["shape_angle_y"].as_int(),
                    at(e - 1, "the seed's travel angle, which the init sets to shape_angle.y"));
    }
    c.note("2 of the init's 4 lines are copied and unobserved here - both seeds already hold what "
           "they write. This case is about the capture, not about the port: it cannot go red on "
           "a port regression, and it is not counted as gating those two lines");
}

TWWE_TEST(the_pad_alignment_is_invisible_across_the_wind_ups,
          "a constant the gate cannot see would be reported as one it checks") {
    // A no-change check, not a red control: btn_hold is 640 on every row of both wind-ups, so
    // PAD_LEAD is not checked here (it is in test_roll_replay and test_cut_turn_move).
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions late;
    late.pad_lead = 0;
    std::vector<CutTurnChargeRun> base =
        tww_engine::testing::run_cut_turn_charge_replay(g, CutTurnChargeReplayOptions{});
    std::vector<CutTurnChargeRun> other =
        tww_engine::testing::run_cut_turn_charge_replay(g, late);

    REQUIRE_INT(c, (long long)other.size(), (long long)base.size(), "runs replayed either way");
    for (size_t r = 0; r < base.size(); r++) {
        REQUIRE_INT(c, (long long)other[r].rows.size(), (long long)base[r].rows.size(),
                    "frames in the run entered at " + std::to_string(base[r].entry));
        for (size_t i = 0; i < base[r].rows.size(); i++) {
            REQUIRE_BITS_RAW(c, other[r].rows[i].anim_bits, base[r].rows[i].anim_bits,
                             at(base[r].rows[i].frame, "anim_frame under the other alignment"));
            REQUIRE_INT(c, other[r].rows[i].proc, base[r].rows[i].proc,
                        at(base[r].rows[i].frame, "proc under the other alignment"));
        }
        REQUIRE_INT(c, other[r].exit_proc, base[r].exit_proc,
                    "the exit of the run entered at " + std::to_string(base[r].entry));
        // ...and the pad byte is the same on every frame of the span.
        for (int f = base[r].entry; f <= base[r].exit; f++) {
            REQUIRE_INT(c, g[size_t(f)]["btn_hold"].as_int(),
                        g[size_t(f - 1)]["btn_hold"].as_int(),
                        at(f, "btn_hold against the row before it"));
        }
    }
    c.note("btn_hold is constant across both wind-ups, so PAD_LEAD is UNCHECKED by this gate - "
           "test_roll_replay and test_cut_turn_move are where it is checked");
}

// ------------------------------------------------------------------------ 2. the red controls

TWWE_RED_CONTROL(red_turn_charge_the_comparator_itself,
                 "the expected anim_frame moved by one ULP on the first wind-up frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutTurnChargeRun> runs =
        tww_engine::testing::run_cut_turn_charge_replay(g, CutTurnChargeReplayOptions{});
    compare(c, g, runs, tww_engine::testing::kChargeFirstFrame);
}

TWWE_RED_CONTROL(red_turn_charge_the_B_hold_dropped,
                 "B released, which is the first half of the body's own exit test") {
    // `if (!swordButton() || checkCurse()) checkNextMode(0);`: the port leaves on the first body
    // frame, and nine of ten rows read the wrong proc.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions opt;
    opt.no_b_hold = true;
    compare(c, g, tww_engine::testing::run_cut_turn_charge_replay(g, opt));
}

TWWE_RED_CONTROL(red_turn_charge_the_curse_answered_yes,
                 "daPy_dmEcallBack_c::checkCurse() true - the other half of the same test") {
    // The other half of the same `||`.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions opt;
    opt.cursed = true;
    compare(c, g, tww_engine::testing::run_cut_turn_charge_replay(g, opt));
}

TWWE_RED_CONTROL(red_turn_charge_the_proc_run_before_the_anim_clock,
                 "the order: the exit test reads the previous frame's rate") {
    // The whole body is the read that slips: the wind-up lasts eleven frames and row 238 reads 89.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions opt;
    opt.proc_before_anim = true;
    compare(c, g, tww_engine::testing::run_cut_turn_charge_replay(g, opt));
}

TWWE_RED_CONTROL(red_turn_charge_the_length_under_a_wrong_start,
                 "the length check itself, with the clock seeded at 0.0") {
    // The length check's own control: with start 0.0 the port needs twelve frames and the console
    // still says ten.
    CutTurnChargeReplayOptions opt;
    opt.start_at_zero = true;
    check_length(c, tww_engine::testing::golden(kGolden), opt);
}

TWWE_RED_CONTROL(red_turn_charge_the_anim_started_at_zero,
                 "the clock seeded at 0.0 instead of mCutTurnR.field_0x10") {
    // The init's start argument wrong: anim_frame moves on every row, and the wind-up is twelve
    // frames.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions opt;
    opt.start_at_zero = true;
    compare(c, g, tww_engine::testing::run_cut_turn_charge_replay(g, opt));
}

TWWE_RED_CONTROL(red_turn_charge_the_anim_rate_at_one,
                 "the clock's rate forced to 1.0 instead of mCutTurnR.field_0xC") {
    // The init's rate argument wrong: fc_rate moves on every row and the wind-up ends after nine.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutTurnChargeReplayOptions opt;
    opt.rate_one = true;
    compare(c, g, tww_engine::testing::run_cut_turn_charge_replay(g, opt));
}

}  // namespace
