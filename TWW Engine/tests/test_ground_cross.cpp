// test_ground_cross.cpp - red controls for the ground check's per-polygon test.
//
// test_ground_walk.cpp holds the ground check to the 1,112 console frames through `Room`. The
// controls here swap pieces of cM3d_CrossY_Tri_Front or getCrossY_NonIsZero in a local harness,
// which `the_ground_variant_harness_is_the_ported_walk` holds to `Room` first.
//
//   kaze r11    1,082 frames, 332 candidates, flat axis-aligned floors: holds the poly choice.
//               With normal (0,1,0) the nx and nz terms are multiplied by zero.
//   GanonA r0   30 frames, 100 candidates, a micro-incline: holds the height, bit for bit
//               (evaluating the plane in double and rounding once is 6 of 30 wrong).
//   sea r41     chosen probes aimed at crease edges, the only corpus inside the -20.0f edge
//               dilation band; the walked rooms come no closer than 836 area-units.

#include <set>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "SSystem/SComponent/c_m3d.h"
#include "engine/room.h"
#include "room_dzb.h"

namespace {

using tww_engine::Room;
using tww_engine::RoomDzb;
using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::read_room_dzb;

/// dBgS_Acch::GroundCheck raises the probe by `m_ground_check_offset - m_ground_up_h`
/// (d_bg_s_acch.cpp:128); 60.0f and 0.0f from dBgS_Acch's constructor (:59-60). Not pinned by
/// these frames: 10.0f and 100.0f give the same answers.
const f32 kGroundCheckOffset = 60.0f;

/// One candidate polygon as a floors capture banks it: poly index, world vertices and the stored
/// plane.
struct Candidate {
    int poly;
    Vec v[3];
    cXyz n;
    f32 d;
};

std::vector<Candidate> candidates(const char* golden) {
    const Json& g = tww_engine::testing::golden(golden);
    const Json& polys = g["polys"];
    std::vector<Candidate> out;
    for (size_t i = 0; i < polys.size(); i++) {
        const Json& p = polys[i];
        Candidate r;
        r.poly = p["poly"].as_int();
        for (int k = 0; k < 3; k++) {
            r.v[k].x = p["v"][k][0].as_f32();
            r.v[k].y = p["v"][k][1].as_f32();
            r.v[k].z = p["v"][k][2].as_f32();
        }
        r.n.x = p["n"][0].as_f32();
        r.n.y = p["n"][1].as_f32();
        r.n.z = p["n"][2].as_f32();
        r.d = p["d"].as_f32();
        out.push_back(r);
    }
    return out;
}

/// The two rooms, built from the disc's .dzb, as test_ground_walk.cpp gates them.
Room& kaze() {
    static Room r(read_room_dzb(tww_engine::testing::golden("kaze_r11_bgd.json")));
    return r;
}

Room& ganona() {
    static Room r(read_room_dzb(tww_engine::testing::golden("ganona_r0_bgd.json")));
    return r;
}

const RoomDzb& sea_dzb() {
    static RoomDzb d = read_room_dzb(tww_engine::testing::golden("sea_r41_bgd.json"));
    return d;
}

/// sea r41, where the dilation is reached.
Room& sea() {
    static Room r(sea_dzb());
    return r;
}

/// sea r41's candidates minus what dBgW refuses, derived from the room's tables:
/// poly -> cBgD_Tri_t::id -> cBgD_Ti_t::mPolyInf3, and the depth-2 group's m_info.
const std::vector<Candidate>& sea_candidates() {
    static std::vector<Candidate> kept;
    if (!kept.empty()) {
        return kept;
    }
    const RoomDzb& d = sea_dzb();
    std::set<int> refused;
    for (size_t i = 0; i < d.t_tbl.size(); i++) {
        const u16 id = d.t_tbl[i].id;
        if (id < d.ti_tbl.size() && (d.ti_tbl[id].mPolyInf3 & 0x04)) {
            refused.insert((int)i);
        }
    }
    const int root = sea().bgw().m_rootGrpIdx;
    std::vector<int> skip;
    for (u16 g = d.g_tbl[(size_t)root].m_first_child; g != 0xFFFF;
         g = d.g_tbl[g].m_next_sibling) {
        if (d.g_tbl[g].m_info & 0x80700) {
            skip.push_back((int)g);
        }
    }
    for (size_t n = 0; n < skip.size(); n++) {
        const int g = skip[n];
        for (u16 ch = d.g_tbl[(size_t)g].m_first_child; ch != 0xFFFF;
             ch = d.g_tbl[ch].m_next_sibling) {
            skip.push_back((int)ch);
        }
        for (size_t i = 0; i < d.t_tbl.size(); i++) {
            if ((int)d.t_tbl[i].grp == g) {
                refused.insert((int)i);
            }
        }
    }
    const std::vector<Candidate> all = candidates("sea_r41_floors.json");
    for (size_t i = 0; i < all.size(); i++) {
        if (refused.find(all[i].poly) == refused.end()) {
            kept.push_back(all[i]);
        }
    }
    return kept;
}

/// One row of the chosen-probe corpus: the probe (post-move XZ, pre-move Y; see
/// test_ground_walk.cpp) and the poly it answered with.
struct SeaRow {
    cXyz probe;
    int floor_tri;
};

const std::vector<SeaRow>& sea_rows() {
    static std::vector<SeaRow> all;
    static bool done = false;
    if (done) {
        return all;
    }
    done = true;
    const Json& g = tww_engine::testing::golden("sea_r41_ground_live.json")["rows"];
    for (size_t i = 0; i < g.size(); i++) {
        if (g[i]["floor_bg"].as_int() != 0) {
            continue;
        }
        SeaRow r;
        r.probe.x = g[i]["pos_x"].as_f32();
        r.probe.y = g[i]["pre_y"].as_f32() + g[i]["ground_check_offset"].as_f32() -
                    g[i]["ground_up_h"].as_f32() + g[i]["ground_up_h_diff"].as_f32();
        r.probe.z = g[i]["pos_z"].as_f32();
        r.floor_tri = (int)g[i]["floor_tri"].as_int();
        all.push_back(r);
    }
    return all;
}

struct Frame {
    f32 x, y, z;
    int floor_tri;
    std::string where;
};

/// The kaze frames: every row of the two captures in that room, with the console's poly.
const std::vector<Frame>& kaze_frames() {
    static std::vector<Frame> all;
    if (!all.empty()) {
        return all;
    }
    static const char* const kCaps[] = {"setup_finder_demo_live.json",
                                        "setup_finder_sword_live.json"};
    for (const char* name : kCaps) {
        const Json& g = tww_engine::testing::golden(name);
        for (size_t i = 0; i < g.size(); i++) {
            Frame f;
            f.x = g[i]["pos_x"].as_f32();
            f.y = g[i]["pos_y"].as_f32();
            f.z = g[i]["pos_z"].as_f32();
            f.floor_tri = g[i]["floor_tri"].as_int();
            f.where = std::string(name) + " frame " + std::to_string(i);
            all.push_back(f);
        }
    }
    return all;
}

const std::vector<Frame>& ganona_frames() {
    static std::vector<Frame> all;
    if (!all.empty()) {
        return all;
    }
    const Json& g = tww_engine::testing::golden("seam255_rest_golden.json")["frames"];
    for (size_t i = 0; i < g.size(); i++) {
        Frame f;
        f.x = g[i]["pos_x"].as_f32();
        f.y = g[i]["pos_y"].as_f32();
        f.z = g[i]["pos_z"].as_f32();
        f.floor_tri = -1;  //: this capture records the height, not the poly
        f.where = "seam255_rest_golden.json frame " + std::to_string(i);
        all.push_back(f);
    }
    return all;
}

cXyz probe_of(const Frame& f) {
    cXyz p;
    p.x = f.x;
    p.y = f.y + kGroundCheckOffset;
    p.z = f.z;
    return p;
}

// ------------------------------------------------------------------- the variant harness

enum class Variant {
    None,          //: the ported path, unchanged
    XzOrder,       //: the 2d test taken in (x, z) rather than the decomp's (z, x)
    CwWinding,     //: the three edges taken the other way round
    AnyEdge,       //: inside when any edge accepts, instead of all three
    NoDilate,      //: the -20.0f edge dilation dropped to 0.0f
    NoBox,         //: cM3d_InclusionCheckPosIn3PosBox2d skipped
    NoMinusD,      //: getCrossY_NonIsZero without its `- mD`
    NoMinusNx,     //: without the leading minus on the nx term
    NoMinusNz,     //: with `+ mNormal.z * i_axis.z`
    CrossYDouble,  //: the whole plane expression in f64, rounded once at the end
};

f32 cross_y(const cM3dGPla& pla, const cXyz& p, Variant var) {
    const cXyz& n = *pla.GetNP();
    switch (var) {
        case Variant::NoMinusD:
            return (-n.x * p.x - n.z * p.z) / n.y;
        case Variant::NoMinusNx:
            return (n.x * p.x - n.z * p.z - pla.GetD()) / n.y;
        case Variant::NoMinusNz:
            return (-n.x * p.x + n.z * p.z - pla.GetD()) / n.y;
        case Variant::CrossYDouble:
            return (f32)((-(double)n.x * (double)p.x - (double)n.z * (double)p.z -
                          (double)pla.GetD()) /
                         (double)n.y);
        default:
            return (-n.x * p.x - n.z * p.z - pla.GetD()) / n.y;
    }
}

bool inside(const Vec& a, const Vec& b, const Vec& cc, const cXyz& p, Variant var) {
    const f32 dil = var == Variant::NoDilate ? 0.0f : -20.0f;
    // The decomp takes both the box and the edges in (z, x), in that argument order.
    f32 a1 = a.z, a2 = a.x, b1 = b.z, b2 = b.x, c1 = cc.z, c2 = cc.x, p1 = p.z, p2 = p.x;
    if (var == Variant::XzOrder) {
        a1 = a.x; a2 = a.z; b1 = b.x; b2 = b.z; c1 = cc.x; c2 = cc.z; p1 = p.x; p2 = p.z;
    }
    if (var != Variant::NoBox) {
        f32 lo = a1 < b1 ? a1 : b1;
        f32 hi = a1 < b1 ? b1 : a1;
        if (lo > c1) { lo = c1; } else if (hi < c1) { hi = c1; }
        if (lo > p1 || hi < p1) {
            return false;
        }
        lo = a2 < b2 ? a2 : b2;
        hi = a2 < b2 ? b2 : a2;
        if (lo > c2) { lo = c2; } else if (hi < c2) { hi = c2; }
        if (lo > p2 || hi < p2) {
            return false;
        }
    }
    f32 e0, e1, e2;
    if (var == Variant::CwWinding) {
        e0 = cM3d_VectorProduct2d(c1, c2, b1, b2, p1, p2);
        e1 = cM3d_VectorProduct2d(b1, b2, a1, a2, p1, p2);
        e2 = cM3d_VectorProduct2d(a1, a2, c1, c2, p1, p2);
    } else {
        e0 = cM3d_VectorProduct2d(a1, a2, b1, b2, p1, p2);
        e1 = cM3d_VectorProduct2d(b1, b2, c1, c2, p1, p2);
        e2 = cM3d_VectorProduct2d(c1, c2, a1, a2, p1, p2);
    }
    if (var == Variant::AnyEdge) {
        return e0 >= dil || e1 >= dil || e2 >= dil;
    }
    return e0 >= dil && e1 >= dil && e2 >= dil;
}

/// RwgGroundCheckCommon's decision with one piece swappable: the running maximum, the strict
/// `>`, the `y < probe.y` test, over the candidates in capture order.
f32 ground_cross_variant(const std::vector<Candidate>& polys, const cXyz& probe, int* out_poly,
                         Variant var) {
    f32 now = -G_CM3D_F_INF;
    int hit = 0xFFFF;
    for (const Candidate& p : polys) {
        cM3dGPla pla;
        pla.mNormal = p.n;
        pla.mD = p.d;
        const f32 y = cross_y(pla, probe, var);
        if (y < probe.y && y > now && inside(p.v[0], p.v[1], p.v[2], probe, var)) {
            now = y;
            hit = p.poly;
        }
    }
    if (out_poly != nullptr) {
        *out_poly = hit;
    }
    return now;
}

/// How many kaze frames the variant puts on the wrong triangle.
int kaze_wrong(Variant var) {
    static const std::vector<Candidate> polys = candidates("kaze_r11_floors.json");
    int bad = 0;
    for (const Frame& f : kaze_frames()) {
        int got = 0;
        ground_cross_variant(polys, probe_of(f), &got, var);
        if (got != f.floor_tri) {
            bad++;
        }
    }
    return bad;
}

/// How many GanonA frames the variant puts at the wrong height, to the bit.
int ganona_wrong(Variant var) {
    static const std::vector<Candidate> polys = candidates("ganona_r0_floors.json");
    int bad = 0;
    for (const Frame& f : ganona_frames()) {
        const f32 got = ground_cross_variant(polys, probe_of(f), nullptr, var);
        if (tww_engine::testing::bits(got) != tww_engine::testing::bits(f.y)) {
            bad++;
        }
    }
    return bad;
}

/// How many sea rows the variant puts on the wrong triangle, not counting rows the unmutated
/// harness already gets wrong.
int sea_wrong(Variant var) {
    const std::vector<Candidate>& kz = sea_candidates();
    int bad = 0;
    for (const SeaRow& row : sea_rows()) {
        int base = 0, got = 0;
        ground_cross_variant(kz, row.probe, &base, Variant::None);
        if (base != row.floor_tri) {
            continue;
        }
        ground_cross_variant(kz, row.probe, &got, var);
        if (got != row.floor_tri) {
            bad++;
        }
    }
    return bad;
}

void expect_kaze_matches(Case& c, Variant var, const char* what) {
    const int bad = kaze_wrong(var);
    c.note(std::string(what) + ": " + std::to_string(bad) + " of " +
           std::to_string(kaze_frames().size()) + " frames on the wrong triangle");
    REQUIRE_INT(c, bad, 0, std::string("frames ") + what + " gets wrong");
}

void expect_ganona_matches(Case& c, Variant var, const char* what) {
    const int bad = ganona_wrong(var);
    c.note(std::string(what) + ": " + std::to_string(bad) + " of " +
           std::to_string(ganona_frames().size()) + " ground heights wrong");
    REQUIRE_INT(c, bad, 0, std::string("heights ") + what + " gets wrong");
}

}  // namespace

