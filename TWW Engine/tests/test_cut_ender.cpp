// test_cut_ender.cpp - procCutEA and procCutEB against the old sim, with red controls.
//
// changeCutProc hands the fourth cut of a chain (m34C4) to an ender: forward or right stick is
// procCutEA; left, back and neutral are procCutEB. Unlike the basic cuts, the enders have:
//   * no `getFrame() > field_0xC` arm, so R and a held stick do nothing;
//   * no aim: changeCutProc drops its sVar2 on this arm (d_a_player_sword.inc:425), so
//     shape_angle.y cannot move;
//   * a post-anim hold (`m34D0 = field_0x2`) before checkNextMode(0); 0 on both shipped rows;
//   * daPy_HIO_cutEA_c1 (0x30): field_0x0 is the anim end (19), field_0x2 the hold.
// The movement is the basic cuts': checkPass at field_0x24 launches `|speedF| * field_0xC +
// field_0x10`, then cLib_addCalc decays it.
//
// The goldens are sim-tier: no setup-finder capture has a row in proc 0x45 or 0x46.
//
// Not claimed:
//   * `fc_rate` and `fc_end` have no oracle column; they are held to each HIO row.
//   * field_0xC is unreachable: the entry speedF is 0 on every chain path (asserted below).
//   * the hold's `> 0` arm is never taken; only that the init read field_0x2 is asserted.
//   * procCutEB's unconditional setShapeAngleToAtnActor / `current.angle.y = shape_angle.y`
//     reach no column, since the chain already leaves travel == facing. The old sim's
//     `_proc_cut_ender` has no travel write at all; the difference is unobservable here.
//   * setFinishCutAtParam is a STUB (no attack collision); only the cut type is asserted.
//   * `no_r_hold` and `wrong_init_aim` are not registered: neither can bite (section 5).
//   * the BOKO arm of checkNextActionFromButton's second call site.
//   * the frames before each entry; each scenario is seeded at its entry row.

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

enum : int { kEnderScenarios = 5 };

//: The two enders. Every green case below walks both.
const CutKind kEnders[] = {CutKind::EA, CutKind::EB};

//: The basic cuts, so the init case can require an ender's resources are none of theirs.
const CutKind kBasics[] = {CutKind::L, CutKind::F, CutKind::R};

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

/// The port's frames against the oracle's, over one ender's five scenarios.
/// `perturb` moves the expected anim_frame by one ULP on each scenario's first row (4.0 there,
/// so the ULP is not a denormal).
void compare(Case& c, CutKind kind, const std::vector<CutOracleRun>& runs, bool perturb = false) {
    const CutSpec& spec = cut_spec(kind);
    const Json& g = golden_of(kind);
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(spec.golden);
    const Json& scenarios = g["scenarios"];
    int compared = 0;
    int bad = 0;
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

            tww_engine::testing::ledger_record(want_proc, tier, 2, 3);
            compared++;
        }

        // The exit: WAIT on three scenarios, CUT_TURN_CHARGE on the two with B down at the end.
        const int want_exit = int(rows[size_t(run.exit)]["proc"].as_int());
        REQUIRE_INT(c, run.exit_proc, want_exit,
                    at(run, run.exit, "the proc the port left the ender for"));
        watch(run.exit_proc == want_exit,
              at(run, run.exit, "the proc the port left the ender for"));
    }
    c.note(std::string(spec.fn) + ": compared " + std::to_string(compared) + " frame(s) over " +
           std::to_string(runs.size()) + " scenario(s)");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

// ------------------------------------------------------------- 0. what the oracle is

