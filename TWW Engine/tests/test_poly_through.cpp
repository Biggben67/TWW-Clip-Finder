// test_poly_through.cpp - dBgW's two refusals, in a room where they refuse something.
//
// A room's collision is a dBgW. cBgW::ChkPolyThrough and cBgW::ChkGrpThrough are virtual
// `return false`s, and dBgW overrides both:
//
//   ChkPolyThrough   per candidate, inside RwgGroundCheckCommon, after the poly is found below the
//                    probe, above the best and inside the triangle. It tests one bit of
//                    m_ti_tbl[m_t_tbl[poly].id].mPolyInf3 per asker; Link's ground check is 0x04.
//   ChkGrpThrough    per group at depth 2 (the root's children), before its octree is entered.
//                    A NORMAL_GRP-only query skips groups flagged water (0x100), lava (0x200),
//                    doku (0x400) or light (0x80000) in m_g_tbl[grp].m_info.
//
// In kaze r11 and GanonA r0, where the walk is gated, neither can decide anything (asserted by
// the first case). sea r41 reaches both on disjoint polygons from the disc's own data: `Water_00`
// is a depth-2 group with m_info 0x129 and 17 ground triangles, and 25 more ground triangles in
// kept groups have mPolyInf3 & 0x04.
//
// No live capture of sea r41 exists, so this grades reach and decision, not console agreement.
// `PassChk::None` takes the decomp's own `if (chk == NULL) return false` arm, so a Link-vs-None
// difference is the copied body's decision.

#include <set>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/runner.h"

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

//: dBgS_PolyPassChk::SetLink's bit in mPolyInf3, d_bg_w.cpp:887.
const u32 kLinkThrough = 0x04;
//: The four kinds dBgW::ChkGrpThrough tests for, d_bg_w.cpp:918.
const u32 kSpecialGrp = 0x80700;
//: d_bg_s_acch.cpp:59-60, :128 - the raise dBgS_Acch::GroundCheck makes before the query.
const f32 kGroundCheckOffset = 60.0f;

/// The room's tables read the way the two overrides read them, plus the sets a probe can be
/// attributed to, all derived from the fixture.
class Sea {
  public:
    Sea() : m_dzb(read_room_dzb(tww_engine::testing::golden("sea_r41_bgd.json"))), m_room(m_dzb) {
        // Every poly in some block's ground chain: what RwgGroundCheckCommon can be asked about.
        for (int b = 0; b < m_room.block_count(); b++) {
            for (int poly : m_room.ground_chain(b)) {
                m_ground.push_back(poly);
            }
        }

        // poly -> cBgD_Tri_t::id -> cBgD_Ti_t::mPolyInf3.
        for (int poly : m_ground) {
            const u16 id = m_dzb.t_tbl[(size_t)poly].id;
            if (id < m_dzb.ti_tbl.size() && (m_dzb.ti_tbl[id].mPolyInf3 & kLinkThrough)) {
                m_link_through.insert(poly);
            }
        }

        // The depth-2 groups ChkGrpThrough refuses a NORMAL_GRP-only query, and every polygon under
        // each.
        const int root = m_room.bgw().m_rootGrpIdx;
        for (u16 g = m_dzb.g_tbl[(size_t)root].m_first_child; g != 0xFFFF;
             g = m_dzb.g_tbl[g].m_next_sibling) {
            if (m_dzb.g_tbl[g].m_info & kSpecialGrp) {
                m_skipped_groups.push_back((int)g);
                collect_group_polys((int)g);
            }
        }

        // One probe over each ground polygon's centroid, raised clear of it.
        for (int poly : m_ground) {
            const cBgD_Tri_t& t = m_dzb.t_tbl[(size_t)poly];
            const cBgD_Vtx_t* v = m_room.bgw().pm_vtx_tbl;
            const u16 idx[3] = {t.vtx0, t.vtx1, t.vtx2};
            cXyz q;
            q.x = (v[idx[0]].x + v[idx[1]].x + v[idx[2]].x) / 3.0f;
            q.y = (v[idx[0]].y + v[idx[1]].y + v[idx[2]].y) / 3.0f + kGroundCheckOffset;
            q.z = (v[idx[0]].z + v[idx[1]].z + v[idx[2]].z) / 3.0f;
            m_probes.push_back(q);
        }
    }

    Room& room() { return m_room; }
    const RoomDzb& dzb() const { return m_dzb; }
    const std::vector<int>& ground() const { return m_ground; }
    const std::set<int>& link_through() const { return m_link_through; }
    const std::vector<int>& skipped_groups() const { return m_skipped_groups; }
    const std::set<int>& in_skipped_group() const { return m_in_skipped; }
    const std::vector<cXyz>& probes() const { return m_probes; }