TWWE_TEST(the_ground_variant_harness_is_the_ported_walk,
          "the red controls below swap one piece of a local copy of the per-polygon test, and "
          "that copy no longer answers as Room::GroundCross does - so what they are evidence "
          "about is the copy, not the port") {
    // Compared against `Room`, so each variant's count is frames the gated walk would get wrong.
    // The two sides differ both in the loop and in flat list versus octree.
    static const std::vector<Candidate> kz = candidates("kaze_r11_floors.json");
    static const std::vector<Candidate> ga = candidates("ganona_r0_floors.json");
    REQUIRE_INT(c, (int)kz.size(), 332, "kaze r11 recorded candidates");
    REQUIRE_INT(c, (int)ga.size(), 100, "GanonA r0 recorded candidates");
    int differ = 0;
    for (const Frame& f : kaze_frames()) {
        int a = 0, b = 0;
        const f32 ya = kaze().GroundCross(probe_of(f), &a);
        const f32 yb = ground_cross_variant(kz, probe_of(f), &b, Variant::None);
        if (a != b || tww_engine::testing::bits(ya) != tww_engine::testing::bits(yb)) {
            differ++;
        }
    }
    for (const Frame& f : ganona_frames()) {
        int a = 0, b = 0;
        const f32 ya = ganona().GroundCross(probe_of(f), &a);
        const f32 yb = ground_cross_variant(ga, probe_of(f), &b, Variant::None);
        if (a != b || tww_engine::testing::bits(ya) != tww_engine::testing::bits(yb)) {
            differ++;
        }
    }
    REQUIRE_INT(c, differ, 0, "frames where the variant harness and the ported walk disagree");
    REQUIRE_TRUE(c, kaze_frames().size() == 1082 && ganona_frames().size() == 30,
                 "the two frame corpora are not the 1,082 and 30 rows the captures hold - a "
                 "harness that reproduces the walk on an empty population reads the same green");
    c.note("the harness reproduces Room::GroundCross on all " +
           std::to_string(kaze_frames().size() + ganona_frames().size()) + " frames");
}