TWWE_TEST(the_ender_oracles_are_the_old_sim_and_the_suite_says_so,
          "a regression-tier golden would be being counted as console evidence") {
    // The tier comes from the manifest row, and no console frame of either ender exists in the
    // sword capture.
    const Json& sword = tww_engine::testing::golden("setup_finder_sword_live.json");
    for (CutKind kind : kEnders) {
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
                    std::string(spec.fn) + ": the golden is the one for this proc - the two files "
                                           "read alike and are keyed only by this field");

        int in_proc = 0;
        for (size_t f = 0; f < sword.size(); f++) {
            if (sword[f]["proc"].as_int() == spec.proc_id) {
                in_proc++;
            }
        }
        REQUIRE_INT(c, in_proc, 0,
                    std::string(spec.fn) +
                        ": rows of the 849-frame sword capture in this proc - if this stops "
                        "being 0, it has a console gate available and the old sim should stop "
                        "being its only one");
    }
    c.note("the sword capture holds " + std::to_string(sword.size()) +
           " rows and 0 of them are CUT_EA or CUT_EB; the oracle for both is " +
           golden_of(CutKind::EA)["_oracle"]["repo"].str + " @ " +
           golden_of(CutKind::EA)["_oracle"]["head"].str);
}

TWWE_TEST(the_old_sims_two_engines_are_recorded_where_they_part,
          "an oracle gap would be sitting in a file nobody reads it out of") {
    // The producer records where the old sim's Python and native engines disagree outside the
    // compared frames (`_two_engine_gap`). The gap is speedF on the first MOVE frame after a cut
    // left with the stick held, not the ender's. This keeps it from moving into the window.
    int gaps = 0;
    for (CutKind kind : kEnders) {
        const Json& g = golden_of(kind);
        const Json& scenarios = g["scenarios"];
        for (size_t s = 0; s < scenarios.size(); s++) {
            const Json& sc = scenarios[s];
            if (!sc.has("_two_engine_gap")) {
                continue;
            }
            const Json& gap = sc["_two_engine_gap"];
            gaps++;
            const int f = int(gap["frame"].as_int());
            REQUIRE_TRUE(c, f > int(sc["exit"].as_int()),
                         std::string(cut_spec(kind).fn) + " " + sc["name"].str +
                             ": the old sim's two engines part after the frames this golden "
                             "asserts, so no compared column rests on the disagreement");
            REQUIRE_INT(c, int(gap["proc"].as_int()), daPy_lk_c::daPyProc_MOVE_e,
                        std::string(cut_spec(kind).fn) + " " + sc["name"].str +
                            ": ...and it is in procMove, not in the ender");
            c.note(std::string(cut_spec(kind).fn) + " " + sc["name"].str + ": old-sim two-engine "
                   "gap at frame " + std::to_string(f) + ", after the exit at " +
                   std::to_string(int(sc["exit"].as_int())) + ", column " +
                   gap["columns"][size_t(0)].str);
        }
    }
    REQUIRE_INT(c, gaps, 2,
                "scenarios whose two old-sim engines part at all - if this drops to 0 the old "
                "sim has been changed, and it is frozen; if it rises, a new one appeared");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(the_two_combo_enders_are_bit_exact_against_the_old_sim,
          "a ported combo ender no longer reproduces the old sim's answer, bit for bit") {
    int total = 0;
    for (CutKind kind : kEnders) {
        const CutSpec& spec = cut_spec(kind);
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});

        REQUIRE_INT(c, (long long)runs.size(), kEnderScenarios,
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
            REQUIRE_INT(c, run.rnd_draws_compared, 0,
                        "RNG draws over the compared frames of " + run.cut + " " + run.name);
            REQUIRE_INT(c, run.rnd_draws, run.exit_proc == daPy_lk_c::daPyProc_WAIT_e ? 1 : 0,
                        "RNG draws including the exit of " + run.cut + " " + run.name);
        }
        REQUIRE_TRUE(c, frames > 0, std::string(spec.fn) + ": frames were replayed at all");
        total += frames;

        compare(c, kind, runs);

        // Two different exit procs, counted per ender.
        int to_wait = 0, to_charge = 0;
        for (const CutOracleRun& run : runs) {
            to_wait += run.exit_proc == daPy_lk_c::daPyProc_WAIT_e;
            to_charge += run.exit_proc == daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e;
        }
        REQUIRE_INT(c, to_wait, 3,
                    std::string(spec.fn) + ": scenarios that rest at the end of the ender");
        REQUIRE_INT(c, to_charge, 2,
                    std::string(spec.fn) +
                        ": scenarios that leave into the spin's wind-up - B held through the "
                        "proc, and B pressed on the one frame the exit reads");
        for (const CutOracleRun& run : runs) {
            c.note(run.cut + " " + run.name + ": " + run.covers);
        }
    }
    c.note("total compared frames over the two enders: " + std::to_string(total));
}

