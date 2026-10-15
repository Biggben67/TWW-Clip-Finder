// test_wall_walk.cpp - the editable copy of the wall pass (`wall_walk.h`): the gate that holds it
// to the ported pass, its controls, and what it measures - whether any probe reaches
// cM2d_CrossCirLin's unassigned-`t` arms, and the full chain of corrections (`cir_poly` keeps
// only the last). Probes cover all four rooms, from `wall_probes.h`.

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/runner.h"

#include "engine/room.h"
#include "room_dzb.h"
#include "wall_probes.h"
#include "wall_walk.h"

namespace {

using tww_engine::kMaxWallCyl;
using tww_engine::Room;
using tww_engine::RoomDzb;
using tww_engine::testing::bits;
using tww_engine::testing::kWallH;
using tww_engine::testing::kWallR;
using tww_engine::testing::kWallSpeedY;
using tww_engine::testing::read_room_dzb;
using tww_engine::testing::WallProbe;
using tww_engine::testing::wall_probe_set;
using tww_engine::testing::WallStep;
using tww_engine::testing::WallVariant;
using tww_engine::testing::WallWalk;

//: The four rooms probed.
const char* kRooms[] = {"kaze_r11_bgd.json", "ganona_r0_bgd.json", "sea_r41_bgd.json",
                        "kaisen_r0_bgd.json"};
const char* kLabels[] = {"kaze r11", "GanonA r0", "sea r41", "Kaisen r0"};
const int kRoomCount = 4;

/// One loaded room and its probe set, built once.
struct Loaded {
    RoomDzb dzb;
    Room* room;
    std::vector<WallProbe> probes;
    int extra_flat;
};

Loaded& loaded(int i) {
    static Loaded slots[kRoomCount];
    static bool built[kRoomCount] = {false, false, false, false};
    if (!built[i]) {
        slots[i].dzb = read_room_dzb(tww_engine::testing::golden(kRooms[i]));
        slots[i].room = new Room(slots[i].dzb);
        slots[i].probes = wall_probe_set(*slots[i].room, slots[i].dzb, &slots[i].extra_flat);
        built[i] = true;
    }
    return slots[i];
}

void link_cylinders(Room::WallCyl* cyls) {
    for (int i = 0; i < 3; i++) {
        cyls[i].h = kWallH[i];
        cyls[i].r = kWallR;
    }
}

/// Bit-for-bit over the position, the acch hit flag, and per-cylinder hit, polygon and angle.
bool same_answer(const cXyz& pa, const Room::WallResult& ra, const cXyz& pb,
                 const Room::WallResult& rb) {
    if (bits(pa.x) != bits(pb.x) || bits(pa.z) != bits(pb.z)) {
        return false;
    }
    if (ra.wall_hit != rb.wall_hit) {
        return false;
    }
    for (int i = 0; i < 3; i++) {
        if (ra.cir_hit[i] != rb.cir_hit[i] || ra.cir_poly[i] != rb.cir_poly[i] ||
            ra.cir_angle[i] != rb.cir_angle[i]) {
            return false;
        }
    }
    return true;
}

/// Does the ported pass have a defined answer here? Not where cM3d_Len2dSqPntAndSegLine's
/// degenerate arm fires and RwgWallCorrect reads the two locals it left unassigned.
/// Asked through `SegAssignsStart`, since an unmutated walk would read its own stack there; the
/// first degenerate read precedes any divergence, so the answer is the port's either way.
bool answer_is_defined(WallWalk& probe_walk, const WallProbe& p, const Room::WallCyl* cyls) {
    cXyz q = p.pos;
    Room::WallResult r;
    probe_walk.run(&q, p.pos, kWallSpeedY, cyls, 3, &r);
    return probe_walk.degenerate_reads() == 0;
}

/// How many of a room's probes with a defined answer the variant answers differently from the
/// ported pass.
int differs_from_port(Loaded& L, WallVariant var, long long* broke = nullptr,
                      int* compared = nullptr) {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    WallWalk defined(*L.room, WallVariant::SegAssignsStart);
    WallWalk w(*L.room, var);
    int bad = 0;
    for (const WallProbe& p : L.probes) {
        if (!answer_is_defined(defined, p, cyls)) {
            continue;
        }
        if (compared != nullptr) {
            (*compared)++;
        }
        cXyz a = p.pos;
        Room::WallResult ra;
        L.room->WallCorrect(&a, p.pos, kWallSpeedY, cyls, 3, &ra);
        cXyz b = p.pos;
        Room::WallResult rb;
        w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
        if (!same_answer(a, ra, b, rb)) {
            bad++;
        }
    }
    if (broke != nullptr) {
        *broke += w.broken_asserts();
    }
    return bad;
}

int total_probes() {
    int n = 0;
    for (int i = 0; i < kRoomCount; i++) {
        n += (int)loaded(i).probes.size();
    }
    return n;
}

}  // namespace