TWWE_TEST(the_candidate_order_is_not_what_these_controls_hold,
          "reversing the harness's candidate order changed an answer - which would mean the red "
          "controls below are counting an order effect, and the recorded traversal order the "
          "harness happens to carry would be doing work the harness does not name") {
    static std::vector<Candidate> kz = candidates("kaze_r11_floors.json");
    std::vector<Candidate> rev(kz.rbegin(), kz.rend());
    int differ = 0;
    for (const Frame& f : kaze_frames()) {
        int a = 0, b = 0;
        ground_cross_variant(kz, probe_of(f), &a, Variant::None);
        ground_cross_variant(rev, probe_of(f), &b, Variant::None);
        if (a != b) {
            differ++;
        }
    }
    REQUIRE_INT(c, differ, 0, "frames whose triangle changes when the candidates are reversed");
    c.note("order-independent on all " + std::to_string(kaze_frames().size()) +
           " frames: no two accepted candidates are ever at the same height here");
}

TWWE_TEST(the_edge_dilation_is_reached_by_the_chosen_probes,
          "the sea r41 rows stopped coming within the -20.0f edge band - which would put the "
          "dilation back where it was, copied and reached by nothing, and would make the red "
          "control below a control over a constant no row exercises") {
    // Over the kaze frames the closest approach to any candidate edge is 836 area-units, 42 times
    // outside the band.
    static const std::vector<Candidate> kz = candidates("kaze_r11_floors.json");
    f32 walked_accepted = 1.0e30f;
    for (const Frame& f : kaze_frames()) {
        const cXyz p = probe_of(f);
        for (const Candidate& g : kz) {
            const f32 e0 = cM3d_VectorProduct2d(g.v[0].z, g.v[0].x, g.v[1].z, g.v[1].x, p.z, p.x);
            const f32 e1 = cM3d_VectorProduct2d(g.v[1].z, g.v[1].x, g.v[2].z, g.v[2].x, p.z, p.x);
            const f32 e2 = cM3d_VectorProduct2d(g.v[2].z, g.v[2].x, g.v[0].z, g.v[0].x, p.z, p.x);
            f32 w = e0 < e1 ? e0 : e1;
            w = w < e2 ? w : e2;
            if (w >= -20.0f) {
                walked_accepted = w < walked_accepted ? w : walked_accepted;
            }
        }
    }

    // The sea probes sit just outside a candidate, so only the dilation lets them in.
    f32 accepted = 1.0e30f, rejected = -1.0e30f;
    int in_band = 0;
    for (const SeaRow& row : sea_rows()) {
        bool hit = false;
        for (const Candidate& g : sea_candidates()) {
            const f32 e0 = cM3d_VectorProduct2d(g.v[0].z, g.v[0].x, g.v[1].z, g.v[1].x,
                                                row.probe.z, row.probe.x);
            const f32 e1 = cM3d_VectorProduct2d(g.v[1].z, g.v[1].x, g.v[2].z, g.v[2].x,
                                                row.probe.z, row.probe.x);
            const f32 e2 = cM3d_VectorProduct2d(g.v[2].z, g.v[2].x, g.v[0].z, g.v[0].x,
                                                row.probe.z, row.probe.x);
            f32 w = e0 < e1 ? e0 : e1;
            w = w < e2 ? w : e2;
            if (w >= -20.0f) {
                accepted = w < accepted ? w : accepted;
                hit = hit || w < 0.0f;
            } else {
                rejected = w > rejected ? w : rejected;
            }
        }
        in_band += hit ? 1 : 0;
    }
    c.note("walked: closest accepted " + std::to_string(walked_accepted) +
           " - the whole corpus is outside the band. chosen: closest accepted " +
           std::to_string(accepted) + ", closest rejected " + std::to_string(rejected) + "; " +
           std::to_string(in_band) + " of " + std::to_string(sea_rows().size()) +
           " rows have a candidate inside [-20, 0)");
    REQUIRE_TRUE(c, walked_accepted > 0.0f,
                 "a walked frame is inside the band after all, so the two corpora are not "
                 "reaching different things and this case is describing one of them wrongly");
    REQUIRE_TRUE(c, in_band > 0 && accepted < 0.0f && accepted >= -20.0f,
                 "no chosen probe is inside the -20 band, so the constant is still copied and "
                 "reached by nothing");
}

