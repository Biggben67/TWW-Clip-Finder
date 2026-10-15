// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_w.cpp - cBgW's load-time build, its line and ground walks, and the per-polygon tests
// (c_bg_w.cpp:104-122, 134-142, 144-187, 189-193, 195-204, 206-230, 232-253, 255-273,
// 275-297, 299-304, 368-398, 407-442, 445-467, 469-481, 483-497, 499-512, 514-575, 577-602,
// 730-737, 756-760, 715-718, 725-728).
// cBgW::ChkPolyThrough and ChkGrpThrough are virtual and return false; a room is a dBgW,
// whose overrides can refuse.

#include "SSystem/SComponent/c_bg_w.h"

#include "SSystem/SComponent/c_bg_s_gnd_chk.h"
#include "SSystem/SComponent/c_bg_s_lin_chk.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_tri.h"

/* 80247840-80247944       .text CalcPlane__4cBgWFv */
void cBgW::CalcPlane() {
    const cBgD_Tri_t* t_tbl = pm_bgd->m_t_tbl;

    if (pm_vtx_tbl == NULL)
        return;

    if (!mbNeedsFullTransform) {
        for (s32 i = 0; i < pm_bgd->m_t_num; i++) {
            f32 dot = VECDotProduct(pm_tri[i].m_plane.GetNP(), &mTransVel);
            pm_tri[i].m_plane.mD -= dot;
        }
    } else {
        for (s32 i = 0; i < pm_bgd->m_t_num; i++) {
            cBgW_TriElm* tri_elm = &pm_tri[i];
            cM3d_CalcPla(&pm_vtx_tbl[t_tbl[i].vtx0], &pm_vtx_tbl[t_tbl[i].vtx1], &pm_vtx_tbl[t_tbl[i].vtx2], tri_elm->m_plane.GetNP(), &tri_elm->m_plane.mD);
        }
    }
}

/* 802479D8-80247A24       .text BlckConnect__4cBgWFPUsPii */
void cBgW::BlckConnect(u16* rwg, int* prev, int i_no) {
    if (*rwg == 0xFFFF)
        *rwg = i_no;
    if (*prev != 0xFFFF)
        pm_rwg[*prev].next = i_no;
    *prev = i_no;
    pm_rwg[*prev].next = -1;
}

/* 80247A24-80247BF8       .text ClassifyPlane__4cBgWFv */
void cBgW::ClassifyPlane() {
    if (pm_vtx_tbl == NULL)
        return;

    s32 i = 0;

    int roof, wall, ground;
    for (; i < pm_bgd->m_b_num; i++) {
        s32 startTri = pm_bgd->m_b_tbl[i].startTri;
        s32 lastTri;
        if (i != pm_bgd->m_b_num - 1)
            lastTri = pm_bgd->m_b_tbl[i + 1].startTri - 1;
        else
            lastTri = pm_bgd->m_t_num - 1;

        pm_blk[i].roof = 0xFFFF;
        pm_blk[i].wall = 0xFFFF;
        pm_blk[i].ground = 0xFFFF;

        ground = 0xFFFF;
        wall = 0xFFFF;
        roof = 0xFFFF;

        for (s32 j = startTri; j <= lastTri; j++) {
            cBgW_TriElm* tri_elm = &pm_tri[j];

            f32 ny = tri_elm->m_plane.GetNP()->y;
            if (cM3d_IsZero(tri_elm->m_plane.GetNP()->x) && cM3d_IsZero(tri_elm->m_plane.GetNP()->y) && cM3d_IsZero(tri_elm->m_plane.GetNP()->z))
                continue;

            if (cBgW_CheckBGround(ny)) {
                if (!(mIgnorePlaneType & 1))
                    BlckConnect(&pm_blk[i].ground, &ground, j);
            } else if (cBgW_CheckBRoof(ny)) {
                if (!(mIgnorePlaneType & 4))
                    BlckConnect(&pm_blk[i].roof, &roof, j);
            } else {
                if (!(mIgnorePlaneType & 2))
                    BlckConnect(&pm_blk[i].wall, &wall, j);
            }
        }
    }
}

