// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_w.cpp - dBgW's constructor, the wall pass, the roof walk, CrrPos and the two
// refusals (d_bg_w.cpp:14-24, 32-40, 42-259, 261-294, 296-320, 322-344, 346-377, 379-406,
// 867-871, 879-898, 911-929). The refusals are reached only through the vtable.
// ChkGrpThrough's five arms accept; its fall-through `return true` refuses.

#include "d/d_bg_w.h"

// <math.h>, not <cmath>: libstdc++'s <cmath> removes the unqualified isnan
// that JUT_ASSERT(208, !isnan(x)) uses.
#include <math.h>

#include "SSystem/SComponent/c_m2d.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_cir.h"
#include "SSystem/SComponent/c_math.h"
#include "d/d_bg_s_acch.h"
#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"
#include "d/d_bg_s_roof_chk.h"
#include "engine/jut_assert.h"
#include "engine/ppc_fp.h"

/* 800A5C3C-800A5CA8       .text __ct__4dBgWFv */
dBgW::dBgW() {
    mRotYDelta = 0;
    mOldRotY = 0;
    m_crr_func = NULL;
    mpRideCb = NULL;
    mpPushPullCb = NULL;
    mFlag = 0;
    mRoomNo = 0xFFFF;
    mRoomNo2 = 0xFF;
}

/* 800A5CD4-800A5E64       .text positionWallCorrect__4dBgWFP9dBgS_AcchfR8cM3dGPlaP4cXyzf */
void dBgW::positionWallCorrect(dBgS_Acch* acch, f32 dist, cM3dGPla& plane, cXyz* pupper_pos, f32 speed) {
    acch->SetWallHit();
    f32 move = speed * dist;
    pupper_pos->x += move * plane.mNormal.x;
    pupper_pos->z += move * plane.mNormal.z;
    JUT_ASSERT(208, !isnan(pupper_pos->x));
    JUT_ASSERT(209, !isnan(pupper_pos->z));
}

