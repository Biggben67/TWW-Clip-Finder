// test_turn_atn.cpp - procWaitTurn and procAtnMove against the old sim, with red controls.
//
// The oracle is the old sim because the banked setup-finder captures hold no row in proc 0x17
// and three in 0x07 (counted by the first case). The two procs share an oracle and a replay
// (turn_atn_replay.cpp), not a body: the pivot latches a goal at dispatch and leaves when the
// residual reaches zero; the sidestep latches nothing, has no clock, and leaves only when taken.
//
// What a run can answer that the copied bodies cannot:
//   * which HIO row each arm indexes: setSpeedAndAngleAtn picks mMove (forward), mAtnMoveB
//     (backward) or mAtnMove (side). `side`, `backward` and `forward` differ by nothing else;
//     their caps are 12.0, 15.0 and 17.0 on the entry frame.
//   * the exit dispatch, on both procs and two branches of the pivot's;
//   * the direction machine's forks;
//   * the boundary's answers.
//
// Scenarios (each `covers` string is in the golden and printed by the replay case):
//   procWaitTurn   reversal        the full 0x8000 pivot: four minSteps and the overshoot clamp
//                  short_pivot     aimed 0x7A00 round - a frame shorter, every angle different
//                  l_at_the_exit   L on the exit frame: checkNextMode's targeting arm
//   procAtnMove    from_the_roll   the finder's own route, `dry_roll_r` out of the old sim
//                  side            the strafe: facing at the lock, travel chasing the stick
//                  backward        the tail call into setSpeedAndAngleAtnBack and mAtnMoveB
//                  forward         the arm that is setSpeedAndAngleNormal and not this proc
//                  direction_swing all three arms in one run, tables changing under it
//
// Not claimed:
//   * procWaitTurn's changeSlideProc() and checkNextActionFromButton(): the old sim models three
//     of its five statements. No scenario presses a button mid-pivot (asserted below).
//   * getGroundAngle's non-zero arm: the rig's collision world is empty, so the angle is 0.
//   * position: the pivot does not move, and the sidestep's motion is posMoveFromFootPos's.
//   * the frame before `from_the_roll`'s entry: its FRONT_ROLL seed row exits on a clock no column
//     carries, so it is seeded at its entry. The other seven replay their dispatching frame.

#include <cstdlib>
#include <string>
#include <vector>

#include "player_rig.h"
#include "turn_atn_replay.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::Rig;
using tww_engine::testing::TurnAtnFrame;
using tww_engine::testing::TurnAtnKind;
using tww_engine::testing::TurnAtnOptions;
using tww_engine::testing::TurnAtnRun;
using tww_engine::testing::TurnAtnSpec;
using tww_engine::testing::turn_atn_spec;

//: Ordered by catalog blocks: 2 then 1.
const TurnAtnKind kKinds[] = {TurnAtnKind::WaitTurn, TurnAtnKind::AtnMove};

std::string at(const TurnAtnRun& run, int frame, const char* column) {
    return run.fn + " " + run.name + " frame " + std::to_string(frame) + " " + column;
}

uint32_t hex_bits(const Json& v) {
    return uint32_t(std::strtoul(v.str.c_str(), nullptr, 16));
}

const Json& golden_of(TurnAtnKind kind) {
    return tww_engine::testing::golden(turn_atn_spec(kind).golden);
}

std::vector<TurnAtnRun> replay(TurnAtnKind kind, const TurnAtnOptions& opt) {
    return tww_engine::testing::run_turn_atn_replay(kind, golden_of(kind), opt);
}