TWWE_RED_CONTROL(red_ground_edge_dilation_dropped,
                 "cM3d_CrossY_Tri_Front's -20.0f edge dilation dropped to 0.0f, so a probe is "
                 "inside a triangle only when it is strictly inside it. The two walked rooms "
                 "cannot see this - their closest approach to an edge is 836 area-units, a "
                 "factor of 42 outside the band - and it is the constant the third room's corpus "
                 "was chosen to reach") {
    const int bad = sea_wrong(Variant::NoDilate);
    c.note("the dilation dropped to 0: " + std::to_string(bad) + " of " +
           std::to_string(sea_rows().size()) + " chosen-probe rows on the wrong triangle");
    REQUIRE_INT(c, bad, 0, "rows the -20 dilation gets wrong when it is removed");
}

TWWE_RED_CONTROL(red_ground_2d_test_in_xz_instead_of_zx,
                 "cM3d_CrossY_Tri_Front's box and edge tests taken in (x, z). The decomp passes "
                 "(z, x) - r3.z, r3.x, r4.z, r4.x ... - and swapping them negates every vector "
                 "product, which turns the whole mesh inside out") {
    expect_kaze_matches(c, Variant::XzOrder, "the 2d test in (x,z)");
}

TWWE_RED_CONTROL(red_ground_triangle_wound_the_other_way,
                 "the three edges taken C->B, B->A, A->C. Same triangle, opposite sign on every "
                 "vector product, so the test accepts exactly the outside") {
    expect_kaze_matches(c, Variant::CwWinding, "the winding reversed");
}

