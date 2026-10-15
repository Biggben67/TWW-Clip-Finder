// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s.cpp - dBgS's collision loops, GetRoomId and the polygon-id accessors
// (d_bg_s.cpp:16-24, 65-74, 277-297, 157-165, 177-180, 237-239, 85-95, 97-100, 241-250,
// 252-256, 257-261, 331-352, 354-369, 371-387, 437-451, 521-529).
// WallCorrect moves Link as it goes, so the order it visits collision objects in is part of
// the answer.

#include "d/d_bg_s.h"

#include "SSystem/SComponent/c_m3d.h"
#include "d/actor/d_a_player_main.h"
#include "d/d_bg_s_acch.h"
#include "d/d_bg_s_roof_chk.h"
#include "d/d_bg_s_spl_grp_chk.h"
#include "engine/jut_assert.h"

/* 800A0270-800A0290       .text Ct__4dBgSFv */
void dBgS::Ct() {
    cBgS::Ct();
}

/* 800A0290-800A02B0       .text Dt__4dBgSFv */
void dBgS::Dt() {
    cBgS::Dt();
}

bool dBgS::ChkMoveBG(cBgS_PolyInfo& polyInfo) {
    dBgW* bgwp = dComIfG_Bgsp()->GetBgWPointer(polyInfo);
    if (bgwp != NULL) {
        if (bgwp->ChkLock())
            return false;
        if (bgwp->ChkMoveBg())
            return true;
    }
    return false;
}

/* 800A0E68-800A0F88       .text GetRoomId__4dBgSFR13cBgS_PolyInfo */
s32 dBgS::GetRoomId(cBgS_PolyInfo& polyInfo) {
    if (!polyInfo.ChkSetInf())
        return -1;

    s32 id = polyInfo.GetBgIndex();
    JUT_ASSERT(0x51b, 0 <= id && id < 256);

    if (!ChkPolySafe(polyInfo))
        return -1;

    dBgW* bgwp = (dBgW*)m_chk_element[id].m_bgw_base_ptr;
    s32 roomNo = bgwp->mRoomNo;
    if (roomNo == 0xFFFF) {
        s32 grp = GetTriGrp(polyInfo);
        roomNo = GetGrpToRoomId(polyInfo.GetBgIndex(), grp);
        if (roomNo == 0xFFFF)
            return -1;
    }
    return roomNo;
}

int dBgS::GetPolyId1(int bg_index, int poly_index, int defv, u32 mask, u32 shift) {
    JUT_ASSERT(0x414, 0 <= bg_index && bg_index < 256);
    if (!m_chk_element[bg_index].ChkUsed())
        return defv;

    dBgW* bgwp = (dBgW*)m_chk_element[bg_index].m_bgw_base_ptr;
    u32 inf_id = bgwp->GetPolyInfId(poly_index);
    return (bgwp->GetPolyInf1(inf_id) & mask) >> shift;
}

/* 800A0ACC-800A0B08       .text GetSpecialCode__4dBgSFR13cBgS_PolyInfo */
int dBgS::GetSpecialCode(cBgS_PolyInfo& polyInfo) {
    return GetPolyId1(polyInfo.GetBgIndex(), polyInfo.GetPolyIndex(), 0x00, 0x0000F000, 12);
}

int dBgS::GetGroundCode(cBgS_PolyInfo& polyInfo) {
    return GetPolyId1(polyInfo.GetBgIndex(), polyInfo.GetPolyIndex(), 0x00, 0x03E00000, 21);
}


/* 800A046C-800A0604       .text GetPolyId0__4dBgSFiiiUlUl */
int dBgS::GetPolyId0(int bg_index, int poly_index, int defv, u32 mask, u32 shift) {
    JUT_ASSERT(0x349, 0 <= bg_index && bg_index < 256);
    if (!m_chk_element[bg_index].ChkUsed())
        return defv;

    dBgW* bgwp = (dBgW*)m_chk_element[bg_index].m_bgw_base_ptr;
    u32 inf_id = bgwp->GetPolyInfId(poly_index);
    return (bgwp->GetPolyInf0(inf_id) & mask) >> shift;
}

/* 800A0604-800A0630       .text GetPolyCamId__4dBgSFii */
int dBgS::GetPolyCamId(int i_bg_index, int i_poly_index) {
    return GetPolyId0(i_bg_index, i_poly_index, 0xFF, 0x000000FF, 0);
}

/* 800A0BE0-800A0D7C       .text GetPolyId2__4dBgSFiiiUlUl */
int dBgS::GetPolyId2(int bg_index, int poly_index, int defv, u32 mask, u32 shift) {
    JUT_ASSERT(0x4c1, 0 <= bg_index && bg_index < 256);
    if (!m_chk_element[bg_index].ChkUsed())
        return defv;

    dBgW* bgwp = (dBgW*)m_chk_element[bg_index].m_bgw_base_ptr;
    u32 inf_id = bgwp->GetPolyInfId(poly_index);
    return (bgwp->GetPolyInf2(inf_id) & mask) >> shift;
}

/* 800A0D7C-800A0DB4       .text GetCamMoveBG__4dBgSFR13cBgS_PolyInfo */
int dBgS::GetCamMoveBG(cBgS_PolyInfo& polyInfo) {
    return GetPolyId2(polyInfo.GetBgIndex(), polyInfo.GetPolyIndex(), 0xFF, 0x000000FF, 0);
}


