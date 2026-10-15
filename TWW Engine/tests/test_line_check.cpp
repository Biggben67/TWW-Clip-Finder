// test_line_check.cpp - the line check: cBgW::LineCheckGrpRp -> LineCheckRp -> RwgLineCheck,
// driven the way dBgS_Acch::LineCheck drives them.
//
// dBgS_Acch::CrrPos runs it before the wall pass when the frame's XZ movement exceeds the wall
// radius, and again after if a wall corrected (d_bg_s_acch.cpp:236-248), so a fast Link cannot
// pass through a wall his cylinders never overlap. A crossing whose polygon has an XZ normal
// latches `SetWallHDirect(pm_pos->y)`, and RwgWallCorrect then cuts at that height.
//
// No console capture: the evidence is the ported walk against a flat sweep of the same room, and
// every knob measured.

#include <algorithm>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "SSystem/SComponent/c_m3d.h"
#include "framework/golden.h"
#include "framework/json.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "line_walk.h"
#include "room_dzb.h"

namespace tww_engine {
namespace testing {
namespace {

//: The same four rooms the wall arm uses.
const char* kRooms[] = {"kaze_r11_bgd.json", "ganona_r0_bgd.json", "sea_r41_bgd.json",
                        "kaisen_r0_bgd.json"};

const char* kClasses[] = {"cross_mid", "cross_short", "graze", "stops_short", "corner_cross"};

Room::WallCyl link_cyls(Room::WallCyl* out) {
    for (int i = 0; i < 3; i++) {
        out[i].h = kLineWallH[i];
        out[i].r = kLineWallR;
    }
    return out[0];
}

/// One probe's answer: position bits, hit flag, and per cylinder the polygon and wall-height
/// latch, compared as a whole.
struct Answer {
    u32 x, y, z;
    bool hit;
    int poly[3];
    bool whd_set[3];
    u32 whd[3];
    int ground_branch;

    bool operator!=(const Answer& o) const {
        if (x != o.x || y != o.y || z != o.z || hit != o.hit ||
            ground_branch != o.ground_branch) {
            return true;
        }
        for (int i = 0; i < 3; i++) {
            if (poly[i] != o.poly[i] || whd_set[i] != o.whd_set[i] || whd[i] != o.whd[i]) {
                return true;
            }
        }
        return false;
    }
};

Answer answer_of(const cXyz& pos, const Room::LineResult& r) {
    Answer a;
    a.x = bits(pos.x);
    a.y = bits(pos.y);
    a.z = bits(pos.z);
    a.hit = r.hit;
    a.ground_branch = r.ground_branch;
    for (int i = 0; i < 3; i++) {
        a.poly[i] = r.cir_poly[i];
        a.whd_set[i] = r.whd_set[i];
        a.whd[i] = bits(r.whd[i]);
    }
    return a;
}

/// The distance in ulps between two same-sign finite f32 bit patterns. Reported, not asserted.
long long ulp_gap(u32 p, u32 q) {
    const long long a = (p & 0x80000000u) ? -(long long)(p & 0x7FFFFFFFu) : (long long)p;
    const long long b = (q & 0x80000000u) ? -(long long)(q & 0x7FFFFFFFu) : (long long)q;
    return a > b ? a - b : b - a;
}

/// The port's own answer at one probe.
Answer ported(Room& room, const LineProbe& p, const Room::WallCyl* cyls) {
    cXyz pos = p.pos;
    Room::LineResult r;
    room.LineCheck(&pos, p.old_pos, cyls, 3, &r);
    return answer_of(pos, r);
}

/// A variant's answer at one probe.
Answer variant(LineWalk& w, const LineProbe& p, const Room::WallCyl* cyls) {
    cXyz pos = p.pos;
    Room::LineResult r;
    w.run(&pos, p.old_pos, cyls, 3, &r);
    return answer_of(pos, r);
}

}  // namespace

// ================================================================= the probe set

TWWE_TEST(the_line_probe_set_is_derived_from_the_rooms_own_polygons,
          "every segment the line gates ask about is built from a polygon's own centroid, its own "
          "vertices and its own normal - and one class of them stops short of the plane, so a run "
          "in which everything crossed would be visible as the geometry having decided it") {
    long long total = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        int dropped = 0;
        const std::vector<LineProbe> probes = line_probe_set(room, dzb, &dropped);
        REQUIRE_TRUE(c, !probes.empty(), std::string(rn) + " derives at least one segment");

        std::set<std::string> classes;
        for (const LineProbe& p : probes) {
            classes.insert(p.cls);
        }
        for (const char* cls : kClasses) {
            REQUIRE_TRUE(c, classes.count(cls) == 1,
                         std::string(rn) + " has probes of class " + cls);
        }
        total += (long long)probes.size();
        c.note(std::string(rn) + ": " + std::to_string(probes.size()) + " segment(s) over " +
               std::to_string(room.tri_count()) + " triangle(s), " + std::to_string(dropped) +
               " polygon(s) with no usable normal");
    }
    c.note(std::to_string(total) + " segment(s) over the four rooms");
}

// ================================================================= the harness
//
// The harness is held to the extracted bodies bit for bit before any knob is turned.

TWWE_TEST(the_line_variant_harness_is_the_ported_walk,
          "tests/line_walk.h's unmutated walk against Room::LineCheck over every derived segment "
          "in four rooms: position, hit flag, and each cylinder's polygon and wall-height latch, "
          "bit for bit") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    long long n = 0, crossed = 0, offered = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::None);
        for (const LineProbe& p : probes) {
            const Answer want = ported(room, p, cyls);
            const Answer got = variant(w, p, cyls);
            REQUIRE_TRUE(c, !(want != got),
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls +
                             ": the harness answers what the port answers");
            if (want.hit) {
                crossed++;
            }
            n++;
        }
        offered += w.offered();
    }
    c.note(std::to_string(n) + " segment(s), " + std::to_string(crossed) +
           " of them crossing something; the harness offered " + std::to_string(offered) +
           " polygon(s) to the per-polygon test");
}

