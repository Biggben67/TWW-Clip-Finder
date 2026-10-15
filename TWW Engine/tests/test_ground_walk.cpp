// test_ground_walk.cpp - the ground check's octree descent (cBgW::GroundCrossGrpRp /
// GroundCrossRp, child order 2,3,6,7,0,1,4,5) and its load-time build (CalcPlane,
// ClassifyPlane/BlckConnect, MakeNodeTree), held to console captures in three rooms.
//
// The room is the disc's .dzb (kaze_r11_bgd.json etc.): input, not an oracle. Pinned:
//   planes  CalcPlane's output against pm_tri read out of RAM (kaze_r11_floors.json,
//           kaze_r11_walls_ordered.json), bit for bit, through cBgD_Tri_t's vertex indices;
//   chains  ClassifyPlane's per-block ground/wall split against the floors capture;
//   answer  the poly (kaze r11) and the height (GanonA r0 incline) of console frames.
// kaze r11's floors are flat, so getCrossY_NonIsZero's nx/nz terms are zero there. dBgW's two
// refusals decide nothing in those two rooms (every mPolyInf3 is zero); sea r41 is where they do.
// tests/recorded_list.h is a control: the same per-polygon test over the recorded candidates.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "SSystem/SComponent/c_m3d.h"
#include "engine/room.h"
#include "recorded_list.h"
#include "room_dzb.h"

namespace {

using tww_engine::Room;
using tww_engine::RoomDzb;
using tww_engine::testing::bits;
using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::RecordedList;
using tww_engine::testing::RecordedPoly;
using tww_engine::testing::read_room_dzb;

//: d_bg_s_acch.cpp:59-60, :128
const f32 kGroundCheckOffset = 60.0f;

/// One row of the console's pm_tri: the three vertices fed to cM3d_CalcPla and the plane stored.
struct ConsolePoly {
    bool have = false;
    Vec v[3];
    cXyz n;
    f32 d = 0.0f;

    bool same_as(const ConsolePoly& o) const {
        for (int k = 0; k < 3; k++) {
            if (bits(v[k].x) != bits(o.v[k].x) || bits(v[k].y) != bits(o.v[k].y) ||
                bits(v[k].z) != bits(o.v[k].z)) {
                return false;
            }
        }
        return bits(n.x) == bits(o.n.x) && bits(n.y) == bits(o.n.y) &&
               bits(n.z) == bits(o.n.z) && bits(d) == bits(o.d);
    }
};

/// One room's .dzb, its built Room and its console captures.
///   kaze r11    1,082 console frames on flat floors: holds the poly choice.
///   GanonA r0   30 frames on a micro-incline: holds the height.
class Fixture {
  public:
    Fixture(const char* bgd, const char* floors, const char* walls)
        : m_bgd(bgd), m_floors(floors), m_walls(walls) {}

    RoomDzb& dzb() {
        if (m_dzb.t_tbl.empty()) {
            m_dzb = read_room_dzb(tww_engine::testing::golden(m_bgd));
        }
        return m_dzb;
    }

    Room& room() {
        if (!m_room) {
            m_room.reset(new Room(dzb()));
        }
        return *m_room;
    }

/// The console's pm_tri rows, floors and walls together, keyed by the game's poly index. The
/// two captures overlap (wall polys with ny >= 0.014f are in both) and were taken on different
/// runs; `overlap_conflicts()` counts rows whose two readings differ.
    const std::vector<ConsolePoly>& console_polys() {
        if (!m_console.empty()) {
            return m_console;
        }
        m_console.resize(dzb().t_tbl.size());
        const char* const caps[] = {m_floors, m_walls};
        for (const char* name : caps) {
            const Json& polys = tww_engine::testing::golden(name)["polys"];
            for (size_t i = 0; i < polys.size(); i++) {
                const ConsolePoly p = read_console_poly(polys[i]);
                ConsolePoly& slot = m_console[(size_t)polys[i]["poly"].as_int()];
                if (slot.have) {
                    m_overlap++;
                    if (!slot.same_as(p)) {
                        m_overlap_conflicts++;
                    }
                }
                slot = p;
            }
        }
        return m_console;
    }

    int overlap() { console_polys(); return m_overlap; }
    int overlap_conflicts() { console_polys(); return m_overlap_conflicts; }

/// The floors capture's poly list in capture order, which is the traversal's own: group DFS,
/// octree DFS in GroundCrossRp's child order, then per leaf the ground polys and the wall polys
/// with ny >= 0.014f.
    const std::vector<int>& floors_order() {
        if (m_order.empty()) {
            const Json& polys = tww_engine::testing::golden(m_floors)["polys"];
            for (size_t i = 0; i < polys.size(); i++) {
                m_order.push_back((int)polys[i]["poly"].as_int());
            }
        }
        return m_order;
    }

/// A poly's block from cBgD_Blk_t::startTri, by ClassifyPlane's ranges (c_bg_w.cpp:151-155):
/// block i owns [startTri(i), startTri(i+1) - 1] and the last owns the tail.
    int block_of(int poly) {
        const std::vector<cBgD_Blk_t>& b = dzb().b_tbl;
        int found = -1;
        for (size_t i = 0; i < b.size(); i++) {
            const int lo = b[i].startTri;
            const int hi = (i + 1 < b.size()) ? (int)b[i + 1].startTri - 1
                                              : (int)dzb().t_tbl.size() - 1;
            if (poly >= lo && poly <= hi) {
                found = (int)i;
            }
        }
        return found;
    }

/// The same room with the candidates as the capture recorded them: the differential control.
    RecordedList& stand_in() {
        if (!m_stand_in) {
            std::vector<RecordedPoly> rows;
            const Json& polys = tww_engine::testing::golden(m_floors)["polys"];
            for (size_t i = 0; i < polys.size(); i++) {
                const ConsolePoly cp = read_console_poly(polys[i]);
                RecordedPoly g;
                g.poly = (int)polys[i]["poly"].as_int();
                for (int k = 0; k < 3; k++) {
                    g.v[k] = cp.v[k];
                }
                g.n = cp.n;
                g.d = cp.d;
                rows.push_back(g);
            }
            m_stand_in.reset(new RecordedList(rows));
        }
        return *m_stand_in;
    }

/// One probe 100 u above each candidate's centroid. The console frames stand on a handful of
/// blocks; these reach every leaf the floors capture names (ChainsShortByOne is caught only here).
    const std::vector<cXyz>& centroid_probes() {
        if (!m_probes.empty()) {
            return m_probes;
        }
        for (int poly : floors_order()) {
            const ConsolePoly& p = console_polys()[(size_t)poly];
            cXyz q;
            q.x = (p.v[0].x + p.v[1].x + p.v[2].x) / 3.0f;
            q.y = (p.v[0].y + p.v[1].y + p.v[2].y) / 3.0f + 100.0f;
            q.z = (p.v[0].z + p.v[1].z + p.v[2].z) / 3.0f;
            m_probes.push_back(q);
        }
        return m_probes;
    }

  private:
    static ConsolePoly read_console_poly(const Json& r) {
        ConsolePoly p;
        p.have = true;
        for (int k = 0; k < 3; k++) {
            p.v[k].x = r["v"][k][0].as_f32();
            p.v[k].y = r["v"][k][1].as_f32();
            p.v[k].z = r["v"][k][2].as_f32();
        }
        p.n.x = r["n"][0].as_f32();
        p.n.y = r["n"][1].as_f32();
        p.n.z = r["n"][2].as_f32();
        p.d = r["d"].as_f32();
        return p;
    }

    const char* m_bgd;
    const char* m_floors;
    const char* m_walls;
    RoomDzb m_dzb;
    std::unique_ptr<Room> m_room;
    std::unique_ptr<RecordedList> m_stand_in;
    std::vector<ConsolePoly> m_console;
    std::vector<int> m_order;
    std::vector<cXyz> m_probes;
    int m_overlap = 0;
    int m_overlap_conflicts = 0;
};

Fixture& kaze() {
    static Fixture f("kaze_r11_bgd.json", "kaze_r11_floors.json", "kaze_r11_walls_ordered.json");
    return f;
}

Fixture& ganona() {
    static Fixture f("ganona_r0_bgd.json", "ganona_r0_floors.json",
                     "ganona_r0_walls_ordered.json");
    return f;
}

/// sea r41 (Forest Haven outdoors): its attribute tables are not all zero, so dBgW's refusals
/// decide something, and its probes were placed rather than walked, which reaches the -20 edge
/// band and the node-box margin.
Fixture& sea() {
    static Fixture f("sea_r41_bgd.json", "sea_r41_floors.json", "sea_r41_walls_ordered.json");
    return f;
}

struct Frame {
    f32 x, y, z;
    int floor_tri;
    std::string where;
};

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
            f.floor_tri = (int)g[i]["floor_tri"].as_int();
            f.where = std::string(name) + " frame " + std::to_string(i);
            all.push_back(f);
        }
    }
    return all;
}

/// seam255_rest_golden.json: 30 frames on the GanonA r0 incline. No floor_tri; pos_y is
/// GroundCheck's own return value, so each row is a captured height.
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

/// sea_r41_ground_live.json. A row is one ground check: the poly left in +0x554 and
/// `dBgS_Acch::m_ground_h`, which is `cBgS::GroundCross`'s return value.
/// The probe uses `pre`, not `pos`: `dBgS_Acch::GroundCheck` writes `pm_pos->y` from its own
/// answer, so the post-frame position is the check's output.
int g_sea_off_room = -1;
std::vector<std::string> g_sea_cls;
std::vector<int> g_sea_proc;
std::vector<f32> g_sea_height;

/// One row's probe and both halves of the console's answer.
struct SeaRow {
    cXyz probe;
    int floor_tri;
    f32 ground_h;
    std::string where;
};

const std::vector<SeaRow>& sea_rows() {
    static std::vector<SeaRow> all;
    if (g_sea_off_room >= 0) {
        return all;
    }
    g_sea_off_room = 0;
    const Json& g = tww_engine::testing::golden("sea_r41_ground_live.json")["rows"];
    for (size_t i = 0; i < g.size(); i++) {
        // floor_bg != 0 is an actor's collision; this port has one room and no actors, so the
        // row is counted and skipped.
        if (g[i]["floor_bg"].as_int() != 0) {
            g_sea_off_room++;
            continue;
        }
        SeaRow r;
        // The probe is the post-move xz and the pre-move y. The frame runs: xz move, ground
        // check, y snap from the answer, gravity. A walking Link sits at the fixed point, where
        // every pairing agrees; falling and sliding rows tell them apart.
        r.probe.x = g[i]["pos_x"].as_f32();
        r.probe.y = g[i]["pre_y"].as_f32() + g[i]["ground_check_offset"].as_f32() -
                    g[i]["ground_up_h"].as_f32() + g[i]["ground_up_h_diff"].as_f32();
        r.probe.z = g[i]["pos_z"].as_f32();
        r.floor_tri = (int)g[i]["floor_tri"].as_int();
        r.ground_h = g[i]["ground_h"].as_f32();
        r.where = "sea_r41_ground_live.json row " + std::to_string(i) + " (" + g[i]["cls"].str +
                  " step " + std::to_string(g[i]["step"].as_int()) + ")";
        all.push_back(r);
        g_sea_cls.push_back(g[i]["cls"].str);
        g_sea_proc.push_back((int)g[i]["proc"].as_int());
    }
    return all;
}

int sea_off_room_rows() {
    sea_rows();
    return g_sea_off_room;
}

cXyz probe_of(const Frame& f) {
    cXyz p;
    p.x = f.x;
    p.y = f.y + kGroundCheckOffset;
    p.z = f.z;
    return p;
}

// ------------------------------------------------------------------ what this gate can catch
//
// The copied bodies cannot be edited, so each variant perturbs an input or a built table:
//   a reader variant is a plausible misreading of the .dzb layout;
//   a table variant asks whether an arm of the copied code is reached by this data at all.
//
// Two reader mistakes cannot be controls because they crash rather than fail: children read one
// slot early (a node becomes its own ancestor's child and GroundCrossRp overflows the stack), and
// a leaf's block taken from mChild[1] (0xFFFF on every leaf; pm_blk[] is subscripted unchecked).
// The decomp trusts its disc tables completely.