// --------------------------------------------- 2. the two negatives, asserted as an equality

TWWE_TEST(R_and_the_stick_reach_no_column_of_an_ender,
          "the two inputs that end a basic cut early would be reaching this one unnoticed") {
    // A basic cut's `getFrame() > field_0xC` arm runs checkNextMode(1) on R or a held stick; the
    // enders have no such arm and no aim. `r_held` and `stick_held` must match `standstill`'s
    // output frame for frame while their input column differs on at least one frame.
    for (CutKind kind : kEnders) {
        const CutSpec& spec = cut_spec(kind);
        const Json& scenarios = golden_of(kind)["scenarios"];
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});

        REQUIRE_TRUE(c, runs.size() == 5 && runs[0].name == "standstill" &&
                            runs[3].name == "r_held" && runs[4].name == "stick_held",
                     std::string(spec.fn) +
                         ": the scenario order this case indexes by - standstill, b_held, "
                         "b_at_the_exit, r_held, stick_held");

        const CutOracleRun& base = runs[0];
        const struct { size_t idx; const char* input; } kNegatives[] = {
            {3, "btn_r"}, {4, "msd_hex"},
        };
        for (const auto& neg : kNegatives) {
            const CutOracleRun& run = runs[neg.idx];
            REQUIRE_INT(c, (long long)run.rows.size(), (long long)base.rows.size(),
                        std::string(spec.fn) + " " + run.name +
                            ": the run is the same length as standstill's - on a basic cut this "
                            "input is what makes it shorter");
            for (size_t k = 0; k < run.rows.size() && k < base.rows.size(); k++) {
                const CutOracleFrame& a = base.rows[k];
                const CutOracleFrame& b = run.rows[k];
                REQUIRE_BITS_RAW(c, b.nspeed_bits, a.nspeed_bits,
                                 at(run, b.frame, "mNormalSpeed against standstill's"));
                REQUIRE_BITS_RAW(c, b.anim_bits, a.anim_bits,
                                 at(run, b.frame, "anim_frame against standstill's"));
                REQUIRE_INT(c, b.proc, a.proc, at(run, b.frame, "proc against standstill's"));
                REQUIRE_INT(c, b.shape_angle_y, a.shape_angle_y,
                            at(run, b.frame, "shape_angle_y against standstill's"));
                REQUIRE_INT(c, b.travel_angle, a.travel_angle,
                            at(run, b.frame, "travel_angle against standstill's"));
            }
            REQUIRE_INT(c, run.exit_proc, base.exit_proc,
                        std::string(spec.fn) + " " + run.name +
                            ": ...and it leaves for the same proc standstill does");

            // The input really did change, read off the golden over the frames the replay consumed.
            int differing = 0;
            const Json& mine = scenarios[neg.idx]["frames"];
            const Json& theirs = scenarios[0]["frames"];
            for (int f = base.entry; f <= base.exit; f++) {
                if (mine[size_t(f)][neg.input].str != theirs[size_t(f)][neg.input].str ||
                    mine[size_t(f)][neg.input].as_int() != theirs[size_t(f)][neg.input].as_int()) {
                    differing++;
                }
            }
            REQUIRE_TRUE(c, differing > 0,
                         std::string(spec.fn) + " " + run.name + ": frames on which " +
                             neg.input + " differs from standstill's - if this is 0 the "
                             "scenario is a duplicate and the equality above claims nothing");
            c.note(std::string(spec.fn) + " " + run.name + ": " + std::to_string(differing) +
                   " frame(s) of " + neg.input + " changed, 0 columns moved");
        }
    }
}

// ------------------------------------------------------- 3. the init, through what it recorded