TWWE_TEST(the_offer_log_is_everything_the_descent_handed_to_the_per_polygon_test,
          "the offered list the port cannot emit: Room::LogVisitedPolys sits on "
          "dBgW::ChkPolyThrough and RwgLineCheck reaches that only after cM3d_Cross_LinTri has "
          "accepted, so the port's log is the polygons that crossed. The harness records one "
          "level earlier, and its crossing subset has to be the port's list, in order") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    long long offers = 0, crossed = 0, refused = 0, segs = 0, quiet = 0;
    long long stray_refusal = 0, stray_cyl = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::None);
        std::vector<LineOffer> log;
        std::vector<int> visited;
        for (const LineProbe& p : probes) {
            // The answer with the log off, so recording is measured to change nothing.
            w.OfferTo(nullptr);
            const Answer quiet_a = variant(w, p, cyls);

            w.ResetCounts();
            w.OfferTo(&log);
            visited.clear();
            room.LogVisitedPolys(&visited);
            cXyz pos = p.pos;
            Room::LineResult r;
            w.run(&pos, p.old_pos, cyls, 3, &r);
            room.LogVisitedPolys(nullptr);
            w.OfferTo(nullptr);
            const Answer logged = answer_of(pos, r);

            REQUIRE_TRUE(c, !(quiet_a != logged),
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls +
                             ": recording the offers changes no answer");
            if (!(quiet_a != logged)) {
                quiet++;
            }

            // The counter and the list are independent recordings of the same event.
            REQUIRE_TRUE(c, (long long)log.size() == w.offered(),
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls +
                             ": the log has one entry per offer (" + std::to_string(log.size()) +
                             " vs " + std::to_string(w.offered()) + ")");

            // The oracle for the log: `visited` is every polygon dBgW::ChkPolyThrough was asked
            // about, which is exactly the ones cM3d_Cross_LinTri accepted, refusals included.
            std::vector<int> mine;
            for (const LineOffer& o : log) {
                if (o.crossed) {
                    mine.push_back(o.poly);
                }
            }
            REQUIRE_TRUE(c, mine == visited,
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls +
                             ": the log's crossing subset is the port's visit list, in order (" +
                             std::to_string(mine.size()) + " vs " +
                             std::to_string(visited.size()) + ")");

            // Counted and asserted once: these are invariants over 1.2 million entries.
            for (const LineOffer& o : log) {
                offers++;
                if (o.crossed) {
                    crossed++;
                }
                if (o.refused) {
                    refused++;
                }
                if (o.refused && !o.crossed) {
                    stray_refusal++;
                }
                if (o.cyl < 0 || o.cyl >= 3) {
                    stray_cyl++;
                }
            }
            segs++;
        }
    }
    // An empty log would satisfy every assertion above.
    REQUIRE_TRUE(c, crossed > 0 && offers > crossed,
                 "the descent offered more than it accepted - without that this case compares two "
                 "empty lists");
    REQUIRE_TRUE(c, stray_refusal == 0,
                 "ChkPolyThrough is only ever asked about a crossing (" +
                     std::to_string(stray_refusal) + " offer(s) say otherwise)");
    REQUIRE_TRUE(c, stray_cyl == 0,
                 "every offer names one of the three cylinders (" + std::to_string(stray_cyl) +
                     " offer(s) do not)");
    c.note(std::to_string(segs) + " segment(s), " + std::to_string(quiet) +
           " of them answered identically with the log on; " + std::to_string(offers) +
           " offer(s), " + std::to_string(crossed) + " of them crossings and " +
           std::to_string(refused) + " of those refused by dBgW::ChkPolyThrough");
}