/* 80247BF8-80247C4C       .text MakeBlckTransMinMax__4cBgWFP4cXyzP4cXyz */
void cBgW::MakeBlckTransMinMax(cXyz* min, cXyz* max) {
    VECAdd(min, &mTransVel, min);
    VECAdd(max, &mTransVel, max);
}

/* 80247C4C-80247CD4       .text MakeBlckMinMax__4cBgWFiP4cXyzP4cXyz */
void cBgW::MakeBlckMinMax(int i_no, cXyz* min, cXyz* max) {
    Vec* vtx = &pm_vtx_tbl[i_no];
    if (min->x > vtx->x) min->x = vtx->x;
    if (max->x < vtx->x) max->x = vtx->x;
    if (min->y > vtx->y) min->y = vtx->y;
    if (max->y < vtx->y) max->y = vtx->y;
    if (min->z > vtx->z) min->z = vtx->z;
    if (max->z < vtx->z) max->z = vtx->z;
}

/* 80247CD4-80247E48       .text MakeBlckBnd__4cBgWFiP4cXyzP4cXyz */
void cBgW::MakeBlckBnd(int i, cXyz* min, cXyz* max) {
    s32 startTri = pm_bgd->m_b_tbl[i].startTri;
    s32 lastTri = (i != pm_bgd->m_b_num - 1) ? pm_bgd->m_b_tbl[i + 1].startTri - 1 : pm_bgd->m_t_num - 1;

    if (!mbNeedsFullTransform) {
        MakeBlckTransMinMax(min, max);
    } else {
        min->x = min->y = min->z = G_CM3D_F_INF;
        max->x = max->y = max->z = -G_CM3D_F_INF;

        for (s32 j = startTri; j <= lastTri; j++) {
            MakeBlckMinMax(pm_bgd->m_t_tbl[j].vtx0, min, max);
            MakeBlckMinMax(pm_bgd->m_t_tbl[j].vtx1, min, max);
            MakeBlckMinMax(pm_bgd->m_t_tbl[j].vtx2, min, max);
        }

        min->x -= 1.0f;
        min->y -= 1.0f;
        min->z -= 1.0f;
        max->x += 1.0f;
        max->y += 1.0f;
        max->z += 1.0f;
    }
}

/* 80247E48-80247F4C       .text MakeNodeTreeRp__4cBgWFi */
void cBgW::MakeNodeTreeRp(int i) {
    const cBgD_Tree_t* tree = &pm_bgd->m_tree_tbl[i];
    if (tree->mFlag & 1) {
        // leaf
        s32 block = tree->mBlock;
        if (block != 0xFFFF) {
            MakeBlckBnd(tree->mBlock, m_nt_tbl[i].GetMinP(), m_nt_tbl[i].GetMaxP());
        }
    } else {
        // branch
        m_nt_tbl[i].ClearForMinMax();
        for (s32 j = 0; j < 8; j++) {
            s32 child = tree->mChild[j];
            if (child == 0xFFFF)
                continue;
            MakeNodeTreeRp(child);
            m_nt_tbl[i].SetMinMax(*m_nt_tbl[child].GetMinP());
            m_nt_tbl[i].SetMinMax(*m_nt_tbl[child].GetMaxP());
        }
    }
}

/* 80247F4C-80248078       .text MakeNodeTreeGrpRp__4cBgWFi */
void cBgW::MakeNodeTreeGrpRp(int grp_id) {
    u32 tree_idx = pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree_idx != 0xFFFF) {
        MakeNodeTreeRp(tree_idx);
        pm_grp[grp_id].aab.SetMin(*m_nt_tbl[pm_bgd->m_g_tbl[grp_id].m_tree_idx].GetMinP());
        pm_grp[grp_id].aab.SetMax(*m_nt_tbl[pm_bgd->m_g_tbl[grp_id].m_tree_idx].GetMaxP());
    }

    s32 child_idx = pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF)
            break;
        MakeNodeTreeGrpRp(child_idx);
        pm_grp[grp_id].aab.SetMin(*pm_grp[child_idx].aab.GetMinP());
        pm_grp[grp_id].aab.SetMax(*pm_grp[child_idx].aab.GetMaxP());
        child_idx = pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }
}