enum class Variant {
    None,
    //: reader - group fields read as [parent, first_child, next_sibling, tree_idx]; they are
    //: [parent, next_sibling, first_child, tree_idx], at 0x24, 0x26, 0x28, 0x2E.
    GroupChildSiblingSwapped,
    //: reader - cBgD_Tri_t's second and third vertex indices exchanged: same shape, reversed
    //: winding, so CalcPlane negates the normal.
    TriangleVerticesSwapped,
    //: reader - every block's startTri shifted by one.
    BlockStartsShifted,
    //: order - each branch's eight child slots rotated by one: same visited set, other order.
    TreeChildrenRotated,
    //: table - every node box +/-infinity in y, so UnderPlaneYUnder and TopPlaneYUnder never
    //: prune.
    NodeBoxesUnboundedY,
    //: table - every node box shrunk by the 1.0 MakeBlckBnd adds per axis. Exact on branches
    //: too; asserted in the_box_margin_is_reached_through_the_Y_predicates.
    NodeBoxesUnexpanded,
    //: table - every node box emptied; the descent must find nothing.
    NodeBoxesEmpty,
    //: table - each block's ground and wall chain heads swapped, which moves the ny >= 0.014f
    //: gate onto the wrong chain.
    ChainHeadsSwapped,
    //: table - ClassifyPlane's loop as `j < lastTri`: each block's last triangle enters no
    //: chain while MakeBlckBnd's box still covers it.
    ChainsShortByOne,
    //: table - BlckConnect's `if (*rwg == 0xFFFF)` guard dropped, so each head ends up at the
    //: last poly.
    ChainHeadIsTheLast,
};

RoomDzb mutated_dzb(Fixture& fx, Variant var) {
    RoomDzb d = fx.dzb();
    switch (var) {
        case Variant::GroupChildSiblingSwapped:
            for (cBgD_Grp_t& g : d.g_tbl) {
                const u16 t = g.m_first_child;
                g.m_first_child = g.m_next_sibling;
                g.m_next_sibling = t;
            }
            break;
        case Variant::TriangleVerticesSwapped:
            for (cBgD_Tri_t& t : d.t_tbl) {
                const u16 v = t.vtx1;
                t.vtx1 = t.vtx2;
                t.vtx2 = v;
            }
            break;
        case Variant::BlockStartsShifted:
            for (size_t i = 0; i + 1 < d.b_tbl.size(); i++) {
                d.b_tbl[i].startTri = d.b_tbl[i + 1].startTri;
            }
            break;
        case Variant::TreeChildrenRotated:
            for (cBgD_Tree_t& t : d.tree_tbl) {
                if (!(t.mFlag & 1)) {
                    const u16 first = t.mChild[0];
                    for (int k = 0; k < 7; k++) {
                        t.mChild[k] = t.mChild[k + 1];
                    }
                    t.mChild[7] = first;
                }
            }
            break;
        default:
            break;
    }
    return d;
}

void mutate_tables(Room& r, Variant var) {
    const int nodes = r.node_count();
    for (int i = 0; i < nodes; i++) {
        cXyz* mn = r.bgw().m_nt_tbl[i].GetMinP();
        cXyz* mx = r.bgw().m_nt_tbl[i].GetMaxP();
        switch (var) {
            case Variant::NodeBoxesUnboundedY:
                mn->y = -G_CM3D_F_INF;
                mx->y = G_CM3D_F_INF;
                break;
            case Variant::NodeBoxesUnexpanded:
                mn->x += 1.0f; mn->y += 1.0f; mn->z += 1.0f;
                mx->x -= 1.0f; mx->y -= 1.0f; mx->z -= 1.0f;
                break;
            case Variant::NodeBoxesEmpty:
                mn->x = mn->y = mn->z = G_CM3D_F_INF;
                mx->x = mx->y = mx->z = -G_CM3D_F_INF;
                break;
            default:
                break;
        }
    }
    if (var == Variant::ChainHeadsSwapped) {
        for (int b = 0; b < r.block_count(); b++) {
            const u16 t = r.bgw().pm_blk[b].ground;
            r.bgw().pm_blk[b].ground = r.bgw().pm_blk[b].wall;
            r.bgw().pm_blk[b].wall = t;
        }
    }
    if (var == Variant::ChainsShortByOne) {
        // Drop each block's last triangle from whichever chain holds it; the box still covers it.
        for (int b = 0; b < r.block_count(); b++) {
            const int hi = (b + 1 < r.block_count())
                               ? (int)r.bgw().pm_bgd->m_b_tbl[b + 1].startTri - 1
                               : r.tri_count() - 1;
            u16* head[2] = {&r.bgw().pm_blk[b].ground, &r.bgw().pm_blk[b].wall};
            for (int k = 0; k < 2; k++) {
                if (*head[k] == 0xFFFF) {
                    continue;
                }
                if ((int)*head[k] == hi) {
                    *head[k] = r.bgw().pm_rwg[hi].next;
                    continue;
                }
                u16 i = *head[k];
                while (r.bgw().pm_rwg[i].next != 0xFFFF) {
                    if ((int)r.bgw().pm_rwg[i].next == hi) {
                        r.bgw().pm_rwg[i].next = r.bgw().pm_rwg[hi].next;
                        break;
                    }
                    i = r.bgw().pm_rwg[i].next;
                }
            }
        }
    }
    if (var == Variant::ChainHeadIsTheLast) {
        for (int b = 0; b < r.block_count(); b++) {
            const std::vector<int> g = r.ground_chain(b);
            const std::vector<int> w = r.wall_chain(b);
            if (!g.empty()) {
                r.bgw().pm_blk[b].ground = (u16)g.back();
            }
            if (!w.empty()) {
                r.bgw().pm_blk[b].wall = (u16)w.back();
            }
        }
    }
}

/// Kaze frames on the wrong triangle, and centroid probes that differ from the recorded list,
/// kept apart because they reach different blocks.
struct Wrong {
    int frames = 0;
    int probes = 0;
    int total() const { return frames + probes; }
};

Wrong wrong_with(Fixture& fx, const std::vector<Frame>& frames, Variant var) {
    Room r(mutated_dzb(fx, var));
    mutate_tables(r, var);
    Wrong w;
    for (const Frame& f : frames) {
        int got = 0;
        r.GroundCross(probe_of(f), &got);
        if (got != f.floor_tri) {
            w.frames++;
        }
    }
    for (const cXyz& q : fx.centroid_probes()) {
        int a = 0, b = 0;
        const f32 ya = r.GroundCross(q, &a);
        const f32 yb = fx.stand_in().GroundCross(q, &b);
        if (a != b || bits(ya) != bits(yb)) {
            w.probes++;
        }
    }
    return w;
}

Wrong wrong_with(Variant var) {
    return wrong_with(kaze(), kaze_frames(), var);
}

/// sea r41 console rows only: its recorded list includes candidates dBgW refuses, so it is no
/// stand-in. Rows the unmutated room already misses are not counted.
int sea_wrong_with(Variant var) {
    Room r(mutated_dzb(sea(), var));
    mutate_tables(r, var);
    int bad = 0;
    for (const SeaRow& row : sea_rows()) {
        int base = 0, got = 0;
        sea().room().GroundCross(row.probe, &base);
        if (base != row.floor_tri) {
            continue;
        }
        r.GroundCross(row.probe, &got);
        if (got != row.floor_tri) {
            bad++;
        }
    }
    return bad;
}

void expect_wrong(Case& c, Variant var, const char* what) {
    const Wrong w = wrong_with(var);
    c.note(std::string(what) + ": " + std::to_string(w.frames) + " of " +
           std::to_string(kaze_frames().size()) + " frames and " + std::to_string(w.probes) +
           " of " + std::to_string(kaze().centroid_probes().size()) + " probes wrong");
    REQUIRE_INT(c, w.total(), 0, std::string("answers ") + what + " gets wrong");
}