TWWE_TEST(each_enders_init_asks_for_its_own_resources,
          "an init would be indexing another cut's tables and nothing compared would move") {
    // These values are arguments to boundary calls, so they are asserted as recorded, and required
    // to differ from the other ender's and all three basic cuts' so a swap would be noticed.
    for (CutKind kind : kEnders) {
        const CutSpec& spec = cut_spec(kind);
        for (const CutOracleRun& run : replay(kind, CutOracleOptions{})) {
            REQUIRE_INT(c, run.sword_anim_idx, spec.sword_anm,
                        run.cut + " " + run.name +
                            ": the sword .bck checkNormalSwordEquip's true arm asked for");
            // Both ender inits call setBlurPosResource; procCutF_init does not.
            REQUIRE_INT(c, run.blur_pos_idx, spec.blur_pos,
                        run.cut + " " + run.name +
                            ": the blur-trail buffer setBlurPosResource loaded");
            REQUIRE_TRUE(c, run.blur_pos_idx != -1,
                         run.cut + " " + run.name +
                             ": ...and it was called at all, which procCutF_init does not do");
            REQUIRE_INT(c, run.cut_at_param_type, spec.cut_type,
                        run.cut + " " + run.name +
                            ": the cut type setFinishCutAtParam was handed - a different "
                            "function from the basic cuts' setNormalCutAtParam, sharing this "
                            "recorder because the two are mutually exclusive and these two type "
                            "values are only ever passed to the finish one");
            REQUIRE_INT(c, (long long)run.player_status0, (long long)daPyStts0_SWORD_SWING_e,
                        run.cut + " " + run.name + ": the player-status bit the init raised");
            // The cut-sound window (5..11): seStartSwordCut is a stub that records its cue.
            REQUIRE_INT(c, run.sword_cut_se, JA_SE_LK_SW_KAZEKIRI_S,
                        run.cut + " " + run.name +
                            ": the wind-cut cue, which says field_0x28..field_0x2C was entered");

            const CutSpec& other = cut_spec(kind == CutKind::EA ? CutKind::EB : CutKind::EA);
            REQUIRE_TRUE(c, run.sword_anim_idx != other.sword_anm,
                         run.cut + ": ...and the sword .bck is not " + other.fn + "'s");
            REQUIRE_TRUE(c, run.blur_pos_idx != other.blur_pos,
                         run.cut + ": ...nor the blur buffer");
            REQUIRE_TRUE(c, run.cut_at_param_type != other.cut_type,
                         run.cut + ": ...nor the cut type");
            for (CutKind basic : kBasics) {
                const CutSpec& b = cut_spec(basic);
                REQUIRE_TRUE(c, run.sword_anim_idx != b.sword_anm,
                             run.cut + ": ...nor " + b.fn + "'s .bck");
                REQUIRE_TRUE(c, run.cut_at_param_type != b.cut_type,
                             run.cut + ": ...nor " + b.fn + "'s cut type");
            }
            REQUIRE_TRUE(c, run.sword_anim_idx != dRes_INDEX_LKANM_BCK_CUTAA_e,
                         run.cut + ": ...nor the slash's CUTAA");
            REQUIRE_TRUE(c, run.cut_at_param_type != daPy_lk_c::CUT_TYPE_CUT_A,
                         run.cut + ": ...nor the slash's cut type");
        }
    }
    c.note("CUTEAA/_CUTEA_POS/CUT_TYPE_CUT_EA and CUTEBA/_CUTEB_POS/CUT_TYPE_CUT_EB - on all "
           "five scenarios of each, and neither is any of the other four cuts'");
}