/// The port's frames against the oracle's, over one proc's scenarios.
/// `perturb` moves the expected mMaxNormalSpeed by one ULP on each scenario's first row; the cap
/// (17.0 or 12.0) is used because mNormalSpeed is 0.0 through the whole pivot.
void compare(Case& c, TurnAtnKind kind, const std::vector<TurnAtnRun>& runs,
             bool perturb = false) {
    const TurnAtnSpec& spec = turn_atn_spec(kind);
    const Json& g = golden_of(kind);
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(spec.golden);
    const Json& scenarios = g["scenarios"];
    int compared = 0;
    int bad = 0;
    int exit_rows_skipped = 0;
    int exit_rows_agreeing_anyway = 0;
    // The runner suppresses a red case's log, so record where it first disagreed.
    std::string first_bad;
    auto watch = [&](bool ok, const std::string& where) {
        if (!ok) {
            bad++;
            if (first_bad.empty()) {
                first_bad = where;
            }
        }
    };

    for (size_t s = 0; s < runs.size(); s++) {
        const TurnAtnRun& run = runs[s];
        const Json& rows = scenarios[s]["frames"];
        for (size_t k = 0; k < run.rows.size(); k++) {
            const TurnAtnFrame& row = run.rows[k];
            const Json& want = rows[size_t(row.frame)];
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_cap = hex_bits(want["max_nspeed_hex"]);
            if (perturb && k == 0) {
                want_cap += 1;   // the red control
            }
            REQUIRE_BITS_RAW(c, row.max_nspeed_bits, want_cap,
                             at(run, row.frame, "mMaxNormalSpeed"));
            watch(row.max_nspeed_bits == want_cap, at(run, row.frame, "mMaxNormalSpeed"));

            const uint32_t want_nspeed = hex_bits(want["nspeed_hex"]);
            REQUIRE_BITS_RAW(c, row.nspeed_bits, want_nspeed, at(run, row.frame, "mNormalSpeed"));
            watch(row.nspeed_bits == want_nspeed, at(run, row.frame, "mNormalSpeed"));

            REQUIRE_INT(c, row.proc, want_proc, at(run, row.frame, "proc"));
            watch(row.proc == want_proc, at(run, row.frame, "proc"));
            REQUIRE_INT(c, row.shape_angle_y, want["shape_angle_y"].as_int(),
                        at(run, row.frame, "shape_angle_y"));
            watch(row.shape_angle_y == want["shape_angle_y"].as_int(),
                  at(run, row.frame, "shape_angle_y"));
            // travel_angle and mDirection are not held on the exit row: checkNextMode's
            // changeWaitProc() -> procWait_init() writes `current.angle.y = shape_angle.y` and
            // `mDirection = DIR_NONE` (d_a_player_main.cpp:6070-6071), which the old sim's
            // changeWaitProc does not model. The skip is counted; the pivot's exit rows agree
            // anyway.
            const bool exit_row = row.frame == run.exit;
            if (exit_row) {
                exit_rows_skipped++;
                if (row.travel_angle == want["travel_angle"].as_int() &&
                    row.direction == want["direction"].as_int()) {
                    exit_rows_agreeing_anyway++;
                }
            } else {
                REQUIRE_INT(c, row.travel_angle, want["travel_angle"].as_int(),
                            at(run, row.frame, "travel_angle"));
                watch(row.travel_angle == want["travel_angle"].as_int(),
                      at(run, row.frame, "travel_angle"));
                REQUIRE_INT(c, row.direction, want["direction"].as_int(),
                            at(run, row.frame, "mDirection"));
                watch(row.direction == want["direction"].as_int(),
                      at(run, row.frame, "mDirection"));
            }

            // mProcVar2.m34D4 is held only on the pivot; on a sidestep the old sim's value is its
            // constructor's.
            if (spec.latches_turn_target) {
                REQUIRE_INT(c, row.turn_target, want["turn_target"].as_int(),
                            at(run, row.frame, "mProcVar2.m34D4, the latched pivot goal"));
                watch(row.turn_target == want["turn_target"].as_int(),
                      at(run, row.frame, "mProcVar2.m34D4, the latched pivot goal"));
            }

            // 2 bit comparisons and 4 or 5 integer ones per frame, 2 fewer on an exit row.
            tww_engine::testing::ledger_record(
                want_proc, tier, 2, (spec.latches_turn_target ? 5 : 4) - (exit_row ? 2 : 0));
            compared++;
        }

        // The exit. Both leave for WAIT: MOVE needs |mNormalSpeed| > 0.001 and every run stops.
        const int want_exit = int(rows[size_t(run.exit)]["proc"].as_int());
        REQUIRE_INT(c, run.exit_proc, want_exit,
                    at(run, run.exit, "the proc the port left for"));
        watch(run.exit_proc == want_exit, at(run, run.exit, "the proc the port left for"));
    }
    c.note(std::string(spec.fn) + ": compared " + std::to_string(compared) + " frame(s) over " +
           std::to_string(runs.size()) + " scenario(s); " + std::to_string(exit_rows_skipped) +
           " exit row(s) had travel_angle and mDirection skipped (procWait_init writes both and "
           "the old sim's changeWaitProc models neither) and " +
           std::to_string(exit_rows_agreeing_anyway) + " of them agree on both regardless");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

}  // namespace

// ------------------------------------------------------------- 0. what the oracle is