// ------------------------------------------------ the 1.0 node-box margin, one arm at a time
//
// MakeBlckBnd grows a leaf's box by 1.0 per axis and MakeNodeTreeRp grows branches over those.
// Three predicates read the box, each monotone, so the margin can only add candidates:
//
//   CrossY            the probe's xz inside the box               the SKIRT arm
//   UnderPlaneYUnder  min.y < probe.y                             the LOW-Y arm
//   TopPlaneYUnder    max.y >= the best height found so far       the HIGH-Y arm
//
// The skirt arm cannot fire: cM3d_CrossY_Tri_Front first checks the triangle's own undilated xz
// box (cM3d_InclusionCheckPosIn3PosBox2d), and a block's raw box is the union of those boxes.
// The Y arms can, where a plane leaves its block's y range inside the -20 dilated region.
namespace margin {

using Pt = std::pair<double, double>;

/// Sutherland-Hodgman against one dilated edge, (Q.z-P.z)(x-P.x) - (Q.x-P.x)(z-P.z) >= -20
/// (cM3d_VectorProduct2d). Double, because this only searches; decisions use the port's f32.
std::vector<Pt> clip(const std::vector<Pt>& poly, const Vec& P, const Vec& Q) {
    std::vector<Pt> out;
    for (size_t i = 0; i < poly.size(); i++) {
        const Pt& p = poly[i];
        const Pt& q = poly[(i + 1) % poly.size()];
        const double fp = ((double)Q.z - P.z) * (p.first - P.x) -
                          ((double)Q.x - P.x) * (p.second - P.z) + 20.0;
        const double fq = ((double)Q.z - P.z) * (q.first - P.x) -
                          ((double)Q.x - P.x) * (q.second - P.z) + 20.0;
        if (fp >= 0.0) {
            out.push_back(p);
        }
        if ((fp >= 0.0) != (fq >= 0.0)) {
            const double t = fp / (fp - fq);
            out.push_back(Pt(p.first + t * (q.first - p.first),
                             p.second + t * (q.second - p.second)));
        }
    }
    return out;
}

/// One point where removing the margin changes the port's answer.
struct Probe {
    const char* arm;
    int blk, poly;
    cXyz at;
    f32 slack;          //: the largest xz step whose four neighbours still all decide
    int poly_with, poly_without;
    f32 h_with, h_without;
};

struct Arms {
    int leaves = 0;
    int cands = 0;
    int tris_outside_block_box = 0;
    int low_reach = 0, high_reach = 0;    //: candidates whose admitted region leaves the block's y
    int low_decides = 0, high_decides = 0;  //: probes where removing the margin changes the answer
    //: the LOW-Y probes retried at the top edge of the 1.0 window
    int low_decides_at_edge = 0;
    double worst_low = 0.0, worst_high = 0.0;
    //: every deciding probe, with its xz slack
    std::vector<Probe> named;
};

/// A float as decimal and its 32 bits; these probes sit in slivers 0.01 u wide.
std::string exact(f32 v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.9g [%08x]", (double)v, (unsigned)bits(v));
    return std::string(buf);
}

/// The largest xz step at which all four neighbours still answer differently with and without
/// the margin: the tolerance a placement has to beat.
f32 xz_slack(Room& full, Room& shrunk, const cXyz& probe) {
    static const f32 kSteps[] = {2.0f, 1.0f, 0.5f, 0.1f, 0.01f, 0.001f};
    for (f32 step : kSteps) {
        bool all = true;
        for (int k = 0; k < 4 && all; k++) {
            cXyz q = probe;
            const f32 d = (k % 2 == 0) ? step : -step;
            if (k < 2) {
                q.x += d;
            } else {
                q.z += d;
            }
            int wa = 0, wb = 0;
            const f32 ya = full.GroundCross(q, &wa);
            const f32 yb = shrunk.GroundCross(q, &wb);
            all = (wa != wb || bits(ya) != bits(yb));
        }
        if (all) {
            return step;
        }
    }
    return 0.0f;
}

/// The region cM3d_CrossY_Tri_Front admits for one polygon: its xz box clipped by the three
/// dilated edges. Returns the corners, where a linear function takes its extremes.
std::vector<Pt> admitted_region(const Vec& a, const Vec& b, const Vec& cc) {
    const double x0 = std::min(std::min(a.x, b.x), cc.x), x1 = std::max(std::max(a.x, b.x), cc.x);
    const double z0 = std::min(std::min(a.z, b.z), cc.z), z1 = std::max(std::max(a.z, b.z), cc.z);
    std::vector<Pt> r;
    r.push_back(Pt(x0, z0));
    r.push_back(Pt(x1, z0));
    r.push_back(Pt(x1, z1));
    r.push_back(Pt(x0, z1));
    r = clip(r, a, b);
    if (!r.empty()) {
        r = clip(r, b, cc);
    }
    if (!r.empty()) {
        r = clip(r, cc, a);
    }
    return r;
}

/// A corner pulled a thousandth of the way toward the region's middle, so the point handed to the
/// port is strictly inside the half-planes its own corner sits exactly on.
Pt inset(const std::vector<Pt>& region, size_t k) {
    double mx = 0.0, mz = 0.0;
    for (const Pt& p : region) {
        mx += p.first / (double)region.size();
        mz += p.second / (double)region.size();
    }
    return Pt(region[k].first + 0.001 * (mx - region[k].first),
              region[k].second + 0.001 * (mz - region[k].second));
}

Pt centre(const std::vector<Pt>& region) {
    double mx = 0.0, mz = 0.0;
    for (const Pt& p : region) {
        mx += p.first / (double)region.size();
        mz += p.second / (double)region.size();
    }
    return Pt(mx, mz);
}

/// The admitted region cut to where the plane's height is on one side of `level`. crossY is
/// linear in x and z, so the result stays convex and its centre is a usable probe.
std::vector<Pt> below(const std::vector<Pt>& region, const cM3dGPla& pla, f32 level, bool want_low) {
    const cXyz& n = *pla.GetNP();
    // (-nx*x - nz*z - d) / ny <= level, with ny > 0 for every candidate the chains admit.
    const double s = want_low ? 1.0 : -1.0;
    std::vector<Pt> out;
    for (size_t i = 0; i < region.size(); i++) {
        const Pt& p = region[i];
        const Pt& q = region[(i + 1) % region.size()];
        const double fp = s * ((double)level * n.y - (-(double)n.x * p.first -
                                                      (double)n.z * p.second - (double)pla.GetD()));
        const double fq = s * ((double)level * n.y - (-(double)n.x * q.first -
                                                      (double)n.z * q.second - (double)pla.GetD()));
        if (fp >= 0.0) {
            out.push_back(p);
        }
        if ((fp >= 0.0) != (fq >= 0.0)) {
            const double t = fp / (fp - fq);
            out.push_back(Pt(p.first + t * (q.first - p.first),
                             p.second + t * (q.second - p.second)));
        }
    }
    return out;
}

/// One node's box without the margin: the box over every vertex in its subtree. The built box
/// is exactly this plus 1.0 per face, branches included, since f32 subtraction is monotone.
struct Box {
    f32 mn[3];
    f32 mx[3];
};

Box raw_subtree(const RoomDzb& d, const Vec* vtx, int node) {
    Box b;
    for (int k = 0; k < 3; k++) {
        b.mn[k] = G_CM3D_F_INF;
        b.mx[k] = -G_CM3D_F_INF;
    }
    const cBgD_Tree_t& t = d.tree_tbl[(size_t)node];
    if (t.mFlag & 1) {
        if (t.mBlock == 0xFFFF) {
            return b;
        }
        const int lo = d.b_tbl[t.mBlock].startTri;
        const int hi = ((size_t)t.mBlock + 1 < d.b_tbl.size())
                           ? (int)d.b_tbl[(size_t)t.mBlock + 1].startTri - 1
                           : (int)d.t_tbl.size() - 1;
        for (int p = lo; p <= hi; p++) {
            const u16 iv[3] = {d.t_tbl[(size_t)p].vtx0, d.t_tbl[(size_t)p].vtx1,
                               d.t_tbl[(size_t)p].vtx2};
            for (int k = 0; k < 3; k++) {
                const Vec& v = vtx[iv[k]];
                const f32 c3[3] = {v.x, v.y, v.z};
                for (int ax = 0; ax < 3; ax++) {
                    b.mn[ax] = std::min(b.mn[ax], c3[ax]);
                    b.mx[ax] = std::max(b.mx[ax], c3[ax]);
                }
            }
        }
        return b;
    }
    for (int j = 0; j < 8; j++) {
        if (t.mChild[j] == 0xFFFF) {
            continue;
        }
        const Box k = raw_subtree(d, vtx, t.mChild[j]);
        for (int ax = 0; ax < 3; ax++) {
            b.mn[ax] = std::min(b.mn[ax], k.mn[ax]);
            b.mx[ax] = std::max(b.mx[ax], k.mx[ax]);
        }
    }
    return b;
}

std::string describe(const Probe& q) {
    return std::string("slack ") + std::to_string(q.slack) + " u: " + q.arm + " block " +
           std::to_string(q.blk) + " poly " + std::to_string(q.poly) + " at x=" + exact(q.at.x) +
           " y=" + exact(q.at.y) + " z=" + exact(q.at.z) + " -> poly " +
           std::to_string(q.poly_with) + " h=" + exact(q.h_with) + " with the margin, poly " +
           std::to_string(q.poly_without) + " h=" + exact(q.h_without) + " without";
}

/// One row of the probe list for a capture. %.9g round-trips an f32; the hex is for checking.
std::string as_json(const char* room, const Probe& q) {
    char buf[512];
    std::snprintf(buf, sizeof(buf),
                  "  {\"room\": \"%s\", \"arm\": \"%s\", \"block\": %d, \"poly\": %d, "
                  "\"x\": %.9g, \"y\": %.9g, \"z\": %.9g, \"bits\": [\"%08x\", \"%08x\", "
                  "\"%08x\"], \"slack\": %.9g, \"poly_with\": %d, \"h_with\": %.9g, "
                  "\"poly_without\": %d, \"h_without\": %.9g}",
                  room, q.arm, q.blk, q.poly, (double)q.at.x, (double)q.at.y, (double)q.at.z,
                  (unsigned)bits(q.at.x), (unsigned)bits(q.at.y), (unsigned)bits(q.at.z),
                  (double)q.slack, q.poly_with, (double)q.h_with, q.poly_without,
                  (double)q.h_without);
    return std::string(buf);
}

/// Written only when TWWE_MARGIN_PROBES names a path, so the suite's own run writes nothing.
std::string write_probes(const std::string& rows) {
    const char* path = std::getenv("TWWE_MARGIN_PROBES");
    if (path == nullptr) {
        return "set TWWE_MARGIN_PROBES=<path> to write every deciding probe out as JSON for a "
               "capture to aim with";
    }
    std::FILE* f = std::fopen(path, "wb");
    if (f == nullptr) {
        return std::string("TWWE_MARGIN_PROBES names a path that could not be opened: ") + path;
    }
    std::fprintf(f, "[\n%s\n]\n", rows.c_str());
    std::fclose(f);
    return std::string("deciding probes written to ") + path;
}

Arms measure(Fixture& fx) {
    Arms m;
    Room& full = fx.room();
    Room shrunk(fx.dzb());
    mutate_tables(shrunk, Variant::NodeBoxesUnexpanded);
    const RoomDzb& d = fx.dzb();
    const Vec* vtx = full.bgw().pm_vtx_tbl;

    for (size_t n = 0; n < d.tree_tbl.size(); n++) {
        const cBgD_Tree_t& t = d.tree_tbl[n];
        if (!(t.mFlag & 1) || t.mBlock == 0xFFFF) {
            continue;
        }
        const int blk = t.mBlock;
        m.leaves++;

        // The block's raw bound as MakeBlckBnd computes it before adding the 1.0.
        const int lo = d.b_tbl[(size_t)blk].startTri;
        const int hi = ((size_t)blk + 1 < d.b_tbl.size())
                           ? (int)d.b_tbl[(size_t)blk + 1].startTri - 1
                           : (int)d.t_tbl.size() - 1;
        f32 bmin[3] = {G_CM3D_F_INF, G_CM3D_F_INF, G_CM3D_F_INF};
        f32 bmax[3] = {-G_CM3D_F_INF, -G_CM3D_F_INF, -G_CM3D_F_INF};
        for (int p = lo; p <= hi; p++) {
            const u16 iv[3] = {d.t_tbl[(size_t)p].vtx0, d.t_tbl[(size_t)p].vtx1,
                               d.t_tbl[(size_t)p].vtx2};
            for (int k = 0; k < 3; k++) {
                const Vec& v = vtx[iv[k]];
                const f32 c3[3] = {v.x, v.y, v.z};
                for (int ax = 0; ax < 3; ax++) {
                    bmin[ax] = std::min(bmin[ax], c3[ax]);
                    bmax[ax] = std::max(bmax[ax], c3[ax]);
                }
            }
        }

        std::vector<int> cands = full.ground_chain(blk);
        for (int p : full.wall_chain(blk)) {
            if (full.bgw().pm_tri[(size_t)p].m_plane.GetNP()->y >= 0.014f) {
                cands.push_back(p);
            }
        }

        for (int p : cands) {
            m.cands++;
            const cBgD_Tri_t& tri = d.t_tbl[(size_t)p];
            const Vec& a = vtx[tri.vtx0];
            const Vec& b = vtx[tri.vtx1];
            const Vec& cc = vtx[tri.vtx2];

            // The skirt arm's premise: the polygon's xz box, the only place
            // cM3d_CrossY_Tri_Front accepts anything, lies inside the block's raw box.
            if (std::min(std::min(a.x, b.x), cc.x) < bmin[0] ||
                std::max(std::max(a.x, b.x), cc.x) > bmax[0] ||
                std::min(std::min(a.z, b.z), cc.z) < bmin[2] ||
                std::max(std::max(a.z, b.z), cc.z) > bmax[2]) {
                m.tris_outside_block_box++;
            }

            const std::vector<Pt> region = admitted_region(a, b, cc);
            if (region.empty()) {
                continue;
            }
            const cM3dGPla& pla = full.bgw().pm_tri[(size_t)p].m_plane;
            size_t kmin = 0, kmax = 0;
            f32 ymin = G_CM3D_F_INF, ymax = -G_CM3D_F_INF;
            for (size_t k = 0; k < region.size(); k++) {
                const Pt q = inset(region, k);
                cXyz at;
                at.x = (f32)q.first;
                at.y = 0.0f;
                at.z = (f32)q.second;
                const f32 y = pla.getCrossY_NonIsZero(at);
                if (y < ymin) { ymin = y; kmin = k; }
                if (y > ymax) { ymax = y; kmax = k; }
            }

            // LOW-Y arm. UnderPlaneYUnder passes when min.y < probe.y, so the margin decides the
            // leaf for probe.y in (raw min.y - 1, raw min.y]. A candidate there needs a height
            // below the block's own y range.
            if (ymin < bmin[1]) {
                m.low_reach++;
                m.worst_low = std::max(m.worst_low, (double)bmin[1] - (double)ymin);
                // The centre of the deciding set, not its deepest corner, which no placement
                // can hit.
                const std::vector<Pt> dec = below(region, pla, bmin[1], true);
                if (dec.empty()) {
                    continue;
                }
                const Pt q = centre(dec);
                cXyz at;
                at.x = (f32)q.first;
                at.y = 0.0f;
                at.z = (f32)q.second;
                const f32 y_here = pla.getCrossY_NonIsZero(at);
                // The window's middle; its top edge `bmin` is tried too and counted apart.
                const f32 floor_of_window =
                    std::max(bmin[1] - 1.0f, std::nextafter(y_here, bmin[1]));
                const f32 mid = (floor_of_window + bmin[1]) * 0.5f;
                const f32 ys[2] = {mid, bmin[1]};
                for (int which = 0; which < 2; which++) {
                    if (!(ys[which] > y_here && ys[which] <= bmin[1] &&
                          ys[which] > bmin[1] - 1.0f)) {
                        continue;
                    }
                    cXyz probe;
                    probe.x = (f32)q.first;
                    probe.y = ys[which];
                    probe.z = (f32)q.second;
                    int wa = 0, wb = 0;
                    const f32 ya = full.GroundCross(probe, &wa);
                    const f32 yb = shrunk.GroundCross(probe, &wb);
                    if (wa == wb && bits(ya) == bits(yb)) {
                        continue;
                    }
                    if (which == 1) {
                        m.low_decides_at_edge++;
                        continue;
                    }
                    m.low_decides++;
                    const Probe found = {"LOW-Y", blk,       p,  probe, xz_slack(full, shrunk, probe),
                                         wa,      wb,        ya, yb};
                    m.named.push_back(found);
                }
            }

            // HIGH-Y arm. TopPlaneYUnder prunes when max.y < the best height so far, so the
            // margin saves the leaf when that height is in (raw max.y, raw max.y + 1]. The probe
            // is the lowest y that still admits this candidate.
            if (ymax > bmax[1]) {
                m.high_reach++;
                m.worst_high = std::max(m.worst_high, (double)ymax - (double)bmax[1]);
                const std::vector<Pt> dec = below(region, pla, bmax[1], false);
                if (dec.empty()) {
                    continue;
                }
                const Pt q = centre(dec);
                cXyz at;
                at.x = (f32)q.first;
                at.y = 0.0f;
                at.z = (f32)q.second;
                cXyz probe;
                probe.x = (f32)q.first;
                probe.y = std::nextafter(pla.getCrossY_NonIsZero(at), G_CM3D_F_INF);
                probe.z = (f32)q.second;
                int wa = 0, wb = 0;
                const f32 ya = full.GroundCross(probe, &wa);
                const f32 yb = shrunk.GroundCross(probe, &wb);
                if (wa != wb || bits(ya) != bits(yb)) {
                    m.high_decides++;
                    const Probe found = {"HIGH-Y", blk,      p,  probe, xz_slack(full, shrunk, probe),
                                         wa,       wb,       ya, yb};
                    m.named.push_back(found);
                }
            }
        }
    }
    return m;
}

}  // namespace margin

}  // namespace

