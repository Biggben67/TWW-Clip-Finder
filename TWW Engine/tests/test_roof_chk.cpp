// test_roof_chk.cpp - dBgS::RoofChk (called from CrrPos, d_bg_s_acch.cpp:250-253) against the
// console's margin-corpus rows, and red controls for the ways it mirrors the ground walk.
//
// The walk is dBgW's RwgRoofChk / RoofChkRp / RoofChkGrpRp. Versus the ground walk, four things
// point the other way: the chain (pm_blk[].roof), the window (`y > pos.y && y < NowY`), the node
// predicates (same three, y arguments exchanged), and cM3d_CrossY_Tri (either winding, where the
// ground check's `_Front` takes one).
//
// The margin corpora carry roof_tri / roof_bg / roof_now_y / roof_h per row: 6 rows name a
// ceiling (kaze r11 polys 685 / 965 / 970, GanonA r0 poly 147) and 36 sea r41 rows find none.

#include <cstdio>
#include <set>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "SSystem/SComponent/c_bg_w.h"
#include "SSystem/SComponent/c_m3d.h"
#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"
#include "engine/room.h"
#include "room_dzb.h"

namespace {

using tww_engine::PassChk;
using tww_engine::Room;
using tww_engine::RoomDzb;
using tww_engine::testing::bits;
using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::read_room_dzb;

//: daPyProc_WAIT_e: only WAIT->WAIT rows have a reconstructable probe (see test_ground_walk.cpp).
const int kProcWait = 4;

//: cBgS_PolyInfo's "no poly".
const int kNoPoly = 0xFFFF;

Room& room_of(const char* bgd) {
    if (std::string(bgd) == "kaze_r11_bgd.json") {
        static Room r(read_room_dzb(tww_engine::testing::golden("kaze_r11_bgd.json")));
        return r;
    }
    if (std::string(bgd) == "ganona_r0_bgd.json") {
        static Room r(read_room_dzb(tww_engine::testing::golden("ganona_r0_bgd.json")));
        return r;
    }
    static Room r(read_room_dzb(tww_engine::testing::golden("sea_r41_bgd.json")));
    return r;
}

// ------------------------------------------------------------------------------- the corpus

/// One frame's ceiling check, which can run twice: CrrPos asks from Link's position before the
/// ground snap (d_bg_s_acch.cpp:250-253), then GroundRoofProc asks again from the snapped
/// position when `m_ground_h >= m_roof_height` (:160-168). The capture holds the last answer.
struct RoofRow {
    cXyz probe;      //: pm_pos as CrrPos passed it, not raised by 60
    cXyz post;       //: *pm_pos as GroundRoofProc passes it: the row's end-of-frame y
    f32 ground_h;    //: m_ground_h, which GroundRoofProc's condition tests
    int roof_tri;    //: 0xFFFF when the console found no ceiling
    f32 roof_h;
    std::string where;
};

/// The admitted rows and a count for each admission rule.
struct RoofCorpus {
    std::vector<RoofRow> rows;
    int aimed = 0;         //: rows in the file
    int malformed = 0;     //: rows with no `placement_held` bool
    int not_wait = 0;      //: rows whose frame did not begin and end in daPyProc_WAIT_e
    int displaced = 0;     //: rows the placement did not hold, or whose ground was another bg
    int other_bg = 0;      //: rows whose ceiling belongs to another collision object
    int found = 0;         //: admitted rows naming a ceiling
    int none = 0;          //: admitted rows where the console found none
    int halves_disagree = 0;  //: rows where m_roof_height is not dBgS_RoofChk::m_now_y
    int second_call = 0;      //: admitted rows where GroundRoofProc asked a second time
    int second_changed = 0;   //: of those, the ones where the second answer is not the first
    int room_bg = -1;
    bool says_room_bg = false;
    const Json* file = nullptr;
};

RoofCorpus load(const char* name) {
    RoofCorpus out;
    const Json& file = tww_engine::testing::golden(name);
    out.file = &file;
    out.says_room_bg = file["room_bg"].kind == Json::Kind::Number;
    out.room_bg = out.says_room_bg ? (int)file["room_bg"].as_int() : -1;
    const Json& g = file["rows"];
    out.aimed = (int)g.size();
    for (size_t i = 0; i < g.size(); i++) {
        if (g[i]["placement_held"].kind != Json::Kind::Bool) {
            out.malformed++;
        }
        if (g[i]["proc_in"].kind != Json::Kind::Number ||
            g[i]["proc"].kind != Json::Kind::Number ||
            g[i]["proc_in"].as_int() != kProcWait || g[i]["proc"].as_int() != kProcWait) {
            out.not_wait++;
            continue;
        }
        if (!g[i]["placement_held"].boolean || (int)g[i]["floor_bg"].as_int() != out.room_bg) {
            out.displaced++;
            continue;
        }
        // dBgS::RoofChk returns chk->GetNowY() into m_roof_height; the two must match.
        if (bits(g[i]["roof_h"].as_f32()) != bits(g[i]["roof_now_y"].as_f32())) {
            out.halves_disagree++;
        }
        const int tri = (int)g[i]["roof_tri"].as_int();
        // dBgS::RoofChk takes the min over every registered bg; only the room is loaded here.
        if (tri != kNoPoly && (int)g[i]["roof_bg"].as_int() != out.room_bg) {
            out.other_bg++;
            continue;
        }
        RoofRow r;
        // d_bg_s_acch.cpp:250-253: `m_roof.SetPos(*pm_pos)` with no offset, before GroundCheck.
        // The y is test_ground_walk.cpp's reconstruction without its +60.
        r.probe.x = g[i]["pos_x"].as_f32();
        r.probe.y = g[i]["pre_y"].as_f32() + g[i]["probe_dy"].as_f32();
        r.probe.z = g[i]["pos_z"].as_f32();
        // The second call's point: nothing after GroundRoofProc moves y, so end-of-frame pos_y.
        r.post = r.probe;
        r.post.y = g[i]["pos_y"].as_f32();
        r.ground_h = g[i]["ground_h"].as_f32();
        r.roof_tri = tri;
        r.roof_h = g[i]["roof_now_y"].as_f32();
        r.where = std::string(name) + " row " + std::to_string(i);
        out.rows.push_back(r);
        if (tri == kNoPoly) {
            out.none++;
        } else {
            out.found++;
        }
    }
    return out;
}

RoofCorpus& sea_roof() {
    static RoofCorpus c = load("sea_r41_margin_live.json");
    return c;
}

RoofCorpus& kaze_roof() {
    static RoofCorpus c = load("kaze_r11_margin_live.json");
    return c;
}

RoofCorpus& ganona_roof() {
    static RoofCorpus c = load("ganona_r0_margin_live.json");
    return c;
}

std::string exact(f32 v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.9g", (double)v);
    return buf;
}

/// The frame's ceiling answer: CrrPos's call, then GroundRoofProc's where it runs. `twice` says
/// whether the second ran, `moved` whether it changed the answer.
f32 answer_for(Room& room, const RoofRow& row, int* out_poly, bool* twice, bool* moved) {
    int p = 0;
    const f32 first = room.RoofChk(row.probe, &p);
    *twice = false;
    *moved = false;
    // GroundRoofProc, d_bg_s_acch.cpp:157-168.
    if (bits(row.ground_h) != bits(-G_CM3D_F_INF) && row.ground_h >= first) {
        *twice = true;
        int p2 = 0;
        const f32 second = room.RoofChk(row.post, &p2);
        *moved = (p2 != p) || (bits(second) != bits(first));
        if (out_poly != nullptr) {
            *out_poly = p2;
        }
        return second;
    }
    if (out_poly != nullptr) {
        *out_poly = p;
    }
    return first;
}

/// Height asserted per row with REQUIRE_BITS; poly mismatches counted, `first_bad` names the first.
int check(Case& c, Room& room, RoofCorpus& corpus, int& wrong_poly, int& wrong_h,
          std::string& first_bad) {
    std::set<int> answers;
    wrong_poly = 0;
    wrong_h = 0;
    corpus.second_call = 0;
    corpus.second_changed = 0;
    first_bad.clear();
    for (const RoofRow& row : corpus.rows) {
        int got = 0;
        bool twice = false, moved = false;
        const f32 y = answer_for(room, row, &got, &twice, &moved);
        answers.insert(row.roof_tri);
        corpus.second_call += twice ? 1 : 0;
        corpus.second_changed += moved ? 1 : 0;
        const bool bad_poly = got != row.roof_tri;
        const bool bad_h = bits(y) != bits(row.roof_h);
        wrong_poly += bad_poly ? 1 : 0;
        wrong_h += bad_h ? 1 : 0;
        REQUIRE_BITS(c, y, row.roof_h, row.where + ": the ceiling height m_roof_height held");
        if ((bad_poly || bad_h) && first_bad.empty()) {
            first_bad = ". First: " + row.where + " at x=" + exact(row.probe.x) + " y=" +
                        exact(row.probe.y) + " z=" + exact(row.probe.z) + " - console poly " +
                        std::to_string(row.roof_tri) + " h=" + exact(row.roof_h) +
                        ", port poly " + std::to_string(got) + " h=" + exact(y);
        }
    }
    return (int)answers.size();
}

/// The same rows with CrrPos's answer alone, GroundRoofProc's second call dropped.
int wrong_without_the_second_call(Room& room, const RoofCorpus& corpus) {
    int bad = 0;
    for (const RoofRow& row : corpus.rows) {
        int got = 0;
        const f32 y = room.RoofChk(row.probe, &got);
        if (got != row.roof_tri || bits(y) != bits(row.roof_h)) {
            bad++;
        }
    }
    return bad;
}

// ---------------------------------------------------------------------- the variant harness
//
// An editable copy of dBgW::RwgRoofChk / RoofChkRp / RoofChkGrpRp with one piece swappable.
// `the_roof_variant_harness_is_the_ported_walk` holds Variant::None equal to Room::RoofChk.

enum class Variant {
    None,         //: the ported path, unchanged
    SwapYArgs,    //: UnderPlaneYUnder(pos.y) / TopPlaneYUnder(NowY), the ground walk's order
    WindowDown,   //: `y < pos.y && y > NowY` off -G_CM3D_F_INF, a maximum below the probe
    FrontOnly,    //: cM3d_CrossY_Tri_Front, which accepts one winding
    GroundChain,  //: pm_blk[].ground walked instead of pm_blk[].roof
    NoIsZero,     //: getCrossY_NonIsZero - the plane's ny guard dropped
    GroundOrder,  //: children visited 2,3,6,7,0,1,4,5 rather than 0..7
};

class RoofWalk {
  public:
    RoofWalk(Room& room, Variant var) : m_w(room.bgw()), m_var(var) {
        m_poly_pass.SetLink();
    }