/* 800A5E64-800A6DF8       .text RwgWallCorrect__4dBgWFP9dBgS_AcchUs */
bool dBgW::RwgWallCorrect(dBgS_Acch* pwi, u16 i_poly_idx) {
    bool correct = false;

    while (true) {
        cBgW_RwgElm* rwg_elm = &pm_rwg[i_poly_idx];

        if (!ChkPolyThrough(i_poly_idx, pwi->GetPolyPassChk())) {
            cBgW_TriElm* tri = &pm_tri[i_poly_idx];

            f32 sp68 = ppc::sqrtf_msl(SQUARE(tri->m_plane.GetNP()->x) + SQUARE(tri->m_plane.GetNP()->z));
            if (cM3d_IsZero(sp68)) {
                if (rwg_elm->next != 0xFFFF) {
                    i_poly_idx = rwg_elm->next;
                    continue;
                }
                break;
            }

            f32 sp6C = 1.0f / sp68;
            cBgD_Tri_t* tri_data = &pm_bgd->m_t_tbl[i_poly_idx];

            for (int cir_index = 0; cir_index < pwi->GetTblSize(); cir_index++) {
                f32 sp78 = sp6C * pwi->GetWallR(cir_index);
                Vec sp50;
                sp50.x = sp78 * tri->m_plane.GetNP()->x;
                sp50.y = 0.0f;
                sp50.z = sp78 * tri->m_plane.GetNP()->z;

                f32 sp7C;
                if (!pwi->ChkWallHDirect(cir_index)) {
                    sp7C =
                        (pwi->GetWallAddY(sp50, cir_index) + (pwi->GetPos()->y + pwi->GetWallH(cir_index))) -
                        pwi->GetSpeedY();
                } else {
                    sp7C = pwi->GetWallHDirect(cir_index);
                }

                f32 sp5C[3];
                sp5C[0] = pm_vtx_tbl[tri_data->vtx0].y - sp7C;
                sp5C[1] = pm_vtx_tbl[tri_data->vtx1].y - sp7C;
                sp5C[2] = pm_vtx_tbl[tri_data->vtx2].y - sp7C;

                if (((sp5C[0] > 0.0f) && (sp5C[1] > 0.0f) && (sp5C[2] > 0.0f)) ||
                    ((sp5C[0] < 0.0f) && (sp5C[1] < 0.0f) && (sp5C[2] < 0.0f)))
                {
                    continue;
                }

                int sp8C = 0;
                if (cM3d_IsZero(sp5C[0])) {
                    sp8C++;
                }
                if (cM3d_IsZero(sp5C[1])) {
                    sp8C++;
                }
                if (cM3d_IsZero(sp5C[2])) {
                    sp8C++;
                }

                int sp80, sp84, sp88;
                if (sp8C != 1) {
                    if ((sp5C[0] > 0.0f && (sp5C[1] <= 0.0f) && (sp5C[2] <= 0.0f)) ||
                        (sp5C[0] < 0.0f && (sp5C[1] >= 0.0f) && (sp5C[2] >= 0.0f)))
                    {
                        sp80 = 0;
                        sp84 = 1;
                        sp88 = 2;
                    } else if ((sp5C[1] > 0.0f && (sp5C[0] <= 0.0f) && (sp5C[2] <= 0.0f)) ||
                               (sp5C[1] < 0.0f && (sp5C[0] >= 0.0f) && (sp5C[2] >= 0.0f)))
                    {
                        sp80 = 1;
                        sp84 = 0;
                        sp88 = 2;
                    } else {
                        sp80 = 2;
                        sp84 = 0;
                        sp88 = 1;
                    }

                    f32 sp90 = sp5C[sp80] - sp5C[sp84];
                    f32 sp94 = sp5C[sp80] - sp5C[sp88];
                    if (!cM3d_IsZero(sp90) && !cM3d_IsZero(sp94)) {
                        f32 sp98 = -sp5C[sp84] / sp90;
                        f32 sp9C = -sp5C[sp88] / sp94;

                        f32 vtx0_x = pm_vtx_tbl[tri_data->vtx0].x;
                        f32 vtx0_z = pm_vtx_tbl[tri_data->vtx0].z;
                        f32 vtx1_x = pm_vtx_tbl[tri_data->vtx1].x;
                        f32 vtx1_z = pm_vtx_tbl[tri_data->vtx1].z;
                        f32 vtx2_x = pm_vtx_tbl[tri_data->vtx2].x;
                        f32 vtx2_z = pm_vtx_tbl[tri_data->vtx2].z;

                        f32 cx0, cy0, cx1, cy1;
                        if (sp80 == 0) {
                            cx0 = vtx1_x + sp98 * (vtx0_x - vtx1_x);
                            cy0 = vtx1_z + sp98 * (vtx0_z - vtx1_z);
                            cx1 = vtx2_x + sp9C * (vtx0_x - vtx2_x);
                            cy1 = vtx2_z + sp9C * (vtx0_z - vtx2_z);
                        } else if (sp80 == 1) {
                            cx0 = vtx0_x + sp98 * (vtx1_x - vtx0_x);
                            cy0 = vtx0_z + sp98 * (vtx1_z - vtx0_z);
                            cx1 = vtx2_x + sp9C * (vtx1_x - vtx2_x);
                            cy1 = vtx2_z + sp9C * (vtx1_z - vtx2_z);
                        } else {
                            cx0 = vtx0_x + sp98 * (vtx2_x - vtx0_x);
                            cy0 = vtx0_z + sp98 * (vtx2_z - vtx0_z);
                            cx1 = vtx1_x + sp9C * (vtx2_x - vtx1_x);
                            cy1 = vtx1_z + sp9C * (vtx2_z - vtx1_z);
                        }

                        cx0 += sp50.x;
                        cy0 += sp50.z;
                        cx1 += sp50.x;
                        cy1 += sp50.z;

                        f32 spC8, spCC, spD0;
                        bool sp107 = cM3d_Len2dSqPntAndSegLine(
                            pwi->GetCx(), pwi->GetCz(),
                            cx0, cy0,
                            cx1, cy1,
                            &spCC, &spD0,
                            &spC8
                        );

                        f32 spD4 = spCC - pwi->GetCx();
                        f32 spD8 = spD0 - pwi->GetCz();
                        f32 spDC = pwi->GetWallRR(cir_index);

                        if ((spC8 > spDC) || (spD4 * sp50.x + spD8 * sp50.z < 0.0f)) {
                            continue;
                        }

                        if (sp107 == 1) {
                            positionWallCorrect(pwi, sp6C, tri->m_plane, pwi->GetPos(),
                                                ppc::sqrtf_msl(spC8));
                            pwi->CalcMovePosWork();
                            pwi->SetWallCirHit(cir_index);
                            pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                            pwi->SetWallAngleY(
                                cir_index,
                                cM_atan2s(tri->m_plane.GetNP()->x, tri->m_plane.GetNP()->z)
                            );
                            correct = true;
                        } else {
                            cx0 -= sp50.x;
                            cy0 -= sp50.z;
                            cx1 -= sp50.x;
                            cy1 -= sp50.z;

                            f32 spE0 = cM3d_Len2dSq(cx0, cy0, pwi->GetPos()->x, pwi->GetPos()->z);
                            f32 spE4 = cM3d_Len2dSq(cx1, cy1, pwi->GetPos()->x, pwi->GetPos()->z);

                            f32 onx = -tri->m_plane.GetNP()->x;
                            f32 ony = -tri->m_plane.GetNP()->z;

                            JUT_ASSERT(DEMO_SELECT(444, 463), !(cM3d_IsZero(onx) && cM3d_IsZero(ony)));

                            if (spE0 < spE4) {
                                if ((spE0 > spDC) || (std::fabs(spE0 - spDC) < 0.008f)) {
                                    continue;
                                }
                                f32 spF0, spF4;
                                cM2d_CrossCirLin(*pwi->GetWallCirP(cir_index), cx0, cy0,
                                                    onx, ony, &spF0, &spF4);
                                pwi->GetPos()->x += cx0 - spF0;
                                pwi->GetPos()->z += cy0 - spF4;

                                JUT_ASSERT(DEMO_SELECT(465, 484), !isnan(pwi->GetPos()->x));
                                JUT_ASSERT(DEMO_SELECT(466, 485), !isnan(pwi->GetPos()->z));

                                pwi->CalcMovePosWork();
                                pwi->SetWallCirHit(cir_index);
                                pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                                pwi->SetWallAngleY(
                                    cir_index,
                                    cM_atan2s(tri->m_plane.GetNP()->x, tri->m_plane.GetNP()->z)
                                );
                                correct = true;
                                pwi->SetWallHit();
                            } else {
                                if ((spE4 > spDC) || (std::fabs(spE4 - spDC) < 0.008f)) {
                                    continue;
                                }
                                f32 spF8, spFC;
                                cM2d_CrossCirLin(*pwi->GetWallCirP(cir_index), cx1, cy1,
                                                    onx, ony, &spF8, &spFC);
                                pwi->GetPos()->x += cx1 - spF8;
                                pwi->GetPos()->z += cy1 - spFC;

                                JUT_ASSERT(DEMO_SELECT(505, 524), !isnan(pwi->GetPos()->x));
                                JUT_ASSERT(DEMO_SELECT(506, 525), !isnan(pwi->GetPos()->z));

                                pwi->CalcMovePosWork();
                                pwi->SetWallCirHit(cir_index);
                                pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                                pwi->SetWallAngleY(
                                    cir_index,
                                    cM_atan2s(tri->m_plane.GetNP()->x, tri->m_plane.GetNP()->z)
                                );
                                correct = true;
                                pwi->SetWallHit();
                            }
                        }
                    }
                }
            }
        }

        if (rwg_elm->next == 0xFFFF) {
            break;
        }

        i_poly_idx = rwg_elm->next;
    }

    return correct;
}

