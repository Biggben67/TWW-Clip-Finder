// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_cyl.cpp - the CHECK_* macros and SetC / SetH / SetR (c_m3d_g_cyl.cpp:10-11,
// 13-36).

#include "SSystem/SComponent/c_m3d_g_cyl.h"

#include <math.h>   // unqualified isnan - see d_bg_w.cpp

#include "SSystem/SComponent/c_m3d.h"
#include "engine/jut_assert.h"

#define CHECK_FLOAT_RANGE(line, x) JUT_ASSERT(line, -1.0e32f < x && x < 1.0e32f);
#define CHECK_VEC3_RANGE(line, v) JUT_ASSERT(line, -1.0e32f < v.x && v.x < 1.0e32f && -1.0e32f < v.y && v.y < 1.0e32f && -1.0e32f < v.z && v.z < 1.0e32f)

#if VERSION > VERSION_DEMO
/* 80251D88-80252020       .text SetC__8cM3dGCylFRC4cXyz */
void cM3dGCyl::SetC(const cXyz& pos) {
    JUT_ASSERT(21, !isnan(pos.x));
    JUT_ASSERT(22, !isnan(pos.y));
    JUT_ASSERT(23, !isnan(pos.z));
    CHECK_VEC3_RANGE(26, pos);
    mCenter = pos;
}

/* 80252020-8025214C       .text SetH__8cM3dGCylFf */
void cM3dGCyl::SetH(f32 h) {
    JUT_ASSERT(36, !isnan(h));
    CHECK_FLOAT_RANGE(37, h);
    mHeight = h;
}

/* 8025214C-80252278       .text SetR__8cM3dGCylFf */
void cM3dGCyl::SetR(f32 r) {
    JUT_ASSERT(48, !isnan(r));
    CHECK_FLOAT_RANGE(49, r);
    mRadius = r;
}
#endif
