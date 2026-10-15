// Camera sphere clearance and traversal ported from the JP TWW decomp.
#include <algorithm>
#include <cmath>
#include "d/d_camera.h"
#include "d/actor/d_a_player_main.h"
#include "d/d_bg_s.h"
#include "d/d_bg_s_sph_chk.h"
#include "SSystem/SComponent/c_m3d_g_tri.h"
#include "boundary/game_boundary.h"

namespace {
f32 component(const Vec& point, int axis) {
    return axis==0 ? point.x : axis==1 ? point.y : point.z;
}

f32 signedLength(const cM3dGPla& plane, const Vec& point) {
    const f32 length=VECMag(plane.GetNP());
    return cM3d_IsZero(length) ? 0.0f : plane.getPlaneFunc(&point)/length;
}

bool inBounds(f32 a, f32 b, f32 c, f32 point, f32 margin) {
    return std::min({a,b,c})-margin<=point && std::max({a,b,c})+margin>=point;
}

bool projectedInside(const cM3dGTri& tri, const Vec& point, int axis) {
    if (cM3d_IsZero(component(*tri.GetNP(),axis))) return false;
    const int u=(axis+1)%3, v=(axis+2)%3;
    const f32 a[]={tri.mA.x,tri.mA.y,tri.mA.z};
    const f32 b[]={tri.mB.x,tri.mB.y,tri.mB.z};
    const f32 c[]={tri.mC.x,tri.mC.y,tri.mC.z};
    const f32 p[]={point.x,point.y,point.z};
    if (!inBounds(a[u],b[u],c[u],p[u],0.0f) || !inBounds(a[v],b[v],c[v],p[v],0.0f)) return false;
    const f32 ab=cM3d_VectorProduct2d(a[u],a[v],b[u],b[v],p[u],p[v]);
    const f32 bc=cM3d_VectorProduct2d(b[u],b[v],c[u],c[v],p[u],p[v]);
    const f32 ca=cM3d_VectorProduct2d(c[u],c[v],a[u],a[v],p[u],p[v]);
    return (ab<=0.0f && bc<=0.0f && ca<=0.0f) || (ab>=0.0f && bc>=0.0f && ca>=0.0f);
}

bool edgeCross(const Vec& start, const Vec& end, const dBgS_SphChk& sphere) {
    const Vec& center=sphere.mCenter;
    for (int i=0;i<3;++i) {
        const f32 c=component(center,i), a=component(start,i), b=component(end,i);
        if ((c+sphere.mRadius<a && c+sphere.mRadius<b) ||
            (c-sphere.mRadius>a && c-sphere.mRadius>b)) return false;
    }
    Vec line, delta;
    VECSubtract(&end,&start,&line);
    const f32 length=VECSquareMag(&line);
    if (cM3d_IsZero(length)) return false;
    VECSubtract(&center,&start,&delta);
    const f32 projection=VECDotProduct(&delta,&line)/length;
    const f32 radius2=sphere.mRadius*sphere.mRadius;
    if (projection<0.0f || projection>1.0f) {
        const Vec& nearest=VECSquareDistance(&start,&center)<VECSquareDistance(&end,&center) ? start : end;
        return VECSquareDistance(&nearest,&center)<=radius2;
    }
    Vec scaled, closest;
    VECScale(&line,&scaled,projection);
    VECAdd(&scaled,&start,&closest);
    return VECSquareDistance(&closest,&center)<=radius2;
}

struct CameraMargin {
    f32 radius;
    cXyz corrected;
    cXyz gaze;
};

void sphereCallback(dBgS_SphChk*, cBgD_Vtx_t*, int, int, int, cM3dGPla* plane, void* data) {
    auto& margin=*static_cast<CameraMargin*>(data);
    const f32 length=signedLength(*plane,margin.corrected);
    if (plane->getPlaneFunc(&margin.gaze)>=-0.0001f && length<margin.radius) {
        const cXyz normal=*plane->GetNP();
        margin.corrected+=normal*(margin.radius-length);
    }
}
}

bool dBgS_SphChk::crossBox(const cM3dGAab& box) const {
    const Vec& low=*box.GetMinP(); const Vec& high=*box.GetMaxP();
    for (int axis : {0,2,1}) {
        const f32 center=component(mCenter,axis);
        if (component(low,axis)>center+mRadius || component(high,axis)<center-mRadius) return false;
    }
    return true;
}