    f32 run(const cXyz& pos, int* out_poly) {
        m_now = (m_var == Variant::WindowDown) ? -G_CM3D_F_INF : G_CM3D_F_INF;
        m_hit = kNoPoly;
        grp_rp(pos, m_w.m_rootGrpIdx, 1);
        if (out_poly != nullptr) {
            *out_poly = m_hit;
        }
        return m_now;
    }

  private:
    /// RoofChkRp's node-box predicates, or GroundCrossRp's (arguments exchanged).
    bool box_ok(const cM3dGAab& box, const cXyz& pos) const {
        if (!box.CrossY(&pos)) {
            return false;
        }
        if (m_var == Variant::SwapYArgs) {
            return box.UnderPlaneYUnder(pos.y) && !box.TopPlaneYUnder(m_now);
        }
        return box.UnderPlaneYUnder(m_now) && !box.TopPlaneYUnder(pos.y);
    }

    bool rwg(u16 poly_index, const cXyz& pos) {
        bool ret = false;
        while (true) {
            f32 y;
            bool crossed;
            if (m_var == Variant::NoIsZero) {
                y = m_w.pm_tri[poly_index].m_plane.getCrossY_NonIsZero(pos);
                crossed = true;
            } else {
                crossed = m_w.pm_tri[poly_index].m_plane.getCrossY(pos, &y);
            }
            const bool in_window = (m_var == Variant::WindowDown) ? (y < pos.y && y > m_now)
                                                                  : (y > pos.y && y < m_now);
            if (crossed && in_window) {
                const cBgD_Tri_t* tri = &m_w.pm_bgd->m_t_tbl[poly_index];
                const Vec& a = m_w.pm_vtx_tbl[tri->vtx0];
                const Vec& b = m_w.pm_vtx_tbl[tri->vtx1];
                const Vec& c = m_w.pm_vtx_tbl[tri->vtx2];
                const bool inside =
                    (m_var == Variant::FrontOnly)
                        ? cM3d_CrossY_Tri_Front(a, b, c, &pos)
                        : cM3d_CrossY_Tri(a, b, c, m_w.pm_tri[poly_index].m_plane, &pos);
                if (inside && !m_w.ChkPolyThrough(poly_index, &m_poly_pass)) {
                    m_now = y;
                    m_hit = poly_index;
                    ret = true;
                }
            }
            if (m_w.pm_rwg[poly_index].next == 0xFFFF) {
                break;
            }
            poly_index = m_w.pm_rwg[poly_index].next;
        }
        return ret;
    }