  private:
    void collect_group_polys(int g) {
        const u16 tree_idx = m_dzb.g_tbl[(size_t)g].m_tree_idx;
        if (tree_idx != 0xFFFF) {
            collect_node_polys((int)tree_idx);
        }
        for (u16 c = m_dzb.g_tbl[(size_t)g].m_first_child; c != 0xFFFF;
             c = m_dzb.g_tbl[c].m_next_sibling) {
            collect_group_polys((int)c);
        }
    }

    /// The octree under one node. A leaf is `mFlag & 1` and its block is mChild[0] (cBgD_Tree_t's
    /// mBlock union).
    void collect_node_polys(int node) {
        const cBgD_Tree_t& n = m_dzb.tree_tbl[(size_t)node];
        if (n.mFlag & 1) {
            const u16 blk = n.mChild[0];
            if (blk == 0xFFFF) {
                return;
            }
            const int lo = m_dzb.b_tbl[blk].startTri;
            const int hi = ((size_t)blk + 1 < m_dzb.b_tbl.size())
                               ? (int)m_dzb.b_tbl[blk + 1].startTri - 1
                               : (int)m_dzb.t_tbl.size() - 1;
            for (int p = lo; p <= hi; p++) {
                m_in_skipped.insert(p);
            }
            return;
        }
        for (int k = 0; k < 8; k++) {
            if (n.mChild[k] != 0xFFFF) {
                collect_node_polys((int)n.mChild[k]);
            }
        }
    }

    RoomDzb m_dzb;
    Room m_room;
    std::vector<int> m_ground;
    std::set<int> m_link_through;
    std::vector<int> m_skipped_groups;
    std::set<int> m_in_skipped;
    std::vector<cXyz> m_probes;
};

Sea& sea() {
    static Sea s;
    return s;
}

/// What a Link ground check and a pass-check-free one disagree about, by override.
/// `unattributed` is reported separately: nonzero means something else decides.
struct Split {
    int differ = 0;
    int by_poly = 0;
    int by_group = 0;
    int unattributed = 0;
};

Split split_of(Room& r, const Sea& s) {
    Split out;
    for (const cXyz& q : s.probes()) {
        int with_link = 0, without = 0;
        const f32 y_link = r.GroundCross(q, &with_link, PassChk::Link);
        const f32 y_none = r.GroundCross(q, &without, PassChk::None);
        if (with_link == without && bits(y_link) == bits(y_none)) {
            continue;
        }
        out.differ++;
        // Attributed by what the unrefused query found.
        if (s.link_through().count(without) != 0) {
            out.by_poly++;
        } else if (s.in_skipped_group().count(without) != 0) {
            out.by_group++;
        } else {
            out.unattributed++;
        }
    }
    return out;
}

/// The room with one field of the fixture changed; the copied bodies are never edited.
enum class Variant {
    None,
    IdAlwaysZero,     //: GetPolyInfId collapsed to row 0 - the two-step lookup made one step
    LinkBitIsArrow,   //: mPolyInf3's 0x04 moved to 0x08, the bit an arrow check would read
    SpecialGrpMoved,  //: m_info's 0x100 moved to 0x800, which is outside ChkGrpThrough's mask
};

// No control for "is the table read at all" (m_ti_num = 0, m_ti_tbl null): GetPolyInf3's
// JUT_ASSERT aborts the run instead of going red. The bound is checked by the last case.

RoomDzb mutated(Variant v) {
    RoomDzb d = sea().dzb();
    if (v == Variant::IdAlwaysZero) {
        for (cBgD_Tri_t& t : d.t_tbl) {
            t.id = 0;
        }
    }
    if (v == Variant::LinkBitIsArrow) {
        for (cBgD_Ti_t& row : d.ti_tbl) {
            if (row.mPolyInf3 & kLinkThrough) {
                row.mPolyInf3 = (row.mPolyInf3 & ~kLinkThrough) | 0x08;
            }
        }
    }
    if (v == Variant::SpecialGrpMoved) {
        for (cBgD_Grp_t& g : d.g_tbl) {
            if (g.m_info & 0x100) {
                g.m_info = (g.m_info & ~0x100u) | 0x800u;
            }
        }
    }
    return d;
}

/// The split the unmutated room produces, computed once.
const Split& baseline() {
    static Split s = split_of(sea().room(), sea());
    return s;
}