TWWE_TEST(the_room_is_the_discs_own_tables,
          "the .dzb fixture is not the room the frames were captured in - so every case below "
          "is right about a different room, and nothing says so") {
    REQUIRE_INT(c, (int)kaze().dzb().v_tbl.size(), 683, "kaze r11 vertices");
    REQUIRE_INT(c, (int)kaze().dzb().t_tbl.size(), 1141, "kaze r11 triangles");
    REQUIRE_INT(c, (int)kaze().dzb().b_tbl.size(), 234, "kaze r11 blocks");
    REQUIRE_INT(c, (int)kaze().dzb().tree_tbl.size(), 288, "kaze r11 octree nodes");
    REQUIRE_INT(c, (int)kaze().dzb().g_tbl.size(), 6, "kaze r11 groups");

    // Room seeds m_rootGrpIdx with -1 and MakeNodeTree sets it to the parentless group, so this
    // also checks the build ran.
    REQUIRE_TRUE(c, kaze().room().bgw().m_rootGrpIdx >= 0 &&
                        kaze().room().bgw().m_rootGrpIdx < (int)kaze().dzb().g_tbl.size(),
                 "MakeNodeTree did not set m_rootGrpIdx - the load-time build did not run");
    REQUIRE_INT(c, (int)kaze().dzb().g_tbl[kaze().room().bgw().m_rootGrpIdx].m_parent, 0xFFFF,
                "the root group's parent");
    c.note("683 verts, 1141 tris, 234 blocks, 288 nodes, 6 groups; root group " +
           std::to_string(kaze().room().bgw().m_rootGrpIdx));
}

TWWE_TEST(the_build_computes_the_consoles_own_planes,
          "cBgW::CalcPlane over the disc's vertices no longer produces the plane the game left "
          "in pm_tri - so either cM3d_CalcPla's estimate arithmetic or the vertex indirection "
          "through cBgD_Tri_t is not the game's") {
    int checked = 0;
    for (size_t i = 0; i < kaze().console_polys().size(); i++) {
        const ConsolePoly& want = kaze().console_polys()[i];
        if (!want.have) {
            continue;
        }
        const std::string where = "poly " + std::to_string(i);
        const cBgD_Tri_t& t = kaze().dzb().t_tbl[i];
        const cBgD_Vtx_t* vtx = kaze().room().bgw().pm_vtx_tbl;
        const u16 idx[3] = {t.vtx0, t.vtx1, t.vtx2};
        for (int k = 0; k < 3; k++) {
            REQUIRE_BITS(c, vtx[idx[k]].x, want.v[k].x, where + " v" + std::to_string(k) + ".x");
            REQUIRE_BITS(c, vtx[idx[k]].y, want.v[k].y, where + " v" + std::to_string(k) + ".y");
            REQUIRE_BITS(c, vtx[idx[k]].z, want.v[k].z, where + " v" + std::to_string(k) + ".z");
        }
        const cM3dGPla& got = kaze().room().bgw().pm_tri[i].m_plane;
        REQUIRE_BITS(c, got.GetNP()->x, want.n.x, where + " nx");
        REQUIRE_BITS(c, got.GetNP()->y, want.n.y, where + " ny");
        REQUIRE_BITS(c, got.GetNP()->z, want.n.z, where + " nz");
        REQUIRE_BITS(c, got.GetD(), want.d, where + " d");
        checked++;
    }
    REQUIRE_INT(c, checked, 1067,
                "distinct triangles the two RAM captures cover - a rate over a population nobody "
                "counted reads the same green either way");
    REQUIRE_INT(c, kaze().overlap(), 30, "triangles both captures carry");
    REQUIRE_INT(c, kaze().overlap_conflicts(), 0,
                "triangles the two captures disagree about - two reads of the same pm_tri row, "
                "on different runs, so a conflict means one of the files is not this room's");
    c.note("1067 of 1141 triangles held to the console's own pm_tri, verts and plane, bit for "
           "bit; 30 of them appear in both captures and agree. The 74 neither file names are the "
           "roof chain and the degenerate rows - captured by neither, so gated by neither.");
}

TWWE_TEST(classify_plane_builds_the_consoles_candidate_chains,
          "the per-block ground and wall chains cBgW::ClassifyPlane threads through pm_rwg are "
          "no longer the candidate lists the console's own traversal was captured to have - so "
          "the plane-kind split, a block's triangle range, or BlckConnect's linking is wrong") {
    // The capture is the traversal flattened per leaf (ground polys, then wall polys with
    // ny >= 0.014f); partitioning it by startTri gives the per-block lists.
    std::vector<std::vector<int> > want_ground(kaze().dzb().b_tbl.size());
    std::vector<std::vector<int> > want_wall(kaze().dzb().b_tbl.size());
    for (int poly : kaze().floors_order()) {
        const int b = kaze().block_of(poly);
        if (b < 0) {
            REQUIRE_TRUE(c, false, "poly " + std::to_string(poly) + " is in no block's range");
            continue;
        }
        const cXyz* n = kaze().room().bgw().pm_tri[poly].m_plane.GetNP();
        (cBgW_CheckBGround(n->y) ? want_ground : want_wall)[(size_t)b].push_back(poly);
    }

    int blocks_with_ground = 0, blocks_with_wall = 0, ground_polys = 0, wall_polys = 0;
    for (size_t b = 0; b < kaze().dzb().b_tbl.size(); b++) {
        const std::string where = "block " + std::to_string(b);
        const std::vector<int> got_g = kaze().room().ground_chain((int)b);
        REQUIRE_TRUE(c, got_g == want_ground[b],
                     where + " ground chain: built " + std::to_string(got_g.size()) +
                         " poly(s), the capture has " + std::to_string(want_ground[b].size()));
        blocks_with_ground += got_g.empty() ? 0 : 1;
        ground_polys += (int)got_g.size();

        // The capture only carries the wall polys RwgGroundCheckWall looks at, so filter by the
        // same gate (c_bg_w.cpp:505).
        std::vector<int> got_w;
        for (int poly : kaze().room().wall_chain((int)b)) {
            if (kaze().room().bgw().pm_tri[poly].m_plane.GetNP()->y >= 0.014f) {
                got_w.push_back(poly);
            }
        }
        REQUIRE_TRUE(c, got_w == want_wall[b],
                     where + " wall chain (ny >= 0.014f): built " + std::to_string(got_w.size()) +
                         " poly(s), the capture has " + std::to_string(want_wall[b].size()));
        blocks_with_wall += got_w.empty() ? 0 : 1;
        wall_polys += (int)got_w.size();
    }
    REQUIRE_INT(c, ground_polys + wall_polys, (int)kaze().floors_order().size(),
                "candidates the built chains hold, against the capture's 332");
    c.note(std::to_string(ground_polys) + " ground + " + std::to_string(wall_polys) +
           " wall candidate(s) over " + std::to_string(blocks_with_ground) + " and " +
           std::to_string(blocks_with_wall) + " block(s) of 234");
}

TWWE_TEST(the_walk_finds_the_console_triangle,
          "the ported descent no longer reaches the polygon the game recorded in "
          "dBgS_LinkAcch+0x554 - so the octree walk, the group DFS, or a node box the load-time "
          "build produced is not the game's") {
    REQUIRE_TRUE(c, kaze_frames().size() == 1082,
                 "the kaze frame corpus is not the 1,082 rows the two captures hold");
    for (const Frame& f : kaze_frames()) {
        int got = 0;
        kaze().room().GroundCross(probe_of(f), &got);
        REQUIRE_INT(c, got, f.floor_tri, f.where + " floor_tri");
    }
    c.note("1082 console frames, candidates from the room's own octree");
    tww_engine::testing::ledger_record_subsystem(
        "collision", tww_engine::testing::Tier::Console,
        "with the candidates from each room's own octree (cBgW::GroundCrossGrpRp / GroundCrossRp "
        "over the disc's .dzb): 1082 frame(s) of floor_tri in kaze r11, 30 frame(s) of ground "
        "height on the GanonA r0 incline, 1562 triangle(s) of CalcPlane output against the "
        "console's own pm_tri in the two rooms, and 432 centroid probes differential against the "
        "recorded candidate list. The ceiling check beside it (dBgS::RoofChk through dBgW's own "
        "walk): 42 row(s) of m_roof_height and its polygon in three rooms, 6 naming a ceiling "
        "and 36 saying there is none - see test_roof_chk.cpp");
}

TWWE_TEST(the_walk_and_the_golden_list_answer_alike,
          "the descent and the recorded candidate list disagree somewhere - which would mean the "
          "walk reaches a different set than the capture holds, and only one of the two gates "
          "above could be right about this room") {
    // A control, not the gate: both sides run the same copied per-polygon test, so this says the
    // candidate sets match. The centroid probes add reach beyond the frames.
    int differ = 0;
    for (const Frame& f : kaze_frames()) {
        int a = 0, b = 0;
        const f32 ya = kaze().room().GroundCross(probe_of(f), &a);
        const f32 yb = kaze().stand_in().GroundCross(probe_of(f), &b);
        if (a != b || bits(ya) != bits(yb)) {
            differ++;
        }
    }
    int probe_differ = 0, probe_found = 0;
    for (const cXyz& q : kaze().centroid_probes()) {
        int a = 0, b = 0;
        const f32 ya = kaze().room().GroundCross(q, &a);
        const f32 yb = kaze().stand_in().GroundCross(q, &b);
        if (a != b || bits(ya) != bits(yb)) {
            probe_differ++;
        }
        if (a != 0xFFFF) {
            probe_found++;
        }
    }
    REQUIRE_INT(c, differ, 0, "console frames where the walk and the golden list disagree");
    REQUIRE_INT(c, probe_differ, 0, "centroid probes where the walk and the golden list disagree");
    REQUIRE_INT(c, probe_found, (int)kaze().centroid_probes().size(),
                "centroid probes that found any ground - a probe set that finds nothing agrees "
                "with anything");
    c.note(std::to_string(kaze_frames().size()) + " frames and " +
           std::to_string(kaze().centroid_probes().size()) +
           " centroid probes, height and poly identical on every one");
}


TWWE_TEST(the_walk_variant_harness_is_the_ported_walk,
          "the controls below rebuild the room and then perturb it, and the rebuild alone "
          "already changes an answer - so what they measure is the rebuild, not the perturbation") {
    const Wrong w = wrong_with(Variant::None);
    REQUIRE_INT(c, w.total(), 0,
                "answers that differ when the room is rebuilt and nothing is changed");
    c.note("a rebuilt, unperturbed room answers all " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           " identically - the controls below start from zero");
}

TWWE_TEST(the_descent_order_is_not_what_this_gate_holds,
          "rotating every branch's eight child slots changed an answer. That would mean the "
          "order the octree is descended in is load-bearing on this data - which would make the "
          "child order 2,3,6,7,0,1,4,5 gated here, and it is currently not") {
    // Order reaches an answer only through RwgGroundCheckCommon's strict `y > mNowY` (a tie) and
    // TopPlaneYUnder(mNowY), which can never prune a winning candidate.
    const Wrong w = wrong_with(Variant::TreeChildrenRotated);
    REQUIRE_INT(c, w.total(), 0, "answers that change when the child slots are rotated");
    c.note("order-independent on all " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           " answers: the descent's order is copied and UNGATED, here as in the flat list");
}

TWWE_TEST(the_node_boxes_are_read_at_all,
          "emptying every node's bounding box did not stop the descent from finding ground - "
          "which would mean the boxes are not being consulted, and every case above would be "
          "passing with the prune disabled") {
    Room r(kaze().dzb());
    mutate_tables(r, Variant::NodeBoxesEmpty);
    int found = 0;
    for (const Frame& f : kaze_frames()) {
        int got = 0;
        r.GroundCross(probe_of(f), &got);
        if (got != 0xFFFF) {
            found++;
        }
    }
    for (const cXyz& q : kaze().centroid_probes()) {
        int got = 0;
        r.GroundCross(q, &got);
        if (got != 0xFFFF) {
            found++;
        }
    }
    REQUIRE_INT(c, found, 0, "queries that still found ground with every node box emptied");
    c.note("all " + std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           " queries return no poly when the boxes cannot be crossed - cM3dGAab::CrossY and the "
           "two Y predicates are on the path");
}