    bool rp(const cXyz& pos, int i) {
        if (!box_ok(m_w.m_nt_tbl[i], pos)) {
            return false;
        }
        const cBgD_Tree_t* tree = &m_w.pm_bgd->m_tree_tbl[i];
        if (tree->mFlag & 1) {
            const u16 head = (m_var == Variant::GroundChain) ? m_w.pm_blk[tree->mBlock].ground
                                                             : m_w.pm_blk[tree->mBlock].roof;
            return head != 0xFFFF && rwg(head, pos);
        }
        static const int kRoof[8] = {0, 1, 2, 3, 4, 5, 6, 7};
        static const int kGround[8] = {2, 3, 6, 7, 0, 1, 4, 5};
        const int* order = (m_var == Variant::GroundOrder) ? kGround : kRoof;
        bool ret = false;
        for (int k = 0; k < 8; k++) {
            const u16 child = tree->mChild[order[k]];
            if (child != 0xFFFF && rp(pos, child)) {
                ret = true;
            }
        }
        return ret;
    }

    bool grp_rp(const cXyz& pos, int grp_id, int depth) {
        if (m_w.ChkGrpThrough(grp_id, &m_grp_pass, depth)) {
            return false;
        }
        if (!box_ok(m_w.pm_grp[grp_id].aab, pos)) {
            return false;
        }
        bool ret = false;
        const cBgD_Grp_t* grpd = &m_w.pm_bgd->m_g_tbl[grp_id];
        const u32 tree_idx = grpd->m_tree_idx;
        if (tree_idx != 0xFFFF && rp(pos, (int)tree_idx)) {
            ret = true;
        }
        depth++;
        s32 child_idx = grpd->m_first_child;
        while (child_idx != 0xFFFF) {
            if (grp_rp(pos, child_idx, depth)) {
                ret = true;
            }
            child_idx = m_w.pm_bgd->m_g_tbl[child_idx].m_next_sibling;
        }
        return ret;
    }