// ===============================================================================================
// The gate
// ===============================================================================================

TWWE_TEST(the_wall_variant_harness_is_the_ported_walk,
          "the editable copy of the wall pass answers exactly what dBgW's copied bodies answer - "
          "position, hit flag and all three cylinders' polygon and angle - at every probe in all "
          "four rooms. Without this, every count below is evidence about this file rather than "
          "about the port, and so is the trace the leads are read off") {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);

    int checked = 0, differs = 0, corrected = 0, flat = 0, undefined = 0;
    std::string first_bad;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk defined(*L.room, WallVariant::SegAssignsStart);
        WallWalk w(*L.room, WallVariant::None);
        flat += L.extra_flat;
        for (const WallProbe& p : L.probes) {
            // Set aside and counted: no defined answer on either side. Covered by the known gap
            // `the_wall_pass_reads_two_uninitialised_locals_at_a_degenerate_water_line`.
            if (!answer_is_defined(defined, p, cyls)) {
                undefined++;
                continue;
            }
            cXyz a = p.pos;
            Room::WallResult ra;
            L.room->WallCorrect(&a, p.pos, kWallSpeedY, cyls, 3, &ra);
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
            checked++;
            if (ra.wall_hit) {
                corrected++;
            }
            if (!same_answer(a, ra, b, rb)) {
                differs++;
                if (first_bad.empty()) {
                    char buf[256];
                    std::snprintf(buf, sizeof(buf),
                                  " - first at %s %s of poly %d (%.9g, %.9g, %.9g)", kLabels[i],
                                  p.cls, p.of_poly, (double)p.pos.x, (double)p.pos.y,
                                  (double)p.pos.z);
                    first_bad = buf;
                }
            }
        }
    }
    REQUIRE_INT(c, (long long)differs, 0,
                "probes where the variant harness and the ported walk disagree" + first_bad);
    // The population: something compared, and something corrected.
    REQUIRE_TRUE(c, checked > 0, "the harness was never compared against anything");
    REQUIRE_TRUE(c, corrected > 0,
                 "no probe in any of the four rooms was corrected at all, so the agreement above "
                 "is agreement about a pass that never ran");
    c.note(std::to_string(checked) + " probe(s) over " + std::to_string(kRoomCount) +
           " room(s), " + std::to_string(corrected) +
           " of them corrected by the pass; every column bit for bit. " +
           std::to_string(undefined) +
           " more set aside because the pass reads an unassigned local there and neither side "
           "has a defined answer");
    c.note(std::to_string(flat) +
           " candidate polygon(s) here that the old sim's differential drops - |n_xz| between "
           "G_CM3D_F_ABS_MIN and its own 1.0e-3 cut. This set takes RwgWallCorrect's own guard, "
           "so it is a superset of the differential's, and that band is exactly the population "
           "cM2d_CrossCirLin's unassigned arm needs");
}

// ===============================================================================================
// The controls
// ===============================================================================================