/* 800A6DF8-800A7004       .text WallCorrectRp__4dBgWFP9dBgS_Acchi */
bool dBgW::WallCorrectRp(dBgS_Acch* acch, int i) {
    cBgW_NodeTree* node = &m_nt_tbl[i];
    if (!node->Cross(acch->GetWallBmdCylP()))
        return false;

    cBgD_Tree_t* tree = &pm_bgd->m_tree_tbl[i];
    bool ret = false;
    if (tree->mFlag & 1) {
        if (pm_blk[tree->mBlock].wall != 0xFFFF && RwgWallCorrect(acch, pm_blk[tree->mBlock].wall))
            ret = true;
        if (pm_blk[tree->mBlock].roof != 0xFFFF && RwgWallCorrect(acch, pm_blk[tree->mBlock].roof))
            ret = true;
        return ret;
    } else {
        if (tree->mChild[0] != 0xFFFF && WallCorrectRp(acch, tree->mChild[0]))
            ret = true;
        if (tree->mChild[1] != 0xFFFF && WallCorrectRp(acch, tree->mChild[1]))
            ret = true;
        if (tree->mChild[2] != 0xFFFF && WallCorrectRp(acch, tree->mChild[2]))
            ret = true;
        if (tree->mChild[3] != 0xFFFF && WallCorrectRp(acch, tree->mChild[3]))
            ret = true;
        if (tree->mChild[4] != 0xFFFF && WallCorrectRp(acch, tree->mChild[4]))
            ret = true;
        if (tree->mChild[5] != 0xFFFF && WallCorrectRp(acch, tree->mChild[5]))
            ret = true;
        if (tree->mChild[6] != 0xFFFF && WallCorrectRp(acch, tree->mChild[6]))
            ret = true;
        if (tree->mChild[7] != 0xFFFF && WallCorrectRp(acch, tree->mChild[7]))
            ret = true;
        return ret;
    }
}