    cBgW& m_w;
    Variant m_var;
    dBgS_PolyPassChk m_poly_pass;
    dBgS_GrpPassChk m_grp_pass;
    f32 m_now = 0.0f;
    int m_hit = kNoPoly;
};

/// `answer_for` through the harness.
f32 harness_answer(RoofWalk& w, const RoofRow& row, int* out_poly) {
    int p = 0;
    const f32 first = w.run(row.probe, &p);
    if (bits(row.ground_h) != bits(-G_CM3D_F_INF) && row.ground_h >= first) {
        return w.run(row.post, out_poly);
    }
    if (out_poly != nullptr) {
        *out_poly = p;
    }
    return first;
}

/// Rows the variant gets wrong, among rows the unmutated harness gets right.
int wrong_with(Room& room, const RoofCorpus& corpus, Variant var) {
    RoofWalk base(room, Variant::None);
    RoofWalk mut(room, var);
    int bad = 0;
    for (const RoofRow& row : corpus.rows) {
        int got = 0;
        const f32 y = harness_answer(base, row, &got);
        if (got != row.roof_tri || bits(y) != bits(row.roof_h)) {
            continue;
        }
        int got_m = 0;
        const f32 y_m = harness_answer(mut, row, &got_m);
        if (got_m != row.roof_tri || bits(y_m) != bits(row.roof_h)) {
            bad++;
        }
    }
    return bad;
}

struct Arm {
    const char* bgd;
    RoofCorpus& (*corpus)();
    const char* label;
};

const Arm kArms[] = {
    {"sea_r41_bgd.json", sea_roof, "sea r41"},
    {"kaze_r11_bgd.json", kaze_roof, "kaze r11"},
    {"ganona_r0_bgd.json", ganona_roof, "GanonA r0"},
};

int total_rows() {
    return (int)(sea_roof().rows.size() + kaze_roof().rows.size() + ganona_roof().rows.size());
}

int total_found() {
    return sea_roof().found + kaze_roof().found + ganona_roof().found;
}

}  // namespace

