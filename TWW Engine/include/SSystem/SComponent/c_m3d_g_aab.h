// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_aab.h - cM3dGAab, trimmed to what the octree walks use (c_m3d_g_aab.h:10-32,
// 42-44, 48-50, 55-62, 93-113).

#ifndef TWW_PORT_C_M3D_G_AAB_H
#define TWW_PORT_C_M3D_G_AAB_H

#include "dolphin/types.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_lin.h"

class cM3dGAab {
private:
    /* 0x00 */ cXyz mMin;
    /* 0x0C */ cXyz mMax;
    /* 0x18 */ /* vtable */

public:
    virtual ~cM3dGAab() {}
    void SetMinMax(const cXyz&);
    void SetMinMax(const cM3dGAab& aab) {
        SetMinMax(aab.mMin);
        SetMinMax(aab.mMax);
    }
    void Set(const cXyz* min, const cXyz* max) {
        mMin = *min;
        mMax = *max;
    }
    void SetMin(const cXyz&);
    void SetMax(const cXyz&);
    const cXyz* GetMaxP() const { return &mMax; }
    const cXyz* GetMinP() const { return &mMin; }
    cXyz* GetMaxP() { return &mMax; }
    cXyz* GetMinP() { return &mMin; }

    bool Cross(const cM3dGCyl *cyl) {
        return cM3d_Cross_AabCyl(this, cyl);
    }

    bool Cross(const cM3dGLin *lin) {
        return cM3d_Cross_MinMaxBoxLine(GetMinP(), GetMaxP(), lin->GetStartP(), lin->GetEndP());
    }

    void ClearForMinMax() {
        mMin.z = G_CM3D_F_INF;
        mMin.y = G_CM3D_F_INF;
        mMin.x = G_CM3D_F_INF;
        mMax.z = -G_CM3D_F_INF;
        mMax.y = -G_CM3D_F_INF;
        mMax.x = -G_CM3D_F_INF;
    }

    bool CrossY(const cXyz* v) const {
        if (mMin.x > v->x || mMax.x < v->x || mMin.z > v->z || mMax.z < v->z) {
            return false;
        } else {
            return true;
        }
    }
    bool UnderPlaneYUnder(f32 y) const {
        if (mMin.y < y) {
            return true;
        } else {
            return false;
        }
    }
    bool TopPlaneYUnder(f32 y) const {
        if (mMax.y < y) {
            return true;
        } else {
            return false;
        }
    }
};

#endif