bool dBgS_SphChk::cross(const cM3dGTri* tri) const {
    for (int axis : {0,2,1}) {
        if (!inBounds(component(tri->mA,axis),component(tri->mB,axis),component(tri->mC,axis),component(mCenter,axis),mRadius)) return false;
    }
    const f32 distance=signedLength(*tri,mCenter);
    if (std::fabs(distance)>mRadius) return false;
    Vec scaled, point;
    VECScale(tri->GetNP(),&scaled,distance);
    VECSubtract(&mCenter,&scaled,&point);
    const int axis=std::fabs(tri->GetNP()->y)>0.5f ? 1 : std::fabs(tri->GetNP()->x)>0.5f ? 0 : 2;
    if (projectedInside(*tri,point,axis)) return true;
    return edgeCross(tri->mA,tri->mB,*this) || edgeCross(tri->mB,tri->mC,*this) || edgeCross(tri->mC,tri->mA,*this);
}

bool dBgW::RwgSphChk(u16 index, dBgS_SphChk* query, void* data) {
    bool hit=false;
    while (true) {
        const auto& rwg=pm_rwg[index];
        if (!ChkPolyThrough(index,query->GetPolyPassChk())) {
            const auto& face=pm_bgd->m_t_tbl[index];
            auto& plane=pm_tri[index].m_plane;
            cM3dGTri tri;
            tri.setBg(&pm_vtx_tbl[face.vtx0],&pm_vtx_tbl[face.vtx1],&pm_vtx_tbl[face.vtx2],&plane);
            if (query->cross(&tri)) {
                if (query->mpCallback) query->mpCallback(query,pm_vtx_tbl,face.vtx0,face.vtx1,face.vtx2,&plane,data);
                query->SetPolyIndex(index);
                hit=true;
            }
        }
        if (rwg.next==0xffff) break;
        index=rwg.next;
    }
    return hit;
}

bool dBgW::SphChkRp(dBgS_SphChk* query, void* data, int index) {
    if (!query->crossBox(m_nt_tbl[index])) return false;
    const auto& tree=pm_bgd->m_tree_tbl[index];
    bool hit=false;
    if (tree.mFlag&1) {
        const auto& block=pm_blk[tree.mBlock];
        // Console callback order matters: each correction feeds the next plane.
        for (u16 head : {block.ground,block.roof,block.wall}) {
            if (head!=0xffff && RwgSphChk(head,query,data)) hit=true;
        }
    } else {
        for (u16 child : tree.mChild) {
            if (child!=0xffff && SphChkRp(query,data,child)) hit=true;
        }
    }
    return hit;
}

bool dBgW::SphChkGrpRp(dBgS_SphChk* query, void* data, int index, int depth) {
    if (ChkGrpThrough(index,query->GetGrpPassChk(),depth) || !query->crossBox(pm_grp[index].aab)) return false;
    const auto& group=pm_bgd->m_g_tbl[index];
    bool hit=group.m_tree_idx!=0xffff && SphChkRp(query,data,group.m_tree_idx);
    for (u16 child=group.m_first_child;child!=0xffff;child=pm_bgd->m_g_tbl[child].m_next_sibling) {
        if (SphChkGrpRp(query,data,child,depth+1)) hit=true;
    }
    return hit;
}

bool dBgS::SphChk(dBgS_SphChk* query, void* data) {
    query->Init();
    bool hit=false;
    for (int i=0;i<256;++i) {
        auto& element=m_chk_element[i];
        if (!element.ChkUsed() || !element.m_bgw_base_ptr->GetVtxTbl() || query->ChkSameActorPid(element.m_actor_id)) continue;
        auto& world=*static_cast<dBgW*>(element.m_bgw_base_ptr);
        if (world.SphChkGrpRp(query,data,world.m_rootGrpIdx,1)) {
            query->SetActorInfo(i,&world,element.m_actor_id);
            hit=true;
        }
    }
    return hit;
}

cXyz dCamera_c::compWallMargin(cXyz* center, f32 radius) {
    dBgS_CamSphChk query;
    CameraMargin margin{radius,*center,mViewCache.mCenter};
    query.SetCallback(sphereCallback);
    query.Set(*center,radius);
    return dComIfG_Bgsp()->SphChk(&query,&margin) ? margin.corrected : *center;
}
