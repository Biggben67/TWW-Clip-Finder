#include "room_dzb.h"

namespace tww_engine {
namespace testing {

/// The disc fixture's tables, as cBgD_t holds them. The engine has no file format;
/// this is the one place a banked .dzb becomes the structs cBgW::Set is handed.
RoomDzb read_room_dzb(const Json& g) {
    RoomDzb d;

    const Json& verts = g["verts"];
    d.v_tbl.resize(verts.size());
    for (size_t i = 0; i < verts.size(); i++) {
        d.v_tbl[i].x = verts[i][0].as_f32();
        d.v_tbl[i].y = verts[i][1].as_f32();
        d.v_tbl[i].z = verts[i][2].as_f32();
    }

    // `tris` is the three vertex indices; `tri_id` and `tri_grp` are cBgD_Tri_t's other two u16.
    // `id` is the attribute row dBgW::ChkPolyThrough reads the polygon's flags through.
    const Json& tris = g["tris"];
    const Json& tri_id = g["tri_id"];
    const Json& tri_grp = g["tri_grp"];
    d.t_tbl.resize(tris.size());
    for (size_t i = 0; i < tris.size(); i++) {
        d.t_tbl[i].vtx0 = (u16)tris[i][0].as_int();
        d.t_tbl[i].vtx1 = (u16)tris[i][1].as_int();
        d.t_tbl[i].vtx2 = (u16)tris[i][2].as_int();
        d.t_tbl[i].id = (u16)tri_id[i].as_int();
        d.t_tbl[i].grp = (u16)tri_grp[i].as_int();
    }

    // cBgD_Ti_t, four u32 per row. GetPolyInf3 reads the fourth; the rest are carried as the
    // file has them.
    const Json& ti = g["ti"];
    d.ti_tbl.resize(ti.size());
    for (size_t i = 0; i < ti.size(); i++) {
        d.ti_tbl[i].mPolyInf0 = (u32)ti[i][0].as_int();
        d.ti_tbl[i].mPolyInf1 = (u32)ti[i][1].as_int();
        d.ti_tbl[i].mPolyInf2 = (u32)ti[i][2].as_int();
        d.ti_tbl[i].mPolyInf3 = (u32)ti[i][3].as_int();
    }

    const Json& blocks = g["blocks"];
    d.b_tbl.resize(blocks.size());
    for (size_t i = 0; i < blocks.size(); i++) {
        d.b_tbl[i].startTri = (u16)blocks[i].as_int();
    }

    // [mFlag, mParent, eight children]. mChild[8] and mBlock are a union in cBgD_Tree_t, so on
    // a leaf (mFlag & 1) mChild[0] is the block index.
    const Json& tree = g["tree"];
    d.tree_tbl.resize(tree.size());
    for (size_t i = 0; i < tree.size(); i++) {
        d.tree_tbl[i].mFlag = (u16)tree[i][0].as_int();
        d.tree_tbl[i].mParent = (u16)tree[i][1].as_int();
        for (int k = 0; k < 8; k++) {
            d.tree_tbl[i].mChild[k] = (u16)tree[i][2 + k].as_int();
        }
    }

    // [m_parent, m_next_sibling, m_first_child, m_tree_idx] at 0x24, 0x26, 0x28, 0x2E, plus
    // m_info @0x30 as `grp_info`, which dBgW::ChkGrpThrough tests against 0x80700. The group's
    // transform is read only by the moving-collision path.
    const Json& groups = g["groups"];
    const Json& grp_info = g["grp_info"];
    d.g_tbl.resize(groups.size());
    for (size_t i = 0; i < groups.size(); i++) {
        cBgD_Grp_t& grp = d.g_tbl[i];
        grp.m_name = nullptr;
        grp.m_scale.x = grp.m_scale.y = grp.m_scale.z = 1.0f;
        grp.m_rotation.x = grp.m_rotation.y = grp.m_rotation.z = 0;
        grp.m_translation.x = grp.m_translation.y = grp.m_translation.z = 0.0f;
        grp.m_parent = (u16)groups[i][0].as_int();
        grp.m_next_sibling = (u16)groups[i][1].as_int();
        grp.m_first_child = (u16)groups[i][2].as_int();
        grp.m_tree_idx = (u16)groups[i][3].as_int();
        grp.m_room_id = 0;
        grp.m_first_vtx_idx = 0;
        grp.m_info = (u32)grp_info[i].as_int();
    }

    return d;
}

}  // namespace testing
}  // namespace tww_engine
