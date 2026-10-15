// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_roof_chk.h - dBgS_RoofChk, trimmed (d_bg_s_roof_chk.h:9-19, 24-27, 29-32). m_now_y
// is the running minimum.
// The poly info is this class's first base and cBgS_GndChk's second, so its index is at
// +0x00 here and +0x14 there.

#ifndef TWW_PORT_D_BG_S_ROOF_CHK_H
#define TWW_PORT_D_BG_S_ROOF_CHK_H

#include "SSystem/SComponent/c_bg_s_chk.h"
#include "SSystem/SComponent/c_bg_s_poly_info.h"
#include "d/d_bg_s_chk.h"
#include "dolphin/types.h"

class dBgS_RoofChk : public cBgS_PolyInfo, public cBgS_Chk, public dBgS_Chk {
public:
    dBgS_RoofChk() {
        SetPolyPassChk(GetPolyPassChkInfo());
        SetGrpPassChk(GetGrpPassChkInfo());
        m_pos.x = 0.0f;
        m_pos.y = 0.0f;
        m_pos.z = 0.0f;
        SetActorPid(fpcM_ERROR_PROCESS_ID_e);
        field_0x44 = NULL;
    }

    void SetPos(cXyz &pos) { m_pos = pos; }
    cXyz* GetPosP() { return &m_pos; }
    f32 GetNowY() { return m_now_y; }
    void SetNowY(f32 y) { m_now_y = y; }

private:
    /* 0x38 */ cXyz m_pos;
    /* 0x44 */ void* field_0x44;
    /* 0x48 */ f32 m_now_y;
};

#endif