TWWE_TEST(every_control_knob_of_the_wall_walk_changes_an_answer,
          "each knob the harness carries as a control, measured: how many of the four rooms' "
          "probes it moves off the ported answer. A knob with two values that agree everywhere "
          "the gate looks is not a control, and the gate above would be green with it stuck "
          "either way") {
    struct Knob {
        WallVariant var;
        const char* what;
    };
    static const Knob kKnobs[] = {
        {WallVariant::NoRebuild,
         "CalcMovePosWork dropped, so the circle and the octree's cylinder do not follow him"},
        {WallVariant::WallChainOnly, "the leaf's roof chain not walked (d_bg_w.cpp:272)"},
        {WallVariant::RoofFirst, "the roof chain walked before the wall chain"},
        {WallVariant::ChildrenReversed, "the octree's eight children visited 7..0"},
        {WallVariant::NearEndOnly, "the corner arm always taking the first endpoint"},
    };
    for (const Knob& k : kKnobs) {
        int bad = 0, n = 0;
        long long broke = 0;
        std::string split;
        for (int i = 0; i < kRoomCount; i++) {
            const int m = differs_from_port(loaded(i), k.var, &broke, &n);
            bad += m;
            split += std::string(split.empty() ? "" : ", ") + kLabels[i] + " " + std::to_string(m);
        }
        REQUIRE_TRUE(c, bad > 0,
                     std::string("nothing in four rooms notices when ") + k.what +
                         " - so that knob is not a control and the gate would not catch it");
        c.note(std::string(k.what) + ": " + std::to_string(bad) + " of the " +
               std::to_string(n) + " probe(s) with a defined answer on both sides answered "
               "differently (" + split + ")" +
               (broke ? ", and it broke a JUT_ASSERT the decomp makes " + std::to_string(broke) +
                            " time(s) - the game says that argument cannot be handed to "
                            "cM2d_CrossCirLin, so those probes are outside what any engine answers"
                      : ""));
    }
    // Unlike the ground and roof walks (a running extremum), the wall pass moves Link on every
    // acceptance, so visit order is part of the answer.
    int order = 0;
    for (int i = 0; i < kRoomCount; i++) {
        order += differs_from_port(loaded(i), WallVariant::ChildrenReversed);
    }
    REQUIRE_TRUE(c, order > 0,
                 "reversing the octree's child order changes no answer in four rooms - which "
                 "would mean the wall pass is order-independent after all, and the whole reason "
                 "its visit list has to be the port's own would be gone");
}

// ===============================================================================================
// The old sim's spellings - candidate causes of a disagreement, not controls
// ===============================================================================================
//
// The old sim's wall pass differs from the decomp in named places; running the port with each
// spelling attributes a disagreement to it.