/* 800A0DB4-800A0DF0       .text GetRoomCamId__4dBgSFR13cBgS_PolyInfo */
int dBgS::GetRoomCamId(cBgS_PolyInfo& polyInfo) {
    return GetPolyId2(polyInfo.GetBgIndex(), polyInfo.GetPolyIndex(), 0xFF, 0x0000FF00, 8);
}


/* 800A12A4-800A13E0       .text WallCorrect__4dBgSFP9dBgS_Acch */
void dBgS::WallCorrect(dBgS_Acch* acch) {
    acch->CalcWallRR();
    acch->SetWallCir();
    acch->SetLin();
    acch->CalcWallBmdCyl();

    cBgS_ChkElm* elm;
    for (s32 prio = 0; prio < 3; prio++) {
        for (s32 bg_index = 0; bg_index < (s32)ARRAY_SIZE(m_chk_element); bg_index++) {
            elm = &m_chk_element[bg_index];
            if (elm->ChkUsed() && elm->m_bgw_base_ptr->GetVtxTbl() != NULL) {
                acch->SetNowActorInfo(bg_index, elm->m_bgw_base_ptr, elm->m_actor_id);
                if (!acch->ChkSameActorPid(elm->m_actor_id)) {
                    dBgW* bgwp = (dBgW*)elm->m_bgw_base_ptr;
                    if (bgwp->ChkPriority(prio))
                        bgwp->WallCorrectGrpRp(acch, bgwp->m_rootGrpIdx, 1);
                }
            }
        }
    }
}

/* 800A13E0-800A14FC       .text RoofChk__4dBgSFP12dBgS_RoofChk */
f32 dBgS::RoofChk(dBgS_RoofChk* chk) {
    chk->SetNowY(G_CM3D_F_INF);
    chk->ClearPi();
    cBgS_ChkElm* elm;
    for (s32 bg_index = 0; bg_index < (s32)ARRAY_SIZE(m_chk_element); bg_index++) {
        elm = &m_chk_element[bg_index];
        if (elm->ChkUsed() && elm->m_bgw_base_ptr->GetVtxTbl() != NULL && !chk->ChkSameActorPid(elm->m_actor_id)) {
            dBgW* bgwp = (dBgW*)elm->m_bgw_base_ptr;
            if (bgwp->RoofChkGrpRp(chk, elm->m_bgw_base_ptr->m_rootGrpIdx, 1)) {
                chk->SetActorInfo(bg_index, elm->m_bgw_base_ptr, elm->m_actor_id);
            }
        }
    }
    return chk->GetNowY();
}

/* 800A14FC-800A160C       .text SplGrpChk__4dBgSFP14dBgS_SplGrpChk */
bool dBgS::SplGrpChk(dBgS_SplGrpChk* chk) {
    bool ret = false;
    chk->Init();
    for (s32 bg_index = 0; bg_index < (s32)ARRAY_SIZE(m_chk_element); bg_index++) {
        cBgS_ChkElm* elm = &m_chk_element[bg_index];
        if (elm->ChkUsed() && elm->m_bgw_base_ptr->GetVtxTbl() != NULL && !chk->ChkSameActorPid(elm->m_actor_id)) {
            dBgW* bgwp = (dBgW*)elm->m_bgw_base_ptr;
            if (bgwp->SplGrpChkGrpRp(chk, elm->m_bgw_base_ptr->m_rootGrpIdx, 1)) {
                ret = true;
                chk->SetActorInfo(bg_index, elm->m_bgw_base_ptr, elm->m_actor_id);
                chk->OnFind();
            }
        }
    }
    return ret;
}

/* 800A1954-800A1A74       .text MoveBgCrrPos__4dBgSFR13cBgS_PolyInfobP4cXyzP5csXyzP5csXyz */
void dBgS::MoveBgCrrPos(cBgS_PolyInfo& polyInfo, bool accept, cXyz* pos, csXyz* angle, csXyz* shape_angle) {
    if (!accept || !polyInfo.ChkBgIndex())
        return;

    s32 bg_index = polyInfo.GetBgIndex();
    JUT_ASSERT(1911, 0 <= bg_index && bg_index < 256);

    if (m_chk_element[bg_index].ChkUsed()) {
        dBgW* bgwp = (dBgW*)m_chk_element[bg_index].m_bgw_base_ptr;
        if (bgwp->mFlag & 1 && ChkPolySafe(polyInfo)) {
            bgwp->CrrPos(polyInfo, m_chk_element[bg_index].m_actor_ptr, accept, pos, angle, shape_angle);
        }
    }
}

/* 800A1DF8-800A1ED0       .text RideCallBack__4dBgSFR13cBgS_PolyInfoP10fopAc_ac_c */
void dBgS::RideCallBack(cBgS_PolyInfo& polyInfo, fopAc_ac_c* ac) {
    s32 bg_index = polyInfo.GetBgIndex();
    JUT_ASSERT(0x881, 0 <= bg_index && bg_index < 256);

    dBgW* bgwp = (dBgW*)m_chk_element[bg_index].m_bgw_base_ptr;
    if (bgwp->ChkUsed() && bgwp->mpRideCb != NULL)
        bgwp->mpRideCb(bgwp, m_chk_element[bg_index].m_actor_ptr, ac);
}