TWWE_TEST(the_console_answers_the_ported_ceiling_check,
          "dBgS::RoofChk's answer - the polygon and the height - at every point in the three "
          "margin corpora where the console can say what it was, bit for bit, in all three "
          "rooms") {
    int rows = 0, found = 0, none = 0, answers = 0, second = 0, second_changed = 0;
    for (const Arm& arm : kArms) {
        RoofCorpus& m = arm.corpus();
        REQUIRE_TRUE(c, m.says_room_bg,
                     std::string(arm.label) +
                         "'s corpus does not say which dBgS slot its room is in, so the slot "
                         "every row is filtered against is a constant this file chose");
        REQUIRE_INT(c, m.malformed, 0,
                    std::string(arm.label) +
                        ": rows with no `placement_held` bool - a row that cannot say whether "
                        "the check happened at the aim is not a row about the aim");
        REQUIRE_INT(c, m.halves_disagree, 0,
                    std::string(arm.label) +
                        ": rows where m_roof_height and dBgS_RoofChk::m_now_y are not the same "
                        "float - they are the return value and its copy");
        int wrong_poly = 0, wrong_h = 0;
        std::string first_bad;
        const int distinct = check(c, room_of(arm.bgd), m, wrong_poly, wrong_h, first_bad);
        REQUIRE_INT(c, wrong_poly, 0,
                    std::string(arm.label) + ": rows the roof walk puts on the wrong ceiling " +
                        "polygon" + first_bad);
        rows += (int)m.rows.size();
        found += m.found;
        none += m.none;
        answers += distinct;
        second += m.second_call;
        second_changed += m.second_changed;
        c.note(std::string(arm.label) + ": " + std::to_string(m.rows.size()) +
               " row(s) admitted of " + std::to_string(m.aimed) + " (" +
               std::to_string(m.found) + " naming a ceiling, " + std::to_string(m.none) +
               " with none), in dBgS slot " + std::to_string(m.room_bg) + ". Set aside: " +
               std::to_string(m.not_wait) + " not WAIT->WAIT, " + std::to_string(m.displaced) +
               " displaced, " + std::to_string(m.other_bg) + " whose ceiling is another slot's");
    }
    REQUIRE_TRUE(c, found > 0,
                 "no admitted row names a ceiling at all, so every assertion above is about "
                 "the walk finding nothing - which it would also do if it never ran");
    REQUIRE_TRUE(c, none > 0,
                 "no admitted row says there is no ceiling, so nothing here would catch a walk "
                 "that finds one over open sea");
    c.note(std::to_string(rows) + " console row(s) over " + std::to_string(answers) +
           " distinct answer(s): " + std::to_string(found) + " name a ceiling and " +
           std::to_string(none) + " say there is none. The 36 sea rows are the population that "
           "catches a walk which finds a ceiling where there is open sky");
    c.note(std::to_string(second) + " of the " + std::to_string(rows) +
           " rows take GroundRoofProc's second call, and it changes the answer on " +
           std::to_string(second_changed) +
           " of them - so the frame's ceiling is the second call's there and CrrPos's on the "
           "rest. The two are asked ~60 u apart, because the ground snap runs between them");
    int without = 0;
    for (const Arm& arm : kArms) {
        without += wrong_without_the_second_call(room_of(arm.bgd), arm.corpus());
    }
    REQUIRE_TRUE(c, without > 0,
                 "no row notices when GroundRoofProc's second call is dropped and CrrPos's "
                 "answer is taken as the frame's - so the sequence above is modelled and not "
                 "gated, and a port that made only the first call would be green here");
    c.note("dropping GroundRoofProc's second call and taking CrrPos's answer as the frame's: " +
           std::to_string(without) + " of " + std::to_string(rows) + " rows wrong");
}