TWWE_TEST(the_boxes_y_pruning_is_conservative_here,
          "opening every node box to +/-infinity in y changed an answer. The two Y predicates "
          "can only ever remove candidates, so widening them must be a no-op - a difference "
          "would mean the copied test does not take the max over a superset") {
    const Wrong w = wrong_with(Variant::NodeBoxesUnboundedY);
    REQUIRE_INT(c, w.total(), 0, "answers that change when the Y prune is disabled");
    c.note("UnderPlaneYUnder and TopPlaneYUnder remove work and no answers on all " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) + " queries");
}

TWWE_TEST(the_one_unit_box_margin_is_unreached_by_a_walk,
          "shrinking every node box by the 1.0 MakeBlckBnd adds on each axis changed an answer in "
          "a walked room - which would mean these two corpora reach the margin after all, and a "
          "probe placed on purpose is not the only thing that does") {
    const Wrong w = wrong_with(Variant::NodeBoxesUnexpanded);
    REQUIRE_INT(c, w.total(), 0, "answers that change when the 1.0 box margin is removed");
    c.note("the 1.0 margin decides no answer on any of the " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           " walked queries. It is not unreachable in this room - 6 chosen points in it are "
           "answered differently without the margin, and the widest of them holds over a 2.0 u "
           "square - but a walking Link stands at the ground check's fixed point and never "
           "below a block's own lowest vertex, which is where the reachable arm lives. See "
           "the_box_margin_is_reached_through_the_Y_predicates.");
}

TWWE_RED_CONTROL(red_walk_group_child_and_sibling_swapped,
                 "the group row's four fields read as [parent, first_child, next_sibling, "
                 "tree_idx]. They are [parent, next_sibling, first_child, tree_idx] - 0x24, "
                 "0x26, 0x28, 0x2E - and swapping the middle two makes the group DFS follow "
                 "siblings as children") {
    expect_wrong(c, Variant::GroupChildSiblingSwapped, "the group DFS following the wrong links");
}

TWWE_RED_CONTROL(red_walk_triangle_vertices_swapped,
                 "cBgD_Tri_t's second and third vertex indices exchanged - three u16 in a row, "
                 "and two of them read the wrong way round. Every triangle keeps its shape, so "
                 "nothing about the mesh looks wrong; CalcPlane negates every normal, which sends "
                 "the whole room through ClassifyPlane's roof arm instead of its ground arm") {
    expect_wrong(c, Variant::TriangleVerticesSwapped, "the triangle winding reversed");
}

TWWE_TEST(a_consistent_block_range_error_is_not_an_answer_error,
          "shifting every block's startTri to the next block's changed an answer. It should not, "
          "and the reason is a property of the port rather than of this data: MakeBlckBnd and "
          "ClassifyPlane range a block with the same expression, so a shift moves each block's "
          "box along with its chain and the descent still finds every triangle it covers") {
    // A shift drops only the triangles no range covers - block 0's polys 0..7, none a ground
    // candidate. The inconsistent range error is red_walk_chains_short_by_one.
    const Wrong w = wrong_with(Variant::BlockStartsShifted);
    REQUIRE_INT(c, w.total(), 0, "answers that change when every block range is shifted by one");
    c.note("a consistent shift changes no answer of " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           "; what it drops is polys 0..7, block 0's, and none of them is a ground candidate");
}

TWWE_TEST(the_wall_chains_ny_gate_admits_nothing_that_wins,
          "swapping each block's two chain heads changed an answer. That is not vacuous - it "
          "really does hand RwgGroundCheckGnd 735 near-vertical polys the ny >= 0.014f gate "
          "exists to exclude - so a change here would mean that gate decides an answer, and a "
          "port that dropped it would be caught. It is not caught, and this records that") {
    // getCrossY_NonIsZero divides by ny, so a plane with ny < 0.014 crosses the probe's vertical
    // far above (rejected by `y < chk->GetPointP()->y`) or far below (loses the max).
    const Wrong w = wrong_with(Variant::ChainHeadsSwapped);
    REQUIRE_INT(c, w.total(), 0, "answers that change when the two chain heads are swapped");
    c.note("the 0.014f gate decides no answer of " +
           std::to_string(kaze_frames().size() + kaze().centroid_probes().size()) +
           ", though swapping the heads admits 735 wall polys below it. Copied, not gated.");
}

TWWE_RED_CONTROL(red_walk_chains_short_by_one,
                 "ClassifyPlane's loop written `j < lastTri` instead of `j <= lastTri`, so each "
                 "block's last triangle enters no chain while MakeBlckBnd's box - ranged by the "
                 "same expression, one line away - still covers it. The range error that is "
                 "inconsistent between the box and the chain, which is the one that bites") {
    expect_wrong(c, Variant::ChainsShortByOne, "each block's last triangle dropped from its chain");
}

TWWE_RED_CONTROL(red_walk_chain_head_is_the_last_poly,
                 "BlckConnect's `if (*rwg == 0xFFFF)` guard dropped, so the head is rewritten on "
                 "every link and ends up at the last poly instead of the first. Five lines, and "
                 "the guard is the only thing in them that makes a head a head - every chain "
                 "becomes one element long") {
    expect_wrong(c, Variant::ChainHeadIsTheLast, "every chain cut to its last element");
}


// ------------------------------------------------------------------------------- GanonA r0
//
// kaze's floors are flat, so getCrossY_NonIsZero's nx and nz terms are zero there. GanonA r0 is a
// micro-incline; the same expression evaluated in double gets 6 of its 30 frames wrong.

TWWE_TEST(the_ganona_room_is_the_discs_own_tables,
          "the GanonA .dzb fixture is not the room the incline frames were captured in") {
    REQUIRE_INT(c, (int)ganona().dzb().v_tbl.size(), 400, "GanonA r0 vertices");
    REQUIRE_INT(c, (int)ganona().dzb().t_tbl.size(), 557, "GanonA r0 triangles");
    REQUIRE_INT(c, (int)ganona().dzb().b_tbl.size(), 176, "GanonA r0 blocks");
    REQUIRE_INT(c, (int)ganona().dzb().tree_tbl.size(), 205, "GanonA r0 octree nodes");
    REQUIRE_INT(c, (int)ganona().dzb().g_tbl.size(), 25, "GanonA r0 groups");
    REQUIRE_TRUE(c, ganona().room().bgw().m_rootGrpIdx >= 0,
                 "MakeNodeTree did not set m_rootGrpIdx - the load-time build did not run");
    c.note("400 verts, 557 tris, 176 blocks, 205 nodes, 25 groups; root group " +
           std::to_string(ganona().room().bgw().m_rootGrpIdx) +
           " - and 25 groups against kaze's 6, so the group DFS is doing more here");
}

TWWE_TEST(the_ganona_build_computes_the_consoles_own_planes,
          "cBgW::CalcPlane over the GanonA disc's vertices no longer produces the plane the game "
          "left in pm_tri. This room is where that matters most: its normals are not (0,1,0), so "
          "an estimate-class error in cM3d_CalcPla changes the height and not only the choice") {
    int checked = 0;
    for (size_t i = 0; i < ganona().console_polys().size(); i++) {
        const ConsolePoly& want = ganona().console_polys()[i];
        if (!want.have) {
            continue;
        }
        const std::string where = "GanonA poly " + std::to_string(i);
        const cBgD_Tri_t& t = ganona().dzb().t_tbl[i];
        const cBgD_Vtx_t* vtx = ganona().room().bgw().pm_vtx_tbl;
        const u16 idx[3] = {t.vtx0, t.vtx1, t.vtx2};
        for (int k = 0; k < 3; k++) {
            REQUIRE_BITS(c, vtx[idx[k]].x, want.v[k].x, where + " v" + std::to_string(k) + ".x");
            REQUIRE_BITS(c, vtx[idx[k]].y, want.v[k].y, where + " v" + std::to_string(k) + ".y");
            REQUIRE_BITS(c, vtx[idx[k]].z, want.v[k].z, where + " v" + std::to_string(k) + ".z");
        }
        const cM3dGPla& got = ganona().room().bgw().pm_tri[i].m_plane;
        REQUIRE_BITS(c, got.GetNP()->x, want.n.x, where + " nx");
        REQUIRE_BITS(c, got.GetNP()->y, want.n.y, where + " ny");
        REQUIRE_BITS(c, got.GetNP()->z, want.n.z, where + " nz");
        REQUIRE_BITS(c, got.GetD(), want.d, where + " d");
        checked++;
    }
    REQUIRE_TRUE(c, checked > 0, "the GanonA captures cover no triangle at all");
    REQUIRE_INT(c, ganona().overlap_conflicts(), 0,
                "GanonA triangles the two captures disagree about");
    c.note(std::to_string(checked) + " of " + std::to_string(ganona().dzb().t_tbl.size()) +
           " triangles held to the console's own pm_tri, verts and plane, bit for bit; " +
           std::to_string(ganona().overlap()) + " appear in both captures and agree");
}

TWWE_TEST(the_walk_returns_the_console_height_on_a_slope,
          "the ported descent no longer returns the height the game wrote into pos_y on the "
          "GanonA micro-incline. kaze cannot see this: its floors are (0,1,0) and the nx and nz "
          "terms are multiplied by zero, so this is the only gate holding the plane arithmetic "
          "with the candidates coming out of the octree rather than out of a golden") {
    REQUIRE_TRUE(c, ganona_frames().size() == 30,
                 "the GanonA rest golden is not its 30 frames - a rate over a population nobody "
                 "checked reads the same green either way");
    for (const Frame& f : ganona_frames()) {
        const f32 y = ganona().room().GroundCross(probe_of(f), nullptr);
        REQUIRE_BITS(c, y, f.y, f.where + " ground height");
    }
    c.note("30 console frames on a slope, ground height bit for bit, candidates from the room's "
           "own octree");
}

TWWE_TEST(the_ganona_walk_and_the_golden_list_answer_alike,
          "the descent and the recorded candidate list disagree on the incline - so the walk "
          "reaches a different set there than the capture holds") {
    int differ = 0;
    for (const Frame& f : ganona_frames()) {
        int a = 0, b = 0;
        const f32 ya = ganona().room().GroundCross(probe_of(f), &a);
        const f32 yb = ganona().stand_in().GroundCross(probe_of(f), &b);
        if (a != b || bits(ya) != bits(yb)) {
            differ++;
        }
    }
    int probe_differ = 0, probe_found = 0;
    for (const cXyz& q : ganona().centroid_probes()) {
        int a = 0, b = 0;
        const f32 ya = ganona().room().GroundCross(q, &a);
        const f32 yb = ganona().stand_in().GroundCross(q, &b);
        if (a != b || bits(ya) != bits(yb)) {
            probe_differ++;
        }
        if (a != 0xFFFF) {
            probe_found++;
        }
    }
    REQUIRE_INT(c, differ, 0, "GanonA frames where the walk and the golden list disagree");
    REQUIRE_INT(c, probe_differ, 0, "GanonA probes where the walk and the golden list disagree");
    REQUIRE_INT(c, probe_found, (int)ganona().centroid_probes().size(),
                "GanonA probes that found any ground - a probe set that finds nothing agrees "
                "with anything");
    c.note(std::to_string(ganona_frames().size()) + " frames and " +
           std::to_string(ganona().centroid_probes().size()) +
           " centroid probes, height and poly identical on every one");
}


// ----------------------------------------------------------------------------------- sea r41
//
// A chosen corpus. Walks do not reach three arms of the copied code: the -20.0f edge dilation,
// the 1.0 node-box margin, and dBgW's two refusals (every attribute row is zero in the walked
// rooms). test_poly_through.cpp owns the refusals here; these cases own the answer.