TWWE_RED_CONTROL(red_ground_inside_on_any_edge,
                 "inside when any of the three edges accepts rather than all three - the "
                 "half-plane intersection turned into a union, which admits every triangle whose "
                 "plane the probe is on the correct side of for one edge") {
    expect_kaze_matches(c, Variant::AnyEdge, "any edge instead of all three");
}

TWWE_RED_CONTROL(red_ground_plane_without_its_offset,
                 "getCrossY_NonIsZero without `- mD`. The plane's distance term is what turns a "
                 "normal into a height, and without it every candidate crosses at the same "
                 "near-zero y") {
    expect_kaze_matches(c, Variant::NoMinusD, "getCrossY without `- mD`");
}

TWWE_RED_CONTROL(red_ground_plane_nx_sign,
                 "getCrossY_NonIsZero's leading minus on the nx term, dropped. Invisible on kaze, "
                 "whose floors are (0,1,0) - this is the control that needed a slope, and the "
                 "GanonA incline sees it on every one of its 30 frames") {
    expect_ganona_matches(c, Variant::NoMinusNx, "getCrossY's minus on nx");
}

TWWE_RED_CONTROL(red_ground_plane_nz_sign,
                 "getCrossY_NonIsZero's minus on the nz term, flipped to a plus. Same class as "
                 "the nx one and equally invisible on a flat floor") {
    expect_ganona_matches(c, Variant::NoMinusNz, "getCrossY's minus on nz");
}