TWWE_TEST(the_roof_variant_harness_is_the_ported_walk,
          "the editable copy of the roof walk answers exactly what dBgW's copied bodies answer, "
          "on every admitted row and at both candidate positions - without which a red control "
          "below is evidence about this file rather than about the port") {
    int checked = 0, differs = 0;
    for (const Arm& arm : kArms) {
        Room& r = room_of(arm.bgd);
        RoofWalk h(r, Variant::None);
        for (const RoofRow& row : arm.corpus().rows) {
            for (const cXyz* p : {&row.probe, &row.post}) {
                int a = 0, b = 0;
                const f32 ya = r.RoofChk(*p, &a);
                const f32 yb = h.run(*p, &b);
                checked++;
                if (a != b || bits(ya) != bits(yb)) {
                    differs++;
                }
            }
        }
    }
    REQUIRE_INT(c, differs, 0,
                "points where the variant harness and the ported walk disagree");
    REQUIRE_TRUE(c, checked > 0, "the harness was never compared against anything");
    c.note(std::to_string(checked) + " point(s) compared, poly and height both");
}

TWWE_TEST(the_ceiling_walk_is_not_the_ground_walk_wearing_a_different_chain,
          "each of the four things that point the other way in the roof walk, written the "
          "ground walk's way instead - and what that costs on the console rows") {
    struct Control {
        Variant var;
        const char* what;
    };
    static const Control kControls[] = {
        {Variant::SwapYArgs,
         "the three node-box predicates given the ground walk's y arguments"},
        {Variant::WindowDown, "the window written `y < pos.y && y > NowY`, off -G_CM3D_F_INF"},
        {Variant::FrontOnly, "cM3d_CrossY_Tri_Front in place of cM3d_CrossY_Tri"},
        {Variant::GroundChain, "the block's ground chain walked instead of its roof chain"},
    };
    for (const Control& ctl : kControls) {
        int bad = 0, over = 0;
        std::string split;
        for (const Arm& arm : kArms) {
            const int n = wrong_with(room_of(arm.bgd), arm.corpus(), ctl.var);
            bad += n;
            over += (int)arm.corpus().rows.size();
            split += std::string(split.empty() ? "" : ", ") + arm.label + " " +
                     std::to_string(n);
        }
        c.note(std::string(ctl.what) + ": " + std::to_string(bad) + " of " +
               std::to_string(over) + " rows wrong (" + split + ")");
        REQUIRE_TRUE(c, bad > 0,
                     std::string("no console row notices when ") + ctl.what +
                         " - so nothing here holds that piece of the walk, and it is copied "
                         "rather than gated");
    }
}

TWWE_TEST(the_ny_guard_inside_the_roof_walk_cannot_fire_on_a_roof_chain,
          "RwgRoofChk asks getCrossY, which refuses a plane whose ny is IsZero, and "
          "cM3d_CrossY_Tri opens with the same test - but ClassifyPlane only threads a polygon "
          "onto a roof chain for ny < -0.8f, so neither guard has a plane it can refuse. This "
          "is the structural reason, as a number, instead of a red control that never bites") {
    int polys = 0;
    f32 worst = 1.0f;
    std::string where;
    for (const Arm& arm : kArms) {
        Room& r = room_of(arm.bgd);
        for (int b = 0; b < r.block_count(); b++) {
            for (int poly : r.roof_chain(b)) {
                const f32 ny = r.bgw().pm_tri[poly].m_plane.GetNP()->y;
                const f32 mag = ny < 0.0f ? -ny : ny;
                polys++;
                if (mag < worst) {
                    worst = mag;
                    where = std::string(arm.label) + " poly " + std::to_string(poly);
                }
            }
        }
    }
    REQUIRE_TRUE(c, polys > 0,
                 "no polygon is on any roof chain in any of the three rooms, so there is no "
                 "roof walk here to say anything about");
    // cBgW_CheckBRoof is `ny < -4.0f/5.0f` (c_bg_w.h); cM3d_IsZero's threshold is
    // G_CM3D_F_ABS_MIN = 3.8146973e-06f.
    REQUIRE_TRUE(c, worst >= 0.8f,
                 "a polygon on a roof chain has |ny| below cBgW_CheckBRoof's own 0.8 threshold "
                 "(" + where + " at " + exact(worst) +
                 ") - which would mean the chain was built by something other than "
                 "ClassifyPlane, and the ny guards become reachable");
    c.note(std::to_string(polys) + " roof-chain polygon(s) over the three rooms; the smallest "
           "|ny| among them is " + exact(worst) + " (" + where +
           "), against cM3d_IsZero's 3.8146973e-06f. Measured, not argued: swapping getCrossY "
           "for getCrossY_NonIsZero changes no answer on any of the console rows either");
}