/* 80248078-80248178       .text MakeNodeTree__4cBgWFv */
void cBgW::MakeNodeTree() {
    if (pm_vtx_tbl == NULL) {
        for (s32 i = 0; i < pm_bgd->m_g_num; i++) {
            if (pm_bgd->m_g_tbl[i].m_parent == 0xFFFF) {
                m_rootGrpIdx = i;
                break;
            }
        }
    } else {
        for (s32 i = 0; i < pm_bgd->m_g_num; i++) {
            pm_grp[i].aab.ClearForMinMax();
        }

        for (s32 i = 0; i < pm_bgd->m_g_num; i++) {
            if (pm_bgd->m_g_tbl[i].m_parent == 0xFFFF) {
                m_rootGrpIdx = i;
                MakeNodeTreeGrpRp(i);
                break;
            }
        }
    }
}

/* 80248178-802481C4       .text ChkMemoryError__4cBgWFv */
bool cBgW::ChkMemoryError() {
    if (pm_tri == NULL || pm_rwg == NULL || pm_blk == NULL || m_nt_tbl == NULL || pm_grp == NULL)
        return true;
    return false;
}

bool cBgW::RwgLineCheck(u16 poly_index, cBgS_LinChk* chk) {
    bool ret = false;
    cM3dGTri gtri;

    cM3dGLin *lin = chk->GetLinP();
    while (true) {
        cBgW_TriElm* tri_elm;
        cBgD_Tri_t* tri;

        tri = &pm_bgd->m_t_tbl[poly_index];
        tri_elm = &pm_tri[poly_index];

        gtri.setBg(&pm_vtx_tbl[tri->vtx0], &pm_vtx_tbl[tri->vtx1], &pm_vtx_tbl[tri->vtx2], &tri_elm->m_plane);
        bool backFlag = chk->ChkBackFlag();
        bool frontFlag = chk->ChkFrontFlag();

        cXyz pt;
        if (cM3d_Cross_LinTri(lin, &gtri, &pt, frontFlag, backFlag) && !ChkPolyThrough(poly_index, chk->GetPolyPassChk())) {
            chk->GetLinP()->SetEnd(pt);
            chk->SetPolyIndex(poly_index);
            ret = true;
        }

        if (pm_rwg[poly_index].next == 0xFFFF)
            break;

        poly_index = pm_rwg[poly_index].next;
    }

    return ret;
}

bool cBgW::LineCheckRp(cBgS_LinChk* chk, int i) {
    cBgW_NodeTree* node = &m_nt_tbl[i];
    if (!cM3d_Cross_MinMaxBoxLine(node->GetMinP(), node->GetMaxP(), chk->GetLinP()->GetStartP(), chk->GetLinP()->GetEndP()))
        return false;

    cBgD_Tree_t* tree = &pm_bgd->m_tree_tbl[i];
    bool ret = false;
    if (tree->mFlag & 1) {
        if (chk->mPreWallChk && pm_blk[tree->mBlock].wall != 0xFFFF && RwgLineCheck(pm_blk[tree->mBlock].wall, chk))
            ret = true;
        if (chk->mPreGroundChk && pm_blk[tree->mBlock].ground != 0xFFFF && RwgLineCheck(pm_blk[tree->mBlock].ground, chk))
            ret = true;
        if (chk->mPreRoofChk && pm_blk[tree->mBlock].roof != 0xFFFF && RwgLineCheck(pm_blk[tree->mBlock].roof, chk))
            ret = true;
        return ret;
    } else {
        // was this manually unrolled?
        if (tree->mChild[0] != 0xFFFF && LineCheckRp(chk, tree->mChild[0]))
            ret = true;
        if (tree->mChild[1] != 0xFFFF && LineCheckRp(chk, tree->mChild[1]))
            ret = true;
        if (tree->mChild[2] != 0xFFFF && LineCheckRp(chk, tree->mChild[2]))
            ret = true;
        if (tree->mChild[3] != 0xFFFF && LineCheckRp(chk, tree->mChild[3]))
            ret = true;
        if (tree->mChild[4] != 0xFFFF && LineCheckRp(chk, tree->mChild[4]))
            ret = true;
        if (tree->mChild[5] != 0xFFFF && LineCheckRp(chk, tree->mChild[5]))
            ret = true;
        if (tree->mChild[6] != 0xFFFF && LineCheckRp(chk, tree->mChild[6]))
            ret = true;
        if (tree->mChild[7] != 0xFFFF && LineCheckRp(chk, tree->mChild[7]))
            ret = true;
        return ret;
    }
}

