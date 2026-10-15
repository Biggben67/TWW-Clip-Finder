// test_cut_oracle.cpp - procCutL, procCutF and procCutR against the old sim, with red controls.
//
// The three unlocked basic cuts: changeCutProc reaches procCutA_init only under
// checkAttentionLock(), and getDirectionFromAngle picks among these by stick (FORWARD procCutF,
// RIGHT procCutR, LEFT / BACKWARD / neutral procCutL). One decomp body over three
// `daPy_HIO_cut*_c1` rows, so one replay and one file; `CutSpec` holds what differs.
//
// Goldens are sim tier: no banked console capture has a frame in procs 0x42-0x44. See
// cut_oracle_replay.h for what agreement can and cannot catch.
//
// Scenarios (each `covers` string is in the golden):
//   standstill     full-length run, out through the rate-expired arm
//   r_at_the_exit  R lands on the deciding frame: out through `> field_0xC`
//   moving         entered carrying speed - four arms of cLib_addCalc on this cut's maxStep
//   b_held         B never released: out into CUT_TURN_CHARGE
//   aim_off_axis   an off-axis aim latched from the stick, walked by cLib_addCalcAngleS
//   aim_locked     L held, so the aim is the facing; the entry is strafing
//
// Not claimed:
//   * `fc_rate` / `fc_end` have no oracle column; held to each cut's HIO row.
//   * `mpCutfBpk` / `mpCutfBtk` are not modelled by the old sim; held to the same row's MOVE0 clock.
//   * `m34C5` is held to the decomp, where the old sim differs.
//   * The BOKO arm of checkNextActionFromButton's second call site.
//   * The frames before each entry; each scenario is seeded at its own entry row.

#include <cstdlib>
#include <string>
#include <vector>

#include "cut_oracle_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CutKind;
using tww_engine::testing::CutOracleFrame;
using tww_engine::testing::CutOracleOptions;
using tww_engine::testing::CutOracleRun;
using tww_engine::testing::CutSpec;
using tww_engine::testing::cut_spec;
using tww_engine::testing::Json;

enum : int { kCutScenarios = 6 };

//: Ordered by reach in the port list.
const CutKind kKinds[] = {CutKind::L, CutKind::F, CutKind::R};

std::string at(const CutOracleRun& run, int frame, const char* column) {
    return run.cut + " " + run.name + " frame " + std::to_string(frame) + " " + column;
}

uint32_t hex_bits(const Json& v) {
    return uint32_t(std::strtoul(v.str.c_str(), nullptr, 16));
}

const Json& golden_of(CutKind kind) {
    return tww_engine::testing::golden(cut_spec(kind).golden);
}

std::vector<CutOracleRun> replay(CutKind kind, const CutOracleOptions& opt) {
    return tww_engine::testing::run_cut_oracle_replay(kind, golden_of(kind), opt);
}