TWWE_TEST(the_sea_room_is_the_discs_own_tables,
          "the sea r41 .dzb fixture is not the room the chosen-probe rows were captured in - so "
          "every case below is right about a different room, and nothing else would say so") {
    REQUIRE_INT(c, (int)sea().dzb().v_tbl.size(), 2189, "sea r41 vertices");
    REQUIRE_INT(c, (int)sea().dzb().t_tbl.size(), 2906, "sea r41 triangles");
    REQUIRE_INT(c, (int)sea().dzb().b_tbl.size(), 825, "sea r41 blocks");
    REQUIRE_INT(c, (int)sea().dzb().tree_tbl.size(), 987, "sea r41 octree nodes");
    REQUIRE_INT(c, (int)sea().dzb().g_tbl.size(), 66, "sea r41 groups");
    REQUIRE_TRUE(c, sea().room().bgw().m_rootGrpIdx >= 0,
                 "MakeNodeTree did not set m_rootGrpIdx - the load-time build did not run");

    // The capture writes the loaded room's cBgD_t counts into its header. sea r41 has seven
    // `kirikae` room-switch groups, so this also checks no row came from another room.
    const Json& g = tww_engine::testing::golden("sea_r41_ground_live.json");
    REQUIRE_INT(c, (int)g["v_num"].as_int(), (int)sea().dzb().v_tbl.size(),
                "the capture's loaded-room vertex count");
    REQUIRE_INT(c, (int)g["t_num"].as_int(), (int)sea().dzb().t_tbl.size(),
                "the capture's loaded-room triangle count");
    c.note("2189 verts, 2906 tris, 825 blocks, 987 nodes, 66 groups; root group " +
           std::to_string(sea().room().bgw().m_rootGrpIdx) + "; the capture agrees it is this room");
}

TWWE_TEST(the_sea_build_computes_the_consoles_own_planes,
          "cBgW::CalcPlane over sea r41's disc vertices no longer produces the plane the game "
          "left in pm_tri - which would mean the third room's fixture is not the room the "
          "console loaded, and every reach and refusal measured on it is about another room") {
    int checked = 0;
    for (size_t i = 0; i < sea().console_polys().size(); i++) {
        const ConsolePoly& want = sea().console_polys()[i];
        if (!want.have) {
            continue;
        }
        const std::string where = "sea poly " + std::to_string(i);
        const cBgD_Tri_t& t = sea().dzb().t_tbl[i];
        const cBgD_Vtx_t* vtx = sea().room().bgw().pm_vtx_tbl;
        const u16 idx[3] = {t.vtx0, t.vtx1, t.vtx2};
        for (int k = 0; k < 3; k++) {
            REQUIRE_BITS(c, vtx[idx[k]].x, want.v[k].x, where + " v" + std::to_string(k) + ".x");
            REQUIRE_BITS(c, vtx[idx[k]].y, want.v[k].y, where + " v" + std::to_string(k) + ".y");
            REQUIRE_BITS(c, vtx[idx[k]].z, want.v[k].z, where + " v" + std::to_string(k) + ".z");
        }
        const cM3dGPla& got = sea().room().bgw().pm_tri[i].m_plane;
        REQUIRE_BITS(c, got.GetNP()->x, want.n.x, where + " nx");
        REQUIRE_BITS(c, got.GetNP()->y, want.n.y, where + " ny");
        REQUIRE_BITS(c, got.GetNP()->z, want.n.z, where + " nz");
        REQUIRE_BITS(c, got.GetD(), want.d, where + " d");
        checked++;
    }
    REQUIRE_TRUE(c, checked > 0, "the sea r41 captures cover no triangle at all");
    REQUIRE_INT(c, sea().overlap_conflicts(), 0,
                "sea r41 triangles the two captures disagree about");
    c.note(std::to_string(checked) + " of " + std::to_string(sea().dzb().t_tbl.size()) +
           " triangles held to the console's own pm_tri, verts and plane, bit for bit; " +
           std::to_string(sea().overlap()) + " appear in both captures and agree");
}

TWWE_TEST(the_walk_answers_the_console_in_the_third_room,
          "the ported descent no longer reaches the polygon the game left in the acch at chosen "
          "probes in sea r41 - the room where the -20 edge band and both of dBgW's refusals are "
          "live, and the two walked rooms reach none of them") {
    REQUIRE_TRUE(c, !sea_rows().empty(),
                 "the sea corpus is empty - a walk over no rows agrees with anything");
    std::map<std::string, int> by_cls;
    std::set<int> answers;
    int wrong_poly = 0, wrong_h = 0;
    for (size_t i = 0; i < sea_rows().size(); i++) {
        const SeaRow& row = sea_rows()[i];
        int got = 0;
        const f32 y = sea().room().GroundCross(row.probe, &got);
        answers.insert(row.floor_tri);
        if (got != row.floor_tri) {
            wrong_poly++;
            by_cls[g_sea_cls[i]]++;
        }
        if (bits(y) != bits(row.ground_h)) {
            wrong_h++;
        }
    }
    std::string brk;
    for (std::map<std::string, int>::const_iterator it = by_cls.begin(); it != by_cls.end(); ++it) {
        brk += " " + it->first + "=" + std::to_string(it->second);
    }
    REQUIRE_INT(c, wrong_poly, 0, "chosen-probe rows the walk puts on the wrong triangle" + brk);
    // m_ground_h is cBgS::GroundCross's return value, here on normals that are not (0,1,0).
    REQUIRE_INT(c, wrong_h, 0, "chosen-probe rows whose ground height is not the console's, bit "
                               "for bit");
    // The poly column has to vary, or agreeing with it is agreeing with a constant.
    REQUIRE_TRUE(c, answers.size() > 20,
                 "the console's poly column takes too few distinct values to be responding to "
                 "the probe at all");
    c.note(std::to_string(sea_rows().size()) + " console rows in sea r41 over " +
           std::to_string(answers.size()) + " distinct answers, candidates from the room's own "
           "octree and both refusals live; " + std::to_string(sea_off_room_rows()) +
           " row(s) set aside as an actor's collision rather than the room's. Poly and height "
           "both, and the height is m_ground_h - GroundCross's own return - not a pos_y that "
           "only carries it because a walking Link sits at the fixed point");
    c.note("the probe is the post-move XZ and the pre-move Y: dBgS_Acch::GroundCheck reads "
           "*pm_pos and then writes pm_pos->y out of its own answer, so the position visible "
           "after a frame is the check's output. A walked corpus cannot see that - a walking "
           "Link is at the fixed point - and pairing on `pos` put 13 of these rows on a point "
           "the game never probed");
}

TWWE_TEST(the_refusals_decide_an_answer_the_console_agrees_with,
          "dBgW's two overrides stopped changing any answer the console was also asked - which "
          "would put test_poly_through.cpp's whole file back to grading reach, with nothing "
          "saying the refusals decide what the game decides") {
    int differ = 0, console_takes_the_refusal = 0;
    for (const SeaRow& row : sea_rows()) {
        int link = 0, none = 0;
        sea().room().GroundCross(row.probe, &link, tww_engine::PassChk::Link);
        sea().room().GroundCross(row.probe, &none, tww_engine::PassChk::None);
        if (link == none) {
            continue;
        }
        differ++;
        if (link == row.floor_tri) {
            console_takes_the_refusal++;
        }
    }
    REQUIRE_TRUE(c, differ > 0,
                 "no row of this corpus is one the refusals change, so the corpus is not "
                 "reaching what it was taken for");
    REQUIRE_INT(c, console_takes_the_refusal, differ,
                "rows where the refusals change the answer and the console agrees with the "
                "refusing one - a Link-vs-None difference the game does not make would be the "
                "port refusing something the game keeps");
    c.note(std::to_string(differ) + " of " + std::to_string(sea_rows().size()) +
           " rows answer differently with dBgS_LinkAcch's pass-checks than without them, and the "
           "console takes the refusing answer on every one. Worked example: at the camera_01 "
           "trigger the port returns the floor at y=450 and would return the trigger's own "
           "surface at y=1160 without ChkPolyThrough; the console returns 450");
}

TWWE_RED_CONTROL(red_walk_sea_node_boxes_empty,
                 "every node box in sea r41 emptied, so nothing can pass cBgW_NodeTree::CrossY "
                 "and the descent reaches no leaf at all. The control that the third room's rows "
                 "are answered by the walk and not by something that would answer them anyway - "
                 "the corpus is digest-protected, so the only way to move this gate is to move "
                 "the engine under it") {
    const int bad = sea_wrong_with(Variant::NodeBoxesEmpty);
    c.note("every node box emptied: " + std::to_string(bad) + " of " +
           std::to_string(sea_rows().size()) + " chosen-probe rows on the wrong triangle");
    REQUIRE_INT(c, bad, 0, "rows that still answer when no node box can be entered");
}

TWWE_TEST(the_skirt_probes_were_aimed_at_the_margins_dead_arm,
          "shrinking every node box by the 1.0 cBgW::MakeBlckBnd adds on each axis changed an "
          "answer the console was also asked - which would make these rows a red control instead "
          "of the record of an aim that could not have worked") {
    // These probes sit in a leaf's 1.0 skirt, the margin's CrossY arm, which cannot fire:
    // cM3d_CrossY_Tri_Front first checks the triangle's own undilated xz box, and a block's raw
    // box is the union of those boxes. The margin decides through the Y predicates instead (see
    // the_box_margin_is_reached_through_the_Y_predicates).
    const int bad = sea_wrong_with(Variant::NodeBoxesUnexpanded);
    REQUIRE_INT(c, bad, 0, "rows the 1.0 box margin changes when it is removed");
    c.note("the 1.0 margin decides no answer on any of the " + std::to_string(sea_rows().size()) +
           " chosen-probe rows - counted only over rows the unmutated room already answers "
           "correctly, so this is what the shrink would have broken and not what it inherited. "
           "It could not have: every one of these rows is in the skirt, which is the arm the "
           "triangle's own box test makes unreachable.");
}

namespace margin_corpus {

/// daPyProc_WAIT_e (d_a_player_main.h:420). A row is admitted only when the proc is WAIT both
/// going into and coming out of the frame:
///   in, because `place` sets position and zeroes speed but not the proc, and daPyProc_MOVE_e
///   steps Link in xz even on a neutral stick (GanonA r0 probe 1);
///   out, because the proc can rewrite speed.y before fopAcM_posMove, so on a LAND or FALL frame
///   `probe_dy` is not the step taken (sea r41 probe 47). `placement_held` cannot see that.
const int kProcWait = 4;

/// Console ground checks at the points the_box_margin_is_reached_through_the_Y_predicates names.
///   `probe_dy` is the y step applied before dBgS_Acch::GroundCheck (gravity precedes
///   fopAcM_posMove); the capture cancels it, so it must read zero.
///   `placement_held` is false when the wall check pushed Link off the aim before the ground
///   check (a LOW-Y probe sits under its floor, inside Link's height); those rows are set aside.
///   `room_bg` is the room's dBgS slot, which differs per room (sea r41 0, kaze r11 27, GanonA r0
///   4), so it is read from the header and required.
struct Corpus {
    std::vector<SeaRow> rows;
    int aimed = 0;        //: probes that produced a row at all
    int displaced = 0;    //: rows whose check did not happen at the aim, or not on the room
    int malformed = 0;    //: rows that cannot SAY whether it did
    int not_rested = 0;   //: rows placed from a proc that is not daPyProc_WAIT_e
    int held = 0;         //: rows that held the placement, before the proc rule is applied
    int left_wait = 0;    //: of those, the ones whose frame left WAIT - see kProcWait
    int room_bg = -1;
    bool says_room_bg = false;
    const Json* file = nullptr;
};

Corpus load(const char* name) {
    Corpus out;
    const Json& file = tww_engine::testing::golden(name);
    out.file = &file;
    out.says_room_bg = file["room_bg"].kind == Json::Kind::Number;
    out.room_bg = out.says_room_bg ? (int)file["room_bg"].as_int() : -1;
    const Json& g = file["rows"];
    out.aimed = (int)g.size();
    for (size_t i = 0; i < g.size(); i++) {
        // A missing `placement_held` reads as false and would empty the corpus silently, so its
        // kind is counted and asserted.
        if (g[i]["placement_held"].kind != Json::Kind::Bool) {
            out.malformed++;
        }
        if (g[i]["proc_in"].kind != Json::Kind::Number ||
            g[i]["proc_in"].as_int() != kProcWait) {
            out.not_rested++;
        }
        if (!g[i]["placement_held"].boolean || (int)g[i]["floor_bg"].as_int() != out.room_bg) {
            out.displaced++;
            continue;
        }
        out.held++;
        // The frame has to have stayed in WAIT (kProcWait).
        if (g[i]["proc"].kind != Json::Kind::Number || g[i]["proc"].as_int() != kProcWait) {
            out.left_wait++;
            continue;
        }
        SeaRow r;
        r.probe.x = g[i]["pos_x"].as_f32();
        r.probe.y = g[i]["pre_y"].as_f32() + g[i]["probe_dy"].as_f32() +
                    g[i]["ground_check_offset"].as_f32() - g[i]["ground_up_h"].as_f32() +
                    g[i]["ground_up_h_diff"].as_f32();
        r.probe.z = g[i]["pos_z"].as_f32();
        r.floor_tri = (int)g[i]["floor_tri"].as_int();
        r.ground_h = g[i]["ground_h"].as_f32();
        r.where = std::string(name) + " row " + std::to_string(i);
        out.rows.push_back(r);
    }
    return out;
}

Corpus& sea_margin() {
    static Corpus c = load("sea_r41_margin_live.json");
    return c;
}

Corpus& kaze_margin() {
    static Corpus c = load("kaze_r11_margin_live.json");
    return c;
}

Corpus& ganona_margin() {
    static Corpus c = load("ganona_r0_margin_live.json");
    return c;
}

/// Rows the mutation puts on the wrong triangle, counted only over rows the unmutated room
/// already answers correctly.
int wrong_with(Fixture& fx, const Corpus& corpus, Variant var) {
    Room r(mutated_dzb(fx, var));
    mutate_tables(r, var);
    int bad = 0;
    for (const SeaRow& row : corpus.rows) {
        int base = 0, got = 0;
        fx.room().GroundCross(row.probe, &base);
        if (base != row.floor_tri) {
            continue;
        }
        r.GroundCross(row.probe, &got);
        if (got != row.floor_tri) {
            bad++;
        }
    }
    return bad;
}

/// Poly and height, bit for bit. Returns the number of distinct answers; `first_bad` names the
/// first disagreeing row.
int check(Fixture& fx, const Corpus& corpus, int& wrong_poly, int& wrong_h,
          std::string& first_bad) {
    std::set<int> answers;
    wrong_poly = 0;
    wrong_h = 0;
    first_bad.clear();
    for (const SeaRow& row : corpus.rows) {
        int got = 0;
        const f32 y = fx.room().GroundCross(row.probe, &got);
        answers.insert(row.floor_tri);
        const bool bad_poly = got != row.floor_tri;
        const bool bad_h = bits(y) != bits(row.ground_h);
        wrong_poly += bad_poly ? 1 : 0;
        wrong_h += bad_h ? 1 : 0;
        if ((bad_poly || bad_h) && first_bad.empty()) {
            first_bad = ". First: " + row.where + " at x=" + margin::exact(row.probe.x) +
                        " y=" + margin::exact(row.probe.y) + " z=" + margin::exact(row.probe.z) +
                        " - console poly " + std::to_string(row.floor_tri) + " h=" +
                        margin::exact(row.ground_h) + ", port poly " + std::to_string(got) +
                        " h=" + margin::exact(y);
        }
    }
    return (int)answers.size();
}

/// Every row's `probe_dy` must be zero: an uncancelled step moves the probe 2.5 u, and these
/// corpora live inside 0.1 u.
void require_taken_where_it_says(::tww_engine::testing::Case& c, const Corpus& corpus,
                                 const char* name) {
    const Json& g = (*corpus.file)["rows"];
    for (size_t i = 0; i < g.size(); i++) {
        REQUIRE_BITS(c, g[i]["probe_dy"].as_f32(), 0.0f,
                     std::string(name) + " row " + std::to_string(i) +
                         ": the y step the check happens after");
    }
}

}  // namespace margin_corpus

