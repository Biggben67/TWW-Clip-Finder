// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_lin_chk.h - dBgS_LinChk, dBgS_LinkLinChk and the camera line checks
// (d_bg_s_lin_chk.h:9-21, 23-28, 69-86).

#ifndef TWW_PORT_D_BG_S_LIN_CHK_H
#define TWW_PORT_D_BG_S_LIN_CHK_H

#include "SSystem/SComponent/c_bg_s_lin_chk.h"
#include "d/d_bg_s_chk.h"

class fopAc_ac_c;

class dBgS_LinChk : public cBgS_LinChk, public dBgS_Chk {
public:
    dBgS_LinChk() {
        SetPolyPassChk(GetPolyPassChkInfo());
        SetGrpPassChk(GetGrpPassChkInfo());
    }
    void Set(cXyz* pi_start, cXyz* pi_end, fopAc_ac_c* pi_actor);

    virtual ~dBgS_LinChk() {}

    /* 0x00 cBgS_LinChk */
    /* 0x58 dBgS_Chk */
};  // Size: 0x6C

class dBgS_LinkLinChk : public dBgS_LinChk {
public:
    dBgS_LinkLinChk() { SetLink(); }

    virtual ~dBgS_LinkLinChk() {}
};  // Size: 0x6C

class dBgS_CamLinChk : public dBgS_LinChk {
public:
    dBgS_CamLinChk() {
        mbCamThrough = true;
    }

    virtual ~dBgS_CamLinChk() {}
};

class dBgS_CamLinChk_NorWtr : public dBgS_CamLinChk {
public:
    dBgS_CamLinChk_NorWtr() {
        OnWaterGrp();
        OnNormalGrp();
    }

    virtual ~dBgS_CamLinChk_NorWtr() {}
};

#endif
