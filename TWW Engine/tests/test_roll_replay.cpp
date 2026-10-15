// test_roll_replay.cpp - the ported procs against the console capture
// setup_finder_rollfree_live.json, bit for bit, with red controls for the comparator, expression,
// order, reading and pad-alignment slips.

#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "roll_replay.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::ReplayFrame;
using tww_engine::testing::ReplayResult;
using tww_engine::testing::RollReplayOptions;

const char* kGolden = "setup_finder_rollfree_live.json";

//: The seven anim columns the capture carries: setBlendMoveAnime's whole output.
struct AnimColumn {
    const char* name;
    uint32_t ReplayFrame::*float_field;
    int ReplayFrame::*int_field;
};

const AnimColumn kAnimColumns[] = {
    {"anim_frame", &ReplayFrame::anim_bits, nullptr},
    {"fc_rate", &ReplayFrame::rate_bits, nullptr},
    {"fc_end", nullptr, &ReplayFrame::end},
    {"move1_frame", &ReplayFrame::m1frame_bits, nullptr},
    {"move1_rate", &ReplayFrame::m1rate_bits, nullptr},
    {"move1_end", nullptr, &ReplayFrame::m1end},
    {"blend_move", &ReplayFrame::blend_bits, nullptr},
};

/// The columns comparable during the roll. A single anim leaves mAnmRatioUnder[UNDER_MOVE1_e] NULL,
/// so MOVE1 keeps the pre-roll walk's state, which the replay (starting at the roll) lacks; and
/// the partial commonProcInit does not write m3598, so blend_move would agree only by accident.
bool comparable_during_roll(const char* name) {
    return std::string(name) == "anim_frame" || std::string(name) == "fc_rate" ||
           std::string(name) == "fc_end";
}

/// The first frame in [from, to] with `blend_move` >= 1.0, where posMoveFromFootPos's
/// `m3598 < 1.0f` guard fails and the carry is dropped; -1 if none.
int first_standalone(const Json& g, int from, int to) {
    for (int i = from; i <= to; i++) {
        if (g[size_t(i)]["blend_move"].as_f32() >= 1.0f) {
            return i;
        }
    }
    return -1;
}

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

/// The port's frames against the capture's. On `perturb_frame` the expected mNormalSpeed is moved
/// one ULP, the comparator's own red control.
void compare(Case& c, const Json& g, const ReplayResult& res, int perturb_frame = -1) {
    int anim_unchecked = 0;
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    for (const ReplayFrame& row : res.rows) {
        const Json& want = g[size_t(row.frame)];
        // Credited to the capture's proc, not the port's, so a wrong dispatch earns no coverage.
        const int want_proc = int(want["proc"].as_int());
        int frame_bits = 1, frame_ints = 1;  // mNormalSpeed, and the proc column

        uint32_t want_nspeed = want["potential_speed"].as_f32_bits();
        if (row.frame == perturb_frame) {
            want_nspeed += 1;
        }
        REQUIRE_BITS_RAW(c, row.nspeed_bits, want_nspeed, at(row.frame, "mNormalSpeed"));
        REQUIRE_INT(c, row.proc, want["proc"].as_int(), at(row.frame, "proc"));

        for (const AnimColumn& col : kAnimColumns) {
            if (row.frame <= tww_engine::testing::kLastRollFrame && !comparable_during_roll(col.name)) {
                anim_unchecked++;
                continue;
            }
            if (col.float_field) {
                REQUIRE_BITS_RAW(c, row.*(col.float_field), want[col.name].as_f32_bits(),
                                 at(row.frame, col.name));
                frame_bits++;
            } else {
                REQUIRE_INT(c, row.*(col.int_field), want[col.name].as_int(),
                            at(row.frame, col.name));
                frame_ints++;
            }
        }
        tww_engine::testing::ledger_record(want_proc, tier, frame_bits, frame_ints);

        REQUIRE_TRUE(c, !row.crashed,
                     at(row.frame, "") + ": the port crashed the roll, the console did not");
        REQUIRE_TRUE(c, row.anm_meta_missing == 0,
                     at(row.frame, "") + ": an UNDER animation was loaded whose frameMax has "
                                         "never been measured - see generated/d/actor/anm_meta.inc");
    }

    // Sixteen roll frames, four columns each.
    REQUIRE_INT(c, anim_unchecked, 64, "anim columns deliberately left uncompared on the roll");
}

// ------------------------------------------------------------------------------- 0. the pad

