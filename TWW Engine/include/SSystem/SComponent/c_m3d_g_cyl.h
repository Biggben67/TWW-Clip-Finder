// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_cyl.h - cM3dGCyl, trimmed (c_m3d_g_cyl.h:17-22, 24-36, 65-71). Its centre is the
// bottom, not the middle.

#ifndef TWW_PORT_C_M3D_G_CYL_H
#define TWW_PORT_C_M3D_G_CYL_H

#include "global.h"
#include "dolphin/types.h"

class cM3dGCyl {
public:
    /* 0x00 */ cXyz mCenter;
    /* 0x0C */ f32 mRadius;
    /* 0x10 */ f32 mHeight;
    /* 0x14 */ /* vtable */

public:
    cM3dGCyl() {}
    cM3dGCyl(const cXyz*, f32, f32);
    virtual ~cM3dGCyl() {}
#if VERSION == VERSION_DEMO
    void SetC(const cXyz& pos) { mCenter = pos; }
    void SetH(f32 h) { mHeight = h; }
    void SetR(f32 r) { mRadius = r; }
#else
    void SetC(const cXyz& pos);
    void SetH(f32 h);
    void SetR(f32 r);
#endif

    cXyz& GetC() { return mCenter; }
    const cXyz& GetC() const { return mCenter; }
    cXyz* GetCP() { return &mCenter; }
    const cXyz* GetCP() const { return &mCenter; }
    f32 GetR() const { return mRadius; }
    f32* GetRP() { return &mRadius; }
    f32 GetH() const { return mHeight; }
};

#endif
