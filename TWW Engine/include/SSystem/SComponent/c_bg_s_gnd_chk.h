// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_gnd_chk.h - cBgS_GndChk, trimmed (c_bg_s_gnd_chk.h:8-13, 22-28, 30-35). mNowY is
// the running maximum: the ground check takes the highest floor, not the first hit.

#ifndef TWW_PORT_C_BG_S_GND_CHK_H
#define TWW_PORT_C_BG_S_GND_CHK_H

#include "SSystem/SComponent/c_bg_s_chk.h"
#include "SSystem/SComponent/c_bg_s_poly_info.h"
#include "dolphin/types.h"

class cBgS_GndChk : public cBgS_Chk, public cBgS_PolyInfo {
public:
    cBgS_GndChk();
    void SetPos(cXyz* pos) {
        m_pos = *pos;
    }

    f32 GetNowY() const { return mNowY; }
    void SetNowY(f32 y) { mNowY = y; }
    cXyz* GetPointP() { return &m_pos; }
    u32 GetGndPrecheck() const { return mGndPrecheck; }
    u32 GetWallPrecheck() const { return mWallPrecheck; }
    void OffWall() { mFlag &= ~2; }
    void PreCheck() {}

public:
    /* 0x24 */ cXyz m_pos;
    /* 0x30 */ u32 mFlag;
    /* 0x34 */ f32 mNowY;
    /* 0x38 */ u32 mWallPrecheck;
    /* 0x3C */ u32 mGndPrecheck;
};

#endif