TWWE_TEST(the_console_stands_on_the_node_box_margin,
          "the console's ground check at the points where cBgW::MakeBlckBnd's 1.0 decides the "
          "port's answer no longer agrees with the port - which is the whole claim this corpus "
          "exists to make, and the only thing between the margin and copied-and-unreached") {
    using namespace margin_corpus;
    Corpus& m = sea_margin();
    REQUIRE_TRUE(c, m.says_room_bg,
                 "sea_r41_margin_live.json does not say which dBgS slot its room is in, so the "
                 "slot every row is filtered against is a constant this file chose");
    REQUIRE_TRUE(c, !m.rows.empty(),
                 "no row of the margin corpus checked the ground at the point it was aimed at, "
                 "so the corpus says nothing about the margin");
    REQUIRE_INT(c, m.malformed, 0,
                "rows with no `placement_held` bool - a row that cannot say whether the check "
                "happened at the aim is not a row about the aim");
    require_taken_where_it_says(c, m, "sea_r41_margin_live.json");
    int wrong_poly = 0, wrong_h = 0;
    std::string first_bad;
    const int answers = check(sea(), m, wrong_poly, wrong_h, first_bad);
    REQUIRE_INT(c, wrong_poly, 0,
                "margin-probe rows the walk puts on the wrong triangle" + first_bad);
    REQUIRE_INT(c, wrong_h, 0,
                "margin-probe rows whose ground height is not the console's, bit for bit" +
                    first_bad);
    REQUIRE_TRUE(c, answers > 10,
                 "the console's poly column takes too few distinct values here to be responding "
                 "to the probe");
    c.note(std::to_string(m.rows.size()) + " console row(s) standing on the margin, over " +
           std::to_string(answers) + " distinct answers, poly and height both, in dBgS slot " +
           std::to_string(m.room_bg) + ". Of " + std::to_string(m.aimed) + " aimed probes, " +
           std::to_string(m.displaced) +
           " were shoved out of the geometry they were aimed under before the check ran - a "
           "LOW-Y probe sits under a floor by less than Link's own height - and " +
           std::to_string(m.left_wait) +
           " held the placement on a frame that left daPyProc_WAIT_e, which is a point the row "
           "cannot name (kProcWait)");
    c.note("the aim is not what made a probe capturable: the two widest (1.0 and 0.5 u of xz "
           "slack) are both displaced, and every row that held has 0.1 u or less");
    c.note(std::to_string(m.not_rested) + " of the " + std::to_string(m.aimed) +
           " probes did not reach WAIT inside the capture's settle cap - this room drops a LOW-Y "
           "probe into a fall or a swim, and 20 frames on a neutral stick is not always enough. "
           "They are recorded rather than dropped, and the proc rule above is what admits a row");
}

TWWE_TEST(the_console_stands_on_the_margin_in_the_two_walked_rooms_as_well,
          "the two rooms whose corpora were walked no longer stand on the margin at the points "
          "the enumeration names in them - which would leave the whole constant gated on one "
          "room, and sea r41 is the room whose geometry the enumeration was written against") {
    // Removing the margin leaves no ground at all in kaze r11 (0xFFFF, -1e9), and in GanonA r0
    // gives poly 395 at 970.61115 instead of 425 at 1046.56091.
    using namespace margin_corpus;
    struct Row {
        const char* name;
        Fixture& fx;
        Corpus& m;
        int want_rows;
    };
    Row rooms[] = {{"kaze r11", kaze(), kaze_margin(), 5},
                   {"GanonA r0", ganona(), ganona_margin(), 1}};
    for (const Row& row : rooms) {
        const std::string at = std::string(row.name) + ": ";
        REQUIRE_TRUE(c, row.m.says_room_bg,
                     at + "the corpus does not say which dBgS slot its room is in. It is not 0 "
                          "in either of these rooms - 27 and 4 - so a reader that assumes 0 sets "
                          "every row aside as an actor's collision and agrees with everything");
        REQUIRE_INT(c, row.m.malformed, 0, at + "rows with no `placement_held` bool");
        REQUIRE_INT(c, row.m.not_rested, 0,
                    at + "rows placed from a proc that is not daPyProc_WAIT_e");
        REQUIRE_INT(c, row.m.left_wait, 0,
                    at + "rows that held the placement on a frame which left WAIT - these two "
                         "rooms are indoors and every probe stays put, so one appearing means "
                         "the placement started moving Link");
        require_taken_where_it_says(c, row.m, row.name);
        REQUIRE_INT(c, (int)row.m.rows.size(), row.want_rows,
                    at + "console rows that checked the ground at the aim. A corpus that quietly "
                         "shrinks to nothing is a corpus that passes");
        int wrong_poly = 0, wrong_h = 0;
        std::string first_bad;
        const int answers = check(row.fx, row.m, wrong_poly, wrong_h, first_bad);
        REQUIRE_INT(c, wrong_poly, 0,
                    at + "rows the walk puts on the wrong triangle" + first_bad);
        REQUIRE_INT(c, wrong_h, 0,
                    at + "rows whose ground height is not the console's, bit for bit" + first_bad);
        c.note(std::string(row.name) + ": " + std::to_string(row.m.rows.size()) + " of " +
               std::to_string(row.m.aimed) + " aimed probe(s) held, over " +
               std::to_string(answers) + " distinct answer(s), poly and height both, in dBgS "
               "slot " + std::to_string(row.m.room_bg));
    }
}

TWWE_TEST(the_first_corpus_cannot_say_where_its_own_probe_was,
          "the first sea corpus turns out to have rows where the y it is read at and the y its "
          "frame actually checked give different answers - which would mean its 578 rows are "
          "green on a reconstruction nothing in the file can settle") {
    // sea_r41_ground_live.json predates `probe_dy`, so it cannot say whether the check used
    // `pre` or `pos`. This measures whether the two readings ever answer differently there.
    const Json& g = tww_engine::testing::golden("sea_r41_ground_live.json")["rows"];
    int moved = 0, discriminating = 0, checked = 0;
    for (size_t i = 0; i < g.size(); i++) {
        if (g[i]["floor_bg"].as_int() != 0) {
            continue;
        }
        const f32 raise = g[i]["ground_check_offset"].as_f32() - g[i]["ground_up_h"].as_f32() +
                          g[i]["ground_up_h_diff"].as_f32();
        cXyz a;
        a.x = g[i]["pos_x"].as_f32();
        a.z = g[i]["pos_z"].as_f32();
        a.y = g[i]["pre_y"].as_f32() + raise;
        cXyz b = a;
        b.y = g[i]["pos_y"].as_f32() + raise;
        checked++;
        if (bits(a.y) == bits(b.y)) {
            continue;
        }
        moved++;
        int ta = 0, tb = 0;
        const f32 ya = sea().room().GroundCross(a, &ta);
        const f32 yb = sea().room().GroundCross(b, &tb);
        if (ta != tb || bits(ya) != bits(yb)) {
            discriminating++;
        }
    }
    REQUIRE_TRUE(c, moved > 0,
                 "no row of the first corpus moved in y at all, so this measurement is about "
                 "nothing");
    REQUIRE_INT(c, discriminating, 0,
                "rows of the first corpus whose answer differs between the two y readings - each "
                "one is a row the corpus is green on for a reason it cannot state");
    c.note(std::to_string(moved) + " of " + std::to_string(checked) +
           " rows of the first corpus have a frame that moved Link in y, and " +
           std::to_string(discriminating) +
           " of those answer differently at the pre-move y than at the post-move one. The "
           "corpus cannot tell the two apart, so its green bar is evidence about the descent and "
           "not about the reconstruction");
}

TWWE_RED_CONTROL(red_sea_margin_node_boxes_unexpanded,
                 "the 1.0 cBgW::MakeBlckBnd adds on each of a leaf's six faces removed, so the "
                 "octree descent enters a leaf only where the geometry already is. No walk of "
                 "any room reaches this, and the skirt probes of the first corpus were aimed at "
                 "the one arm of it - CrossY - that the triangle's own xz box makes dead") {
    using namespace margin_corpus;
    const int bad = wrong_with(sea(), sea_margin(), Variant::NodeBoxesUnexpanded);
    c.note("the margin removed: " + std::to_string(bad) + " of " +
           std::to_string(sea_margin().rows.size()) + " console rows on the wrong triangle");
    REQUIRE_INT(c, bad, 0, "console rows the 1.0 node-box margin gets wrong when it is removed");
}

TWWE_RED_CONTROL(red_kaze_margin_node_boxes_unexpanded,
                 "the same 1.0 removed in kaze r11, where the without-the-margin answer is not a "
                 "different polygon but no ground at all - the descent reaches no leaf that can "
                 "offer one, and cBgS::GroundCross returns 0xFFFF and -1e9") {
    using namespace margin_corpus;
    const int bad = wrong_with(kaze(), kaze_margin(), Variant::NodeBoxesUnexpanded);
    c.note("the margin removed: " + std::to_string(bad) + " of " +
           std::to_string(kaze_margin().rows.size()) + " console rows on the wrong triangle");
    REQUIRE_INT(c, bad, 0, "console rows the 1.0 node-box margin gets wrong when it is removed");
}

TWWE_RED_CONTROL(red_ganona_margin_node_boxes_unexpanded,
                 "the same 1.0 removed in GanonA r0, where the without-the-margin answer is a "
                 "floor 76 u lower - poly 395 at 970.61115 instead of poly 425 at 1046.56091") {
    using namespace margin_corpus;
    const int bad = wrong_with(ganona(), ganona_margin(), Variant::NodeBoxesUnexpanded);
    c.note("the margin removed: " + std::to_string(bad) + " of " +
           std::to_string(ganona_margin().rows.size()) + " console rows on the wrong triangle");
    REQUIRE_INT(c, bad, 0, "console rows the 1.0 node-box margin gets wrong when it is removed");
}