/* 800A7004-800A7120       .text WallCorrectGrpRp__4dBgWFP9dBgS_Acchii */
bool dBgW::WallCorrectGrpRp(dBgS_Acch* acch, int grp_id, int depth) {
    if (ChkGrpThrough(grp_id, acch->GetGrpPassChk(), depth))
        return false;

    if (!pm_grp[grp_id].aab.Cross(acch->GetWallBmdCylP()))
        return false;

    bool ret = false;
    u32 tree_idx = pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree_idx != 0xFFFF && WallCorrectRp(acch, tree_idx))
        ret = true;

    depth++;
    s32 child_idx = pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF)
            break;
        if (WallCorrectGrpRp(acch, child_idx, depth))
            ret = true;
        child_idx = pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }

    return ret;
}

/* 800A7120-800A72E0       .text RwgRoofChk__4dBgWFUsP12dBgS_RoofChk */
bool dBgW::RwgRoofChk(u16 poly_index, dBgS_RoofChk* chk) {
    bool ret = false;
    while (true) {
        f32 y;
        if (pm_tri[poly_index].m_plane.getCrossY(*chk->GetPosP(), &y) && y > chk->GetPosP()->y && y < chk->GetNowY()) {
            cBgD_Tri_t* tri;
            tri = &pm_bgd->m_t_tbl[poly_index];
            if (cM3d_CrossY_Tri(pm_vtx_tbl[tri->vtx0], pm_vtx_tbl[tri->vtx1], pm_vtx_tbl[tri->vtx2], pm_tri[poly_index].m_plane, chk->GetPosP()) && !ChkPolyThrough(poly_index, chk->GetPolyPassChk())) {
                chk->SetNowY(y);
                chk->SetPolyIndex(poly_index);
                ret = true;
            }
        }

        if (pm_rwg[poly_index].next == 0xFFFF)
            break;

        poly_index = pm_rwg[poly_index].next;
    }

    return ret;
}

/* 800A72E0-800A7514       .text RoofChkRp__4dBgWFP12dBgS_RoofChki */
bool dBgW::RoofChkRp(dBgS_RoofChk* chk, int i) {
    cBgW_NodeTree* node = &m_nt_tbl[i];
    if (!node->CrossY(chk->GetPosP()) || !node->UnderPlaneYUnder(chk->GetNowY()) || node->TopPlaneYUnder(chk->GetPosP()->y))
        return false;

    cBgD_Tree_t* tree = &pm_bgd->m_tree_tbl[i];
    if (tree->mFlag & 1) {
        if (pm_blk[tree->mBlock].roof != 0xFFFF && RwgRoofChk(pm_blk[tree->mBlock].roof, chk))
            return true;
        return false;
    } else {
        bool ret = false;
        if (tree->mChild[0] != 0xFFFF && RoofChkRp(chk, tree->mChild[0]))
            ret = true;
        if (tree->mChild[1] != 0xFFFF && RoofChkRp(chk, tree->mChild[1]))
            ret = true;
        if (tree->mChild[2] != 0xFFFF && RoofChkRp(chk, tree->mChild[2]))
            ret = true;
        if (tree->mChild[3] != 0xFFFF && RoofChkRp(chk, tree->mChild[3]))
            ret = true;
        if (tree->mChild[4] != 0xFFFF && RoofChkRp(chk, tree->mChild[4]))
            ret = true;
        if (tree->mChild[5] != 0xFFFF && RoofChkRp(chk, tree->mChild[5]))
            ret = true;
        if (tree->mChild[6] != 0xFFFF && RoofChkRp(chk, tree->mChild[6]))
            ret = true;
        if (tree->mChild[7] != 0xFFFF && RoofChkRp(chk, tree->mChild[7]))
            ret = true;
        return ret;
    }
}