TWWE_TEST(the_clock_each_ender_init_seeds_is_that_rows_own_and_its_own_bck,
          "each run's length rests on three numbers no oracle column here can see") {
    // `fc_rate` and `fc_end` have no golden column, so they are held to each HIO row; the anim red
    // controls make this bite. The end is field_0x0 on an ender (field_0x2 is the hold, 0).
    // The attribute comes from anm_meta.inc, checked against the golden's `_anm` header parse of
    // the same .bck.
    for (CutKind kind : kEnders) {
        const CutSpec& spec = cut_spec(kind);
        const Json& g = golden_of(kind);
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});
        const f32 rate = kind == CutKind::EA ? 1.0f : 0.9f;

        REQUIRE_INT(c, g["_anm"]["attribute"].as_int(), J3DFrameCtrl::EMode_NONE,
                    std::string(spec.fn) +
                        ": the .bck's own attribute, as parse_bck read it off the shipped "
                        "animation");
        int missing = 0;
        for (const CutOracleRun& run : runs) {
            REQUIRE_INT(c, run.anim_attribute, g["_anm"]["attribute"].as_int(),
                        run.cut + " " + run.name +
                            ": the MOVE0 controller's attribute against the .bck's own");
            REQUIRE_INT(c, run.anim_start, 4, run.cut + " " + run.name + ": start, field_0x8");
            REQUIRE_INT(c, run.anim_end, spec.anim_end,
                        run.cut + " " + run.name +
                            ": end, field_0x0 - not field_0x2, which on this row is the hold");
            REQUIRE_TRUE(c, run.anim_end != spec.wrong_end,
                         run.cut + " " + run.name +
                             ": ...and it is not the row the red control substitutes, which is "
                             "another shipped cut's own end");
            REQUIRE_BITS_RAW(c, run.rows[0].rate_bits, tww_engine::testing::bits(rate),
                             run.cut + " " + run.name + ": rate, field_0x4");
            REQUIRE_TRUE(c, run.rows[0].rate_bits != tww_engine::testing::bits(spec.wrong_rate),
                         run.cut + " " + run.name +
                             ": ...and it is not the other ender's rate, which is what the red "
                             "control substitutes - a control fixed at 1.0 would have been inert "
                             "on procCutEA, whose own rate is 1.0");
            REQUIRE_TRUE(c, run.rows.back().rate_bits == tww_engine::testing::bits(rate),
                         run.cut + " " + run.name +
                             ": the rate is still live on the last compared row");
            // Both shipped holds are 0; the boundary seeds -1, so this shows the init read
            // field_0x2.
            REQUIRE_INT(c, run.hold_after_init, spec.hold,
                        run.cut + " " + run.name +
                            ": mProcVar0.m34D0 as the init left it - field_0x2, the post-anim "
                            "hold, which is 0 on both shipped rows and therefore never felt");
            missing += run.anm_meta_missing;
        }
        REQUIRE_INT(c, missing, 0,
                    std::string(spec.fn) +
                        ": its anim has an anm_meta.inc row, so the boundary must not be "
                        "counting it - a non-zero here is the table going stale");
        c.note(std::string(spec.fn) + ": end " + std::to_string(spec.anim_end) +
               " (field_0x0), hold " + std::to_string(spec.hold) +
               " (field_0x2), anm_meta_missing = " + std::to_string(missing));
    }
}

// ------------------------------------------- 4. what the enders do not have, asserted as zeros

TWWE_TEST(an_ender_writes_no_chain_code_and_launches_off_a_speedF_that_is_always_zero,
          "two fields would read as verified when one is unreachable and one is not written") {
    // m34C5: neither ender body has the `swordTrigger() && m34C5 != 5` line, so it keeps
    // commonProcInit's 0.
    // Entry speedF is 0 on every chain path: a basic cut's cLib_addCalc drives mNormalSpeed to 0
    // before the chain window opens (0 over 5,778 of 23,958 chain schedules that reached an
    // ender). So field_0x10 is the whole launch and field_0xC is unexercised.
    for (CutKind kind : kEnders) {
        const CutSpec& spec = cut_spec(kind);
        const Json& scenarios = golden_of(kind)["scenarios"];
        std::vector<CutOracleRun> runs = replay(kind, CutOracleOptions{});
        for (size_t s = 0; s < runs.size(); s++) {
            const CutOracleRun& run = runs[s];
            REQUIRE_INT(c, run.m34C5, spec.m34C5_decomp,
                        run.cut + " " + run.name +
                            ": m34C5 - neither ender body writes it, so it keeps "
                            "commonProcInit's 0");
            // The row before the entry is the speedF the entry's checkPass reads.
            const Json& before = scenarios[s]["frames"][size_t(run.entry - 1)];
            REQUIRE_TRUE(c, hex_bits(before["speedF_hex"]) == 0u,
                         run.cut + " " + run.name +
                             ": the speedF the ender was entered carrying - 0 on every path the "
                             "chain can take, which is why field_0xC is ungated");
        }
        c.note(std::string(spec.fn) + ": m34C5 = 0 (no line writes it), entry speedF = 0 on all "
               "five scenarios, so the launch is field_0x10 alone");
    }
}

