#include "wall_walk.h"

// <math.h> first: the copied JUT_ASSERTs use unqualified `isnan`, which libstdc++'s <cmath>
// removes as a macro.
#include <math.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_cir.h"
#include "SSystem/SComponent/c_math.h"
#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"
#include "engine/jut_assert.h"
#include "engine/ppc_fp.h"
#include "framework/require_bits.h"

namespace tww_engine {
namespace testing {

namespace {
//: The old sim's IsZero threshold; the console's is 2^-18.
const f32 kLegacyAbsMin = 1.0e-5f;
}  // namespace

/// The decomp's JUT_ASSERT: aborts on `WallVariant::None`, counted (`broken_asserts()`) on a
/// variant, since several variants hand cM2d_CrossCirLin arguments the game asserts against.
#define HARNESS_ASSERT(line, cond)        \
    do {                                  \
        if (m_var == WallVariant::None) { \
            JUT_ASSERT(line, (cond));     \
        } else if (!(cond)) {             \
            m_asserts++;                  \
        }                                 \
    } while (0)

bool WallWalk::is_zero(f32 v) const {
    if (m_var == WallVariant::LegacyIsZero) {
        return std::fabs(v) < kLegacyAbsMin;
    }
    return cM3d_IsZero(v);
}

/// The segment-length IsZero alone, split out so it can be varied apart from the others.
bool WallWalk::seg_is_zero(f32 v) const {
    if (m_var == WallVariant::SegIsZeroLegacy) {
        return std::fabs(v) < kLegacyAbsMin;
    }
    return is_zero(v);
}

/// The pass's square root. `ppc::sqrtf_msl` is the console's (frsqrte + three Newton steps, not
/// correctly rounded); `LibrarySqrt` swaps in a correctly rounded one and counts disagreements.
///
/// The library root is taken only on that variant: taking it on the ported path shifts what the
/// degenerate arm of `cM3d_Len2dSqPntAndSegLine` leaves in the locals (see `degenerate_reads`).
f32 WallWalk::root(f32 v) {
    m_root_calls++;
    const f32 console = ppc::sqrtf_msl(v);
    if (m_var != WallVariant::LibrarySqrt) {
        return console;
    }
    const f32 library = std::sqrt(v);
    if (bits(console) != bits(library)) {
        m_root_differs++;
    }
    return library;
}

void WallWalk::step(int poly, int cyl, char arm, const cXyz* pos) {
    if (m_trace == nullptr) {
        return;
    }
    WallStep s;
    s.poly = poly;
    s.cyl = cyl;
    s.arm = arm;
    s.x_bits = bits(pos->x);
    s.z_bits = bits(pos->z);
    m_trace->push_back(s);
}

// ------------------------------------------------------------- the two primitives it calls

/// cM3d_Len2dSqPntAndSegLine (c_m3d.cpp:50-69), with its one IsZero on the variant's threshold.
bool WallWalk::len2dsq_pnt_seg(f32 xp, f32 yp, f32 x0, f32 y0, f32 x1, f32 y1, f32* outx,
                               f32* outy, f32* seg) {
    bool ret = false;
    f32 xd = x1 - x0;
    f32 yd = y1 - y0;
    f32 dot = (xd * xd + yd * yd);
    if (seg_is_zero(dot)) {
        // Writes only *seg; the closest-point outputs keep the caller's values, which
        // RwgWallCorrect then reads. Counted by `degenerate_reads`.
        m_degenerate++;
        if (m_var == WallVariant::SegAssignsStart) {
            *outx = x0;
            *outy = y0;
        }
        *seg = 0.0f;
        return false;
    }
    f32 mag = (xd * (xp - x0) + yd * (yp - y0)) / dot;
    if (mag >= 0.0f && mag <= 1.0f) {
        ret = true;
    }
    *outx = x0 + xd * mag;
    *outy = y0 + yd * mag;
    *seg = cM3d_Len2dSq(*outx, *outy, xp, yp);
    return ret;
}

/// cM2d_CrossCirLin (c_m2d.cpp:11-55), with its IsZeros and roots on the variant's, and its arms
/// counted. The decomp leaves `t` uninitialised on two arms (the port copies that); here `t` is
/// zeroed so those arms can be counted.
void WallWalk::cross_cir_lin(cM2dGCir& circle, f32 x0, f32 y0, f32 x1, f32 y1, f32* pDstX,
                             f32* pDstY) {
    m_ccl_calls++;
    f32 fVar1 = x0 - circle.GetCx();
    f32 fVar15 = y0 - circle.GetCy();
    f32 dVar13 = x1 * x1 + y1 * y1;
    f32 dVar14 = 2.0f * ((x1 * fVar1) + (y1 * fVar15));
    f32 c = (fVar1 * fVar1 + fVar15 * fVar15) - (circle.GetR() * circle.GetR());
    f32 t = 0.0f;

    HARNESS_ASSERT(0x47, c < 0.0f);

    if (is_zero(dVar13)) {
        if (!is_zero(dVar14)) {
            t = -c / dVar14;
        } else {
            m_ccl_unassigned++;  //: arm one - no assignment to `t` at all
        }
    } else {
        f32 dVar10 = ((dVar14 * dVar14) - (4.0f * dVar13) * c);
        if (is_zero(dVar10)) {
            t = (-dVar14 / (2.0f * dVar13));
        } else {
            if (dVar10 < 0.0f) {
                m_ccl_unassigned++;  //: arm two - likewise
            } else {
                m_ccl_quadratic++;
                f32 fVar2 = 1.0f / (2.0f * dVar13);
                f32 fVar15b = root(dVar10);
                fVar15b = fVar2 * (-dVar14 + fVar15b);
                f32 fVar16 = root(dVar10);
                f32 fVar4 = fVar2 * (-dVar14 - fVar16);
                if (fVar15b > fVar4) {
                    t = fVar15b;
                } else {
                    t = fVar4;
                }
            }
        }
    }

    if (is_zero(t)) {
        *pDstX = x0;
        *pDstY = y0;
    } else {
        HARNESS_ASSERT(0x89, t >= 0.0f);
        *pDstX = x0 + (t * x1);
        *pDstY = y0 + (t * y1);
    }
}

/// dBgW::positionWallCorrect (d_bg_w.cpp:96-103), copied so this walk does not call the port.
void WallWalk::position_wall_correct(dBgS_Acch* acch, f32 dist, cM3dGPla& plane, cXyz* pupper_pos,
                                     f32 speed) {
    acch->SetWallHit();
    f32 move = speed * dist;
    pupper_pos->x += move * plane.mNormal.x;
    pupper_pos->z += move * plane.mNormal.z;
    HARNESS_ASSERT(208, !isnan(pupper_pos->x));
    HARNESS_ASSERT(209, !isnan(pupper_pos->z));
}

// ------------------------------------------------------------------------------- the walk

/// dBgW::RwgWallCorrect (d_bg_w.cpp:104-300).
bool WallWalk::rwg(dBgS_Acch* pwi, u16 i_poly_idx) {
    bool correct = false;

    while (true) {
        cBgW_RwgElm* rwg_elm = &m_w.pm_rwg[i_poly_idx];

        if (!m_w.ChkPolyThrough(i_poly_idx, pwi->GetPolyPassChk())) {
            cBgW_TriElm* tri = &m_w.pm_tri[i_poly_idx];

            f32 sp68 = root(SQUARE(tri->m_plane.GetNP()->x) + SQUARE(tri->m_plane.GetNP()->z));
            if (is_zero(sp68)) {
                if (rwg_elm->next != 0xFFFF) {
                    i_poly_idx = rwg_elm->next;
                    continue;
                }
                break;
            }

            f32 sp6C = 1.0f / sp68;
            cBgD_Tri_t* tri_data = &m_w.pm_bgd->m_t_tbl[i_poly_idx];

            for (int cir_index = 0; cir_index < pwi->GetTblSize(); cir_index++) {
                f32 sp78 = sp6C * pwi->GetWallR(cir_index);
                Vec sp50;
                sp50.x = sp78 * tri->m_plane.GetNP()->x;
                sp50.y = 0.0f;
                sp50.z = sp78 * tri->m_plane.GetNP()->z;

                f32 sp7C;
                if (!pwi->ChkWallHDirect(cir_index)) {
                    sp7C = (pwi->GetWallAddY(sp50, cir_index) +
                            (pwi->GetPos()->y + pwi->GetWallH(cir_index))) -
                           pwi->GetSpeedY();
                } else {
                    sp7C = pwi->GetWallHDirect(cir_index);
                }

                f32 sp5C[3];
                sp5C[0] = m_w.pm_vtx_tbl[tri_data->vtx0].y - sp7C;
                sp5C[1] = m_w.pm_vtx_tbl[tri_data->vtx1].y - sp7C;
                sp5C[2] = m_w.pm_vtx_tbl[tri_data->vtx2].y - sp7C;

                if (((sp5C[0] > 0.0f) && (sp5C[1] > 0.0f) && (sp5C[2] > 0.0f)) ||
                    ((sp5C[0] < 0.0f) && (sp5C[1] < 0.0f) && (sp5C[2] < 0.0f))) {
                    continue;
                }

                int sp8C = 0;
                if (is_zero(sp5C[0])) {
                    sp8C++;
                }
                if (is_zero(sp5C[1])) {
                    sp8C++;
                }
                if (is_zero(sp5C[2])) {
                    sp8C++;
                }

                int sp80, sp84, sp88;
                if (sp8C != 1) {
                    if ((sp5C[0] > 0.0f && (sp5C[1] <= 0.0f) && (sp5C[2] <= 0.0f)) ||
                        (sp5C[0] < 0.0f && (sp5C[1] >= 0.0f) && (sp5C[2] >= 0.0f))) {
                        sp80 = 0;
                        sp84 = 1;
                        sp88 = 2;
                    } else if ((sp5C[1] > 0.0f && (sp5C[0] <= 0.0f) && (sp5C[2] <= 0.0f)) ||
                               (sp5C[1] < 0.0f && (sp5C[0] >= 0.0f) && (sp5C[2] >= 0.0f))) {
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
                    if (!is_zero(sp90) && !is_zero(sp94)) {
                        f32 sp98 = -sp5C[sp84] / sp90;
                        f32 sp9C = -sp5C[sp88] / sp94;

                        f32 vtx0_x = m_w.pm_vtx_tbl[tri_data->vtx0].x;
                        f32 vtx0_z = m_w.pm_vtx_tbl[tri_data->vtx0].z;
                        f32 vtx1_x = m_w.pm_vtx_tbl[tri_data->vtx1].x;
                        f32 vtx1_z = m_w.pm_vtx_tbl[tri_data->vtx1].z;
                        f32 vtx2_x = m_w.pm_vtx_tbl[tri_data->vtx2].x;
                        f32 vtx2_z = m_w.pm_vtx_tbl[tri_data->vtx2].z;

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
                        bool sp107 = len2dsq_pnt_seg(pwi->GetCx(), pwi->GetCz(), cx0, cy0, cx1,
                                                     cy1, &spCC, &spD0, &spC8);

                        f32 spD4 = spCC - pwi->GetCx();
                        f32 spD8 = spD0 - pwi->GetCz();
                        f32 spDC = pwi->GetWallRR(cir_index);

                        if ((spC8 > spDC) || (spD4 * sp50.x + spD8 * sp50.z < 0.0f)) {
                            continue;
                        }

                        if (sp107 == 1) {
                            position_wall_correct(pwi, sp6C, tri->m_plane, pwi->GetPos(),
                                                  root(spC8));
                            if (m_var != WallVariant::NoRebuild) {
                                pwi->CalcMovePosWork();
                            }
                            pwi->SetWallCirHit(cir_index);
                            pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                            pwi->SetWallAngleY(cir_index,
                                               cM_atan2s(tri->m_plane.GetNP()->x,
                                                         tri->m_plane.GetNP()->z));
                            correct = true;
                            step(i_poly_idx, cir_index, 's', pwi->GetPos());
                        } else {
                            cx0 -= sp50.x;
                            cy0 -= sp50.z;
                            cx1 -= sp50.x;
                            cy1 -= sp50.z;

                            f32 spE0 =
                                cM3d_Len2dSq(cx0, cy0, pwi->GetPos()->x, pwi->GetPos()->z);
                            f32 spE4 =
                                cM3d_Len2dSq(cx1, cy1, pwi->GetPos()->x, pwi->GetPos()->z);

                            f32 onx = -tri->m_plane.GetNP()->x;
                            f32 ony = -tri->m_plane.GetNP()->z;

                            HARNESS_ASSERT(DEMO_SELECT(444, 463), !(is_zero(onx) && is_zero(ony)));

                            const bool near_first =
                                (m_var == WallVariant::NearEndOnly) ? true : (spE0 < spE4);
                            if (near_first) {
                                if ((spE0 > spDC) || (std::fabs(spE0 - spDC) < 0.008f)) {
                                    continue;
                                }
                                f32 spF0, spF4;
                                cross_cir_lin(*pwi->GetWallCirP(cir_index), cx0, cy0, onx, ony,
                                              &spF0, &spF4);
                                pwi->GetPos()->x += cx0 - spF0;
                                pwi->GetPos()->z += cy0 - spF4;

                                HARNESS_ASSERT(DEMO_SELECT(465, 484), !isnan(pwi->GetPos()->x));
                                HARNESS_ASSERT(DEMO_SELECT(466, 485), !isnan(pwi->GetPos()->z));

                                if (m_var != WallVariant::NoRebuild) {
                                    pwi->CalcMovePosWork();
                                }
                                pwi->SetWallCirHit(cir_index);
                                pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                                pwi->SetWallAngleY(cir_index,
                                                   cM_atan2s(tri->m_plane.GetNP()->x,
                                                             tri->m_plane.GetNP()->z));
                                correct = true;
                                pwi->SetWallHit();
                                step(i_poly_idx, cir_index, '0', pwi->GetPos());
                            } else {
                                if ((spE4 > spDC) || (std::fabs(spE4 - spDC) < 0.008f)) {
                                    continue;
                                }
                                f32 spF8, spFC;
                                cross_cir_lin(*pwi->GetWallCirP(cir_index), cx1, cy1, onx, ony,
                                              &spF8, &spFC);
                                pwi->GetPos()->x += cx1 - spF8;
                                pwi->GetPos()->z += cy1 - spFC;

                                HARNESS_ASSERT(DEMO_SELECT(505, 524), !isnan(pwi->GetPos()->x));
                                HARNESS_ASSERT(DEMO_SELECT(506, 525), !isnan(pwi->GetPos()->z));

                                if (m_var != WallVariant::NoRebuild) {
                                    pwi->CalcMovePosWork();
                                }
                                pwi->SetWallCirHit(cir_index);
                                pwi->SetWallPolyIndex(cir_index, i_poly_idx);
                                pwi->SetWallAngleY(cir_index,
                                                   cM_atan2s(tri->m_plane.GetNP()->x,
                                                             tri->m_plane.GetNP()->z));
                                correct = true;
                                pwi->SetWallHit();
                                step(i_poly_idx, cir_index, '1', pwi->GetPos());
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

/// dBgW::WallCorrectRp (d_bg_w.cpp:302-355). The decomp's eight child `if`s are a loop here so
/// `ChildrenReversed` can reverse it.
bool WallWalk::rp(dBgS_Acch* acch, int i) {
    cBgW_NodeTree* node = &m_w.m_nt_tbl[i];
    if (!node->Cross(acch->GetWallBmdCylP())) {
        return false;
    }

    cBgD_Tree_t* tree = &m_w.pm_bgd->m_tree_tbl[i];
    bool ret = false;
    if (tree->mFlag & 1) {
        const u16 wall = m_w.pm_blk[tree->mBlock].wall;
        const u16 roof = m_w.pm_blk[tree->mBlock].roof;
        if (m_var == WallVariant::RoofFirst) {
            if (roof != 0xFFFF && rwg(acch, roof)) {
                ret = true;
            }
            if (wall != 0xFFFF && rwg(acch, wall)) {
                ret = true;
            }
            return ret;
        }
        if (wall != 0xFFFF && rwg(acch, wall)) {
            ret = true;
        }
        if (m_var != WallVariant::WallChainOnly && roof != 0xFFFF && rwg(acch, roof)) {
            ret = true;
        }
        return ret;
    }
    for (int k = 0; k < 8; k++) {
        const int slot = (m_var == WallVariant::ChildrenReversed) ? (7 - k) : k;
        const u16 child = tree->mChild[slot];
        if (child != 0xFFFF && rp(acch, child)) {
            ret = true;
        }
    }
    return ret;
}

/// dBgW::WallCorrectGrpRp (d_bg_w.cpp:357-380).
bool WallWalk::grp_rp(dBgS_Acch* acch, int grp_id, int depth) {
    if (m_w.ChkGrpThrough(grp_id, acch->GetGrpPassChk(), depth)) {
        return false;
    }
    if (!m_w.pm_grp[grp_id].aab.Cross(acch->GetWallBmdCylP())) {
        return false;
    }

    bool ret = false;
    u32 tree_idx = m_w.pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree_idx != 0xFFFF && rp(acch, (int)tree_idx)) {
        ret = true;
    }

    depth++;
    s32 child_idx = m_w.pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF) {
            break;
        }
        if (grp_rp(acch, child_idx, depth)) {
            ret = true;
        }
        child_idx = m_w.pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }

    return ret;
}

// ------------------------------------------------------------------------------ the caller

/// `Room::WallCorrect`'s acch setup, replicated (see the header).
bool WallWalk::run(cXyz* pos, const cXyz& old_pos, f32 speed_y, const Room::WallCyl* cyls,
                   int tbl_size, Room::WallResult* out, const Room::LineResult* latch) {
    if (tbl_size < 0 || tbl_size > kMaxWallCyl) {
        std::fprintf(stderr, "WallWalk::run: tbl_size %d is outside 0..%d\n", tbl_size,
                     kMaxWallCyl);
        std::abort();
    }
    if (m_trace != nullptr) {
        m_trace->clear();
    }
    m_degenerate = 0;

    dBgS_AcchCir cir[kMaxWallCyl];
    dBgS_LinkAcch acch;

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
    acch.field_0x78 = &m_w;
    acch.m_ap_id = (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
    acch.m_ground_up_h = 0.0f;
    acch.m_ground_up_h_diff = 0.0f;
    acch.m_ground_h = 0.0f;
    acch.m_ground_check_offset = 0.0f;

    acch.m_pla.mNormal.x = 0.0f;
    acch.m_pla.mNormal.y = 0.0f;
    acch.m_pla.mNormal.z = 0.0f;
    acch.m_pla.mD = 0.0f;

    cXyz speed;
    speed.x = 0.0f;
    speed.y = speed_y;
    speed.z = 0.0f;
    acch.pm_speed = &speed;

    for (int i = 0; i < tbl_size; i++) {
        cir[i].SetWall(cyls[i].h, cyls[i].r);
    }

    // What a line check left, seeded after SetWall as Room::WallCorrect does.
    if (latch != nullptr) {
        for (int i = 0; i < tbl_size; i++) {
            if (latch->whd_set[i]) {
                cir[i].SetWallHDirect(latch->whd[i]);
            }
        }
    }

    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    acch.SetPolyPassChk(&poly_pass);
    acch.SetGrpPassChk(&grp_pass);

    acch.CalcWallRR();
    acch.SetWallCir();
    acch.SetLin();
    acch.CalcWallBmdCyl();

    grp_rp(&acch, m_w.m_rootGrpIdx, 1);

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

}  // namespace testing
}  // namespace tww_engine