bool cBgW::LineCheckGrpRp(cBgS_LinChk* chk, int grp_id, int depth) {
    if (ChkGrpThrough(grp_id, chk->GetGrpPassChk(), depth))
        return false;

    if (!pm_grp[grp_id].aab.Cross(chk->GetLinP()))
        return false;

    bool ret = false;
    u16 tree = pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree != 0xFFFF && LineCheckRp(chk, tree))
        ret = true;

    s32 child_idx = pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF)
            break;
        if (LineCheckGrpRp(chk, child_idx, depth + 1))
            ret = true;
        child_idx = pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }

    return ret;
}

/* 8024898C-80248AB8       .text RwgGroundCheckCommon__4cBgWFfUsP11cBgS_GndChk */
bool cBgW::RwgGroundCheckCommon(f32 y, u16 poly_index, cBgS_GndChk* chk) {
    if (y < chk->GetPointP()->y && y > chk->GetNowY()) {
        cBgD_Tri_t* tri = &pm_bgd->m_t_tbl[poly_index];
        if (cM3d_CrossY_Tri_Front(pm_vtx_tbl[tri->vtx0], pm_vtx_tbl[tri->vtx1], pm_vtx_tbl[tri->vtx2], chk->GetPointP()) && !ChkPolyThrough(poly_index, chk->GetPolyPassChk())) {
            chk->SetNowY(y);
            chk->SetPolyIndex(poly_index);
            return true;
        }
    }

    return false;
}

/* 80248AB8-80248B68       .text RwgGroundCheckGnd__4cBgWFUsP11cBgS_GndChk */
bool cBgW::RwgGroundCheckGnd(u16 poly_index, cBgS_GndChk* chk) {
    bool ret = false;
    while (true) {
        cBgW_RwgElm* rwg = &pm_rwg[poly_index];
        cBgW_TriElm* tri = &pm_tri[poly_index];
        f32 y = tri->m_plane.getCrossY_NonIsZero(*chk->GetPointP());
        if (RwgGroundCheckCommon(y, (u16)poly_index, chk))
            ret = true;
        if (rwg->next == 0xFFFF)
            break;
        poly_index = rwg->next;
    }
    return ret;
}

/* 80248B68-80248C38       .text RwgGroundCheckWall__4cBgWFUsP11cBgS_GndChk */
bool cBgW::RwgGroundCheckWall(u16 poly_index, cBgS_GndChk* chk) {
    bool ret = false;
    while (true) {
        cBgW_TriElm* tri = &pm_tri[poly_index];
        cBgW_RwgElm* rwg = &pm_rwg[poly_index];
        if (tri->m_plane.mNormal.y >= 0.014f && RwgGroundCheckCommon(tri->m_plane.getCrossY_NonIsZero(*chk->GetPointP()), (u16)poly_index, chk))
            ret = true;
        if (rwg->next == 0xFFFF)
            break;
        poly_index = rwg->next;
    }
    return ret;
}