TWWE_TEST(the_old_sims_spellings_against_the_ports,
          "the three places the old sim spells this pass differently from the decomp, each put "
          "into the port's own walk over all four rooms. Two are the other wall pass's and so "
          "are upper bounds; the third is the differential oracle's own, and that one is an "
          "attribution a run can make") {
    int n = 0;

    // The IsZero threshold: 1.0e-5 there against 2^-18 here, on every cM3d_IsZero in the pass.
    int thr = 0;
    std::string thr_split;
    for (int i = 0; i < kRoomCount; i++) {
        const int m = differs_from_port(loaded(i), WallVariant::LegacyIsZero, nullptr, &n);
        thr += m;
        thr_split += std::string(thr_split.empty() ? "" : ", ") + kLabels[i] + " " +
                     std::to_string(m);
    }
    REQUIRE_TRUE(c, thr > 0,
                 "the old sim's 1.0e-5 threshold changes no answer anywhere in four rooms, which "
                 "would mean it can explain no disagreement at all - re-check that the knob is "
                 "wired before believing it");
    c.note("the old sim's cM3d_IsZero at 1.0e-5 rather than 2^-18: " + std::to_string(thr) +
           " of the " + std::to_string(n) +
           " probe(s) with a defined answer on both sides (" + thr_split +
           ") - an upper bound on what that threshold can explain in a differential run");

    // The root: answers changed, and arguments the two roots disagree on, in one pass.
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    int rootdiff = 0;
    long long calls = 0, args = 0;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk defined(*L.room, WallVariant::SegAssignsStart);
        WallWalk w(*L.room, WallVariant::LibrarySqrt);
        for (const WallProbe& p : L.probes) {
            if (!answer_is_defined(defined, p, cyls)) {
                continue;
            }
            cXyz a = p.pos;
            Room::WallResult ra;
            L.room->WallCorrect(&a, p.pos, kWallSpeedY, cyls, 3, &ra);
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
            if (!same_answer(a, ra, b, rb)) {
                rootdiff++;
            }
        }
        calls += w.root_calls();
        args += w.root_differs();
    }
    REQUIRE_TRUE(c, calls > 0,
                 "the pass took no square root at all over four rooms, so the two numbers below "
                 "are rates over an empty population");
    // An answer changed only if some argument differed; otherwise the knob reaches something else.
    REQUIRE_TRUE(c, (rootdiff == 0) == (args == 0),
                 "the root swap changed an answer on a run where the two roots agreed on every "
                 "argument, or agreed everywhere while differing on one - either way the knob is "
                 "not measuring what this case says it is");
    c.note("the old sim's correctly rounded root rather than the console's: " +
           std::to_string(rootdiff) + " of the " + std::to_string(n) +
           " probe(s) with a defined answer on both sides, over " + std::to_string(calls) +
           " square root(s) taken, of which " + std::to_string(args) +
           " have arguments the two answer differently");
    c.note("so the root explains nothing a differential run can find in these four rooms, and "
           "the reason is the arguments: test_wall_correct.cpp already holds that the two are "
           "distinguishable on a negative one and agree on 16,777,216 midpoint-targeted "
           "arguments over [1,4). This is the same answer taken at the call sites");

    // The old sim's `acch_wall_correct` uses 2^-18 everywhere except the segment's squared length
    // in `len2dsq_pnt_seg`, at 1.0e-5.
    int seg = 0;
    std::string seg_split;
    for (int i = 0; i < kRoomCount; i++) {
        const int m = differs_from_port(loaded(i), WallVariant::SegIsZeroLegacy);
        seg += m;
        seg_split += std::string(seg_split.empty() ? "" : ", ") + kLabels[i] + " " +
                     std::to_string(m);
    }
    c.note("the segment-length test alone at 1.0e-5, which is what the differential's oracle "
           "spells: " + std::to_string(seg) + " of the " + std::to_string(n) +
           " probe(s) with a defined answer on both sides (" + seg_split + ")");
}

TWWE_RED_CONTROL(red_the_wall_harness_agrees_with_the_port_on_the_old_sims_threshold,
                 "claims the harness is bit-identical to the ported pass while its IsZero is the "
                 "old sim's 1.0e-5 instead of the console's 2^-18. It must fail: if it passed, "
                 "the gate above would be green for a harness whose arithmetic is a different "
                 "engine's, and the two spellings' attribution below would be measuring nothing") {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk defined(*L.room, WallVariant::SegAssignsStart);
        WallWalk w(*L.room, WallVariant::LegacyIsZero);
        for (const WallProbe& p : L.probes) {
            if (!answer_is_defined(defined, p, cyls)) {
                continue;
            }
            cXyz a = p.pos;
            Room::WallResult ra;
            L.room->WallCorrect(&a, p.pos, kWallSpeedY, cyls, 3, &ra);
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
            REQUIRE_TRUE(c, same_answer(a, ra, b, rb),
                         std::string(kLabels[i]) + " " + p.cls + " of poly " +
                             std::to_string(p.of_poly));
        }
    }
}

// ===============================================================================================
// The uninitialised arms
// ===============================================================================================