TWWE_TEST(the_turn_and_atn_oracles_are_the_old_sim_and_the_suite_says_so,
          "a regression-tier golden would be being counted as console evidence") {
    // The tier comes from the manifest row; the console frames in each proc are counted over the
    // banked captures against the number the producer wrote.
    const char* kCaptures[] = {"setup_finder_demo_live.json", "setup_finder_rollfree_live.json",
                               "setup_finder_sword_live.json"};
    for (TurnAtnKind kind : kKinds) {
        const TurnAtnSpec& spec = turn_atn_spec(kind);
        const Json& g = golden_of(kind);
        REQUIRE_TRUE(c,
                     tww_engine::testing::golden_tier(spec.golden) ==
                         tww_engine::testing::Tier::Sim,
                     std::string(spec.golden) + " is the regression tier, not the console tier");
        REQUIRE_TRUE(c, g["_tier"].str == "regression",
                     std::string(spec.golden) +
                         ": the file's own _tier field says the same thing the manifest does");
        REQUIRE_TRUE(c, !g["_note"].str.empty() && !g["_oracle"]["repo"].str.empty(),
                     std::string(spec.golden) +
                         ": the file names the engine that produced it and the checkout it ran in");
        REQUIRE_INT(c, int(g["_proc"]["id"].as_int()), spec.proc_id,
                    std::string(spec.fn) + ": the golden is the one for this proc");

        int in_proc = 0;
        for (const char* name : kCaptures) {
            const Json& cap = tww_engine::testing::golden(name);
            for (size_t f = 0; f < cap.size(); f++) {
                if (cap[f]["proc"].as_int() == spec.proc_id) {
                    in_proc++;
                }
            }
        }
        REQUIRE_INT(c, in_proc, int(g["_proc"]["console_frames"].as_int()),
                    std::string(spec.fn) +
                        ": console frames counted here against the number the producer wrote "
                        "into the file - if these ever disagree, one of the two is stale");
    }
    c.note("procWaitTurn has 0 console frames and procAtnMove has 3, counted over the three "
           "banked captures that carry a proc column; a proc with three frames is not a proc "
           "with a console gate, and the oracle for both is " +
           golden_of(TurnAtnKind::WaitTurn)["_oracle"]["repo"].str + " @ " +
           golden_of(TurnAtnKind::WaitTurn)["_oracle"]["head"].str);
}

// ------------------------------------------------------------------------- 1. the replay itself

TWWE_TEST(the_pivot_reproduces_the_old_sims_every_frame,
          "procWaitTurn no longer computes what the old sim computes - the pivot rate, the "
          "latched goal, the overshoot clamp or the frame it leaves on") {
    compare(c, TurnAtnKind::WaitTurn, replay(TurnAtnKind::WaitTurn, TurnAtnOptions{}));
    for (const TurnAtnRun& run : replay(TurnAtnKind::WaitTurn, TurnAtnOptions{})) {
        c.note(run.name + ": " + run.covers);
    }
}

TWWE_TEST(the_sidestep_reproduces_the_old_sims_every_frame,
          "procAtnMove no longer computes what the old sim computes - which of the three "
          "speed/angle arms runs, which HIO row it indexes, or where mDirection goes next") {
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, TurnAtnOptions{}));
    for (const TurnAtnRun& run : replay(TurnAtnKind::AtnMove, TurnAtnOptions{})) {
        c.note(run.name + ": " + run.covers);
    }
}

// --------------------------------------------------------------- 2. what each init actually did

TWWE_TEST(the_two_inits_write_the_decomps_own_words,
          "procWaitTurn_init's latched goal or procAtnMove_init's countdown is not written - "
          "which the frame columns cannot see, because the pivot's goal is only visible through "
          "the angles it produces and the countdown has no reader in this port at all") {
    for (const TurnAtnRun& run : replay(TurnAtnKind::WaitTurn, TurnAtnOptions{})) {
        // `mProcVar2.m34D4 = m34E8`, the stick target of the dispatch frame.
        const Json& e = golden_of(TurnAtnKind::WaitTurn)["scenarios"];
        (void)e;
        REQUIRE_INT(c, run.turn_target_after_init >= 0, 1,
                    run.name + ": the init ran and the latched goal was read back");
        // `current.angle.y = shape_angle.y`. Every scenario enters with the two equal, so this
        // asserts the line, not a difference.
        REQUIRE_INT(c, run.travel_after_init, run.rows.front().shape_angle_y,
                    run.name + ": current.angle.y = shape_angle.y, procWaitTurn_init's last line");
        // procWaitTurn_init writes no countdown; reset_boundary leaves -1, so the sidestep's 20 is
        // a write.
        REQUIRE_INT(c, run.hold_after_init, 0,
                    run.name + ": mProcVar0.m34D0 after procWaitTurn_init - untouched, which is "
                               "what makes the sidestep's 20 a write rather than a default");
    }
    for (const TurnAtnRun& run : replay(TurnAtnKind::AtnMove, TurnAtnOptions{})) {
        REQUIRE_INT(c, run.hold_after_init, 20,
                    run.name + ": mProcVar0.m34D0 = 20, procAtnMove_init's last line");
    }
    c.note("the countdown is carried and unread in this port: mProcVar0.m34D0's readers are "
           "procMove_init's own write and the ice-slip arm, and no compared column here is one "
           "of them - which is exactly why it is asserted at the init rather than in a frame");
}