/// The port's frames against the oracle's, over one cut's six scenarios.
///
/// `perturb` moves the expected anim_frame by one ULP on each scenario's first compared row (4.0
/// there, so not a denormal as mNormalSpeed's 0.0 would give).
void compare(Case& c, CutKind kind, const std::vector<CutOracleRun>& runs, bool perturb = false) {
    const CutSpec& spec = cut_spec(kind);
    const Json& g = golden_of(kind);
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(spec.golden);
    const Json& scenarios = g["scenarios"];
    int compared = 0;
    int bad = 0;
    // The runner suppresses a red case's failure log, so this notes where it first disagreed.
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
        const CutOracleRun& run = runs[s];
        const Json& rows = scenarios[s]["frames"];
        for (size_t k = 0; k < run.rows.size(); k++) {
            const CutOracleFrame& row = run.rows[k];
            const Json& want = rows[size_t(row.frame)];
            const int want_proc = int(want["proc"].as_int());

            uint32_t want_anim = hex_bits(want["anim_frame_hex"]);
            if (perturb && k == 0) {
                want_anim += 1;   // the red control
            }
            REQUIRE_BITS_RAW(c, row.anim_bits, want_anim, at(run, row.frame, "anim_frame"));
            watch(row.anim_bits == want_anim, at(run, row.frame, "anim_frame"));

            const uint32_t want_nspeed = hex_bits(want["nspeed_hex"]);
            REQUIRE_BITS_RAW(c, row.nspeed_bits, want_nspeed, at(run, row.frame, "mNormalSpeed"));
            watch(row.nspeed_bits == want_nspeed, at(run, row.frame, "mNormalSpeed"));

            REQUIRE_INT(c, row.proc, want_proc, at(run, row.frame, "proc"));
            watch(row.proc == want_proc, at(run, row.frame, "proc"));
            REQUIRE_INT(c, row.shape_angle_y, want["shape_angle_y"].as_int(),
                        at(run, row.frame, "shape_angle_y"));
            watch(row.shape_angle_y == want["shape_angle_y"].as_int(),
                  at(run, row.frame, "shape_angle_y"));
            REQUIRE_INT(c, row.travel_angle, want["travel_angle"].as_int(),
                        at(run, row.frame, "travel_angle"));
            watch(row.travel_angle == want["travel_angle"].as_int(),
                  at(run, row.frame, "travel_angle"));

            // 2 bit comparisons and 3 integer ones per frame; the oracle has no fc_rate or fc_end.
            tww_engine::testing::ledger_record(want_proc, tier, 2, 3);
            compared++;
        }

        // The exit, against the oracle's proc on the first frame out of the cut: WAIT on five,
        // CUT_TURN_CHARGE on `b_held`.
        const int want_exit = int(rows[size_t(run.exit)]["proc"].as_int());
        REQUIRE_INT(c, run.exit_proc, want_exit,
                    at(run, run.exit, "the proc the port left the cut for"));
        watch(run.exit_proc == want_exit, at(run, run.exit, "the proc the port left the cut for"));
    }
    c.note(std::string(spec.fn) + ": compared " + std::to_string(compared) + " frame(s) over " +
           std::to_string(runs.size()) + " scenario(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// ------------------------------------------------------------- 0. what the oracle is

TWWE_TEST(the_cut_oracles_are_the_old_sim_and_the_suite_says_so,
          "a regression-tier golden would be being counted as console evidence") {
    // Pins the goldens' tier as sim, and counts that the sword capture has no frame in any of
    // these procs.
    const Json& sword = tww_engine::testing::golden("setup_finder_sword_live.json");
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
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
                    std::string(spec.fn) + ": the golden is the one for this proc - the three "
                                           "files read alike and are keyed only by this field");

        int in_cut = 0;
        for (size_t f = 0; f < sword.size(); f++) {
            if (sword[f]["proc"].as_int() == spec.proc_id) {
                in_cut++;
            }
        }
        REQUIRE_INT(c, in_cut, 0,
                    std::string(spec.fn) +
                        ": rows of the 849-frame sword capture in this proc - if this stops "
                        "being 0, it has a console gate available and the old sim should stop "
                        "being its only one");
    }
    c.note("the sword capture holds " + std::to_string(sword.size()) +
           " rows and 0 of them are CUT_L, CUT_F or CUT_R; the oracle for all three is " +
           golden_of(CutKind::L)["_oracle"]["repo"].str + " @ " +
           golden_of(CutKind::L)["_oracle"]["head"].str);
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(the_three_unlocked_cuts_are_bit_exact_against_the_old_sim,
          "a ported basic cut no longer reproduces the old sim's answer, bit for bit") {
    int total = 0;
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});

        REQUIRE_INT(c, (long long)runs.size(), kCutScenarios,
                    std::string(spec.fn) + ": scenarios replayed");

        int frames = 0;
        for (const CutOracleRun& run : runs) {
            REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                        "frames replayed in " + run.cut + " " + run.name);
            frames += int(run.rows.size());

            REQUIRE_INT(c, run.unreached_called, 0,
                        "UNREACHED stubs called in " + run.cut + " " + run.name);
            REQUIRE_INT(c, run.precondition_broken, 0,
                        "stubs called outside their proof's regime in " + run.cut + " " +
                            run.name);
            // No compared column may rest on the RNG, whose seeds are boot-time globals. On the
            // exit frame procWait_init draws once; the wind-up draws none.
            REQUIRE_INT(c, run.rnd_draws_compared, 0,
                        "RNG draws over the compared frames of " + run.cut + " " + run.name);
            REQUIRE_INT(c, run.rnd_draws, run.exit_proc == daPy_lk_c::daPyProc_WAIT_e ? 1 : 0,
                        "RNG draws including the exit of " + run.cut + " " + run.name);
        }
        REQUIRE_TRUE(c, frames > 0, std::string(spec.fn) + ": frames were replayed at all");
        total += frames;

        compare(c, kind, runs);

        // Two different exit procs across the six, per cut.
        int to_wait = 0, to_charge = 0;
        for (const CutOracleRun& run : runs) {
            to_wait += run.exit_proc == daPy_lk_c::daPyProc_WAIT_e;
            to_charge += run.exit_proc == daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e;
        }
        REQUIRE_INT(c, to_wait, 5,
                    std::string(spec.fn) + ": scenarios that rest at the end of the cut");
        REQUIRE_INT(c, to_charge, 1,
                    std::string(spec.fn) +
                        ": scenarios that leave into the spin's wind-up - the B hold's own arm");
        for (const CutOracleRun& run : runs) {
            c.note(run.cut + " " + run.name + ": " + run.covers);
        }
    }
    c.note("total compared frames over the three procs: " + std::to_string(total));
}