TWWE_TEST(pad_is_translatable_on_every_row_this_gate_feeds,
          "a pad bit this harness cannot map would be being silently dropped or silently invented") {
    const Json& g = tww_engine::testing::golden(kGolden);

    // Every row the replay feeds, 43..118: frame i consumes pad row i - kPadLead, over
    // i = 44..119. Row 42 is the seed's, checked below.
    std::vector<std::string> bad = tww_engine::testing::untranslatable_presses(
        g, tww_engine::testing::kFirstFrame,
        tww_engine::testing::kLastFrame - tww_engine::testing::kPadLead);
    REQUIRE_INT(c, (long long)bad.size(), 0,
                "action-mode-gated presses in rows the replay feeds (frame:button)");
    for (const std::string& b : bad) {
        c.fail("untranslatable press at " + b);
    }

    // The seed row's A press is not translated: procFrontRoll_init is called for it by name.
    const long long seed_trig = g[size_t(tww_engine::testing::kSeedFrame)]["btn_trig"].as_int();
    REQUIRE_INT(c, seed_trig & 0x0100, 0x0100,
                "the A press this gate acts on by name sits in row 42's btn_trig");
}

// ---------------------------------------------------------------------------------- 1. replay

TWWE_TEST(roll_replay_is_bit_exact_against_the_console,
          "the ported procs no longer reproduce the console capture, bit for bit") {
    const Json& g = tww_engine::testing::golden(kGolden);
    ReplayResult res = tww_engine::testing::run_roll_replay(g, RollReplayOptions{});

    // The replay must reach the capture's end.
    REQUIRE_INT(c, res.stopped_on_proc, -1, "the replay stopped on a proc this port has no body for");
    REQUIRE_INT(c, (long long)res.rows.size(),
                tww_engine::testing::kLastFrame - tww_engine::testing::kFirstFrame + 1,
                "frames replayed");

    compare(c, g, res);

    // No stub graded UNREACHED called, and no READ-graded stub's precondition broken
    // (boundary/stubs.cpp).
    REQUIRE_INT(c, res.unreached_called, 0, "boundary stubs graded UNREACHED that were called");
    REQUIRE_INT(c, res.precondition_broken, 0, "boundary stubs called outside their proof's regime");

    // Reaching checkNextActionFromButton's tail return is the normal no-action path, so a
    // non-zero count shows the dispatch tree was walked.
    REQUIRE_TRUE(c, res.button_dispatch_fellthrough > 0,
                 "checkNextActionFromButton was never reached - nothing dispatched at all");

    // The procs this run held to the console.
    std::vector<int> procs;
    for (const ReplayFrame& row : res.rows) {
        if (procs.empty() || procs.back() != row.proc) {
            bool seen = false;
            for (int p : procs) {
                seen = seen || p == row.proc;
            }
            if (!seen) {
                procs.push_back(row.proc);
            }
        }
    }
    std::string list;
    for (int p : procs) {
        list += (list.empty() ? "" : ", ") + std::to_string(p);
    }
    // Subsystem rows are stated here, not inferred from the call graph, which cannot see which
    // paths go through stubs.
    const std::string frames = std::to_string(res.rows.size()) + " console frame(s), ";
    tww_engine::testing::ledger_record_subsystem(
        "player procs", tww_engine::testing::Tier::Console,
        frames + "proc and mNormalSpeed bit-exact on every one");
    // One credit per row (`a_subsystem_row_is_credited_by_one_case`), so the foot term's frames
    // are counted here.
    int foot_frames = 0;
    const int standalone = first_standalone(g, tww_engine::testing::kFirstFrame,
                                            tww_engine::testing::kLastFrame);
    for (const ReplayFrame& row : res.rows) {
        foot_frames += (standalone >= 0 && row.frame >= standalone) ? 1 : 0;
    }
    tww_engine::testing::ledger_record_subsystem(
        "animation", tww_engine::testing::Tier::Console,
        frames + "anim_frame, fc_rate and fc_end - J3DFrameCtrl's own outputs - bit-exact; and "
                 "m359C, the planted-toe delta out of the posed skeleton, on " +
            std::to_string(foot_frames) +
            " of them - which is the .bck keyframes, the blend table and the joint walk in one "
            "number (the_foot_term_is_bit_exact_against_the_console)");
    tww_engine::testing::ledger_record_subsystem(
        "cLib / c_math", tww_engine::testing::Tier::Console,
        frames + "cLib_addCalc's three arms, in mNormalSpeed's 5.0 -> 2.5 -> 0.7 -> 0.0 decay");

    c.note("procs held to the console over frames " + std::to_string(res.rows.front().frame) +
           ".." + std::to_string(res.rows.back().frame) + ": " + list +
           "  (FRONT_ROLL 30, MOVE 6, WAIT 4, CROUCH 14)");

    // Every proc gated must be one the finder's block catalog enters.
    for (int p : procs) {
        REQUIRE_TRUE(c, tww_engine::testing::port_list_has_proc(p),
                     "this run held proc " + std::to_string(p) +
                         " to the console, and the port list does not list it as a proc "
                         "the finder's block catalog enters. Either the port list is stale "
                         "(regenerate it) or this gate is measuring a proc the finder cannot "
                         "reach.");
    }
}

