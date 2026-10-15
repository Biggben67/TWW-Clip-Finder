#include "line_walk.h"

#include <cmath>
#include <set>

#include "SSystem/SComponent/c_bg_s_lin_chk.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_tri.h"
#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"
#include "engine/ppc_fp.h"
#include "framework/require_bits.h"

namespace tww_engine {
namespace testing {

const f32 kLineWallH[3] = {30.1f, 89.9f, 125.0f};
const f32 kLineWallR = 35.0f;

namespace {
//: The old sim's G_CM3D_F_ABS_MIN; the console's is 2^-18.
const f32 kLegacyAbsMin = 1.0e-5f;

//: cM3d_Cross_LinTri's per-axis gate (c_m3d.cpp:1235-1237): a literal, not cM3d_IsZero.
//: `AxisIsZeroGate` swaps in the latter.
const f32 kAxisGate = 0.008f;
}  // namespace

bool LineWalk::is_zero(f32 v) const {
    if (m_var == LineVariant::LegacyIsZero) {
        return std::fabs(v) < kLegacyAbsMin;
    }
    return cM3d_IsZero(v);
}

/// cM3d_Cross_LinTri's per-axis skip: true skips that projection's triangle test.
bool LineWalk::axis_gate(f32 n) const {
    if (m_var == LineVariant::AxisIsZeroGate) {
        return cM3d_IsZero(n);
    }
    return std::fabs(n) < kAxisGate;
}

/// Records one offer; `crossed` and `refused` are the two halves of RwgLineCheck's `&&`.
void LineWalk::offer(int poly, bool crossed, bool refused) {
    if (m_offers == nullptr) {
        return;
    }
    LineOffer o;
    o.poly = poly;
    o.cyl = m_cyl;
    o.crossed = crossed;
    o.refused = refused;
    m_offers->push_back(o);
}

void LineWalk::step(int poly, int cyl, const cXyz* pos) {
    if (m_trace == nullptr) {
        return;
    }
    LineStep s;
    s.poly = poly;
    s.cyl = cyl;
    s.x_bits = bits(pos->x);
    s.y_bits = bits(pos->y);
    s.z_bits = bits(pos->z);
    m_trace->push_back(s);
}

// ------------------------------------------------------------------ the two primitives it calls

/// cM3d_Cross_LinPla (c_m3d.cpp:249-268), its IsZero (in cM3d_CrossInfLineVsInfPlane_proc) on
/// the variant's threshold. Front is `startVal >= 0 && endVal <= 0`; back is the other arm.
bool LineWalk::cross_lin_pla(const cM3dGLin* lin, const cM3dGPla* pla, Vec* dst, bool front,
                             bool back) {
    const f32 startVal = pla->getPlaneFunc(lin->GetStartP());
    const f32 endVal = pla->getPlaneFunc(lin->GetEndP());
    if (startVal * endVal > 0.0f) {
        *dst = lin->GetEnd();
        return false;
    }
    const bool take = (startVal >= 0.0f && endVal <= 0.0f) ? front : back;
    if (take) {
        // cM3d_CrossInfLineVsInfPlane_proc, c_m3d.h:154-162.
        if (is_zero(startVal - endVal)) {
            m_lin_pla_degenerate++;
            *dst = *lin->GetEndP();
            return false;
        }
        cM3d_InDivPos2(lin->GetStartP(), lin->GetEndP(), startVal / (startVal - endVal), dst);
        return true;
    }
    *dst = lin->GetEnd();
    return false;
}

/// cM3d_Cross_LinTri (c_m3d.cpp:1232-1244): the plane crossing, then the projected point-in-
/// triangle test in every projection whose normal component is significant.
bool LineWalk::cross_lin_tri(const cM3dGLin* lin, const cM3dGTri* tri, Vec* dst, bool front,
                             bool back) {
    if (!cross_lin_pla(lin, tri, dst, front, back)) {
        return false;
    }
    const bool ok = (axis_gate(tri->GetNP()->x) || cM3d_CrossX_Tri(tri, dst)) &&
                    (axis_gate(tri->GetNP()->y) || cM3d_CrossY_Tri(tri, dst)) &&
                    (axis_gate(tri->GetNP()->z) || cM3d_CrossZ_Tri(tri, dst));
    if (!ok) {
        m_plane_only++;
    }
    return ok;
}

// ------------------------------------------------------------------------------ the walk itself

/// cBgW::RwgLineCheck (c_bg_w.cpp:368-398). Shrinking the segment makes the answer the nearest
/// crossing.
bool LineWalk::rwg(u16 poly_index, cBgS_LinChk* chk) {
    bool ret = false;
    cM3dGTri gtri;
    cM3dGLin* lin = chk->GetLinP();
    while (true) {
        cBgD_Tri_t* tri = &m_w.pm_bgd->m_t_tbl[poly_index];
        cBgW_TriElm* tri_elm = &m_w.pm_tri[poly_index];
        gtri.setBg(&m_w.pm_vtx_tbl[tri->vtx0], &m_w.pm_vtx_tbl[tri->vtx1],
                   &m_w.pm_vtx_tbl[tri->vtx2], &tri_elm->m_plane);
        const bool backFlag = (m_var == LineVariant::TwoSided) ? true : chk->ChkBackFlag();
        const bool frontFlag = chk->ChkFrontFlag();

        m_offered++;
        cXyz pt;
        // One `&&` split in two, short-circuit order kept, so the offer log can name both.
        const bool crossed = cross_lin_tri(lin, &gtri, &pt, frontFlag, backFlag);
        const bool refused = crossed && m_w.ChkPolyThrough(poly_index, chk->GetPolyPassChk());
        offer(poly_index, crossed, refused);
        if (crossed && !refused) {
            m_crossed++;
            if (m_var != LineVariant::NoShrink) {
                chk->GetLinP()->SetEnd(pt);
            } else {
                // Keep the crossing so the last polygon offered wins instead of the nearest.
                m_last_pt = pt;
                m_last_pt_valid = true;
            }
            chk->SetPolyIndex(poly_index);
            ret = true;
        }

        if (m_w.pm_rwg[poly_index].next == 0xFFFF) {
            break;
        }
        poly_index = m_w.pm_rwg[poly_index].next;
    }
    return ret;
}

/// cBgW::LineCheckRp (c_bg_w.cpp:407-442). Three chains per leaf, not one.
bool LineWalk::rp(cBgS_LinChk* chk, int i) {
    cBgW_NodeTree* node = &m_w.m_nt_tbl[i];
    if (m_var != LineVariant::Flat &&
        !cM3d_Cross_MinMaxBoxLine(node->GetMinP(), node->GetMaxP(), chk->GetLinP()->GetStartP(),
                                  chk->GetLinP()->GetEndP())) {
        return false;
    }
    cBgD_Tree_t* tree = &m_w.pm_bgd->m_tree_tbl[i];
    bool ret = false;
    if (tree->mFlag & 1) {
        if (m_var != LineVariant::NoWallChain && chk->mPreWallChk &&
            m_w.pm_blk[tree->mBlock].wall != 0xFFFF &&
            rwg(m_w.pm_blk[tree->mBlock].wall, chk)) {
            ret = true;
        }
        if (m_var != LineVariant::NoGroundChain && chk->mPreGroundChk &&
            m_w.pm_blk[tree->mBlock].ground != 0xFFFF &&
            rwg(m_w.pm_blk[tree->mBlock].ground, chk)) {
            ret = true;
        }
        if (m_var != LineVariant::NoRoofChain && chk->mPreRoofChk &&
            m_w.pm_blk[tree->mBlock].roof != 0xFFFF &&
            rwg(m_w.pm_blk[tree->mBlock].roof, chk)) {
            ret = true;
        }
        return ret;
    }
    for (int k = 0; k < 8; k++) {
        const int child = (m_var == LineVariant::ChildrenReversed) ? (7 - k) : k;
        if (tree->mChild[child] != 0xFFFF && rp(chk, tree->mChild[child])) {
            ret = true;
        }
    }
    return ret;
}

/// cBgW::LineCheckGrpRp (c_bg_w.cpp:445-467).
bool LineWalk::grp_rp(cBgS_LinChk* chk, int grp_id, int depth) {
    if (m_w.ChkGrpThrough(grp_id, chk->GetGrpPassChk(), depth)) {
        return false;
    }
    if (m_var != LineVariant::Flat && !m_w.pm_grp[grp_id].aab.Cross(chk->GetLinP())) {
        return false;
    }
    bool ret = false;
    u16 tree = m_w.pm_bgd->m_g_tbl[grp_id].m_tree_idx;
    if (tree != 0xFFFF && rp(chk, tree)) {
        ret = true;
    }
    s32 child_idx = m_w.pm_bgd->m_g_tbl[grp_id].m_first_child;
    while (true) {
        if (child_idx == 0xFFFF) {
            break;
        }
        if (grp_rp(chk, child_idx, depth + 1)) {
            ret = true;
        }
        child_idx = m_w.pm_bgd->m_g_tbl[child_idx].m_next_sibling;
    }
    return ret;
}

/// cBgS::LineCross (c_bg_s.cpp:110-127), the registered-object loop collapsed to the room, as in
/// Room::LineCheck.
bool LineWalk::line_cross(cBgS_LinChk* chk) {
    chk->ClearPi();
    chk->ClrHit();
    chk->PreCalc();
    m_last_pt_valid = false;
    const bool ret = grp_rp(chk, m_w.m_rootGrpIdx, 1);
    if (ret && m_var == LineVariant::NoShrink && m_last_pt_valid) {
        chk->GetLinP()->SetEnd(m_last_pt);
    }
    if (ret) {
        chk->SetActorInfo(0, &m_w, (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e);
        chk->SetHit();
    }
    return ret;
}

bool LineWalk::run(cXyz* pos, const cXyz& old_pos, const Room::WallCyl* cyls, int tbl_size,
                   Room::LineResult* out) {
    // dBgS_Acch::Set, replicated; a drift from Room::LineCheck's setup shows as a red gate.
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
    acch.SetActorPid((fpc_ProcID)fpcM_ERROR_PROCESS_ID_e);
    for (int i = 0; i < tbl_size; i++) {
        cir[i].SetWall(cyls[i].h, cyls[i].r);
    }
    dBgS_PolyPassChk poly_pass;
    dBgS_GrpPassChk grp_pass;
    poly_pass.SetLink();
    acch.SetPolyPassChk(&poly_pass);
    acch.SetGrpPassChk(&grp_pass);
    acch.OffLineCheckHit();

    if (m_trace != nullptr) {
        m_trace->clear();
    }
    if (m_offers != nullptr) {
        m_offers->clear();
    }
    int ground_branch = 0;

    for (s32 i = 0; i < acch.m_tbl_size; i++) {
        m_cyl = i;
        cBgS_LinChk linChk;
        cXyz lin_old_pos = *acch.pm_old_pos;
        cXyz lin_pos = *acch.pm_pos;
        lin_old_pos.y += cir[i].GetWallH();
        lin_pos.y += cir[i].GetWallH();
        linChk.Set2(&lin_old_pos, &lin_pos, acch.GetActorPid());
        linChk.SetExtChk(acch);

        const bool crossed = line_cross(&linChk);
        if (crossed) {
            *acch.pm_pos = linChk.GetCross();
            acch.OnLineCheckHit();
            cM3dGPla* pla = m_w.GetTriPla(linChk.GetPolyIndex());
            if (!cBgW_CheckBGround(pla->GetNP()->y)) {
                VECAdd(acch.GetPos(), pla->GetNP(), acch.GetPos());
                if (!cM3d_IsZero(ppc::sqrtf_msl(pla->GetNP()->x * pla->GetNP()->x +
                                                pla->GetNP()->z * pla->GetNP()->z))) {
                    cir[i].SetWallHDirect(acch.pm_pos->y);
                }
                acch.pm_pos->y -= cir[i].GetWallH();
            } else {
                acch.pm_pos->y -= 1.0f;
                ground_branch++;
            }
            step(linChk.GetPolyIndex(), i, acch.pm_pos);
        }

        if (out != nullptr) {
            out->cir_hit[i] = crossed;
            out->cir_poly[i] = crossed ? linChk.GetPolyIndex() : 0xFFFF;
            out->whd_set[i] = cir[i].ChkWallHDirect();
            out->whd[i] = cir[i].GetWallHDirect();
        }
    }

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

// ---------------------------------------------------------------------------- the probe set

namespace {
//: Segment start along +normal and end along -normal. `stops_short` ends in front of the plane,
//: so it must never cross.
struct Reach {
    const char* name;
    f32 from;
    f32 to;
};
const Reach kFaceReach[] = {
    {"cross_mid", 40.0f, 40.0f},
    {"cross_short", 40.0f, 2.0f},
    {"graze", 3.0f, 40.0f},
    {"stops_short", 40.0f, -2.0f},
};
const Reach kCornerReach[] = {{"corner_cross", 40.0f, 40.0f}};
}  // namespace

std::vector<LineProbe> line_probe_set(const Room& room, const RoomDzb& dzb, int* flat_dropped) {
    std::vector<LineProbe> out;
    std::set<std::vector<u32> > seen;
    int dropped = 0;

    for (int b = 0; b < room.block_count(); b++) {
        std::vector<int> polys = room.wall_chain(b);
        const std::vector<int> g = room.ground_chain(b);
        polys.insert(polys.end(), g.begin(), g.end());
        const std::vector<int> r = room.roof_chain(b);
        polys.insert(polys.end(), r.begin(), r.end());

        for (int poly : polys) {
            const cXyz* n = room.bgw().pm_tri[poly].m_plane.GetNP();
            // Skip only zero normals; unlike the wall pass, floors are valid targets.
            const f32 nlen = ppc::sqrtf_msl(n->x * n->x + n->y * n->y + n->z * n->z);
            if (cM3d_IsZero(nlen)) {
                dropped++;
                continue;
            }
            const cBgD_Tri_t& t = dzb.t_tbl[poly];
            const cBgD_Vtx_t* v[3] = {&dzb.v_tbl[t.vtx0], &dzb.v_tbl[t.vtx1], &dzb.v_tbl[t.vtx2]};

            LineProbe p;
            p.of_poly = poly;

            const f32 cx = (v[0]->x + v[1]->x + v[2]->x) / 3.0f;
            const f32 cy = (v[0]->y + v[1]->y + v[2]->y) / 3.0f;
            const f32 cz = (v[0]->z + v[1]->z + v[2]->z) / 3.0f;
            for (const Reach& re : kFaceReach) {
                p.cls = re.name;
                // Aims the middle cylinder's line (LineCheck adds wall_h) at the centroid.
                p.old_pos.x = cx + n->x * re.from;
                p.old_pos.y = cy + n->y * re.from - kLineWallH[1];
                p.old_pos.z = cz + n->z * re.from;
                p.pos.x = cx - n->x * re.to;
                p.pos.y = cy - n->y * re.to - kLineWallH[1];
                p.pos.z = cz - n->z * re.to;
                std::vector<u32> key;
                key.push_back(bits(p.old_pos.x));
                key.push_back(bits(p.old_pos.y));
                key.push_back(bits(p.old_pos.z));
                key.push_back(bits(p.pos.x));
                key.push_back(bits(p.pos.y));
                key.push_back(bits(p.pos.z));
                if (seen.insert(key).second) {
                    out.push_back(p);
                }
            }
            for (int a = 0; a < 3; a++) {
                for (const Reach& re : kCornerReach) {
                    p.cls = re.name;
                    p.old_pos.x = v[a]->x + n->x * re.from;
                    p.old_pos.y = v[a]->y + n->y * re.from - kLineWallH[1];
                    p.old_pos.z = v[a]->z + n->z * re.from;
                    p.pos.x = v[a]->x - n->x * re.to;
                    p.pos.y = v[a]->y - n->y * re.to - kLineWallH[1];
                    p.pos.z = v[a]->z - n->z * re.to;
                    std::vector<u32> key;
                    key.push_back(bits(p.old_pos.x));
                    key.push_back(bits(p.old_pos.y));
                    key.push_back(bits(p.old_pos.z));
                    key.push_back(bits(p.pos.x));
                    key.push_back(bits(p.pos.y));
                    key.push_back(bits(p.pos.z));
                    if (seen.insert(key).second) {
                        out.push_back(p);
                    }
                }
            }
        }
    }
    if (flat_dropped != nullptr) {
        *flat_dropped = dropped;
    }
    return out;
}

}  // namespace testing
}  // namespace tww_engine