// ------------------------------------------------------- 2. the init, through what it recorded

TWWE_TEST(each_cuts_init_asks_for_its_own_resources,
          "an init would be indexing another cut's tables and nothing compared would move") {
    // Arguments to boundary calls have no compared column, so they are asserted where the
    // boundary recorded them, and required to differ from the other cuts' so a swap is caught.
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
        for (const CutOracleRun& run : replay(kind, CutOracleOptions{})) {
            REQUIRE_INT(c, run.sword_anim_idx, spec.sword_anm,
                        run.cut + " " + run.name +
                            ": the sword .bck checkNormalSwordEquip's true arm asked for");
            // procCutF_init never calls setBlurPosResource, hence -1.
            REQUIRE_INT(c, run.blur_pos_idx, spec.blur_pos,
                        run.cut + " " + run.name +
                            ": the blur-trail buffer setBlurPosResource loaded, or -1 for the "
                            "thrust, whose init does not call it");
            REQUIRE_INT(c, run.cut_at_param_type, spec.cut_type,
                        run.cut + " " + run.name +
                            ": the cut type setNormalCutAtParam was handed");
            REQUIRE_INT(c, (long long)run.player_status0, (long long)daPyStts0_SWORD_SWING_e,
                        run.cut + " " + run.name + ": the player-status bit the init raised");
            for (CutKind other : kKinds) {
                if (other == kind) {
                    continue;
                }
                const CutSpec& o = cut_spec(other);
                REQUIRE_TRUE(c, run.sword_anim_idx != o.sword_anm,
                             run.cut + ": ...and the sword .bck is not " + o.fn + "'s");
                REQUIRE_TRUE(c, run.cut_at_param_type != o.cut_type,
                             run.cut + ": ...and the cut type is not " + o.fn + "'s");
            }
            REQUIRE_TRUE(c, run.sword_anim_idx != dRes_INDEX_LKANM_BCK_CUTAA_e,
                         run.cut + ": ...nor the slash's CUTAA");
            REQUIRE_TRUE(c, run.cut_at_param_type != daPy_lk_c::CUT_TYPE_CUT_A,
                         run.cut + ": ...nor the slash's cut type");
        }
    }
    c.note("CUTLA/_CUTL_POS/CUT_TYPE_CUT_L, CUTFA/no blur buffer/CUT_TYPE_CUT_F and "
           "CUTRA/_CUTR_POS/CUT_TYPE_CUT_R - on all six scenarios of each");
}

TWWE_TEST(the_clock_each_init_seeds_is_that_cuts_own_row_and_its_own_bck,
          "each run's length rests on three numbers no oracle column here can see") {
    // Start, end and rate have no oracle column, so they are held to each cut's HIO row; the anim
    // red controls move them and the replay goes red. The attribute comes from anm_meta.inc and is
    // checked against the old sim's own parse of the same .bck carried in each golden's `_anm`.
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
        const Json& g = golden_of(kind);
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});

        REQUIRE_INT(c, g["_anm"]["attribute"].as_int(), J3DFrameCtrl::EMode_NONE,
                    std::string(spec.fn) +
                        ": the .bck's own attribute, as parse_bck read it off the shipped "
                        "animation");
        int missing = 0;
        for (const CutOracleRun& run : runs) {
            REQUIRE_INT(c, run.anim_attribute, g["_anm"]["attribute"].as_int(),
                        run.cut + " " + run.name +
                            ": the MOVE0 controller's attribute against the .bck's own");
            REQUIRE_INT(c, run.anim_start, 4,
                        run.cut + " " + run.name + ": start, field_0x8");
            REQUIRE_INT(c, run.anim_end, spec.anim_end,
                        run.cut + " " + run.name + ": end, field_0x2");
            REQUIRE_TRUE(c, run.anim_end != spec.wrong_end,
                         run.cut + " " + run.name +
                             ": ...and it is not the row the red control substitutes, which is "
                             "another shipped cut's own field_0x2");
            // The rate against field_0x4 on the first compared row; all four basic cuts share 1.2.
            REQUIRE_BITS_RAW(c, run.rows[0].rate_bits, tww_engine::testing::bits(1.2f),
                             run.cut + " " + run.name + ": rate, field_0x4");
            // The EMode_NONE clamp zeroes the rate on the exit frame, which is not compared.
            REQUIRE_TRUE(c, run.rows.back().rate_bits == tww_engine::testing::bits(1.2f),
                         run.cut + " " + run.name +
                             ": the rate is still live on the last compared row");
            missing += run.anm_meta_missing;
        }
        REQUIRE_INT(c, missing, 0,
                    std::string(spec.fn) +
                        ": its anim has an anm_meta.inc row, so the boundary must not be "
                        "counting it - a non-zero here is the table going stale");
        c.note(std::string(spec.fn) + ": end " + std::to_string(spec.anim_end) +
               ", anm_meta_missing = " + std::to_string(missing) +
               " (the anim is measured out of the arc; `end` is still explicit, so the frameMax "
               "that row supplies is never read, and the attribute is checked against the .bck's "
               "own header as parsed by the old sim)");
    }
}