// --------------------------------------------------------------------------- 2. the foot term
//
// m359C against the capture's `foot_delta_prev`, which is m359C as posMoveFromFootPos last writes
// it (d_a_player_main.cpp:481). speedF cannot show the term: blend_move (m3598) is 0 on all but
// three frames, where the term contributes `f31_2 * 0.0`.
//
// The term carries `f31_2 = f31_2*0.3 + 0.7*m359C`, so a mid-run start's unposed seed decays but
// never dies. The smoothing runs only while `m3598 < 1.0f`; frames before the first blend_move of
// 1.0 are excluded with a count, and `the_foot_terms_residual_is_carried_state` shows the seed is
// the whole difference there.

/// m359C against `foot_delta_prev`, from the standalone frame to the end. Returns how many frames
/// were compared and writes how many were skipped into `skipped`.
int compare_foot(Case& c, const Json& g, const ReplayResult& res, int& skipped) {
    const int start = first_standalone(g, tww_engine::testing::kFirstFrame,
                                       tww_engine::testing::kLastFrame);
    REQUIRE_TRUE(c, start > 0,
                 "no frame of this capture reads blend_move >= 1.0, so the foot term's carry is "
                 "never discarded and a mid-run replay's seed error never leaves it");
    skipped = 0;
    int compared = 0;
    const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(kGolden);
    for (const ReplayFrame& row : res.rows) {
        if (start < 0 || row.frame < start) {
            // The seed's span: every excluded frame must be one the smoothing ran on.
            REQUIRE_TRUE(c, g[size_t(row.frame)]["blend_move"].as_f32() < 1.0f,
                         at(row.frame, "blend_move") +
                             " is excluded from the foot gate as still carrying the seed, and "
                             "the console says the smoothing was skipped on it");
            skipped++;
            continue;
        }
        REQUIRE_BITS_RAW(c, row.foot_delta_bits,
                         g[size_t(row.frame)]["foot_delta_prev"].as_f32_bits(),
                         at(row.frame, "m359C"));
        // m34BC has no column; the case below checks both feet are planted somewhere.
        REQUIRE_TRUE(c, row.plant == 0 || row.plant == 1,
                     at(row.frame, "m34BC") + ": the plant is neither foot, which is the "
                                              "rest-offset arm on a frame hundreds into a room");
        tww_engine::testing::ledger_record(int(g[size_t(row.frame)]["proc"].as_int()), tier, 1, 0);
        compared++;
    }
    return compared;
}

TWWE_TEST(the_foot_term_is_bit_exact_against_the_console,
          "m359C - posMoveFromFootPos's planted-toe delta, out of the posed skeleton - disagrees "
          "with the capture's own foot_delta_prev column") {
    const Json& g = tww_engine::testing::golden(kGolden);
    ReplayResult res = tww_engine::testing::run_roll_replay(g, RollReplayOptions{});
    REQUIRE_INT(c, res.stopped_on_proc, -1,
                "the replay stopped on a proc this port has no body for");

    int skipped = 0;
    const int compared = compare_foot(c, g, res, skipped);
    int right = 0, left = 0;
    for (const ReplayFrame& row : res.rows) {
        right += row.plant == 0 ? 1 : 0;
        left += row.plant == 1 ? 1 : 0;
    }

    c.note("m359C held to the console on " + std::to_string(compared) + " frame(s) of " +
           std::to_string(res.rows.size()) + "; " + std::to_string(skipped) +
           " excluded as still carrying the replay's own seed - see the header, and "
           "the_foot_terms_residual_is_carried_state for the measurement that says so");
    c.note("planted foot over the whole run, right/left: " + std::to_string(right) + "/" +
           std::to_string(left) + " - m34BC has no console column and is not compared");
    REQUIRE_TRUE(c, compared > 0, "the foot gate compared nothing at all");
    REQUIRE_TRUE(c, right > 0 && left > 0,
                 "both feet are planted somewhere in the run - a term that always chose the same "
                 "one would still smooth and would still look like a walk");
}