/* 80248C38-802491F4       .text GroundCrossRp__4cBgWFP11cBgS_GndChki */
bool cBgW::GroundCrossRp(cBgS_GndChk* chk, int i) {
    bool ret = false;
    cBgD_Tree_t* tree = &pm_bgd->m_tree_tbl[i];
    if (tree->mFlag & 1) {
        if (chk->GetGndPrecheck() && pm_blk[tree->mBlock].ground != 0xFFFF && RwgGroundCheckGnd(pm_blk[tree->mBlock].ground, chk))
            ret = true;
        if (chk->GetWallPrecheck() && pm_blk[tree->mBlock].wall != 0xFFFF && RwgGroundCheckWall(pm_blk[tree->mBlock].wall, chk))
            ret = true;
        return ret;
    } else {
        if (tree->mChild[2] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[2]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[2]))
                ret = true;
        }

        if (tree->mChild[3] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[3]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[3]))
                ret = true;
        }

        if (tree->mChild[6] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[6]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[6]))
                ret = true;
        }

        if (tree->mChild[7] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[7]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[7]))
                ret = true;
        }

        if (tree->mChild[0] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[0]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[0]))
                ret = true;
        }

        if (tree->mChild[1] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[1]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[1]))
                ret = true;
        }

        if (tree->mChild[4] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[4]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[4]))
                ret = true;
        }

        if (tree->mChild[5] != 0xFFFF) {
            cBgW_NodeTree* node = &m_nt_tbl[tree->mChild[5]];
            if (node->CrossY(chk->GetPointP()) && node->UnderPlaneYUnder(chk->GetPointP()->y) && !node->TopPlaneYUnder(chk->mNowY) && GroundCrossRp(chk, tree->mChild[5]))
                ret = true;
        }

        return ret;
    }
}

/* 802491F4-80249368       .text GroundCrossGrpRp__4cBgWFP11cBgS_GndChkii */
bool cBgW::GroundCrossGrpRp(cBgS_GndChk* chk, int grp_id, int depth) {
    if (ChkGrpThrough(grp_id, chk->GetGrpPassChk(), depth))
        return false;

    cBgW_GrpElm* grp = &pm_grp[grp_id];

    if (!grp->aab.CrossY(chk->GetPointP()) || !grp->aab.UnderPlaneYUnder(chk->GetPointP()->y) || grp->aab.TopPlaneYUnder(chk->mNowY))
        return false;

    bool ret = false;
    u32 tree_idx = pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree_idx != 0xFFFF && GroundCrossRp(chk, tree_idx))
        ret = true;

    s32 child_idx = pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF)
            break;
        if (GroundCrossGrpRp(chk, child_idx, depth + 1))
            ret = true;
        child_idx = pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }

    return ret;
}

/* 80249940-80249A18       .text GetGrpToRoomIndex__4cBgWCFi */
u32 cBgW::GetGrpToRoomIndex(int grp_index) const {
    JUT_ASSERT(DEMO_SELECT(3190, 3191), 0 <= grp_index && grp_index < pm_bgd->m_g_num);
    cBgD_Grp_t * g_tbl = pm_bgd->m_g_tbl;
    if (g_tbl[grp_index].m_parent == 0xFFFF || g_tbl[g_tbl[grp_index].m_parent].m_parent == 0xFFFF)
        return 0xFFFF;
    return g_tbl[g_tbl[g_tbl[grp_index].m_parent].m_parent].m_room_id;
}

/* 80249B64-80249BA0       .text GetTopUnder__4cBgWCFPfPf */
void cBgW::GetTopUnder(f32* max, f32* min) const {
    *min = pm_grp[m_rootGrpIdx].aab.GetMinP()->y;
    *max = pm_grp[m_rootGrpIdx].aab.GetMaxP()->y;
}

/* 80249904-8024990C       .text ChkPolyThrough__4cBgWFiP16cBgS_PolyPassChk */
bool cBgW::ChkPolyThrough(int, cBgS_PolyPassChk*) {
    return false;
}

/* 80249938-80249940       .text ChkGrpThrough__4cBgWFiP15cBgS_GrpPassChki */
bool cBgW::ChkGrpThrough(int, cBgS_GrpPassChk*, int) {
    return false;
}