// ================================================================= the prune

TWWE_TEST(the_octree_drops_no_crossing_a_flat_sweep_of_the_room_would_find,
          "the same walk with the octree taken out - every polygon on every block's three chains, "
          "no group box and no node box - asked one segment at a time, so the three cylinders "
          "cannot feed each other. Whether a crossing is found has to agree, and which polygon is "
          "named has to agree too") {
    long long n = 0, any = 0, descent = 0, flat = 0, worst = 0, named = 0, tied = 0;
    int moved = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::None);
        LineWalk f(room, LineVariant::Flat);
        for (const LineProbe& p : probes) {
            // One cylinder per run: dBgS_Acch::LineCheck starts each from where the last left, so a
            // one-ulp difference in cylinder 0 changes cylinder 2's input.
            for (int k = 0; k < 3; k++) {
                Room::WallCyl one;
                one.h = kLineWallH[k];
                one.r = kLineWallR;
                cXyz pa = p.pos, pb = p.pos;
                Room::LineResult ra, rb;
                w.run(&pa, p.old_pos, &one, 1, &ra);
                f.run(&pb, p.old_pos, &one, 1, &rb);
                REQUIRE_TRUE(c, ra.hit == rb.hit,
                             std::string(rn) + " poly " + std::to_string(p.of_poly) + " " +
                                 p.cls + " cyl " + std::to_string(k) +
                                 ": the descent and the flat sweep agree on whether a crossing "
                                 "exists");
                const bool same_pos = bits(pa.x) == bits(pb.x) && bits(pa.y) == bits(pb.y) &&
                                      bits(pa.z) == bits(pb.z);
                if (ra.cir_poly[0] != rb.cir_poly[0]) {
                    named++;
                    if (same_pos) {
                        tied++;
                    } else if (moved < 6) {
                        moved++;
                        char buf[256];
                        std::snprintf(buf, sizeof(buf),
                                      " descent poly %d at (%.9g %.9g %.9g), flat poly %d at "
                                      "(%.9g %.9g %.9g)",
                                      ra.cir_poly[0], (double)pa.x, (double)pa.y, (double)pa.z,
                                      rb.cir_poly[0], (double)pb.x, (double)pb.y, (double)pb.z);
                        c.note(std::string(rn) + " poly " + std::to_string(p.of_poly) + " " +
                               p.cls + " cyl " + std::to_string(k) + buf);
                    }
                }
                if (!same_pos) {
                    any++;
                    worst = std::max(worst,
                                     std::max(ulp_gap(bits(pa.x), bits(pb.x)),
                                              std::max(ulp_gap(bits(pa.y), bits(pb.y)),
                                                       ulp_gap(bits(pa.z), bits(pb.z)))));
                }
                n++;
            }
        }
        descent += w.offered();
        flat += f.offered();
        REQUIRE_TRUE(c, f.offered() > w.offered(),
                     std::string(rn) + ": the flat sweep offers more polygons than the descent - "
                                       "without that this case is comparing two identical walks");
    }
    c.note(std::to_string(n) + " (segment, cylinder) question(s): the descent offered " +
           std::to_string(descent) + " polygon(s) where the flat sweep offered " +
           std::to_string(flat) + " - " + std::to_string(flat - descent) +
           " pruned away, and not one of them a crossing");
    c.note(std::to_string(named) + " name a different polygon and " + std::to_string(any) +
           " land on a different position (worst " + std::to_string(worst) +
           " ulp), of which " + std::to_string(tied) +
           " are a coincident pair the order chose between");
}