void expect_baseline_survives(Case& c, Variant v, const char* what) {
    RoomDzb d = mutated(v);
    Room r(d);
    const Split got = split_of(r, sea());
    c.note(std::string(what) + ": " + std::to_string(got.differ) + " probes differ (" +
           std::to_string(got.by_poly) + " by poly, " + std::to_string(got.by_group) +
           " by group), against " + std::to_string(baseline().differ) + " (" +
           std::to_string(baseline().by_poly) + ", " + std::to_string(baseline().by_group) + ")");
    REQUIRE_INT(c, got.by_poly, baseline().by_poly, "probes refused by ChkPolyThrough");
    REQUIRE_INT(c, got.by_group, baseline().by_group, "probes refused by ChkGrpThrough");
}

}  // namespace

TWWE_TEST(the_two_gated_rooms_cannot_reach_either_refusal,
          "kaze r11 or GanonA r0 has gained an attribute row or a special group - so the walk's "
          "console frames are no longer a pure control for the overrides, and whichever of them "
          "can now decide something has to be gated rather than assumed inert") {
    const char* const rooms[] = {"kaze_r11_bgd.json", "ganona_r0_bgd.json"};
    for (const char* name : rooms) {
        const RoomDzb d = read_room_dzb(tww_engine::testing::golden(name));
        Room r(d);
        const std::string where(name);

        int live_rows = 0;
        for (const cBgD_Ti_t& row : d.ti_tbl) {
            if (row.mPolyInf3 != 0) {
                live_rows++;
            }
        }
        REQUIRE_TRUE(c, !d.ti_tbl.empty(), where + ": no attribute table at all, so the zero "
                                                   "below is an absent file rather than a room "
                                                   "whose polygons carry no flags");
        REQUIRE_INT(c, live_rows, 0, where + ": attribute rows with a nonzero mPolyInf3");

        int special = 0;
        const int root = r.bgw().m_rootGrpIdx;
        for (u16 g = d.g_tbl[(size_t)root].m_first_child; g != 0xFFFF;
             g = d.g_tbl[g].m_next_sibling) {
            if (d.g_tbl[g].m_info & kSpecialGrp) {
                special++;
            }
        }
        REQUIRE_INT(c, special, 0, where + ": depth-2 groups ChkGrpThrough would skip");
        c.note(where + ": " + std::to_string(d.ti_tbl.size()) +
               " attribute rows, all mPolyInf3 == 0; " + std::to_string(d.g_tbl.size()) +
               " groups, none at depth 2 carrying a 0x80700 bit");
    }
}

TWWE_TEST(the_third_room_carries_what_the_refusals_read,
          "sea_r41_bgd.json is not the room the rest of this file is about - so every count "
          "below is a measurement of a different room, and nothing else would say so") {
    REQUIRE_INT(c, (int)sea().dzb().v_tbl.size(), 2189, "sea r41 vertices");
    REQUIRE_INT(c, (int)sea().dzb().t_tbl.size(), 2906, "sea r41 triangles");
    REQUIRE_INT(c, (int)sea().dzb().b_tbl.size(), 825, "sea r41 blocks");
    REQUIRE_INT(c, (int)sea().dzb().tree_tbl.size(), 987, "sea r41 octree nodes");
    REQUIRE_INT(c, (int)sea().dzb().g_tbl.size(), 66, "sea r41 groups");
    REQUIRE_INT(c, (int)sea().dzb().ti_tbl.size(), 55, "sea r41 attribute rows");

    // The fields the overrides read; zero on either and every case below would report nothing.
    int link_rows = 0;
    for (const cBgD_Ti_t& row : sea().dzb().ti_tbl) {
        if (row.mPolyInf3 & kLinkThrough) {
            link_rows++;
        }
    }
    REQUIRE_TRUE(c, link_rows > 0, "no attribute row carries the link-through bit");
    REQUIRE_TRUE(c, !sea().skipped_groups().empty(),
                 "no depth-2 group carries one of ChkGrpThrough's four kinds");
    REQUIRE_TRUE(c, !sea().link_through().empty(),
                 "the link-through rows exist but no ground polygon uses one, so "
                 "RwgGroundCheckCommon would never ask about them");
    c.note(std::to_string(sea().ground().size()) + " ground polys; " +
           std::to_string(link_rows) + " of 55 attribute rows carry 0x04, used by " +
           std::to_string(sea().link_through().size()) + " of them; " +
           std::to_string(sea().skipped_groups().size()) + " depth-2 group(s) skipped, " +
           std::to_string(sea().in_skipped_group().size()) + " polys under them");
}

