// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_gnd_chk.h - dBgS_GndChk, dBgS_LinkGndChk, dBgS_CamGndChk and dBgS_CamGndChk_Wtr
// (d_bg_s_gnd_chk.h:7-14, 18-22, 68-73, 75-83).

#ifndef TWW_PORT_D_BG_S_GND_CHK_H
#define TWW_PORT_D_BG_S_GND_CHK_H

#include "SSystem/SComponent/c_bg_s_gnd_chk.h"
#include "d/d_bg_s_chk.h"

class dBgS_GndChk : public cBgS_GndChk, public dBgS_Chk {
public:
    dBgS_GndChk() {
        SetPolyPassChk(GetPolyPassChkInfo());
        SetGrpPassChk(GetGrpPassChkInfo());
    }
    virtual ~dBgS_GndChk() {}
};  // Size: 0x54

class dBgS_LinkGndChk : public dBgS_GndChk {
public:
    dBgS_LinkGndChk() { SetLink(); }
    virtual ~dBgS_LinkGndChk() {}
};  // Size: 0x54

class dBgS_CamGndChk : public dBgS_GndChk {
public:
    dBgS_CamGndChk() { SetCam(); }

    virtual ~dBgS_CamGndChk() {}
};

class dBgS_CamGndChk_Wtr : public dBgS_CamGndChk {
public:
    dBgS_CamGndChk_Wtr() {
        OffNormalGrp();
        OnWaterGrp();
    };

    virtual ~dBgS_CamGndChk_Wtr() {}
};

#endif
