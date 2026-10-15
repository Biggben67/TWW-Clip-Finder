#include "engine/room.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "SSystem/SComponent/c_bg_s_lin_chk.h"
#include "SSystem/SComponent/c_m3d.h"
#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"
#include "d/d_bg_s_roof_chk.h"

namespace tww_engine {

namespace {
const u16 kNone = 0xFFFF;
}

RoomDzb flat_floor_dzb(f32 floor_y) {
    // 2^19: exact f32 vertices, so the plan test's subtractions do not round.
    const f32 E = 524288.0f;

    RoomDzb d;

    d.v_tbl.resize(4);
    d.v_tbl[0].x = -E; d.v_tbl[0].y = floor_y; d.v_tbl[0].z = -E;
    d.v_tbl[1].x = -E; d.v_tbl[1].y = floor_y; d.v_tbl[1].z =  E;
    d.v_tbl[2].x =  E; d.v_tbl[2].y = floor_y; d.v_tbl[2].z = -E;
    d.v_tbl[3].x =  E; d.v_tbl[3].y = floor_y; d.v_tbl[3].z =  E;

    // Winding sets the normal's sign: (p1-p0) x (p2-p0) must point up, or ClassifyPlane files
    // the floor as a roof.
    d.t_tbl.resize(2);
    d.t_tbl[0].vtx0 = 0; d.t_tbl[0].vtx1 = 1; d.t_tbl[0].vtx2 = 2;
    d.t_tbl[1].vtx0 = 3; d.t_tbl[1].vtx1 = 2; d.t_tbl[1].vtx2 = 1;
    for (int i = 0; i < 2; i++) {
        d.t_tbl[i].id = 0;
        d.t_tbl[i].grp = 0;
    }

    d.b_tbl.resize(1);
    d.b_tbl[0].startTri = 0;

    // A leaf: mFlag bit 0, and the union holds mBlock rather than eight children.
    d.tree_tbl.resize(1);
    d.tree_tbl[0].mFlag = 1;
    d.tree_tbl[0].mParent = kNone;
    d.tree_tbl[0].mBlock = 0;

    d.g_tbl.resize(1);
    cBgD_Grp_t& g = d.g_tbl[0];
    std::memset(&g, 0, sizeof(g));
    g.m_name = NULL;
    // Unread for a room (only moving collision reads it), but no .dzb holds a zero scale.
    g.m_scale.x = g.m_scale.y = g.m_scale.z = 1.0f;
    // The root: MakeNodeTree starts from the group whose parent is 0xFFFF.
    g.m_parent = kNone;
    g.m_next_sibling = kNone;
    g.m_first_child = kNone;
    g.m_room_id = 0;
    g.m_first_vtx_idx = 0;
    g.m_tree_idx = 0;
    // NORMAL_GRP, which dBgS_GrpPassChk lets through on Link's ground path.
    g.m_info = 0;

    // One all-zero attribute row: no THROUGH bit set, so ChkPolyThrough refuses nobody.
    d.ti_tbl.resize(1);
    std::memset(&d.ti_tbl[0], 0, sizeof(d.ti_tbl[0]));

    return d;
}

Room::Room(const RoomDzb& dzb, fpc_ProcID owner_pid) : m_dzb(dzb) {
    m_bgd.m_v_num = (s32)m_dzb.v_tbl.size();
    m_bgd.m_v_tbl = m_dzb.v_tbl.empty() ? nullptr : &m_dzb.v_tbl[0];
    m_bgd.m_t_num = (s32)m_dzb.t_tbl.size();
    m_bgd.m_t_tbl = m_dzb.t_tbl.empty() ? nullptr : &m_dzb.t_tbl[0];
    m_bgd.m_b_num = (s32)m_dzb.b_tbl.size();
    m_bgd.m_b_tbl = m_dzb.b_tbl.empty() ? nullptr : &m_dzb.b_tbl[0];
    m_bgd.m_tree_num = (s32)m_dzb.tree_tbl.size();
    m_bgd.m_tree_tbl = m_dzb.tree_tbl.empty() ? nullptr : &m_dzb.tree_tbl[0];
    m_bgd.m_g_num = (s32)m_dzb.g_tbl.size();
    m_bgd.m_g_tbl = m_dzb.g_tbl.empty() ? nullptr : &m_dzb.g_tbl[0];
    m_bgd.m_ti_num = (s32)m_dzb.ti_tbl.size();
    m_bgd.m_ti_tbl = m_dzb.ti_tbl.empty() ? nullptr : &m_dzb.ti_tbl[0];
    m_bgd.flag = 0;

    // cBgW::Set, c_bg_w.cpp:330-357: pm_bgd, then the five tables (vectors in place of `new`).
    m_tri.resize(m_bgd.m_t_num);
    m_rwg.resize(m_bgd.m_t_num);
    m_blk.resize(m_bgd.m_b_num);
    m_nt.resize(m_bgd.m_tree_num);
    m_grp.resize(m_bgd.m_g_num);

    m_bgw.pm_bgd = &m_bgd;
    m_bgw.pm_tri = m_tri.empty() ? nullptr : &m_tri[0];
    m_bgw.pm_rwg = m_rwg.empty() ? nullptr : &m_rwg[0];
    m_bgw.pm_blk = m_blk.empty() ? nullptr : &m_blk[0];
    m_bgw.m_nt_tbl = m_nt.empty() ? nullptr : &m_nt[0];
    m_bgw.pm_grp = m_grp.empty() ? nullptr : &m_grp[0];
    // -1, not 0: MakeNodeTree sets it, and 0 is usually the right answer, which would hide a
    // MakeNodeTree that never ran.
    m_bgw.m_rootGrpIdx = -1;
    m_bgw.mIgnorePlaneType = 0;
    m_bgw.mFlags = 0;
    m_bgw.mMoveCounter = 0;
    m_bgw.mWallCorrectPriority = 0;
    m_bgw.mTransVel.x = m_bgw.mTransVel.y = m_bgw.mTransVel.z = 0.0f;

    // cBgW::SetVtx's static-room arm (c_bg_w.cpp:97): the disc's vertices, untransformed.
    m_bgw.pm_vtx_tbl = m_bgd.m_v_tbl;

    // cBgW::SetTri's tail, then cBgW::Set's (c_bg_w.cpp:129-130, 359-363). Set raises
    // mbNeedsFullTransform between ClassifyPlane and MakeNodeTree; raising it before CalcPlane
    // too changes nothing, as the other arm subtracts a zero translation velocity.
    m_bgw.mbNeedsFullTransform = true;
    m_bgw.CalcPlane();
    m_bgw.ClassifyPlane();
    m_bgw.MakeNodeTree();

    // cBgS::Ct, then cBgS::Regist - the second statement of dBgS::Regist (d_bg_s.cpp:61). After
    // the tables are built: ChkMemoryError refuses a bgW whose tables are null.
    m_bgs.Ct();
    // Qualified: dBgS's two-argument `Regist` hides the base's three-argument one.
    if (m_bgs.cBgS::Regist(&m_bgw, owner_pid, NULL)) {
        std::fprintf(stderr, "Room::Room: cBgS::Regist refused the room's dBgW\n");
        std::abort();
    }
}

f32 Room::GroundCross(const cXyz& probe, int* out_poly, PassChk who) {
    cBgS_GndChk chk;
    cXyz p = probe;
    chk.SetPos(&p);
    // Link's ground check carries dBgS_LinkAcch's pass-checks (GroundCheckInit's
    // `m_gnd.SetExtChk(*(cBgS_Chk*)this)`): defaults plus `{ SetLink(); }`. Both pointers are
    // written on both arms, because dBgW's overrides dereference them and nothing else sets them.
    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    const bool link = (who == PassChk::Link);
    chk.SetPolyPassChk(link ? &poly_pass : nullptr);
    chk.SetGrpPassChk(link ? &grp_pass : nullptr);

    m_bgs.GroundCross(&chk);

    if (out_poly != nullptr) {
        *out_poly = chk.GetPolyIndex();
    }
    return chk.GetNowY();
}

f32 Room::RoofChk(const cXyz& probe, int* out_poly, PassChk who) {
    dBgS_RoofChk chk;
    cXyz p = probe;
    chk.SetPos(p);
    // The same pass-checks as GroundCross: CrrPos runs `m_roof.SetExtChk(*(cBgS_Chk*)this)`
    // (d_bg_s_acch.cpp:250) before every roof check.
    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    const bool link = (who == PassChk::Link);
    chk.SetPolyPassChk(link ? &poly_pass : nullptr);
    chk.SetGrpPassChk(link ? &grp_pass : nullptr);

    // dBgS::RoofChk, d_bg_s.cpp:354-369.
    m_bgs.RoofChk(&chk);

    if (out_poly != nullptr) {
        *out_poly = chk.GetPolyIndex();
    }
    return chk.GetNowY();
}

std::vector<int> Room::chain_from(u16 head) const {
    std::vector<int> out;
    if (head == kNone) {
        return out;
    }
    // BlckConnect ends a chain with `next` = -1 (0xFFFF as u16). A chain longer than the triangle
    // table is a cycle: return empty.
    u16 i = head;
    while (out.size() <= m_rwg.size()) {
        out.push_back((int)i);
        if (m_rwg[i].next == kNone) {
            return out;
        }
        i = m_rwg[i].next;
    }
    out.clear();
    return out;
}

bool Room::WallCorrect(cXyz* pos, const cXyz& old_pos, f32 speed_y, const WallCyl* cyls,
                       int tbl_size, WallResult* out, PassChk who, const LineResult* latch) {
    if (tbl_size < 0 || tbl_size > kMaxWallCyl) {
        std::fprintf(stderr, "Room::WallCorrect: tbl_size %d is outside 0..%d\n",
                     tbl_size, kMaxWallCyl);
        std::abort();
    }

    dBgS_AcchCir cir[kMaxWallCyl];
    dBgS_LinkAcch acch;

    // Every field dBgS_Acch::Set assigns. m_flags starts 0, since the pass raises WALL_HIT.
    cXyz old = old_pos;
    acch.m_flags = 0;
    acch.pm_pos = pos;
    acch.pm_old_pos = &old;
    acch.pm_speed = nullptr;
    acch.pm_angle = nullptr;
    acch.pm_shape_angle = nullptr;
    acch.m_my_ac = nullptr;
    acch.m_tbl_size = tbl_size;
    acch.pm_acch_cir = cir;
    acch.m_bg_index = 0;
    acch.field_0x78 = &m_bgw;
    acch.m_ap_id = (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
    acch.m_ground_up_h = 0.0f;
    acch.m_ground_up_h_diff = 0.0f;
    acch.m_ground_h = 0.0f;
    acch.m_ground_check_offset = 0.0f;
    acch.SetActorPid((fpc_ProcID)fpcM_ERROR_PROCESS_ID_e);

    // GetWallAddY returns 0 unless GROUND_FIND is up and m_pla.y >= 0.5; with the flag down this
    // is the flat-floor case.
    acch.m_pla.mNormal.x = 0.0f;
    acch.m_pla.mNormal.y = 0.0f;
    acch.m_pla.mNormal.z = 0.0f;
    acch.m_pla.mD = 0.0f;

    // GetSpeedY reads `pm_speed->y` (d_bg_s_acch.h:104-110).
    cXyz speed;
    speed.x = 0.0f;
    speed.y = speed_y;
    speed.z = 0.0f;
    acch.pm_speed = &speed;

    for (int i = 0; i < tbl_size; i++) {
        cir[i].SetWall(cyls[i].h, cyls[i].r);
    }

    // A prior line check's SetWallHDirect latch, after SetWall (which leaves m_flags alone).
    // Without one, RwgWallCorrect derives its own cut height.
    if (latch != nullptr) {
        for (int i = 0; i < tbl_size; i++) {
            if (latch->whd_set[i]) {
                cir[i].SetWallHDirect(latch->whd[i]);
            }
        }
    }

    // Pass-checks as in GroundCross.
    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    const bool link = (who == PassChk::Link);
    acch.SetPolyPassChk(link ? &poly_pass : nullptr);
    acch.SetGrpPassChk(link ? &grp_pass : nullptr);

    // dBgS::WallCorrect, d_bg_s.cpp:331-352. Its SetNowActorInfo overwrites m_bg_index,
    // field_0x78 and m_ap_id set above.
    m_bgs.WallCorrect(&acch);

    const bool hit = acch.ChkWallHit() != 0;
    if (out != nullptr) {
        out->wall_hit = hit;
        out->tbl_size = tbl_size;
        for (int i = 0; i < kMaxWallCyl; i++) {
            out->cir_hit[i] = (i < tbl_size) && cir[i].ChkWallHit();
            out->cir_poly[i] = (i < tbl_size) ? cir[i].GetPolyIndex() : 0xFFFF;
            out->cir_angle[i] = (i < tbl_size) ? cir[i].GetWallAngleY() : (s16)0;
        }
    }
    return hit;
}

bool Room::LineCheck(cXyz* pos, const cXyz& old_pos, const WallCyl* cyls, int tbl_size,
                     LineResult* out, PassChk who) {
    if (tbl_size < 0 || tbl_size > kMaxWallCyl) {
        std::fprintf(stderr, "Room::LineCheck: tbl_size %d is outside 0..%d\n",
                     tbl_size, kMaxWallCyl);
        std::abort();
    }

    dBgS_AcchCir cir[kMaxWallCyl];
    dBgS_LinkAcch acch;

    // dBgS_Acch::Set's fields, as in WallCorrect.
    cXyz old = old_pos;
    acch.m_flags = 0;
    acch.pm_pos = pos;
    acch.pm_old_pos = &old;
    acch.pm_speed = nullptr;
    acch.pm_angle = nullptr;
    acch.pm_shape_angle = nullptr;
    acch.m_my_ac = nullptr;
    acch.m_tbl_size = tbl_size;
    acch.pm_acch_cir = cir;
    acch.m_bg_index = 0;
    acch.field_0x78 = &m_bgw;
    acch.m_ap_id = (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
    acch.m_ground_up_h = 0.0f;
    acch.m_ground_up_h_diff = 0.0f;
    acch.m_ground_h = 0.0f;
    acch.m_ground_check_offset = 0.0f;
    acch.m_pla.mNormal.x = 0.0f;
    acch.m_pla.mNormal.y = 0.0f;
    acch.m_pla.mNormal.z = 0.0f;
    acch.m_pla.mD = 0.0f;

    // cBgS_Chk's pid, not m_ap_id: LineCross compares it against each registered object's.
    acch.SetActorPid((fpc_ProcID)fpcM_ERROR_PROCESS_ID_e);

    for (int i = 0; i < tbl_size; i++) {
        cir[i].SetWall(cyls[i].h, cyls[i].r);
    }

    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    const bool link = (who == PassChk::Link);
    acch.SetPolyPassChk(link ? &poly_pass : nullptr);
    acch.SetGrpPassChk(link ? &grp_pass : nullptr);

    // CrrPos's own line before the call (d_bg_s_acch.cpp:482); whether to run is CrrPos's call.
    acch.OffLineCheckHit();

    int ground_branch = 0;

    // dBgS_Acch::LineCheck, d_bg_s_acch.cpp:175-206, one cylinder at a time.
    for (s32 i = 0; i < acch.m_tbl_size; i++) {
        cBgS_LinChk linChk;
        cXyz lin_old_pos = *acch.pm_old_pos;
        cXyz lin_pos = *acch.pm_pos;

        lin_old_pos.y += cir[i].GetWallH();
        lin_pos.y += cir[i].GetWallH();

        linChk.Set2(&lin_old_pos, &lin_pos, acch.GetActorPid());
        linChk.SetExtChk(acch);

        // cBgS::LineCross, c_bg_s.cpp:109-127.
        bool crossed = m_bgs.LineCross(&linChk);

        if (crossed) {
            *acch.pm_pos = linChk.GetCross();
            acch.OnLineCheckHit();

            // pm_out_poly_info is null here; LineResult carries the crossing instead.
            cM3dGPla* pla = m_bgw.GetTriPla(linChk.GetPolyIndex());
            if (!cBgW_CheckBGround(pla->GetNP()->y)) {
                VECAdd(acch.GetPos(), pla->GetNP(), acch.GetPos());
                if (!cM3d_IsZero(ppc::sqrtf_msl(pla->GetNP()->x * pla->GetNP()->x +
                                                pla->GetNP()->z * pla->GetNP()->z))) {
                    cir[i].SetWallHDirect(acch.pm_pos->y);
                }
                acch.pm_pos->y -= cir[i].GetWallH();
            } else {
                acch.pm_pos->y -= 1.0f;
                // The decomp's next statement, GroundCheck(i_bgs), is not run; counted instead.
                ground_branch++;
            }
        }

        if (out != nullptr) {
            out->cir_hit[i] = crossed;
            out->cir_poly[i] = crossed ? linChk.GetPolyIndex() : 0xFFFF;
            out->whd_set[i] = cir[i].ChkWallHDirect();
            out->whd[i] = cir[i].GetWallHDirect();
        }
    }

    // The decomp has no accessor that reads this bit, so the test is written here.
    const bool hit = (acch.m_flags & dBgS_Acch::LINE_CHECK_HIT) != 0;
    if (out != nullptr) {
        out->hit = hit;
        out->tbl_size = tbl_size;
        out->ground_branch = ground_branch;
        for (int i = tbl_size; i < kMaxWallCyl; i++) {
            out->cir_hit[i] = false;
            out->cir_poly[i] = 0xFFFF;
            out->whd_set[i] = false;
            out->whd[i] = 0.0f;
        }
    }
    return hit;
}

Room::PlayerAcch::PlayerAcch(cXyz* pos, cXyz* old_pos, cXyz* speed, const WallCyl* cyls,
                             int tbl_size, fpc_ProcID pid)
    : m_tbl_size(tbl_size) {
    if (tbl_size < 0 || tbl_size > kMaxWallCyl) {
        std::fprintf(stderr, "Room::PlayerAcch: tbl_size %d is outside 0..%d\n",
                     tbl_size, kMaxWallCyl);
        std::abort();
    }

    // d_a_player_main.cpp:12188-12196, in order. The actor is null, so the pid is the caller's.
    m_acch.Set(pos, old_pos, NULL, tbl_size, m_cir, speed, NULL, NULL);
    m_acch.SetActorPid(pid);
    m_acch.ClrWaterNone();
    m_acch.SetWaterCheckOffset(500.0f);
    m_acch.OnLineCheck();
    m_acch.ClrRoofNone();
    m_acch.SetRoofCrrHeight(125.0f);

    // Chosen per proc by daPy_lk_c::setBgCheckParam, so supplied by the caller.
    for (int i = 0; i < tbl_size; i++) {
        m_cir[i].SetWall(cyls[i].h, cyls[i].r);
    }
}

Room::FrameResult Room::CrrPos(PlayerAcch& player) {
    return CrrPos(player.acch(), &player.cir(0), player.tbl_size());
}

Room::FrameResult Room::CrrPos(dBgS_Acch& acch, dBgS_AcchCir* cirs, int tbl_size) {
    // SetNowActorInfo overwrites this in the wall pass; set so a frame without one still names
    // a collision object.
    acch.field_0x78 = &m_bgw;

    acch.CrrPos(m_bgs);

    FrameResult out;
    out.line_hit = (acch.m_flags & dBgS_Acch::LINE_CHECK_HIT) != 0;
    out.wall_hit = acch.ChkWallHit() != 0;
    out.ground_hit = acch.ChkGroundHit();
    out.ground_find = acch.ChkGroundFind();
    out.ground_landing = acch.ChkGroundLanding();
    out.ground_away = (acch.m_flags & dBgS_Acch::GROUND_AWAY) != 0;
    out.roof_hit = acch.ChkRoofHit();
    out.water_hit = acch.ChkWaterHit();
    out.water_in = acch.ChkWaterIn();
    // CrrPos's `ranLineCheck` is a local, so re-derived from its terms (d_bg_s_acch.cpp:228-229).
    {
        const f32 lowH_R = acch.GetWallAllLowH_R();
        const f32 distXZ2 = acch.GetOldPos()->abs2XZ(*acch.GetPos());
        const f32 distY = acch.GetOldPos()->y - acch.GetPos()->y;
        const f32 lowH = acch.GetWallAllLowH();
        const f32 temp7 = lowH + acch.GetOldPos()->y;
        const f32 temp8 = acch.m_ground_check_offset + acch.GetPos()->y;
        out.ran_line_check =
            !acch.ChkLineCheckNone() && !cM3d_IsZero(lowH_R) &&
            (distXZ2 > lowH_R * lowH_R || temp7 > temp8 ||
             distY > acch.m_ground_check_offset || acch.ChkLineCheck());
    }
    out.ground_h = acch.GetGroundH();
    out.ground_poly = acch.m_gnd.GetPolyIndex();
    out.roof_height = acch.GetRoofHeight();
    out.sea_height = acch.GetSeaHeight();

    out.wall.wall_hit = out.wall_hit;
    out.wall.tbl_size = tbl_size;
    for (int i = 0; i < kMaxWallCyl; i++) {
        const bool live = i < tbl_size;
        out.wall.cir_hit[i] = live && cirs[i].ChkWallHit();
        out.wall.cir_poly[i] = live ? cirs[i].GetPolyIndex() : 0xFFFF;
        out.wall.cir_angle[i] = live ? cirs[i].GetWallAngleY() : (s16)0;
    }
    return out;
}

std::vector<int> Room::ground_chain(int block) const {
    return chain_from(m_blk[block].ground);
}

std::vector<int> Room::wall_chain(int block) const {
    return chain_from(m_blk[block].wall);
}

std::vector<int> Room::roof_chain(int block) const {
    return chain_from(m_blk[block].roof);
}

}  // namespace tww_engine