/* 800A7514-800A767C       .text RoofChkGrpRp__4dBgWFP12dBgS_RoofChkii */
bool dBgW::RoofChkGrpRp(dBgS_RoofChk* chk, int grp_id, int depth) {
    if (ChkGrpThrough(grp_id, chk->GetGrpPassChk(), depth))
        return false;

    cBgW_GrpElm* grp = &pm_grp[grp_id];

    if (!grp->aab.CrossY(chk->GetPosP()) || !grp->aab.UnderPlaneYUnder(chk->GetNowY()) || grp->aab.TopPlaneYUnder(chk->GetPosP()->y))
        return false;

    bool ret = false;
    cBgD_Grp_t* grpd = &pm_bgd->m_g_tbl[grp_id];
    u32 tree_idx = grpd->m_tree_idx;
    if (tree_idx != 0xFFFF && RoofChkRp(chk, tree_idx))
        ret = true;

    depth++;
    s32 child_idx = grpd->m_first_child;
    while (true) {
        if (child_idx == 0xFFFF)
            break;
        if (RoofChkGrpRp(chk, child_idx, depth))
            ret = true;
        child_idx = pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }

    return ret;
}

/* 800A8CB4-800A8CF0       .text CrrPos__4dBgWFR13cBgS_PolyInfoPvbP4cXyzP5csXyzP5csXyz */
void dBgW::CrrPos(cBgS_PolyInfo& poly, void* user, bool accept, cXyz* pos, csXyz* angle, csXyz* shape_angle) {
    if (m_crr_func != NULL)
        m_crr_func(this, user, poly, accept, pos, angle, shape_angle);
}

/* 800A8D2C-800A9474       .text ChkPolyThrough__4dBgWFiP16cBgS_PolyPassChk */
bool dBgW::ChkPolyThrough(int poly_index, cBgS_PolyPassChk* chk) {
    if (chk == NULL)
        return false;
    if (chk->mbObjThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x02)
        return true;
    if (chk->mbCamThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x01)
        return true;
    if (chk->mbLinkThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x04)
        return true;
    if (chk->mbArrowThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x08)
        return true;
    if (chk->mbBombThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x20)
        return true;
    if (chk->mbBoomerangThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x40)
        return true;
    if (chk->mbRopeThrough && GetPolyInf3(GetPolyInfId(poly_index)) & 0x80)
        return true;
    return false;
}

/* 800A9684-800A974C       .text ChkGrpThrough__4dBgWFiP15cBgS_GrpPassChki */
bool dBgW::ChkGrpThrough(int grp_id, cBgS_GrpPassChk* _chk, int depth) {
    dBgS_GrpPassChk* chk = (dBgS_GrpPassChk*)_chk;
    if (depth != 2 || chk == NULL)
        return false;

    int info = pm_bgd->m_g_tbl[grp_id].m_info;
    if (!(info & 0x80700) && chk->MaskNormalGrp())
        return false;
    if ((info & 0x00100) && chk->MaskWaterGrp())
        return false;
    if ((info & 0x00200) && chk->MaskYoganGrp())
        return false;
    if ((info & 0x00400) && chk->MaskDokuGrp())
        return false;
    if ((info & 0x80000) && chk->MaskLightGrp())
        return false;
    return true;
}