TWWE_TEST(no_probe_reaches_cM2d_CrossCirLins_unassigned_arms,
          "cM2d_CrossCirLin leaves `t` unassigned on two arms and the port copies it that way. "
          "test_wall_correct.cpp measures that the four rooms contain polygons flat enough to "
          "enter one; this measures whether any probe gets there, which is the question that "
          "decides whether the copied body can return an undefined answer") {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    long long calls = 0, unassigned = 0, quadratic = 0;
    std::string split;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk w(*L.room, WallVariant::None);
        for (const WallProbe& p : L.probes) {
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
        }
        split += std::string(split.empty() ? "" : ", ") + kLabels[i] + " " +
                 std::to_string(w.cross_cir_lin_calls());
        calls += w.cross_cir_lin_calls();
        unassigned += w.cross_cir_lin_unassigned();
        quadratic += w.cross_cir_lin_quadratic();
    }
    // The population first: the corner arm must be reached at all.
    REQUIRE_TRUE(c, calls > 0,
                 "no probe in four rooms reached the corner arm, so the count below is a rate "
                 "over zero calls and reports success for the wrong reason");
    REQUIRE_INT(c, unassigned, 0,
                "cM2d_CrossCirLin calls that took an arm leaving `t` unassigned - each one is a "
                "position at which the ported body's answer is whatever was on the stack");
    c.note(std::to_string(calls) + " cM2d_CrossCirLin call(s) over " +
           std::to_string(total_probes()) + " probe(s) (" + split + "); " +
           std::to_string(quadratic) +
           " took the quadratic's two roots and " + std::to_string(calls - quadratic) +
           " the degenerate arms, 0 of them unassigned");
    c.note("this is the counter test_wall_correct.cpp's precondition case named and could not "
           "write: the four rooms do carry polygons whose |n_xz| squared reads as zero, and no "
           "probe derived from any of them reaches the arm that would matter");
}

// ===============================================================================================
// The chain
// ===============================================================================================

TWWE_TEST(the_trace_is_the_chain_the_position_was_reached_by,
          "the recorded corrections end where the pass ended, and the last one against each "
          "cylinder is the polygon that cylinder reports. Without both, a trace read off a "
          "disagreement would name a step that is not in the answer the differential compared") {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    std::vector<WallStep> trace;
    long long traced = 0, steps = 0, chains = 0, longest = 0;
    int end_wrong = 0, poly_wrong = 0, untraced_hit = 0;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk w(*L.room, WallVariant::None);
        w.TraceTo(&trace);
        for (const WallProbe& p : L.probes) {
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
            traced++;
            steps += (long long)trace.size();
            if (trace.empty()) {
                if (rb.wall_hit) {
                    untraced_hit++;
                }
                continue;
            }
            chains += (trace.size() > 1) ? 1 : 0;
            if ((long long)trace.size() > longest) {
                longest = (long long)trace.size();
            }
            // The last recorded position must be the answer.
            if (bits(b.x) != trace.back().x_bits || bits(b.z) != trace.back().z_bits) {
                end_wrong++;
            }
            for (int k = 0; k < 3; k++) {
                if (!rb.cir_hit[k]) {
                    continue;
                }
                int last = -1;
                for (size_t s = 0; s < trace.size(); s++) {
                    if (trace[s].cyl == k) {
                        last = trace[s].poly;
                    }
                }
                if (last != rb.cir_poly[k]) {
                    poly_wrong++;
                }
            }
        }
        w.TraceTo(nullptr);
    }
    REQUIRE_INT(c, (long long)end_wrong, 0,
                "probes whose last recorded correction is not the position the pass left");
    REQUIRE_INT(c, (long long)poly_wrong, 0,
                "cylinders whose last recorded corrector is not the polygon cir_poly names");
    REQUIRE_INT(c, (long long)untraced_hit, 0,
                "probes the pass reports a hit on with no correction recorded at all");
    // Some probe must take more than one correction, or `cir_poly` alone would suffice.
    REQUIRE_TRUE(c, chains > 0,
                 "no probe in four rooms was corrected more than once, so nothing here needs a "
                 "trace and cir_poly would say everything");
    c.note(std::to_string(traced) + " probe(s) traced, " + std::to_string(steps) +
           " correction(s) recorded, " + std::to_string(chains) +
           " probe(s) corrected more than once; the longest chain is " + std::to_string(longest) +
           " correction(s)");
}