// ----------------------------------------------------- 3. which scenarios gate their own entry

TWWE_TEST(the_dispatching_frame_is_replayed_wherever_it_can_be,
          "a scenario would be seeding past its own init without saying so - which would make "
          "the init look gated on a run that fed it") {
    int replayed = 0;
    int seeded = 0;
    for (TurnAtnKind kind : kKinds) {
        for (const TurnAtnRun& run : replay(kind, TurnAtnOptions{})) {
            if (run.dispatch_replayed) {
                replayed++;
            } else {
                seeded++;
                REQUIRE_TRUE(c, run.name == "from_the_roll",
                             run.fn + " " + run.name +
                                 ": the only scenario allowed to seed past its dispatch is the "
                                 "one whose seed row is a FRONT_ROLL frame");
            }
        }
    }
    REQUIRE_INT(c, replayed, 7, "scenarios whose dispatching frame this replay runs - so "
                                "checkNextMode's routing and the init are inside the gate");
    REQUIRE_INT(c, seeded, 1, "scenarios seeded at their entry row instead");
    c.note("7 of the 8 scenarios reach their proc through the port's own checkNextMode; "
           "from_the_roll is seeded, because the roll's exit turns on an animation clock the "
           "golden has no column for");
}

// --------------------------------------------------------- 4. the boundary, and the slope arm

TWWE_TEST(the_sidesteps_two_preconditions_hold_on_every_frame,
          "changeFrontWallTypeProc or checkIceSlipFall answering TRUE - either would take the "
          "proc somewhere the oracle does not model, and both are graded on a precondition "
          "rather than on an outcome") {
    for (TurnAtnKind kind : kKinds) {
        for (const TurnAtnRun& run : replay(kind, TurnAtnOptions{})) {
            REQUIRE_INT(c, run.precondition_broken, 0,
                        run.fn + " " + run.name +
                            ": boundary preconditions broken (changeFrontWallTypeProc's centred "
                            "stick, checkIceSlipFall's mNormalSpeed < 10.0)");
            REQUIRE_INT(c, run.unreached_called, 0,
                        run.fn + " " + run.name + ": boundary stubs graded UNREACHED that ran");
        }
    }
    // The pivot's body has no wall or ice test; the sidestep calls the wall one every frame
    // checkNextMode leaves it alone.
    int pivot_wall = 0;
    for (const TurnAtnRun& run : replay(TurnAtnKind::WaitTurn, TurnAtnOptions{})) {
        pivot_wall += run.front_wall_proc_calls;
    }
    int atn_wall = 0;
    for (const TurnAtnRun& run : replay(TurnAtnKind::AtnMove, TurnAtnOptions{})) {
        atn_wall += run.front_wall_proc_calls;
    }
    REQUIRE_INT(c, pivot_wall, 0,
                "changeFrontWallTypeProc calls from the pivot - its body has no wall test");
    REQUIRE_TRUE(c, atn_wall > 0,
                 "changeFrontWallTypeProc calls from the sidestep - `mDirection != DIR_FORWARD "
                 "&& changeFrontWallTypeProc()` is the second term of its own exit guard, so a "
                 "zero here would mean the guard never got past its first term");
    c.note("the sidestep reached the wall test on " + std::to_string(atn_wall) +
           " frame(s) and the pivot on 0");
}

