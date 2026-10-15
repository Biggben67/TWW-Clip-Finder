#include "recorded_list.h"

#include "SSystem/SComponent/c_m3d.h"

namespace tww_engine {
namespace testing {

namespace {
const u16 kNone = 0xFFFF;
}

RecordedList::RecordedList(const std::vector<RecordedPoly>& polys)
    : m_ground_head(kNone), m_wall_head(kNone), m_ground_count(0), m_wall_count(0) {
    // Indexed by the game's poly index, so SetPolyIndex records the number the console left in
    // dBgS_LinkAcch+0x554.
    int top = 0;
    for (const RecordedPoly& p : polys) {
        if (p.poly + 1 > top) {
            top = p.poly + 1;
        }
    }
    m_tri_tbl.resize(top);
    m_tri.resize(top);
    m_rwg.resize(top);
    m_vtx.resize((size_t)top * 3);
    for (int i = 0; i < top; i++) {
        m_tri_tbl[i].vtx0 = (u16)(i * 3 + 0);
        m_tri_tbl[i].vtx1 = (u16)(i * 3 + 1);
        m_tri_tbl[i].vtx2 = (u16)(i * 3 + 2);
        m_tri_tbl[i].id = 0;
        m_tri_tbl[i].grp = 0;
        m_rwg[i].next = kNone;
        // A slot no golden row fills is in no chain. Its plane is left degenerate so a stray
        // visit would be visibly wrong.
        m_tri[i].m_plane.mNormal.x = 0.0f;
        m_tri[i].m_plane.mNormal.y = 0.0f;
        m_tri[i].m_plane.mNormal.z = 0.0f;
        m_tri[i].m_plane.mD = 0.0f;
    }

    u16 ground_tail = kNone;
    u16 wall_tail = kNone;
    for (const RecordedPoly& p : polys) {
        const u16 i = (u16)p.poly;
        for (int k = 0; k < 3; k++) {
            m_vtx[(size_t)i * 3 + k].x = p.v[k].x;
            m_vtx[(size_t)i * 3 + k].y = p.v[k].y;
            m_vtx[(size_t)i * 3 + k].z = p.v[k].z;
        }
        m_tri[i].m_plane.mNormal = p.n;
        m_tri[i].m_plane.mD = p.d;
        // cBgW::ClassifyPlane's split (c_bg_w.cpp:175-183). A floors golden holds no roofs (the
        // capture keeps ny >= 0.014f), so the else-arm is the wall list.
        u16* head = cBgW_CheckBGround(p.n.y) ? &m_ground_head : &m_wall_head;
        u16* tail = cBgW_CheckBGround(p.n.y) ? &ground_tail : &wall_tail;
        int* count = cBgW_CheckBGround(p.n.y) ? &m_ground_count : &m_wall_count;
        if (*tail == kNone) {
            *head = i;
        } else {
            m_rwg[*tail].next = i;
        }
        *tail = i;
        (*count)++;
    }

    m_bgd.m_v_num = (s32)m_vtx.size();
    m_bgd.m_v_tbl = m_vtx.empty() ? nullptr : &m_vtx[0];
    m_bgd.m_t_num = top;
    m_bgd.m_t_tbl = m_tri_tbl.empty() ? nullptr : &m_tri_tbl[0];
    m_bgd.m_b_num = 0;
    m_bgd.m_b_tbl = nullptr;
    m_bgd.m_tree_num = 0;
    m_bgd.m_tree_tbl = nullptr;
    m_bgd.m_g_num = 0;
    m_bgd.m_g_tbl = nullptr;
    m_bgd.m_ti_num = 0;
    m_bgd.m_ti_tbl = nullptr;
    m_bgd.flag = 0;

    m_bgw.pm_bgd = &m_bgd;
    m_bgw.pm_vtx_tbl = m_bgd.m_v_tbl;
    m_bgw.pm_tri = m_tri.empty() ? nullptr : &m_tri[0];
    m_bgw.pm_rwg = m_rwg.empty() ? nullptr : &m_rwg[0];
    m_bgw.pm_blk = nullptr;
}

f32 RecordedList::GroundCross(const cXyz& probe, int* out_poly) {
    cBgS_GndChk chk;
    cXyz p = probe;
    chk.SetPos(&p);
    // Both pass-check pointers set to null (the decomp's `if (chk == NULL) return false` arm),
    // since cBgS_Chk's constructor is not carried and RwgGroundCheckCommon hands one to
    // ChkPolyThrough on every candidate.
    chk.SetPolyPassChk(nullptr);
    chk.SetGrpPassChk(nullptr);
    // cBgS::GroundCross's prologue, c_bg_s.cpp:131-134. mFlag = 3 is cBgS_GndChk's constructor's
    // (c_bg_s_gnd_chk.cpp:12), which this port does not carry.
    chk.mFlag = 3;
    chk.SetNowY(-G_CM3D_F_INF);
    chk.SetPolyIndex(0xFFFF);  // ClearPi's own value for "no poly", c_bg_s_poly_info.h:22
    chk.mWallPrecheck = (chk.mFlag & 0x02);
    chk.mGndPrecheck = (chk.mFlag & 0x01);

    if (chk.GetGndPrecheck() && m_ground_head != kNone) {
        m_bgw.RwgGroundCheckGnd(m_ground_head, &chk);
    }
    if (chk.GetWallPrecheck() && m_wall_head != kNone) {
        m_bgw.RwgGroundCheckWall(m_wall_head, &chk);
    }
    if (out_poly != nullptr) {
        *out_poly = chk.GetPolyIndex();
    }
    return chk.GetNowY();
}

}  // namespace testing
}  // namespace tww_engine