// ------------------------------------------------------------------------- 5. the red controls
// Every control is registered once per ender, so none is inert for one while counted for both.
// `wrong_init_aim` (no aim) and `no_r_hold` (R reaches no column) cannot bite, so they are not
// registered. `b_at_the_exit` exists so `wrong_pad_lead` bites: a B press on the exit frame only.

void red(Case& c, CutKind kind, bool CutOracleOptions::*flag) {
    CutOracleOptions opt;
    opt.*flag = true;
    compare(c, kind, replay(kind, opt));
}

#define ENDER_RED(ident, what, field)                                                          \
    TWWE_RED_CONTROL(red_cut_ea_##ident, what) {                                               \
        red(c, CutKind::EA, &CutOracleOptions::field);                                         \
    }                                                                                          \
    TWWE_RED_CONTROL(red_cut_eb_##ident, what) {                                               \
        red(c, CutKind::EB, &CutOracleOptions::field);                                         \
    }

// The comparator's own control.
TWWE_RED_CONTROL(red_cut_ea_the_comparators_own_ulp,
                 "one ULP added to the expected anim_frame on one row of each CUT_EA scenario") {
    compare(c, CutKind::EA, replay(CutKind::EA, CutOracleOptions{}), true);
}
TWWE_RED_CONTROL(red_cut_eb_the_comparators_own_ulp,
                 "one ULP added to the expected anim_frame on one row of each CUT_EB scenario") {
    compare(c, CutKind::EB, replay(CutKind::EB, CutOracleOptions{}), true);
}

// posMove writes speedF after the dispatch, so frame N reads N-1's. Bites on the checkPass
// frame, the only one that reads speedF.
ENDER_RED(speedf_from_the_current_row,
          "speedF fed from the current row instead of the one posMove wrote it on",
          wrong_speedf_lead)

// PAD_LEAD is 1 against a console capture and 0 against this oracle.
ENDER_RED(the_pad_read_one_frame_late,
          "the stick and buttons taken from the previous row - the console replays' lead",
          wrong_pad_lead)

// The B hold (daPyFlg0_UNK4) shows only in `b_held`'s exit: WAIT instead of CUT_TURN_CHARGE.
ENDER_RED(the_b_hold_dropped,
          "mItemButton's BTN_B never set - swordButton() false on every frame", no_b_hold)

// mEquipItem as a driven input: B is pressed but the sword arm is not entered.
ENDER_RED(no_sword_equipped,
          "mEquipItem left at daPyItem_NONE_e, which shuts the whole sword arm", no_sword_equipped)

// The anim-before-proc order; every anim_frame and the launch move.
ENDER_RED(the_proc_run_before_the_anim_clock,
          "the order: every clock read takes the previous frame's value", proc_before_anim)

// The end forced to CUT_L's field_0x2 (18) against the enders' field_0x0 (19).
ENDER_RED(the_clock_ended_at_another_cuts_own_end,
          "the MOVE0 clock's end forced to another shipped cut's own end", wrong_anim_end)

// The other ender's rate, since 1.0 is procCutEA's own.
ENDER_RED(the_clock_rate_at_the_other_enders,
          "the MOVE0 clock's rate forced to the other ender's field_0x4", wrong_anim_rate)

// changeCutReverseProc needs shield-hit flags and a LineCross this slice lacks, so it is FALSE.
ENDER_RED(the_sword_bounced,
          "changeCutReverseProc answered true - the stub whose default is false", cut_reverse_true)

}  // namespace
