// test_cut_a.cpp - procCutA against setup_finder_sword_live.json, with red controls.
//
// Pinned: shape_angle.y and current.angle.y (cLib_addCalcAngleS), and both exits. Runs 1 and 2
// leave when J3DFrameCtrl::update drops the rate to 0 (procCutA's `getRate() < 0.01f`, then
// checkNextMode(0)); runs 3 and 4 leave through checkNextActionFromButton's spin-charge arm. The
// capture's `proc` column settles both.
//
// Not claimed:
//   * the 61 WAIT frames between runs: `lock_l` is 1, so procWait takes setSpeedAndAngleAtn,
//     which is not ported; each run replays from its own seed row (cut_replay.h).
//   * the angle chase's transient: procCutA_init seeds m34D4 from shape_angle.y, so the column is
//     constant at 51145; what is held is that the port does not move it (`wrong_init_angle`).
//   * ANM_CUTA's frame controller attribute (see its case below).

#include <algorithm>
#include <string>
#include <vector>

#include "cut_replay.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CutFrame;
using tww_engine::testing::CutReplayOptions;
using tww_engine::testing::CutRun;
using tww_engine::testing::Json;

const char* kGolden = "setup_finder_sword_live.json";

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's, over every run.
///
/// `perturb_frame` moves the expected mNormalSpeed by one ULP on that frame: the comparator's
/// own red control.
void compare(Case& c, const Json& g, const std::vector<CutRun>& runs, int perturb_frame = -1) {
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    int compared = 0;
    // Where the comparison first disagreed, tallied here because the runner does not print a red
    // control's failure log; without it a control red for the wrong reason looks the same.
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
    for (const CutRun& run : runs) {
        for (const CutFrame& row : run.rows) {
            const Json& want = g[size_t(row.frame)];
            // Keyed on the capture's proc column, never the port's, so a wrong dispatch cannot
            // report coverage of the proc it picked.
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_nspeed = want["potential_speed"].as_f32_bits();
            if (row.frame == perturb_frame) {
                want_nspeed += 1;   // the red control: one ULP, on one frame
            }
            REQUIRE_BITS_RAW(c, row.nspeed_bits, want_nspeed, at(row.frame, "mNormalSpeed"));
            watch(row.nspeed_bits == want_nspeed, at(row.frame, "mNormalSpeed"));
            REQUIRE_BITS_RAW(c, row.anim_bits, want["anim_frame"].as_f32_bits(),
                             at(row.frame, "anim_frame"));
            watch(row.anim_bits == want["anim_frame"].as_f32_bits(), at(row.frame, "anim_frame"));
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

        // The exit: the capture's proc on the first frame that is not CUT_A.
        REQUIRE_INT(c, run.exit_proc, g[size_t(run.exit)]["proc"].as_int(),
                    at(run.exit, "the proc the port left CUT_A for"));
        watch(run.exit_proc == g[size_t(run.exit)]["proc"].as_int(),
              at(run.exit, "the proc the port left CUT_A for"));
    }
    c.note("compared " + std::to_string(compared) + " CUT_A frame(s) over " +
           std::to_string(runs.size()) + " run(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// --------------------------------------------------------------------------- 0. the inputs

TWWE_TEST(a_B_press_starts_a_slash_exactly_when_the_lock_is_held,
          "a B press the harness cannot map would be being silently dropped or silently invented") {
    const Json& g = tww_engine::testing::golden(kGolden);

    // setStickData gates the B trigger behind `dComIfGp_getButtonActionMode() & 2`
    // (d_a_player_main.cpp:10570), which is neither ported nor captured, so the four entries are
    // acted on by name. This checks they are all of them: the capture's eight B presses split
    // exactly on lock_l. With the lock each starts a slash next frame; without it none changes the
    // proc. changeCutProc would start procCutL_init (0x44) on an unlocked press, so whatever
    // blocks it is upstream (the action mode or checkNextActionFromButton's guards); unresolved.
    std::vector<int> entries = tww_engine::testing::cut_entry_frames(
        g, tww_engine::testing::kCutFirstFrame, tww_engine::testing::kCutLastFrame);
    REQUIRE_INT(c, (long long)entries.size(), tww_engine::testing::kCutRuns,
                "CUT_A runs the capture's own proc column holds");

    int locked = 0, unlocked = 0;
    for (int f : tww_engine::testing::b_trigger_frames(g, 1, int(g.size()) - 2)) {
        const bool lock = g[size_t(f)]["lock_l"].as_int() != 0;
        const int next = int(g[size_t(f + 1)]["proc"].as_int());
        if (lock) {
            locked++;
            REQUIRE_INT(c, next, daPy_lk_c::daPyProc_CUT_A_e,
                        "the proc after the locked B press at row " + std::to_string(f));
            // ...exactly kPadLead frames before the entry it caused.
            REQUIRE_TRUE(c, std::find(entries.begin(), entries.end(),
                                      f + CutReplayOptions{}.pad_lead) != entries.end(),
                         "the locked B press at row " + std::to_string(f) +
                             " is one of the entries the replay acts on by name");
        } else {
            unlocked++;
            REQUIRE_INT(c, next, g[size_t(f)]["proc"].as_int(),
                        "the proc after the unlocked B press at row " + std::to_string(f));
        }
    }
    REQUIRE_INT(c, locked, tww_engine::testing::kCutRuns,
                "B presses with the lock held - each one a slash this gate replays");
    REQUIRE_TRUE(c, unlocked > 0,
                 "no B press without the lock - the split above would be one-sided and would say "
                 "nothing about what the lock decides");
    c.note("B presses: " + std::to_string(locked) + " locked (all four start CUT_A), " +
           std::to_string(unlocked) + " unlocked (none changes the proc)");
}

TWWE_TEST(checkPass_is_the_window_ahead_of_the_clock_and_not_the_clock_itself,
          "the slash's lunge frame would move if checkPass were read as `frame >= pass`") {
    // procCutA's speed half hangs on `frameCtrl.checkPass(field_0x28)`, field_0x28 = 6.0, and the
    // capture puts the lunge at clock 5.2, not 6.4: checkPass looks forward, `cur <= pass <
    // cur + rate` (J3DAnimation.cpp:28). Asserted here because the body that calls it is a copy.
    J3DFrameCtrl fc;
    fc.init(19);
    fc.setAttribute(J3DFrameCtrl::EMode_NONE);
    fc.setRate(1.2f);

    fc.setFrame(5.2f);
    REQUIRE_TRUE(c, fc.checkPass(6.0f) != 0,
                 "checkPass(6.0) at frame 5.2 rate 1.2 - the capture's lunge frame");
    REQUIRE_TRUE(c, !(5.2f >= 6.0f),
                 "...and `frame >= pass` is false there, which is what makes the two readings "
                 "different rather than the same test written twice");

    fc.setFrame(6.4f);
    REQUIRE_TRUE(c, fc.checkPass(6.0f) == 0,
                 "checkPass(6.0) at frame 6.4 - the frame a `>=` reading would have fired on");
    REQUIRE_TRUE(c, 6.4f >= 6.0f, "...and `frame >= pass` is true there");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(cut_a_is_bit_exact_against_the_console,
          "the ported slash no longer reproduces the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutRun> runs = tww_engine::testing::run_cut_replay(g, CutReplayOptions{});

    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kCutRuns, "runs replayed");

    int frames = 0;
    int named = 0;
    bool any_entered = false;
    for (const CutRun& run : runs) {
        // Every CUT_A frame, not a prefix.
        REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                    "frames replayed in the run entered at " + std::to_string(run.entry));
        frames += int(run.rows.size());

        // No UNREACHED stub called and no READ-graded stub outside its precondition, or the
        // grades in boundary/stubs.cpp are unchecked.
        REQUIRE_INT(c, run.unreached_called, 0,
                    "UNREACHED stubs called in the run entered at " + std::to_string(run.entry));
        REQUIRE_INT(c, run.precondition_broken, 0,
                    "stubs called outside their proof's regime, run at " + std::to_string(run.entry));
        // No compared column may rest on the RNG. procCutA does not draw and this says so.
        REQUIRE_INT(c, run.rnd_draws_compared, 0,
                    "RNG draws over the compared frames of the run entered at " +
                        std::to_string(run.entry));
        // The exit frame's draws, keyed on the proc the console left for: procWait_init draws
        // once for its idle countdown, procCutTurnCharge_init not at all.
        const int exit_proc = int(g[size_t(run.exit)]["proc"].as_int());
        REQUIRE_INT(c, run.rnd_draws, exit_proc == daPy_lk_c::daPyProc_WAIT_e ? 1 : 0,
                    "RNG draws including the exit of the run entered at " +
                        std::to_string(run.entry));

        // procCutA_init's two forks have no compared column, so their recorded arguments are
        // asserted.
        REQUIRE_INT(c, run.sword_anim_idx, dRes_INDEX_LKANM_BCK_CUTAA_e,
                    "the .bck checkNormalSwordEquip's fork asked for, run at " +
                        std::to_string(run.entry));
        REQUIRE_INT(c, run.blur_pos_idx, dRes_INDEX_LKANM__CUTA_POS_e,
                    "the blur position buffer the init loaded");
        REQUIRE_INT(c, run.cut_at_param_type, daPy_lk_c::CUT_TYPE_CUT_A,
                    "the cut type the init handed setNormalCutAtParam");
        REQUIRE_INT(c, (long long)run.player_status0, daPyStts0_SWORD_SWING_e,
                    "the player-status bit the init raised");
        // The wind-cut cue shows the `5.0 <= frame < 11.0` window was entered; nothing compared
        // is downstream of it.
        REQUIRE_INT(c, run.sword_cut_se, JA_SE_LK_SW_KAZEKIRI_S,
                    "the wind-cut sound the at-window fired, run at " + std::to_string(run.entry));

        named += run.exit_was_named ? 1 : 0;
        any_entered = any_entered || !run.exit_was_named;
    }

    REQUIRE_TRUE(c, any_entered, "no run left CUT_A into a proc this port has a body for");
    // No run leaves CUT_A by naming a proc (an unported proc-init stub): all four exits are
    // entered. Held at 0 so a route this slice cannot take goes red. No green case reaches
    // `record()` in boundary/stubs.cpp or `next_init`.
    REQUIRE_INT(c, named, 0,
                "runs that left CUT_A by naming a proc - 0 with procCutTurnCharge ported, and "
                "the capture's only two named exits were its");

    compare(c, g, runs);
    c.note("CUT_A frames held to the console: " + std::to_string(frames));
}

TWWE_TEST(the_slashs_missing_animation_metadata_cannot_move_a_compared_column,
          "ANM_CUTA's frame controller would be resting on a defaulted attribute") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutRun> runs = tww_engine::testing::run_cut_replay(g, CutReplayOptions{});

    // ANM_CUTA's metadata is parsed from the shipped LkAnm.arc into anm_meta.inc.
    // frameMax is not read: setSingleMoveAnime takes `end` explicitly (mCutA.field_0x2 = 19) and
    // reads getFrameMax() only when end < 0.
    // The attribute is read from the .bck. The capture rules out EMode_LOOP (runs 1 and 2 leave
    // when the clock reaches 19 and the rate drops to 0) but cannot separate NONE from RESET: they
    // differ only in the frame left on the clamping frame, which procWait_init overwrites.
    for (const CutRun& run : runs) {
        REQUIRE_INT(c, run.anm_meta_missing, 0,
                    "the run at " + std::to_string(run.entry) +
                        " still reports ANM_CUTA as unmeasured - anm_meta.inc has its row, so "
                        "this is the table going stale");
    }
    c.note("ANM_CUTA's row is parsed from the shipped .bck; frameMax is still unread here, and "
           "the capture rules out EMode_LOOP without separating EMode_NONE from EMode_RESET");
    REQUIRE_INT(c, (long long)runs.size(), tww_engine::testing::kCutRuns, "runs replayed");
    (void)g;
}

// ------------------------------------------------------------------------ 2. the red controls

TWWE_RED_CONTROL(red_the_comparator_itself,
                 "the expected mNormalSpeed moved by one ULP on the first lunge frame") {
    const Json& g = tww_engine::testing::golden(kGolden);
    std::vector<CutRun> runs = tww_engine::testing::run_cut_replay(g, CutReplayOptions{});
    compare(c, g, runs, tww_engine::testing::kCutFirstFrame + 1);
}

TWWE_RED_CONTROL(red_speedf_fed_from_the_current_row,
                 "speedF taken from row N instead of the row posMove wrote at the end of N-1") {
    // The harness twin. It changes only each run's lunge frame, the one place speedF is read
    // (`fabs(speedF) * 0.2 + 10.0`), by 1.48 units before the decay.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutReplayOptions opt;
    opt.wrong_speedf_lead = true;
    compare(c, g, tww_engine::testing::run_cut_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_slash_entered_with_no_sword_equipped,
                 "mEquipItem left at reset_boundary's NONE, which shuts the whole sword arm") {
    // `mEquipItem == daPyItem_SWORD_e` gates checkNextActionFromButton's spin-charge arm; shut,
    // runs 3 and 4 leave into WAIT, against the capture's proc at 228 and 302.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutReplayOptions opt;
    opt.no_sword_equipped = true;
    compare(c, g, tww_engine::testing::run_cut_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_B_hold_dropped,
                 "mItemButton's BTN_B never set, so daPyFlg0_UNK4 is cleared every frame") {
    // B's hold is gated by the same unrecorded action mode as its trigger. Without it procCutA
    // clears daPyFlg0_UNK4 every frame and the two runs that held B leave into WAIT, not the spin
    // charge.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutReplayOptions opt;
    opt.no_b_hold = true;
    compare(c, g, tww_engine::testing::run_cut_replay(g, opt));
}

TWWE_RED_CONTROL(red_the_entry_angle_seeded_from_the_stick_target,
                 "procCutA_init handed m34E8 instead of shape_angle.y") {
    // changeCutProc picks between these two (d_a_player_sword.inc:412), and procCutA_init's arm
    // is inside `checkAttentionLock()`, so shape_angle.y is the decomp's. With m34E8 the chase
    // moves off 51145.
    const Json& g = tww_engine::testing::golden(kGolden);
    CutReplayOptions opt;
    opt.wrong_init_angle = true;
    compare(c, g, tww_engine::testing::run_cut_replay(g, opt));
}

}  // namespace
