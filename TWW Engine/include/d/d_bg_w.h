// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_w.h - dBgW, trimmed to the wall pass, the roof walk, the two refusals and the
// object's fields (d_bg_w.h:7, 8, 9, 10, 14-15, 19-20, 21-31, 33, 36-42, 45, 58-59, 61-62,
// 110-117).
// ChkShdwDrawThrough (60) is left out, so the vtable is not the console's layout.

#ifndef TWW_PORT_D_BG_W_H
#define TWW_PORT_D_BG_W_H

#include "SSystem/SComponent/c_bg_w.h"

class dBgS_Acch;

class cM3dGPla;

class dBgS_RoofChk;

class dBgS_SplGrpChk;
class dBgS_SphChk;

class cBgS_PolyInfo;
class fopAc_ac_c;

class dBgW : public cBgW {
public:

    enum PushPullLabel {
        PPLABEL_NONE = 0x00,
        PPLABEL_PUSH = 0x01,
        PPLABEL_PULL = 0x02,
        PPLABEL_UNK4 = 0x04,
        PPLABEL_HEAVY = 0x08,
    };
    
    typedef void (*dBgW_CrrFunc)(dBgW*, void*, cBgS_PolyInfo&, bool, cXyz*, csXyz*, csXyz*);
    typedef void (*dBgW_RideCallBack)(dBgW*, fopAc_ac_c*, fopAc_ac_c*);
    typedef fopAc_ac_c* (*dBgW_PPCallBack)(fopAc_ac_c*, fopAc_ac_c*, s16, dBgW::PushPullLabel);

    dBgW();

    void positionWallCorrect(dBgS_Acch*, f32, cM3dGPla&, cXyz*, f32);
    bool RwgWallCorrect(dBgS_Acch*, u16);
    bool WallCorrectRp(dBgS_Acch*, int);
    bool WallCorrectGrpRp(dBgS_Acch*, int, int);
    bool RwgRoofChk(u16, dBgS_RoofChk*);
    bool RoofChkRp(dBgS_RoofChk*, int);
    bool RoofChkGrpRp(dBgS_RoofChk*, int, int);

    bool SplGrpChkGrpRp(dBgS_SplGrpChk*, int, int);
    bool RwgSphChk(u16, dBgS_SphChk*, void*);
    bool SphChkRp(dBgS_SphChk*, void*, int);
    bool SphChkGrpRp(dBgS_SphChk*, void*, int, int);

    virtual ~dBgW() {}
    virtual bool ChkPolyThrough(int, cBgS_PolyPassChk*);

    virtual bool ChkGrpThrough(int, cBgS_GrpPassChk*, int);
    virtual void CrrPos(cBgS_PolyInfo&, void*, bool, cXyz*, csXyz*, csXyz*);

    /* 0xA8 */ dBgW_CrrFunc m_crr_func;
    /* 0xAC */ s16 mOldRotY;
    /* 0xAE */ s16 mRotYDelta;
    /* 0xB0 */ dBgW_RideCallBack mpRideCb;
    /* 0xB4 */ dBgW_PPCallBack mpPushPullCb;
    /* 0xB8 */ u16 mRoomNo;
    /* 0xBA */ u8 mFlag;
    /* 0xBB */ u8 mRoomNo2;
};

#endif
