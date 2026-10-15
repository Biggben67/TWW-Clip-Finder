// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d.h - cM3d_IsZero, its constants, and the declarations and inlines the collision
// checks use (c_m3d.h:9, 11-13, 15, 21-26, 60-64, 66-68, 72, 74, 77-78, 83, 85, 87-88, 94,
// 96, 135-137, 143-148, 150-152, 154-162).

#ifndef TWW_PORT_C_M3D_H
#define TWW_PORT_C_M3D_H

#include "global.h"
#include "dolphin/types.h"
#include "engine/ps_vec.h"

#include <cmath>

class cM3dGAab;

class cM3dGCyl;
class cM3dGLin;
class cM3dGPla;

class cM3dGTri;

extern const f32 G_CM3D_F_ABS_MIN;
#if VERSION == VERSION_DEMO
extern const f32 G_CM3D_F_INF;
#else
#define G_CM3D_F_INF (1000000000.0f)
#endif

inline f32 cM3d_Len2dSq(f32 x0, f32 y0, f32 x1, f32 y1) {
    f32 x = x0 - x1;
    f32 y = y0 - y1;
    return x*x + y*y;
}

void cM3d_InDivPos1(const Vec*, const Vec*, f32, Vec*);
void cM3d_InDivPos2(const Vec*, const Vec*, f32, Vec*);
bool cM3d_Len2dSqPntAndSegLine(f32, f32, f32, f32, f32, f32, f32*, f32*, f32*);

void cM3d_CalcPla(const Vec*, const Vec*, const Vec*, Vec*, f32*);

bool cM3d_Cross_AabCyl(const cM3dGAab*, const cM3dGCyl*);

bool cM3d_Cross_LinPla(const cM3dGLin*, const cM3dGPla*, Vec*, bool, bool);
bool cM3d_Cross_MinMaxBoxLine(const Vec*, const Vec*, const Vec*, const Vec*);

bool cM3d_CrossX_Tri(const cM3dGTri*, const Vec*);

bool cM3d_CrossY_Tri(const cM3dGTri*, const Vec*);

bool cM3d_CrossY_Tri(const Vec&, const Vec&, const Vec&, const cM3dGPla&, const Vec*);
bool cM3d_CrossY_Tri_Front(const Vec&, const Vec&, const Vec&, const Vec*);

bool cM3d_CrossZ_Tri(const cM3dGTri*, const Vec*);

bool cM3d_Cross_LinTri(const cM3dGLin*, const cM3dGTri*, Vec*, bool, bool);

inline bool cM3d_IsZero(f32 f) {
    return std::fabs(f) < G_CM3D_F_ABS_MIN;
}

inline void cM3d_VectorProduct(const Vec* p0, const Vec* p1, const Vec* p2, Vec* pDst) {
    Vec v01, v02;
    VECSubtract(p1, p0, &v01);
    VECSubtract(p2, p0, &v02);
    VECCrossProduct(&v01, &v02, pDst);
}

inline f32 cM3d_VectorProduct2d(f32 pX1, f32 pY1, f32 pX2, f32 pY2, f32 pX3, f32 pY3) {
    return (pX2 - pX1) * (pY3 - pY1) - (pY2 - pY1) * (pX3 - pX1);
}

inline bool cM3d_CrossInfLineVsInfPlane_proc(f32 a, f32 b, const Vec* pA, const Vec* pB, Vec* pDst) {
    if (cM3d_IsZero(a - b)) {
        *pDst = *pB;
        return false;
    } else {
        cM3d_InDivPos2(pA, pB, a / (a - b), pDst);
        return true;
    }
}

#endif