// --------------------------------------------- 3. the two fields only the thrust's body writes

TWWE_TEST(the_thrusts_blade_flash_is_procCutFs_alone,
          "procCutF's two setFrame lines would be unobserved, or running under the other cuts") {
    // procCutF's `mpCutfBpk->setFrame` / `mpCutfBtk->setFrame` (material and texture-SRT anims)
    // are not modelled by the old sim, so they are held to the decomp's argument, the same frame's
    // MOVE0 clock, and to untouched on the other cuts.
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
        for (const CutOracleRun& run : replay(kind, CutOracleOptions{})) {
            if (spec.sets_cutf_tex) {
                // The init seeds both from field_0x8 (4.0), also the entry row's clock.
                REQUIRE_BITS_RAW(c, run.cutf_bpk_init_bits, tww_engine::testing::bits(4.0f),
                                 run.cut + " " + run.name +
                                     ": mpCutfBpk as procCutF_init left it - field_0x8");
                REQUIRE_BITS_RAW(c, run.cutf_btk_init_bits, tww_engine::testing::bits(4.0f),
                                 run.cut + " " + run.name +
                                     ": mpCutfBtk as procCutF_init left it - field_0x8");
                for (const CutOracleFrame& row : run.rows) {
                    REQUIRE_BITS_RAW(c, row.cutf_bpk_bits, row.anim_bits,
                                     at(run, row.frame, "mpCutfBpk's frame against MOVE0's"));
                    REQUIRE_BITS_RAW(c, row.cutf_btk_bits, row.anim_bits,
                                     at(run, row.frame, "mpCutfBtk's frame against MOVE0's"));
                }
            } else {
                // -1.0f is reset_boundary's seed, distinct from a written 0.
                REQUIRE_BITS_RAW(c, run.cutf_bpk_init_bits, tww_engine::testing::bits(-1.0f),
                                 run.cut + " " + run.name +
                                     ": mpCutfBpk untouched - this init has no such line");
                for (const CutOracleFrame& row : run.rows) {
                    REQUIRE_BITS_RAW(c, row.cutf_bpk_bits, tww_engine::testing::bits(-1.0f),
                                     at(run, row.frame, "mpCutfBpk still untouched"));
                    REQUIRE_BITS_RAW(c, row.cutf_btk_bits, tww_engine::testing::bits(-1.0f),
                                     at(run, row.frame, "mpCutfBtk still untouched"));
                }
            }
        }
    }
    c.note("mpCutfBpk / mpCutfBtk: no oracle column - the old sim does not model them. They are "
           "held to procCutF's own argument (the MOVE0 clock) and to -1 on the other two cuts.");
}

// -------------------------------------------------- 4. the one place the two engines disagree

TWWE_TEST(m34C5_is_held_to_the_decomp_because_the_oracle_collapses_it,
          "a difference between the two engines would be sitting in the port unrecorded") {
    // The `swordTrigger() && m34C5 != 5` line writes 4 / 2 / 3 in procCutL / F / R (procCutA: 1);
    // the old sim writes 1 for every cut type, so the decomp's value is what CutSpec holds. In the
    // game it is the combo chain code changeCutProc reads. No scenario re-presses B inside the
    // cut, so the line is unreached and m34C5 stays 0 on every run.
    for (CutKind kind : kKinds) {
        const CutSpec& spec = cut_spec(kind);
        for (const CutOracleRun& run : replay(kind, CutOracleOptions{})) {
            REQUIRE_INT(c, run.m34C5, 0,
                        run.cut + " " + run.name +
                            ": m34C5 - the chain buffer, unreached by these scenarios because "
                            "none of them re-presses B inside the cut");
        }
        c.note(std::string(spec.fn) + " writes m34C5 = " + std::to_string(spec.m34C5_decomp) +
               " in the decomp; the old sim's one cut body writes 1 for every type. No scenario "
               "here reaches the line, so this is a recorded difference and not a measured one - "
               "it becomes gateable when changeCutProc is ported.");
    }
}

