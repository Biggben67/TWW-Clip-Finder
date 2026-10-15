#ifndef TWW_PORT_D_BG_S_SPH_CHK_H
#define TWW_PORT_D_BG_S_SPH_CHK_H

#include "SSystem/SComponent/c_bg_s_poly_info.h"
#include "SSystem/SComponent/c_bg_w.h"
#include "d/d_bg_s_chk.h"

// The sphere-query subset used by the console camera clearance pass.
class dBgS_SphChk : public cBgS_PolyInfo, public cBgS_Chk, public dBgS_Chk {
public:
    typedef void (*SphChk_Callback)(dBgS_SphChk*, cBgD_Vtx_t*, int, int, int, cM3dGPla*, void*);
    dBgS_SphChk() {
        SetPolyPassChk(GetPolyPassChkInfo());
        SetGrpPassChk(GetGrpPassChkInfo());
        SetActorPid(fpcM_ERROR_PROCESS_ID_e);
        Init();
    }
    virtual ~dBgS_SphChk() {}
    void Init() { ClearPi(); }
    void Set(const cXyz& center, f32 radius) { mCenter=center; mRadius=radius; }
    void SetCallback(SphChk_Callback callback) { mpCallback=callback; }
    bool cross(const cM3dGTri*) const;
    bool crossBox(const cM3dGAab&) const;
    cXyz mCenter;
    f32 mRadius=0.0f;
    SphChk_Callback mpCallback=nullptr;
};

class dBgS_CamSphChk : public dBgS_SphChk {
public:
    dBgS_CamSphChk() { SetCam(); }
};

#endif