TWWE_TEST(the_foot_terms_residual_is_carried_state,
          "the frames this gate excludes have stopped being explained by the replay's own seed, "
          "which would mean the exclusion is hiding a real difference") {
    // Two seeds, held against each other rather than the console. A seed of 1.0 is over ten times
    // the excluded span's largest foot_delta_prev.
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions other;
    other.foot_seed = 1.0f;
    const ReplayResult a = tww_engine::testing::run_roll_replay(g, RollReplayOptions{});
    const ReplayResult b = tww_engine::testing::run_roll_replay(g, other);
    REQUIRE_INT(c, (long long)a.rows.size(), (long long)b.rows.size(), "both runs reached the end");

    const int start = first_standalone(g, tww_engine::testing::kFirstFrame,
                                       tww_engine::testing::kLastFrame);
    int differ_before = 0, differ_after = 0;
    for (size_t i = 0; i < a.rows.size() && i < b.rows.size(); i++) {
        const bool same = a.rows[i].foot_delta_bits == b.rows[i].foot_delta_bits;
        if (a.rows[i].frame < start) {
            differ_before += same ? 0 : 1;
        } else {
            REQUIRE_BITS_RAW(c, b.rows[i].foot_delta_bits, a.rows[i].foot_delta_bits,
                             at(a.rows[i].frame, "m359C under a different seed"));
            differ_after += same ? 0 : 1;
        }
    }
    c.note("frames the seed moves: " + std::to_string(differ_before) + " before frame " +
           std::to_string(start) + ", " + std::to_string(differ_after) + " from it on");
    REQUIRE_INT(c, differ_after, 0,
                "a seed more than ten times the span's own largest value changes nothing from the "
                "frame the console's blend_move discards the carry - so what the excluded frames "
                "carry is the seed and not an error the gate would otherwise be hiding");
    REQUIRE_TRUE(c, differ_before > 0,
                 "and it does move the excluded frames - if it moved nothing anywhere, this "
                 "control would be green for the reason that it ran two identical runs");
}

// ------------------------------------------------------------------------- the red controls

TWWE_RED_CONTROL(red_one_ulp_in_the_expected_value,
                 "the comparator: one ULP added to the console's own mNormalSpeed on frame 60") {
    const Json& g = tww_engine::testing::golden(kGolden);
    compare(c, g, tww_engine::testing::run_roll_replay(g, RollReplayOptions{}), 60);
}

TWWE_RED_CONTROL(red_pad_fed_one_frame_early,
                 "the harness: pad_lead 0. First separates at frame 75, where the R latch "
                 "drops.") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.pad_lead = 0;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}

TWWE_RED_CONTROL(red_proc_before_the_anim_clocks,
                 "an order slip: execute() advances the clocks at 11346 and dispatches at 11394") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.wrong_order = true;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}

TWWE_RED_CONTROL(red_anim_clock_in_double,
                 "an expression slip: mFrame += mRate carried in double instead of f32") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.wrong_anim = true;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}

TWWE_RED_CONTROL(red_addcalc_snaps_to_target,
                 "an expression slip: cLib_addCalc's minStep arm finishing the job instead of "
                 "stepping by minStep") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.wrong_decel = true;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}

TWWE_RED_CONTROL(red_move1_accumulated,
                 "an expression slip: MOVE1's frame accumulated rather than re-slaved to MOVE0's "
                 "phase - identical for three frames, 1 ULP out by the fourth") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.wrong_move1 = true;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}

TWWE_RED_CONTROL(red_blend_read_as_the_move1_ratio,
                 "a reading slip: blend_move taken from the MOVE1 blend ratio instead of m3598") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.wrong_blend = true;
    compare(c, g, tww_engine::testing::run_roll_replay(g, o));
}


TWWE_RED_CONTROL(red_the_skeleton_is_never_posed,
                 "execute()'s tail - setWorldMatrix at :11544 and the 42-joint pass at :11591 - "
                 "never run, so posMoveFromFootPos concatenates m37B4 onto the all-zero joint "
                 "matrices LinkModel is constructed with. Its answer is not zero and does not "
                 "look wrong: the concat zeroes the 3x3 and leaves m37B4's own translation "
                 "column, so all four foot positions become that column and m359C becomes the "
                 "distance Link's origin moved - which on a walk is a plausible number of the "
                 "right magnitude") {
    const Json& g = tww_engine::testing::golden(kGolden);
    RollReplayOptions o;
    o.no_pose = true;
    int skipped = 0;
    compare_foot(c, g, tww_engine::testing::run_roll_replay(g, o), skipped);
}

TWWE_RED_CONTROL(red_the_foot_gate_is_run_over_the_seeded_span_too,
                 "the excluded frames compared anyway. It is the exclusion's own control: if "
                 "these frames passed, the span would not need excluding and the header's "
                 "account of the carry would be wrong. What it must not be is a way of saying "
                 "the port is wrong there - the seed control above is what settles that, and it "
                 "says the whole difference is the seed") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const ReplayResult res = tww_engine::testing::run_roll_replay(g, RollReplayOptions{});
    for (const ReplayFrame& row : res.rows) {
        REQUIRE_BITS_RAW(c, row.foot_delta_bits,
                         g[size_t(row.frame)]["foot_delta_prev"].as_f32_bits(),
                         at(row.frame, "m359C"));
    }
}

}  // namespace
