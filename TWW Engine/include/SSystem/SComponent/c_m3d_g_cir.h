// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_cir.h - cM2dGCir and cM3dGCir (c_m3d_g_cir.h:6-23, 27-37).
// dBgS_AcchCir::SetCir passes (x, z, y + wall height, r), so mPosY holds z and mPosZ the
// height.

#ifndef TWW_PORT_C_M3D_G_CIR_H
#define TWW_PORT_C_M3D_G_CIR_H

#include "global.h"
#include "dolphin/types.h"

class cM2dGCir {
public:
    f32 mPosX;
    f32 mPosY;
    f32 mRadius;
    
    f32 GetCx() const { return mPosX; }
    f32 GetCy() const { return mPosY; }
    f32 GetR() const { return mRadius; }
    void Set(f32 x, f32 y, f32 r) {
        mPosX = x;
        mPosY = y;
        mRadius = r;
    }

    cM2dGCir() {}
    virtual ~cM2dGCir() {}
};  // Size: 0x10

class cM3dGCir : public cM2dGCir {
    f32 mPosZ;

public:
    cM3dGCir() {}
    virtual ~cM3dGCir() {}
    void Set(f32 x, f32 y, f32 z, f32 r) {
        cM2dGCir::Set(x, y, r);
        mPosZ = z;
    }
};  // Size: 0x14

#endif