TWWE_TEST(the_octree_child_order_cannot_change_the_ceiling_the_walk_finds,
          "RoofChkRp visits children 0..7 where GroundCrossRp visits 2,3,6,7,0,1,4,5, and the "
          "order is claimed not to matter because the running extremum only ever moves past "
          "candidates that would have lost - so this is the claim, measured") {
    int checked = 0, differs = 0;
    for (const Arm& arm : kArms) {
        Room& r = room_of(arm.bgd);
        RoofWalk base(r, Variant::None);
        RoofWalk other(r, Variant::GroundOrder);
        for (const RoofRow& row : arm.corpus().rows) {
            int a = 0, b = 0;
            const f32 ya = base.run(row.probe, &a);
            const f32 yb = other.run(row.probe, &b);
            checked++;
            if (a != b || bits(ya) != bits(yb)) {
                differs++;
            }
        }
    }
    REQUIRE_INT(c, differs, 0,
                "rows whose ceiling changes when the octree is walked in the ground check's "
                "child order - if this is ever nonzero the order is load-bearing and the "
                "argument above is wrong");
    c.note(std::to_string(checked) +
           " row(s) answered identically in both child orders, poly and height. So a port that "
           "swapped them would still be green here: what the order changes is how much work is "
           "done, and nothing below measures that");
}

// ---------------------------------------------------------------- which state a corpus is about
//
// The corpora record the proc but not the frame's initial state; `checkRestHPAnime` swaps the
// idle animation at `dComIfGs_getLife() <= 6`, and the animation sets the acch's geometry. A
// known gap until a corpus carries a `has_state` block.

TWWE_TEST(the_corpora_cannot_say_which_link_they_are_about,
          "the console corpora every collision gate stands on do not record the initial state "
          "their rows were taken in, so the gates are conditioned on a variable that was never "
          "written down - this case exists to fail until that is untrue") {
    int with_state = 0;
    for (const Arm& arm : kArms) {
        const Json& file = *arm.corpus().file;
        const bool says = file["has_state"].kind == Json::Kind::Bool && file["has_state"].boolean;
        with_state += says ? 1 : 0;
        c.note(std::string(arm.label) + ": " + std::to_string(arm.corpus().rows.size()) +
               " admitted row(s), state block " + (says ? "PRESENT" : "ABSENT") +
               ". What they can still say: proc_in and proc, both daPyProc_WAIT_e by admission. "
               "What they cannot: low_life, sword_drawn, the idle frame, the anim block");
    }
    EXPECT_KNOWN_GAP(c, with_state == (int)(sizeof(kArms) / sizeof(kArms[0])),
                     "every margin corpus records the LandState seed block its rows were taken "
                     "in. Until then these rows are bit-exact on one unrecorded state, which is a "
                     "smaller claim than it looks - and a capture that carries the block makes "
                     "this a homogeneity gate over its seed states");
    c.note(std::to_string(with_state) + " of 3 corpora carry it. Not a reason to re-capture: "
           "console time is spent only on a difference the offline differential cannot "
           "attribute. This is a standing caveat on the banked rows, and new evidence comes from "
           "the differential against the old sim instead");
}