// ------------------------------------------------------------------------- 5. the red controls
//
// Each control is registered once per cut: a single case looping all three would go red if the
// injection bit on only one.

void red(Case& c, CutKind kind, bool CutOracleOptions::*flag) {
    CutOracleOptions opt;
    opt.*flag = true;
    compare(c, kind, replay(kind, opt));
}

#define CUT_RED(ident, what, field)                                                            \
    TWWE_RED_CONTROL(red_cut_l_##ident, what) {                                                \
        red(c, CutKind::L, &CutOracleOptions::field);                                          \
    }                                                                                          \
    TWWE_RED_CONTROL(red_cut_f_##ident, what) {                                                \
        red(c, CutKind::F, &CutOracleOptions::field);                                          \
    }                                                                                          \
    TWWE_RED_CONTROL(red_cut_r_##ident, what) {                                                \
        red(c, CutKind::R, &CutOracleOptions::field);                                          \
    }

// The comparator's own control.
TWWE_RED_CONTROL(red_cut_l_the_comparators_own_ulp,
                 "one ULP added to the expected anim_frame on one row of each CUT_L scenario") {
    compare(c, CutKind::L, replay(CutKind::L, CutOracleOptions{}), true);
}
TWWE_RED_CONTROL(red_cut_f_the_comparators_own_ulp,
                 "one ULP added to the expected anim_frame on one row of each CUT_F scenario") {
    compare(c, CutKind::F, replay(CutKind::F, CutOracleOptions{}), true);
}
TWWE_RED_CONTROL(red_cut_r_the_comparators_own_ulp,
                 "one ULP added to the expected anim_frame on one row of each CUT_R scenario") {
    compare(c, CutKind::R, replay(CutKind::R, CutOracleOptions{}), true);
}

// posMove writes speedF after the dispatch, so frame N reads N-1's. Visible wherever speedF is
// not 0: `moving`, and the whole thrust run.
CUT_RED(speedf_from_the_current_row,
        "speedF fed from the current row instead of the one posMove wrote it on",
        wrong_speedf_lead)

// Pad lead is 1 against a console capture, 0 here. Bites on `r_at_the_exit`, whose exit moves.
CUT_RED(the_pad_read_one_frame_late,
        "the stick and buttons taken from the previous row - the console replays' lead",
        wrong_pad_lead)

// Each body's first lines maintain daPyFlg0_UNK4 off B. Bites on `b_held`'s exit: WAIT instead
// of CUT_TURN_CHARGE.
CUT_RED(the_b_hold_dropped, "mItemButton's BTN_B never set - swordButton() false on every frame",
        no_b_hold)

// R makes checkNextMode(1) bail while the clock runs; without it `r_at_the_exit` runs to the end.
CUT_RED(the_r_hold_dropped, "mItemButton's BTN_R never set - the early exit undone", no_r_hold)

// Moves the `b_held` exit like the B control, but with B pressed and the sword arm shut.
CUT_RED(no_sword_equipped, "mEquipItem left at daPyItem_NONE_e, which shuts the whole sword arm",
        no_sword_equipped)

// The other side of changeCutProc's `checkAttentionLock() || mStickDistance <= 0.05f ?
// shape_angle.y : m34E8`. Bites on `aim_locked`, where the two differ.
CUT_RED(the_init_aim_from_the_stick_target,
        "mProcVar2.m34D4 seeded from m34E8 instead of changeCutProc's own answer", wrong_init_aim)

// The bodies read the clock in the rate test, the `> field_0xC` exit and checkPass.
CUT_RED(the_proc_run_before_the_anim_clock,
        "the order: every clock read takes the previous frame's value", proc_before_anim)

// A wrong HIO row, on the field that moves the run's length: the slash's 19 for CUT_L, CUT_L's 18
// for the other two.
CUT_RED(the_clock_ended_at_another_cuts_field_0x2,
        "the MOVE0 clock's end forced to another shipped cut's own field_0x2", wrong_anim_end)

// anim_frame drifts from the second row and the run ends late.
CUT_RED(the_clock_rate_at_one, "the MOVE0 clock's rate forced to 1.0 instead of field_0x4's 1.2",
        wrong_anim_rate)

// changeCutReverseProc is a stub (its body needs shield-hit flags and a LineCross), fixed false.
CUT_RED(the_sword_bounced, "changeCutReverseProc answered true - the stub whose default is false",
        cut_reverse_true)

}  // namespace