TWWE_TEST(the_three_cylinders_feed_each_other_so_the_descents_order_does_not_stay_a_last_bit,
          "the octree's child order reversed, measured twice: once per cylinder with both walks "
          "asked the same segment, and once as the game runs it - three cylinders in order, each "
          "starting from the position the last one left. The second number is the first one's "
          "reach, and it is bigger") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    long long one_n = 0, one_diff = 0, one_worst = 0, one_hit = 0;
    std::map<std::string, long long> by_cls, asked_cls;
    long long all_n = 0, all_diff = 0, all_hit = 0, all_poly = 0, all_worst = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::None);
        LineWalk r(room, LineVariant::ChildrenReversed);
        for (const LineProbe& p : probes) {
            for (int k = 0; k < 3; k++) {
                Room::WallCyl one;
                one.h = kLineWallH[k];
                one.r = kLineWallR;
                cXyz pa = p.pos, pb = p.pos;
                Room::LineResult ra, rb;
                w.run(&pa, p.old_pos, &one, 1, &ra);
                r.run(&pb, p.old_pos, &one, 1, &rb);
                if (ra.hit != rb.hit) {
                    one_hit++;
                }
                if (bits(pa.x) != bits(pb.x) || bits(pa.y) != bits(pb.y) ||
                    bits(pa.z) != bits(pb.z) || ra.cir_poly[0] != rb.cir_poly[0] ||
                    ra.hit != rb.hit) {
                    one_diff++;
                    by_cls[p.cls] = by_cls[p.cls] + 1;
                    one_worst = std::max(one_worst,
                                         std::max(ulp_gap(bits(pa.x), bits(pb.x)),
                                                  std::max(ulp_gap(bits(pa.y), bits(pb.y)),
                                                           ulp_gap(bits(pa.z), bits(pb.z)))));
                }
                asked_cls[p.cls] = asked_cls[p.cls] + 1;
                one_n++;
            }
            const Answer a = variant(w, p, cyls);
            const Answer b = variant(r, p, cyls);
            if (a != b) {
                all_diff++;
                if (a.hit != b.hit) {
                    all_hit++;
                }
                for (int k = 0; k < 3; k++) {
                    if (a.poly[k] != b.poly[k]) {
                        all_poly++;
                        break;
                    }
                }
                all_worst = std::max(all_worst,
                                     std::max(ulp_gap(a.x, b.x),
                                              std::max(ulp_gap(a.y, b.y), ulp_gap(a.z, b.z))));
            }
            all_n++;
        }
    }
    // The order is in the answer, and running the three cylinders in order reaches further.
    REQUIRE_TRUE(c, one_diff > 0,
                 "reversing the octree's children changes an answer even one cylinder at a time");
    REQUIRE_TRUE(c, all_diff > 0, "and with the three cylinders run in order");
    // The order decides which crossing is recorded, never whether there was one.
    REQUIRE_TRUE(c, one_hit == 0 && all_hit == 0,
                 "and it never changes whether a crossing was found at all - " +
                     std::to_string(one_hit) + " one at a time, " + std::to_string(all_hit) +
                     " with three");
    c.note("one cylinder at a time: " + std::to_string(one_diff) + " of " +
           std::to_string(one_n) + " question(s) differ, worst " + std::to_string(one_worst) +
           " ulp in the position");
    for (std::map<std::string, long long>::const_iterator it = asked_cls.begin();
         it != asked_cls.end(); ++it) {
        c.note("    " + it->first + ": " + std::to_string(by_cls[it->first]) + " of " +
               std::to_string(it->second));
    }
    c.note("three cylinders in order: " + std::to_string(all_diff) + " of " +
           std::to_string(all_n) + " segment(s) differ - " + std::to_string(all_hit) +
           " in whether anything was hit at all, " + std::to_string(all_poly) +
           " in a named polygon, worst " + std::to_string(all_worst) + " ulp");
}