// ===============================================================================================
// Unassigned locals that probes reach
// ===============================================================================================

TWWE_TEST(the_wall_pass_reads_two_uninitialised_locals_at_a_degenerate_water_line,
          "cM3d_Len2dSqPntAndSegLine's `cM3d_IsZero(dot)` arm writes *seg and leaves the closest "
          "point alone, and RwgWallCorrect's next two lines build its facing test out of exactly "
          "those two locals. This counts the probes that get there - which is the difference "
          "between a copied oddity and a position where the ported pass has no answer") {
    Room::WallCyl cyls[3];
    link_cylinders(cyls);
    int probes = 0, reached = 0, corrected_anyway = 0;
    std::string split, first;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk w(*L.room, WallVariant::None);
        int here = 0;
        for (const WallProbe& p : L.probes) {
            cXyz b = p.pos;
            Room::WallResult rb;
            w.run(&b, p.pos, kWallSpeedY, cyls, 3, &rb);
            probes++;
            if (w.degenerate_reads() > 0) {
                here++;
                reached++;
                if (rb.wall_hit) {
                    corrected_anyway++;
                }
                if (first.empty()) {
                    char buf[192];
                    std::snprintf(buf, sizeof(buf), "%s %s of poly %d at (%.9g, %.9g, %.9g)",
                                  kLabels[i], p.cls, p.of_poly, (double)p.pos.x, (double)p.pos.y,
                                  (double)p.pos.z);
                    first = buf;
                }
            }
        }
        split += std::string(split.empty() ? "" : ", ") + kLabels[i] + " " + std::to_string(here);
    }
    REQUIRE_TRUE(c, probes > 0, "the population is not empty");
    c.note(std::to_string(reached) + " of " + std::to_string(probes) +
           " probe(s) reach the arm (" + split + "), and the pass reports a correction on " +
           std::to_string(corrected_anyway) + " of them. First: " + first);
    // Counterfactual: `SegAssignsStart` (the old sim's behaviour, returning the segment's start)
    // counts the probes whose answer the unassigned locals decide.
    Room::WallCyl cy2[3];
    link_cylinders(cy2);
    int moved_by_assigning = 0;
    for (int i = 0; i < kRoomCount; i++) {
        Loaded& L = loaded(i);
        WallWalk base(*L.room, WallVariant::None);
        WallWalk fixed(*L.room, WallVariant::SegAssignsStart);
        for (const WallProbe& p : L.probes) {
            cXyz a = p.pos;
            Room::WallResult ra;
            base.run(&a, p.pos, kWallSpeedY, cy2, 3, &ra);
            if (base.degenerate_reads() == 0) {
                continue;
            }
            cXyz b = p.pos;
            Room::WallResult rb;
            fixed.run(&b, p.pos, kWallSpeedY, cy2, 3, &rb);
            if (!same_answer(a, ra, b, rb)) {
                moved_by_assigning++;
            }
        }
    }
    REQUIRE_TRUE(c, moved_by_assigning > 0,
                 "giving the unassigned locals a defined value changes no answer at any of the "
                 "probes that read them - which would mean they are read and never matter, and "
                 "the gap below would be book-keeping rather than a defect");
    c.note(std::to_string(moved_by_assigning) + " of the " + std::to_string(reached) +
           " answer differently once that arm assigns the segment's start point the way the old "
           "sim does - so on those the two locals are not incidental, they are the decision");

    // The answer at such a probe depends on the caller's stack frame, so the gate sets them aside.
    EXPECT_KNOWN_GAP(c, reached == 0,
                     "RwgWallCorrect builds `spD4`/`spD8` - and therefore the facing test that "
                     "decides whether a polygon corrects at all - out of two locals "
                     "cM3d_Len2dSqPntAndSegLine's degenerate arm never assigned, and real probes "
                     "get there. This is the decomp's own code and the port copies it, so the "
                     "fix is not an edit to the body: it is a measurement of what the console "
                     "has in those two words at that call, which nothing offline can supply. "
                     "Unmark when the count reaches 0 or when the console says what they are");
}