TWWE_RED_CONTROL(red_ground_plane_in_double_precision,
                 "the plane expression evaluated in double and rounded once at the end. Every "
                 "operand is f32 and the answer is f32, so this looks like a free accuracy "
                 "improvement; the Gekko rounded after each operation and the console's own "
                 "heights say so on 6 of the GanonA incline's 30 frames") {
    expect_ganona_matches(c, Variant::CrossYDouble, "the plane expression in f64");
}

TWWE_RED_CONTROL(red_ground_triangle_box_check_dropped,
                 "cM3d_CrossY_Tri_Front's opening cM3d_InclusionCheckPosIn3PosBox2d skipped, so "
                 "the three dilated edges decide alone. They are a bounded region on their own - "
                 "the triangle pushed out by 20/|AB| per edge - so this looks like a redundant "
                 "early-out, and it is not: an acute corner's miter runs far past the triangle's "
                 "own box, and the box is what cuts it off") {
    // The box test also bounds the node-box margin: no candidate is taken from outside its own
    // triangle's xz box. The walked rooms do not see it.
    const int bad = sea_wrong(Variant::NoBox);
    c.note("the triangle's own box test skipped: " + std::to_string(bad) + " of " +
           std::to_string(sea_rows().size()) + " chosen-probe rows on the wrong triangle (kaze " +
           std::to_string(kaze_wrong(Variant::NoBox)) + " of " +
           std::to_string(kaze_frames().size()) + " and GanonA " +
           std::to_string(ganona_wrong(Variant::NoBox)) + " of " +
           std::to_string(ganona_frames().size()) + ": a walk cannot see this one either)");
    REQUIRE_INT(c, bad, 0, "rows the triangle's own box test gets wrong when it is removed");
}