// Why the two cases above are split. `RwgLineCheck` shortens the segment on every acceptance, so
// the next crossing is interpolated against the current end; two walks accepting the same
// crossings in a different order reach the same point by different arithmetic. Unlike the
// ground walk's running maximum, which is order-independent, and the three cylinders chain.
//
// It bites mostly on `corner_cross` (9,606 of 9,766 order-sensitive questions, against 75 of
// 16,389 `cross_mid`): cM3d_Cross_LinTri dilates each edge by +/-20.0f, so an ulp changes the
// verdict only on an edge, and a vertex sits on three.
//
// So the child order is in the answer and copied. The prune is exact: with only the two box tests
// removed, the walk answers identically.

// ================================================================= the knobs

TWWE_TEST(every_control_knob_of_the_line_walk_changes_an_answer,
          "each swappable piece of the walk measured over the same segments: a knob that changes "
          "nothing is a knob this gate does not hold, and saying which is which is the point") {
    struct Knob {
        LineVariant var;
        const char* name;
        bool must_change;
        const char* why;
    };
    const Knob knobs[] = {
        {LineVariant::NoShrink, "the accepted crossing does not shorten the segment", true,
         "c_bg_w.cpp:386 - what makes the answer the nearest crossing rather than the last one"},
        {LineVariant::TwoSided, "the back flag on", true,
         "cBgS_LinChk::ct clears mBackFlag, so a wall crossed from behind is not a hit"},
        {LineVariant::NoWallChain, "a leaf's wall chain not walked", true, "c_bg_w.cpp:415"},
        {LineVariant::NoGroundChain, "a leaf's ground chain not walked", true, "c_bg_w.cpp:417"},
        {LineVariant::NoRoofChain, "a leaf's roof chain not walked", true, "c_bg_w.cpp:419"},
        {LineVariant::ChildrenReversed, "the octree's children in reverse", true,
         "c_bg_w.cpp:424-439. It changes the last bits and not which crossing is found, for the "
         "reason the flat sweep does - every acceptance re-anchors the next interpolation. The "
         "ground walk's own order knob changes nothing at all, and the difference between the "
         "two walks is exactly that this one's intermediate answers are inputs"},
        {LineVariant::LegacyIsZero, "the old sim's 1.0e-5 at every cM3d_IsZero", false,
         "an upper bound on the threshold's reach in this pass, not an attribution"},
        {LineVariant::AxisIsZeroGate, "cM3d_IsZero in place of the 0.008f axis gate", false,
         "0.008f is 2,097 times G_CM3D_F_ABS_MIN, so this is what a port that reached for the "
         "familiar spelling would have written"},
    };

    Room::WallCyl cyls[3];
    link_cyls(cyls);
    long long n = 0;
    long long moved[sizeof(knobs) / sizeof(knobs[0])] = {0};

    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk base(room, LineVariant::None);
        for (size_t k = 0; k < sizeof(knobs) / sizeof(knobs[0]); k++) {
            LineWalk w(room, knobs[k].var);
            for (const LineProbe& p : probes) {
                if (variant(base, p, cyls) != variant(w, p, cyls)) {
                    moved[k]++;
                }
            }
        }
        n += (long long)probes.size();
    }

    for (size_t k = 0; k < sizeof(knobs) / sizeof(knobs[0]); k++) {
        if (knobs[k].must_change) {
            REQUIRE_TRUE(c, moved[k] > 0,
                         std::string(knobs[k].name) + " changes an answer (" + knobs[k].why + ")");
        }
        c.note(std::string(moved[k] ? "" : "no change  ") + knobs[k].name + ": " +
               std::to_string(moved[k]) + " of " + std::to_string(n) + " segment(s)");
    }
}

// ================================================================= the wall-height latch