TWWE_TEST(both_refusals_take_an_answer_away,
          "one of dBgW's two overrides stopped changing any answer in a room built to make both "
          "of them change one - so it is compiled and copied and reaches no decision, which is "
          "what the base class already did") {
    const Split& s = baseline();
    c.note(std::to_string(s.differ) + " of " + std::to_string(sea().probes().size()) +
           " probes answer differently under a Link ground check: " + std::to_string(s.by_poly) +
           " because ChkPolyThrough refused the polygon, " + std::to_string(s.by_group) +
           " because ChkGrpThrough never entered the group");
    REQUIRE_TRUE(c, s.by_poly > 0, "ChkPolyThrough refused nothing");
    REQUIRE_TRUE(c, s.by_group > 0, "ChkGrpThrough skipped nothing");
    REQUIRE_INT(c, s.unattributed, 0,
                "probes that changed answer for neither override's reason");
}

TWWE_TEST(a_refused_polygon_is_never_the_answer,
          "a polygon whose mPolyInf3 carries 0x04 came back as the ground under a Link check - "
          "so ChkPolyThrough is being asked and its answer is being ignored somewhere between "
          "RwgGroundCheckCommon and the poly index the query returns") {
    int returned = 0, tested = 0;
    for (const cXyz& q : sea().probes()) {
        int poly = 0;
        sea().room().GroundCross(q, &poly, PassChk::Link);
        tested++;
        if (sea().link_through().count(poly) != 0) {
            returned++;
        }
    }
    REQUIRE_INT(c, returned, 0, "link-through polygons returned as the ground");
    c.note(std::to_string(tested) + " probes, none of them landing on any of the " +
           std::to_string(sea().link_through().size()) + " link-through floors");
}

TWWE_TEST(a_skipped_group_is_never_entered,
          "a polygon under a depth-2 group flagged water came back as the ground under a "
          "NORMAL_GRP-only check - so ChkGrpThrough's depth test or its mask is wrong") {
    int returned = 0;
    for (const cXyz& q : sea().probes()) {
        int poly = 0;
        sea().room().GroundCross(q, &poly, PassChk::Link);
        if (sea().in_skipped_group().count(poly) != 0) {
            returned++;
        }
    }
    REQUIRE_INT(c, returned, 0, "polygons under a skipped group returned as the ground");
    c.note("none of " + std::to_string(sea().in_skipped_group().size()) +
           " polys under the skipped group(s) was returned; without the override " +
           std::to_string(baseline().by_group) + " probes get one");
}

TWWE_RED_CONTROL(the_attribute_row_is_found_through_the_polys_own_id,
                 "every cBgD_Tri_t::id forced to 0, so GetPolyInfId always names row 0 and the "
                 "two-step lookup becomes one step") {
    expect_baseline_survives(c, Variant::IdAlwaysZero, "id always 0");
}

TWWE_RED_CONTROL(the_link_check_reads_bit_0x04_and_not_another,
                 "mPolyInf3's 0x04 moved to 0x08 - the bit an arrow check reads - so a Link "
                 "ground check should stop refusing those floors") {
    expect_baseline_survives(c, Variant::LinkBitIsArrow, "link bit moved to 0x08");
}

TWWE_RED_CONTROL(the_group_check_reads_the_0x80700_mask,
                 "m_info's water bit 0x100 moved to 0x800, which is outside the mask "
                 "ChkGrpThrough tests, so the group should stop being skipped") {
    expect_baseline_survives(c, Variant::SpecialGrpMoved, "water bit moved to 0x800");
}

TWWE_TEST(every_polys_attribute_row_is_inside_the_table,
          "a polygon names an attribute row the room does not have - which is not a wrong answer "
          "but an aborted run, because GetPolyInf3 carries the game's own JUT_ASSERT and the "
          "port's macro halts. It is the one place here where bad input is unbounded rather than "
          "incorrect, and it is why the .dzb fixtures are digested") {
    int checked = 0, worst = -1;
    for (const RoomDzb* d : {&sea().dzb()}) {
        for (const cBgD_Tri_t& t : d->t_tbl) {
            checked++;
            if ((int)t.id > worst) {
                worst = (int)t.id;
            }
        }
        REQUIRE_TRUE(c, worst < (int)d->ti_tbl.size(),
                     "a cBgD_Tri_t::id is past the end of m_ti_tbl");
    }
    c.note(std::to_string(checked) + " triangles, highest id " + std::to_string(worst) +
           " against " + std::to_string(sea().dzb().ti_tbl.size()) + " attribute rows");
}