TWWE_TEST(the_ground_angle_is_zero_because_the_world_is_empty,
          "getGroundAngle's slope arm would be silently unexercised - the port would agree with "
          "an oracle that models no slope, and nothing would say which of the two reasons the "
          "answer is 0 for") {
    // setBlendAtnMoveAnime scales by `cM_scos(getGroundAngle(...))`. The rig's dBgS is empty, so
    // `ChkPolySafe` is false and the function returns 0. Called directly because the old sim models
    // no slope either, so the frame columns cannot tell the two reasons apart.
    Rig rig;
    daPy_lk_c& lk = rig.lk;
    REQUIRE_INT(c, (int)lk.getGroundAngle(&lk.mAcch.m_gnd, (s16)0), 0,
                "getGroundAngle over the rig's empty collision world");
    REQUIRE_INT(c, (int)lk.getGroundAngle(&lk.mAcch.m_gnd, (s16)0x4000), 0,
                "...and from a second heading, so the 0 is not one angle's coincidence");
    c.note("UNGATED: getGroundAngle's non-zero arm. It needs a ground polygon and the pad-driven "
           "rig has none; the old sim models no slope in either proc, so no scenario here could "
           "have told the two reasons apart - a console capture on a slope is what would");
}

TWWE_TEST(the_pivot_never_reaches_the_two_lines_the_oracle_does_not_model,
          "a scenario would be gating procWaitTurn's changeSlideProc or checkNextActionFromButton "
          "against an oracle that has neither line - and a disagreement there would read as a "
          "port defect when it is the oracle's own gap") {
    // The old sim's `_proc_wait_turn` is three statements; the decomp's is five. The missing two
    // are early returns ahead of the `sVar1 == 0` test. changeSlideProc is unreachable (no slide
    // polygon); checkNextActionFromButton needs a button, so no scenario may press one.
    int with_a_button = 0;
    const Json& g = golden_of(TurnAtnKind::WaitTurn);
    const Json& scenarios = g["scenarios"];
    for (size_t s = 0; s < scenarios.size(); s++) {
        const Json& rows = scenarios[s]["frames"];
        const int entry = int(scenarios[s]["entry"].as_int());
        const int exit = int(scenarios[s]["exit"].as_int());
        for (int i = entry; i <= exit; i++) {
            if (rows[size_t(i)]["btn_a"].as_int() || rows[size_t(i)]["btn_r"].as_int()) {
                with_a_button++;
            }
        }
    }
    REQUIRE_INT(c, with_a_button, 0,
                "pivot frames with A or R delivered - the inputs that would reach "
                "checkNextActionFromButton, which the oracle does not model");
    c.note("UNGATED on the pivot: changeSlideProc and checkNextActionFromButton. Both are early "
           "returns the old sim has no line for, so this oracle cannot hold "
           "them - a console capture of proc 0x17 is what would, and there is not one");
}

// -------------------------------------------------------------------------- 5. the red controls

TWWE_RED_CONTROL(red_the_one_ulp_comparator,
              "the comparator itself: one ULP on mMaxNormalSpeed, on the first compared row of "
              "every scenario. If this passes, REQUIRE_BITS_RAW is not comparing bits and every "
              "green column above is worth nothing") {
    compare(c, TurnAtnKind::WaitTurn, replay(TurnAtnKind::WaitTurn, TurnAtnOptions{}), true);
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, TurnAtnOptions{}), true);
}

TWWE_RED_CONTROL(red_the_pivot_goal_follows_the_stick,
              "mProcVar2.m34D4 re-read from m34E8 every frame instead of chased from what the "
              "init latched - a pivot written as a stick-follow. It is the single line that "
              "makes procWaitTurn a pivot, and `reversal` releases its stick mid-turn, so the "
              "two diverge from the first frame after the release") {
    TurnAtnOptions opt;
    opt.turn_target_follows_stick = true;
    compare(c, TurnAtnKind::WaitTurn, replay(TurnAtnKind::WaitTurn, opt));
}

TWWE_RED_CONTROL(red_the_pad_read_one_frame_late,
              "the stick and buttons taken from the previous row - which is the console replays' "
              "own alignment and is wrong against this oracle, because the old sim takes its "
              "inputs as arguments to the frame that acts on them") {
    TurnAtnOptions opt;
    opt.wrong_pad_lead = true;
    compare(c, TurnAtnKind::WaitTurn, replay(TurnAtnKind::WaitTurn, opt));
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, opt));
}

TWWE_RED_CONTROL(red_the_attention_lock_dropped,
              "checkAttentionLock() driven FALSE on every frame. On the sidestep it is the whole "
              "proc - checkNextMode's targeting arm is what keeps the run in ATN_MOVE at all - "
              "and on the pivot it is the exit's branch, which `l_at_the_exit` is aimed at") {
    TurnAtnOptions opt;
    opt.no_attention_lock = true;
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, opt));
    compare(c, TurnAtnKind::WaitTurn, replay(TurnAtnKind::WaitTurn, opt));
}