TWWE_TEST(the_line_check_latches_the_height_the_wall_pass_will_cut_at,
          "SetWallHDirect is the coupling between the two passes: where the line check crosses a "
          "polygon with an XZ normal it writes the cylinder's height, and RwgWallCorrect then "
          "uses that instead of deriving one from the position and the frame's speed") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    long long n = 0, hit = 0, latched = 0, ground_arm = 0;
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        for (const LineProbe& p : probes) {
            cXyz pos = p.pos;
            Room::LineResult r;
            room.LineCheck(&pos, p.old_pos, cyls, 3, &r);
            n++;
            if (r.hit) {
                hit++;
            }
            for (int i = 0; i < 3; i++) {
                if (r.whd_set[i]) {
                    latched++;
                    // The latch is written from the position after the push-out.
                    REQUIRE_TRUE(c, r.cir_hit[i],
                                 "a latched cylinder is a cylinder that crossed something");
                }
            }
            ground_arm += r.ground_branch;
        }
    }
    REQUIRE_TRUE(c, latched > 0, "the latch fires somewhere in four rooms");
    c.note(std::to_string(hit) + " of " + std::to_string(n) + " segment(s) crossed something; " +
           std::to_string(latched) + " cylinder-crossing(s) latched a wall height");
    // The gap, counted: Room::LineCheck runs the ground arm's `pm_pos->y -= 1.0f` and not its
    // `GroundCheck(i_bgs)`. Printed even when zero.
    c.note(std::to_string(ground_arm) +
           " cylinder-crossing(s) took the ground arm, whose GroundCheck this engine does not run");
}

// ================================================================= the red controls

TWWE_RED_CONTROL(red_the_line_harness_agrees_with_the_port_without_the_shrink,
              "claims the harness is bit-identical to the ported walk while an accepted crossing "
              "no longer shortens the segment. It must fail: if it passed, the gate above would "
              "be green for a walk that answers with the last polygon it was offered instead of "
              "the nearest, and every knob count below it would be measured against that") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::NoShrink);
        for (const LineProbe& p : probes) {
            const Answer want = ported(room, p, cyls);
            const Answer got = variant(w, p, cyls);
            REQUIRE_TRUE(c, !(want != got),
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls);
        }
    }
}

TWWE_RED_CONTROL(red_the_offer_log_is_the_ports_visit_list,
              "claims the whole offer log is what Room::LogVisitedPolys records - every polygon "
              "the descent handed over, not just the ones that crossed. It must fail: if the two "
              "lists were the same thing the gate above would be holding the port's own log "
              "against itself, and the list this arm exists to produce would not exist") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        LineWalk w(room, LineVariant::None);
        std::vector<LineOffer> log;
        std::vector<int> visited;
        for (const LineProbe& p : probes) {
            w.OfferTo(&log);
            visited.clear();
            room.LogVisitedPolys(&visited);
            cXyz pos = p.pos;
            Room::LineResult r;
            w.run(&pos, p.old_pos, cyls, 3, &r);
            room.LogVisitedPolys(nullptr);
            w.OfferTo(nullptr);
            std::vector<int> mine;
            for (const LineOffer& o : log) {
                mine.push_back(o.poly);
            }
            REQUIRE_TRUE(c, mine == visited,
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls);
        }
    }
}

TWWE_RED_CONTROL(red_the_line_check_crosses_a_segment_that_stops_in_front_of_the_wall,
              "claims every derived segment crosses something, including the `stops_short` class "
              "that ends before the plane. It must fail: without it, a probe set that happened to "
              "cross on every class would be indistinguishable from a pass that says yes to "
              "everything, and the flat-sweep gate above would still be green") {
    Room::WallCyl cyls[3];
    link_cyls(cyls);
    for (const char* rn : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(rn));
        Room room(dzb);
        const std::vector<LineProbe> probes = line_probe_set(room, dzb);
        for (const LineProbe& p : probes) {
            cXyz pos = p.pos;
            Room::LineResult r;
            room.LineCheck(&pos, p.old_pos, cyls, 3, &r);
            REQUIRE_TRUE(c, r.hit,
                         std::string(rn) + " poly " + std::to_string(p.of_poly) + " " + p.cls +
                             " crosses something");
        }
    }
}

// ================================================================= the differential
//
// The port's answer at every segment the old sim will also be asked about. Not a gate: both sides
// port the same decomp.

