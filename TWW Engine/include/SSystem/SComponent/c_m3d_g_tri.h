// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_tri.h - cM3dGTri, trimmed to what cBgW::RwgLineCheck uses (c_m3d_g_tri.h:15-20,
// 23, 27-29, 49-54).

#ifndef TWW_PORT_C_M3D_G_TRI_H
#define TWW_PORT_C_M3D_G_TRI_H

#include "dolphin/types.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_pla.h"

class cM3dGTri : public cM3dGPla {
public:
    /* 0x00 */ /* cM3dGPla */
    /* 0x14 */ Vec mA;
    /* 0x20 */ Vec mB;
    /* 0x2C */ Vec mC;

    cM3dGTri() {}

    bool cross(const cM3dGLin* line, Vec* vec, bool param_3, bool param_4) const {
        return cM3d_Cross_LinTri(line, this, vec, param_3, param_4);
    }

    void setBg(const Vec* a, const Vec* b, const Vec* c, const cM3dGPla* pla) {
        mA = *a;
        mB = *b;
        mC = *c;
        Set(pla);
    }
};

#endif
