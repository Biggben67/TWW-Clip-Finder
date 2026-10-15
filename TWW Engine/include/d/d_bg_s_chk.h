// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_chk.h - dBgS_Chk, whole (d_bg_s_chk.h:7-14).

#ifndef TWW_PORT_D_BG_S_CHK_H
#define TWW_PORT_D_BG_S_CHK_H

#include "d/d_bg_s_grp_pass_chk.h"
#include "d/d_bg_s_poly_pass_chk.h"

class dBgS_Chk : public dBgS_PolyPassChk, public dBgS_GrpPassChk {
public:
    dBgS_Chk() {}
    dBgS_PolyPassChk* GetPolyPassChkInfo() { return (dBgS_PolyPassChk*)this; }
    dBgS_GrpPassChk* GetGrpPassChkInfo() { return (dBgS_GrpPassChk*)this; }

    virtual ~dBgS_Chk() {}
};  // Size: 0x14

#endif