TWWE_TEST(the_port_answers_the_segments_a_line_differential_run_asks_for,
          "with TWWE_DIFF_LINE_POINTS set, the port's line-check answer at every segment the old "
          "sim will also be asked about - written out to diff against the old sim, so the "
          "console is only ever spent where two engines disagree") {
    const char* in_path = std::getenv("TWWE_DIFF_LINE_POINTS");
    const char* out_path = std::getenv("TWWE_DIFF_LINE_OUT");
    if (in_path == nullptr || out_path == nullptr) {
        c.note("set TWWE_DIFF_LINE_POINTS=<points.json> and TWWE_DIFF_LINE_OUT=<answers.json> to "
               "run the line differential (TWWE_DIFF_LINE_VISITS to carry the crossings, "
               "TWWE_DIFF_LINE_OFFERED for everything the descent handed over, "
               "TWWE_DIFF_LINE_VARIANT=<knob> to answer with one of the walk's knobs turned). "
               "Unset, this case answers nothing and asserts nothing");
        REQUIRE_TRUE(c, true, "");
        return;
    }
    Json pts;
    std::string err;
    REQUIRE_TRUE(c, Json::load(in_path, &pts, &err),
                 std::string("TWWE_DIFF_LINE_POINTS could not be read: ") + err);
    const Json& rows = pts["points"];
    const std::string room_name = pts["bgd"].str;

    // The cylinders come from the run: setBgCheckParam chooses them per proc.
    Room::WallCyl cyls[kMaxWallCyl];
    const Json& hs = pts["wall_h"];
    const int tbl_size = (int)hs.size();
    REQUIRE_TRUE(c, tbl_size > 0 && tbl_size <= kMaxWallCyl,
                 "wall_h names between 1 and " + std::to_string(kMaxWallCyl) + " cylinders");
    const f32 wall_r = pts["wall_r"].as_f32();
    for (int i = 0; i < tbl_size && i < kMaxWallCyl; i++) {
        cyls[i].h = hs[i].as_f32();
        cyls[i].r = wall_r;
    }

    const bool want_visits = std::getenv("TWWE_DIFF_LINE_VISITS") != nullptr;
    std::vector<int> visited;

    // The offered list comes off the harness, so each segment is re-checked against
    // Room::LineCheck.
    const bool want_offered = std::getenv("TWWE_DIFF_LINE_OFFERED") != nullptr;
    std::vector<LineOffer> offers;

    // A knob answered with: the old sim's spelling returning the old sim's answer attributes the
    // difference. With a knob named, the harness is the answer and the bit-identity check is
    // skipped.
    const char* var_name = std::getenv("TWWE_DIFF_LINE_VARIANT");
    LineVariant want_var = LineVariant::None;
    if (var_name != nullptr) {
        const std::string v(var_name);
        if (v == "None") {
            want_var = LineVariant::None;
        } else if (v == "Flat") {
            want_var = LineVariant::Flat;
        } else if (v == "NoShrink") {
            want_var = LineVariant::NoShrink;
        } else if (v == "TwoSided") {
            want_var = LineVariant::TwoSided;
        } else if (v == "ChildrenReversed") {
            want_var = LineVariant::ChildrenReversed;
        } else if (v == "LegacyIsZero") {
            want_var = LineVariant::LegacyIsZero;
        } else if (v == "AxisIsZeroGate") {
            want_var = LineVariant::AxisIsZeroGate;
        } else {
            // A misspelling must not fall back to the ported path.
            REQUIRE_TRUE(c, false,
                         "TWWE_DIFF_LINE_VARIANT=" + v +
                             " is not a knob of tests/line_walk.h (None, Flat, NoShrink, "
                             "TwoSided, ChildrenReversed, LegacyIsZero, AxisIsZeroGate)");
            return;
        }
    }
    const bool answer_with_variant = (var_name != nullptr && want_var != LineVariant::None);
    const bool run_harness = want_offered || answer_with_variant;

    RoomDzb dzb = read_room_dzb(golden(room_name));
    Room fx_room(dzb);
    LineWalk harness(fx_room, want_var);

    std::string body;
    for (size_t i = 0; i < rows.size(); i++) {
        cXyz old_pos, pos;
        old_pos.x = rows[i]["ox"].as_f32();
        old_pos.y = rows[i]["oy"].as_f32();
        old_pos.z = rows[i]["oz"].as_f32();
        pos.x = rows[i]["x"].as_f32();
        pos.y = rows[i]["y"].as_f32();
        pos.z = rows[i]["z"].as_f32();
        Room::LineResult res;
        visited.clear();
        fx_room.LogVisitedPolys(want_visits ? &visited : nullptr);
        fx_room.LineCheck(&pos, old_pos, cyls, tbl_size, &res);
        fx_room.LogVisitedPolys(nullptr);
        if (run_harness) {
            cXyz hpos;
            hpos.x = rows[i]["x"].as_f32();
            hpos.y = rows[i]["y"].as_f32();
            hpos.z = rows[i]["z"].as_f32();
            Room::LineResult hres;
            harness.OfferTo(want_offered ? &offers : nullptr);
            harness.run(&hpos, old_pos, cyls, tbl_size, &hres);
            harness.OfferTo(nullptr);
            if (answer_with_variant) {
                pos = hpos;
                res = hres;
            } else {
                REQUIRE_TRUE(c, !(answer_of(pos, res) != answer_of(hpos, hres)),
                             "segment " + std::to_string(i) + " of " + room_name +
                                 ": the harness that emits the offered list answers what the "
                                 "port answers");
            }
        }
        // The latch goes out with the position: `SetWallHDirect` is the only channel to the wall
        // pass, so a staged frame must use this engine's latch.
        char buf[640];
        std::snprintf(buf, sizeof(buf),
                      "%s{\"i\": %zu, \"x\": %.9g, \"y\": %.9g, \"z\": %.9g, \"x_bits\": %u, "
                      "\"y_bits\": %u, \"z_bits\": %u, \"hit\": %s, \"ground_branch\": %d, "
                      "\"cir_poly\": [%d, %d, %d], \"whd_set\": [%s, %s, %s], "
                      "\"whd\": [%.9g, %.9g, %.9g], \"whd_bits\": [%u, %u, %u]",
                      i ? ",\n" : "", i, (double)pos.x, (double)pos.y, (double)pos.z,
                      (unsigned)bits(pos.x), (unsigned)bits(pos.y), (unsigned)bits(pos.z),
                      res.hit ? "true" : "false", res.ground_branch,
                      res.cir_poly[0], res.cir_poly[1], res.cir_poly[2],
                      res.whd_set[0] ? "true" : "false", res.whd_set[1] ? "true" : "false",
                      res.whd_set[2] ? "true" : "false",
                      (double)res.whd[0], (double)res.whd[1], (double)res.whd[2],
                      (unsigned)bits(res.whd[0]), (unsigned)bits(res.whd[1]),
                      (unsigned)bits(res.whd[2]));
        body += buf;
        if (want_visits) {
            body += ", \"visited\": [";
            for (size_t v = 0; v < visited.size(); v++) {
                body += (v ? "," : "") + std::to_string(visited[v]);
            }
            body += "]";
        }
        if (want_offered) {
            // Per cylinder: each descent starts where the last left and shortens its own segment.
            body += ", \"offered\": [";
            for (int k = 0; k < tbl_size; k++) {
                body += (k ? ", [" : "[");
                bool first = true;
                for (const LineOffer& o : offers) {
                    if (o.cyl == k) {
                        body += (first ? "" : ",") + std::to_string(o.poly);
                        first = false;
                    }
                }
                body += "]";
            }
            body += "], \"through\": [";
            for (int k = 0; k < tbl_size; k++) {
                body += (k ? ", [" : "[");
                bool first = true;
                for (const LineOffer& o : offers) {
                    if (o.cyl == k && o.refused) {
                        body += (first ? "" : ",") + std::to_string(o.poly);
                        first = false;
                    }
                }
                body += "]";
            }
            body += "]";
        }
        body += "}";
    }
    std::FILE* f = std::fopen(out_path, "wb");
    REQUIRE_TRUE(c, f != nullptr,
                 std::string("TWWE_DIFF_LINE_OUT could not be opened: ") + out_path);
    if (f != nullptr) {
        std::fprintf(f, "{\"bgd\": \"%s\", \"answers\": [\n%s\n]}\n", room_name.c_str(),
                     body.c_str());
        std::fclose(f);
    }
    c.note(std::to_string(rows.size()) + " segment(s) answered from " + room_name +
           (answer_with_variant ? std::string(" with ") + var_name + " turned on" : std::string())
           + " -> " + out_path);
}

}  // namespace testing
}  // namespace tww_engine
