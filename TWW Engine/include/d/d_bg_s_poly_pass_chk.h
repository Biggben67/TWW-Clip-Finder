// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_poly_pass_chk.h - cBgS_PolyPassChk and dBgS_PolyPassChk, whole
// (d_bg_s_poly_pass_chk.h:6-17, 19-51).

#ifndef TWW_PORT_D_BG_S_POLY_PASS_CHK_H
#define TWW_PORT_D_BG_S_POLY_PASS_CHK_H

#include "dolphin/types.h"

class cBgS_PolyPassChk {
public:
    virtual ~cBgS_PolyPassChk() {}

    /* 0x4 */ bool mbObjThrough;
    /* 0x5 */ bool mbCamThrough;
    /* 0x6 */ bool mbLinkThrough;
    /* 0x7 */ bool mbArrowThrough; // Also light
    /* 0x8 */ bool mbBombThrough;
    /* 0x9 */ bool mbBoomerangThrough;
    /* 0xA */ bool mbRopeThrough; // Actually Hookshot?
};

class dBgS_PolyPassChk : public cBgS_PolyPassChk {
public:
    dBgS_PolyPassChk() {
        mbObjThrough = false;
        mbCamThrough = false;
        mbLinkThrough = false;
        mbArrowThrough = false;
        mbBombThrough = false;
        mbBoomerangThrough = false;
        mbRopeThrough = false;
    }
    virtual ~dBgS_PolyPassChk() {}

    void SetObj() { mbObjThrough = true; }
    void SetCam() { mbCamThrough = true; }
    void SetLink() { mbLinkThrough = true; }
    void SetArrow() { mbArrowThrough = true; }
    void SetBomb() { mbBombThrough = true; }
    void SetBoomerang() { mbBoomerangThrough = true; }
    void SetRope() { mbRopeThrough = true; }

    void ClrObj() { mbObjThrough = false; }
    void ClrCam() { mbCamThrough = false; }
    void ClrLink() { mbLinkThrough = false; }
    void ClrArrow() { mbArrowThrough = false; }
    void ClrBomb() { mbBombThrough = false; }
    void ClrBoomerang() { mbBoomerangThrough = false; }
    void ClrRope() { mbRopeThrough = false; }
    
    void SetPassChkInfo(dBgS_PolyPassChk& other) {
        *this = other;
    }
};

#endif