TWWE_TEST(the_box_margin_is_reached_through_the_Y_predicates,
          "the enumeration that finds where cBgW::MakeBlckBnd's 1.0 decides a ground check found "
          "nothing - which would put the constant back to copied-and-unreached, and would mean "
          "either the octree's Y predicates stopped reading the margin or this search stopped "
          "looking where it does") {
    // The CrossY arm is dead by construction (the containment is asserted below). min.y and max.y
    // are read by the Y predicates, and a plane can leave its block's y range inside the -20
    // dilated region, so that is where the margin decides.
    struct Row {
        const char* name;
        Fixture& fx;
    };
    Row rooms[] = {{"kaze r11", kaze()}, {"GanonA r0", ganona()}, {"sea r41", sea()}};
    int decides_anywhere = 0;
    std::string out;
    for (const Row& row : rooms) {
        // Every node's built box is its subtree's vertices plus exactly 1.0 per face, so the
        // shrink removes the margin and nothing else.
        const RoomDzb& d = row.fx.dzb();
        const Vec* vtx = row.fx.room().bgw().pm_vtx_tbl;
        for (size_t n = 0; n < d.tree_tbl.size(); n++) {
            const margin::Box raw = margin::raw_subtree(d, vtx, (int)n);
            const cXyz* bmn = row.fx.room().bgw().m_nt_tbl[n].GetMinP();
            const cXyz* bmx = row.fx.room().bgw().m_nt_tbl[n].GetMaxP();
            const f32 got_mn[3] = {bmn->x, bmn->y, bmn->z};
            const f32 got_mx[3] = {bmx->x, bmx->y, bmx->z};
            for (int ax = 0; ax < 3; ax++) {
                const std::string at = std::string(row.name) + " node " + std::to_string(n) +
                                       " axis " + std::to_string(ax);
                REQUIRE_BITS(c, got_mn[ax], raw.mn[ax] - 1.0f, at + " min");
                REQUIRE_BITS(c, got_mx[ax], raw.mx[ax] + 1.0f, at + " max");
            }
        }

        const margin::Arms m = margin::measure(row.fx);
        REQUIRE_INT(c, m.tris_outside_block_box, 0,
                    std::string(row.name) +
                        ": candidate triangles whose own xz box leaves their block's raw box - "
                        "the containment the skirt arm's deadness rests on");
        decides_anywhere += m.low_decides + m.high_decides;
        c.note(std::string(row.name) + ": " + std::to_string(m.leaves) + " leaves, " +
               std::to_string(m.cands) + " candidate polys. SKIRT arm dead by construction. "
               "LOW-Y reached by " + std::to_string(m.low_reach) + " (deepest " +
               std::to_string(m.worst_low) + " u below the block's own min.y), decides " +
               std::to_string(m.low_decides) + " at the window's midpoint and " +
               std::to_string(m.low_decides_at_edge) + " at its top edge. HIGH-Y reached by " +
               std::to_string(m.high_reach) + " (highest " + std::to_string(m.worst_high) +
               " u above its max.y), decides " + std::to_string(m.high_decides));
        // Sorted by xz slack: a probe with slack 0 decides only at its own point.
        std::vector<margin::Probe> named = m.named;
        std::sort(named.begin(), named.end(),
                  [](const margin::Probe& a, const margin::Probe& b) { return a.slack > b.slack; });
        int wide = 0;
        for (const margin::Probe& q : named) {
            if (q.slack >= 0.5f) {
                wide++;
            }
        }
        c.note("  " + std::string(row.name) + ": " + std::to_string(wide) + " of " +
               std::to_string((int)named.size()) +
               " deciding probes still decide half a unit away in x and z");
        for (size_t k = 0; k < named.size() && k < 3; k++) {
            c.note("  " + std::string(row.name) + " " + margin::describe(named[k]));
        }
        for (const margin::Probe& q : named) {
            if (!out.empty()) {
                out += ",\n";
            }
            out += margin::as_json(row.name, q);
        }
    }
    REQUIRE_TRUE(c, decides_anywhere > 0,
                 "no probe in any of the three rooms where removing the 1.0 node-box margin "
                 "changes the port's own answer");
    c.note(std::to_string(decides_anywhere) +
           " probe(s) across the three rooms where the margin changes the port's answer, and the "
           "console has been asked in all three - see `the_console_stands_on_the_node_box_"
           "margin`, `..._in_the_two_WALKED_rooms_as_well` and the three red controls. Where a "
           "probe was not capturable it is because the placement put Link inside the geometry he "
           "is aimed under - a LOW-Y probe sits under its floor by less than Link's own height - "
           "and the wall check moves him before GroundCheck runs.");
    c.note(margin::write_probes(out));
}

// ------------------------------------------------------- the ground walk's visit log
//
// The ground walk logs after RwgGroundCheckCommon's window and cM3d_CrossY_Tri_Front, so it needs
// its own two gates (the wall walk's are in test_wall_correct.cpp).

TWWE_TEST(the_ground_visit_log_does_not_change_the_answer,
          "every centroid probe in kaze r11 asked twice, once with the log off and once with it "
          "on: the height's bits and the polygon index have to be the same. An observer that "
          "moved the answer would make every attribution built on it a statement about the "
          "instrumented engine") {
    Room& room = kaze().room();
    std::vector<int> visited;
    int asked = 0, found = 0;
    long long logged = 0;
    for (const cXyz& q : kaze().centroid_probes()) {
        int off_poly = 0;
        room.LogVisitedPolys(nullptr);
        const f32 off_h = room.GroundCross(q, &off_poly);

        int on_poly = 0;
        visited.clear();
        room.LogVisitedPolys(&visited);
        const f32 on_h = room.GroundCross(q, &on_poly);
        room.LogVisitedPolys(nullptr);

        const std::string at = "probe " + std::to_string(asked);
        REQUIRE_BITS(c, on_h, off_h, at + " ground height");
        REQUIRE_INT(c, on_poly, off_poly, at + " poly");
        asked++;
        found += (off_poly != 0xFFFF) ? 1 : 0;
        logged += (long long)visited.size();
    }
    // A run that asked nothing, or found no floor, would pass the checks above vacuously.
    REQUIRE_TRUE(c, asked > 0, "the population is not empty");
    REQUIRE_TRUE(c, found > 0, "and the walk found a floor at some of it");
    REQUIRE_TRUE(c, logged > 0, "and the log recorded something to be wrong about");
    c.note(std::to_string(asked) + " probe(s), " + std::to_string(found) + " with a floor, " +
           std::to_string(logged) + " polygon(s) logged - the logged run bit-identical throughout");
}

TWWE_TEST(the_ground_visit_log_is_what_reached_the_refusal,
          "what comes back is what RwgGroundCheckCommon had already admitted: every logged "
          "polygon is a ground-walk candidate, is under the probe, and contains it in plan - and "
          "the polygon the walk answered with is in the list. That is what lets a caller read an "
          "absence as `the descent never offered it` rather than as `the log is partial`") {
    Room& room = kaze().room();
    const RoomDzb& d = kaze().dzb();
    std::vector<bool> is_candidate((size_t)room.tri_count(), false);
    for (int poly : kaze().floors_order()) {
        is_candidate[(size_t)poly] = true;
    }

    std::vector<int> visited;
    int asked = 0, answered = 0, off_list = 0, above_probe = 0, outside = 0, unlogged_answer = 0;
    long long total = 0;
    for (const cXyz& q : kaze().centroid_probes()) {
        int poly = 0;
        visited.clear();
        room.LogVisitedPolys(&visited);
        const f32 h = room.GroundCross(q, &poly);
        room.LogVisitedPolys(nullptr);
        asked++;
        total += (long long)visited.size();

        for (int p : visited) {
            if (!is_candidate[(size_t)p]) {
                off_list++;
            }
            const cM3dGPla& pla = room.bgw().pm_tri[(size_t)p].m_plane;
            if (!(pla.getCrossY_NonIsZero(q) < q.y)) {
                above_probe++;
            }
            const cBgD_Tri_t& t = d.t_tbl[(size_t)p];
            cXyz at = q;
            if (!cM3d_CrossY_Tri_Front(d.v_tbl[t.vtx0], d.v_tbl[t.vtx1], d.v_tbl[t.vtx2], &at)) {
                outside++;
            }
        }
        if (poly != 0xFFFF) {
            answered++;
            if (std::find(visited.begin(), visited.end(), poly) == visited.end()) {
                unlogged_answer++;
            }
        }
    }
    REQUIRE_INT(c, off_list, 0, "every logged polygon is one of the room's ground candidates");
    REQUIRE_INT(c, above_probe, 0, "every logged polygon crosses below the probe");
    REQUIRE_INT(c, outside, 0, "every logged polygon contains the probe in plan");
    REQUIRE_INT(c, unlogged_answer, 0, "the polygon the walk answered with is in the log");
    REQUIRE_TRUE(c, answered > 0, "and the walk answered somewhere");
    REQUIRE_TRUE(c, total > 0, "and logged something");
    c.note(std::to_string(asked) + " probe(s), " + std::to_string(answered) +
           " with a floor, " + std::to_string(total) +
           " logged offer(s) - each one admitted by the window and by the plan test");
}

// ------------------------------------------------------- the old sim as the broad oracle
//
// Writes the port's answers at points the old sim is also asked about, so console captures can be
// aimed where the two disagree. Not a gate: both are ports of the same decomp.

TWWE_TEST(the_port_answers_the_points_a_differential_run_asks_for,
          "with TWWE_DIFF_POINTS set, the port's ground answer at every point the old sim will "
          "also be asked about - written out to diff against the old sim, so the console is "
          "only ever spent on the points where two engines disagree") {
    const char* in_path = std::getenv("TWWE_DIFF_POINTS");
    const char* out_path = std::getenv("TWWE_DIFF_OUT");
    if (in_path == nullptr || out_path == nullptr) {
        c.note("set TWWE_DIFF_POINTS=<points.json> and TWWE_DIFF_OUT=<answers.json> to run the "
               "differential. Unset, this case answers nothing and asserts nothing");
        REQUIRE_TRUE(c, true, "");
        return;
    }
    Json pts;
    std::string err;
    REQUIRE_TRUE(c, Json::load(in_path, &pts, &err),
                 std::string("TWWE_DIFF_POINTS could not be read: ") + err);
    const Json& rows = pts["points"];
    const std::string room = pts["bgd"].str;
    // The room is whatever golden the run names; golden() refuses by name one that is not in
    // the manifest or fails its digest.
    RoomDzb dzb = read_room_dzb(tww_engine::testing::golden(room));
    Room fx_room(dzb);
    // TWWE_DIFF_VISITS: the ground walk logs a poly only after RwgGroundCheckCommon's window
    // (`y < probe.y && y > NowY`) and cM3d_CrossY_Tri_Front pass, so a logged poly is one the walk
    // would have taken but for the refusal.
    const bool want_visits = std::getenv("TWWE_DIFF_VISITS") != nullptr;
    std::vector<int> visited;
    std::string body;
    for (size_t i = 0; i < rows.size(); i++) {
        cXyz p;
        p.x = rows[i]["x"].as_f32();
        p.y = rows[i]["probe_y"].as_f32();
        p.z = rows[i]["z"].as_f32();
        int poly = 0;
        visited.clear();
        fx_room.LogVisitedPolys(want_visits ? &visited : nullptr);
        const f32 h = fx_room.GroundCross(p, &poly);
        fx_room.LogVisitedPolys(nullptr);
        char buf[256];
        // The height also goes out as bits, so the diff needs no tolerance.
        std::snprintf(buf, sizeof(buf),
                      "%s{\"i\": %zu, \"poly\": %d, \"h\": %.9g, \"h_bits\": %u",
                      i ? ",\n" : "", i, poly, (double)h, (unsigned)bits(h));
        body += buf;
        if (want_visits) {
            body += ", \"visited\": [";
            for (size_t v = 0; v < visited.size(); v++) {
                body += (v ? "," : "") + std::to_string(visited[v]);
            }
            body += "]";
        }
        body += "}";
    }
    std::FILE* f = std::fopen(out_path, "wb");
    REQUIRE_TRUE(c, f != nullptr,
                 std::string("TWWE_DIFF_OUT could not be opened: ") + out_path);
    if (f != nullptr) {
        std::fprintf(f, "{\"bgd\": \"%s\", \"answers\": [\n%s\n]}\n", room.c_str(), body.c_str());
        std::fclose(f);
    }
    c.note(std::to_string(rows.size()) + " point(s) answered from " + room + " -> " + out_path);
}
