// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_pla.h - cM3dGPla, trimmed (c_m3d_g_pla.h:10-13, 25-27, 29-31, 32-38, 39-41,
// 42-48, 52-55, 59-61).

#ifndef TWW_PORT_C_M3D_G_PLA_H
#define TWW_PORT_C_M3D_G_PLA_H

#include "dolphin/types.h"
#include "SSystem/SComponent/c_m3d.h"

class cM3dGPla {
public:
    /* 0x00 */ cXyz mNormal;
    /* 0x0C */ f32 mD;

    f32 getPlaneFunc(const Vec *p) const {
        return mD + VECDotProduct(&mNormal, p);
    }

    cXyz* GetNP() { return &mNormal; }
    const cXyz* GetNP() const { return &mNormal; }
    f32 GetD() const { return mD; }

    bool getCrossY(const cXyz& i_axis, f32* i_value) const {
        if (cM3d_IsZero(mNormal.y)) {
            return false;
        }
        *i_value = (-mNormal.x * i_axis.x - mNormal.z * i_axis.z - mD) / mNormal.y;
        return true;
    }

    f32 getCrossY_NonIsZero(const cXyz& i_axis) const {
        return (-mNormal.x * i_axis.x - mNormal.z * i_axis.z - mD) / mNormal.y;
    }

    bool getCrossYLessD(const Vec& i_axis, f32* i_value) const {
        if (cM3d_IsZero(mNormal.y)) {
            return false;
        }
        *i_value = (-mNormal.x * i_axis.x - mNormal.z * i_axis.z) / mNormal.y;
        return true;
    }

    void Set(const cM3dGPla* pla) {
        mNormal = *pla->GetNP();
        mD = pla->GetD();
    }

    bool cross(const cM3dGLin& line, Vec& point) const {
        return cM3d_Cross_LinPla(&line, this, &point, true, true);
    }
};

#endif