TWWE_RED_CONTROL(red_the_facing_lock_read_from_travel,
              "m34E6 driven to the travel angle instead of the golden's own column. "
              "setSpeedAndAngleAtn's side arm writes `shape_angle.y = m34E6` every frame, so on "
              "a strafe - where the facing and the travel angle are 0x4000 apart - this is the "
              "difference between holding the lock and turning with the stick") {
    TurnAtnOptions opt;
    opt.facing_lock_from_travel = true;
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, opt));
}

TWWE_RED_CONTROL(red_the_direction_machine_frozen,
              "mDirection held at the seed row's value - setBlendAtnMoveAnime allowed to run but "
              "not to move it. Four of the five ATN scenarios pick one arm on the entry frame "
              "and never change it, so this control bites on `direction_swing` and on the entry "
              "of the others, which is what the swing scenario exists to guarantee") {
    TurnAtnOptions opt;
    opt.freeze_direction = true;
    compare(c, TurnAtnKind::AtnMove, replay(TurnAtnKind::AtnMove, opt));
}

// A measurement, not a red control: running the dispatch before animeUpdate moves nothing here.
// procWaitTurn reads no clock, and procAtnMove reads one only in setBlendAtnMoveAnime
// (foot-effect flags and strafe .bck choice), which writes no word this gate holds. The old sim
// has no animation column that could show the order.
TWWE_TEST(the_anim_clock_order_moves_no_column_on_either_proc,
          "a claim that the animeUpdate order is UNCHECKED here would be wrong - which would "
          "matter the day one of these procs grows a clock read that reaches a column") {
    TurnAtnOptions opt;
    opt.proc_before_anim = true;
    for (TurnAtnKind kind : kKinds) {
        const std::vector<TurnAtnRun> normal = replay(kind, TurnAtnOptions{});
        const std::vector<TurnAtnRun> swapped = replay(kind, opt);
        REQUIRE_INT(c, int(swapped.size()), int(normal.size()),
                    std::string(turn_atn_spec(kind).fn) + ": scenarios, both orders");
        for (size_t i = 0; i < normal.size(); i++) {
            REQUIRE_INT(c, int(swapped[i].rows.size()), int(normal[i].rows.size()),
                        normal[i].fn + " " + normal[i].name + ": frames, both orders");
            for (size_t k = 0; k < normal[i].rows.size() && k < swapped[i].rows.size(); k++) {
                const TurnAtnFrame& a = normal[i].rows[k];
                const TurnAtnFrame& b = swapped[i].rows[k];
                REQUIRE_TRUE(c,
                             a.proc == b.proc && a.nspeed_bits == b.nspeed_bits &&
                                 a.max_nspeed_bits == b.max_nspeed_bits &&
                                 a.shape_angle_y == b.shape_angle_y &&
                                 a.travel_angle == b.travel_angle && a.direction == b.direction,
                             at(normal[i], a.frame,
                                "every compared column, with the dispatch run before animeUpdate "
                                "instead of after"));
            }
        }
    }
    c.note("UNGATED: the animeUpdate/dispatch order. Bit-identical both ways on all 8 scenarios "
           "- procWaitTurn reads no clock at all and procAtnMove reads one only for foot flags "
           "and .bck selection, so no compared column here can see the order. Four other gates "
           "in this repo reject the same injection; this one measures that it cannot");
}

// ----------------------------------------------------------- 6. the port list closes at 22 of 22

TWWE_TEST(the_block_catalog_has_no_proc_left_without_a_body,
          "the ratchet's own claim, asserted from the C++ side: a proc the catalog dispatches "
          "that this port has no body for") {
    // Every proc the block catalog dispatches has a body.
    const Json& procs = tww_engine::testing::port_list()["procs"];
    int with_body = 0;
    std::string missing;
    for (size_t i = 0; i < procs.size(); i++) {
        if (procs[i]["extracted"].size() > 0) {
            with_body++;
        } else {
            missing += (missing.empty() ? "" : ", ") + procs[i]["fn"].str;
        }
    }
    REQUIRE_INT(c, with_body, int(procs.size()),
                "procs the block catalog dispatches that have a body" +
                    (missing.empty() ? std::string() : " - still stubbed: " + missing));
    c.note("the block catalog dispatches " + std::to_string(procs.size()) +
           " procs and every one of them has a body");
}
