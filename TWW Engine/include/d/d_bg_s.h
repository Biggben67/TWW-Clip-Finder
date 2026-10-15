// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s.h - dBgS, trimmed (d_bg_s.h:14-26, 63-71, 78, 84-85, 88-118, 120-125).
// dBgS::Regist(cBgW*, fopAc_ac_c*) is declared only: its body reads the actor's shape
// angle.

#ifndef TWW_PORT_D_BG_S_H
#define TWW_PORT_D_BG_S_H

#include "SSystem/SComponent/c_bg_s.h"
#include "d/d_bg_s_chk.h"
#include "d/d_bg_w.h"
#include "dolphin/types.h"

class cBgS_LinChk;
class cBgS_GndChk;
class cBgS_PolyInfo;
class cM3dGPla;
class cBgS_ShdwDraw;
class dBgW;
class fopAc_ac_c;
class dBgS_Acch;
class dBgS_RoofChk;
class dBgS_SplGrpChk;
class dBgS_SphChk;

class dBgS_Acch;

class dBgS : public cBgS {
public:
    dBgS() {}
    virtual ~dBgS() {}

    bool WaterChk(dBgS_SplGrpChk* chk) { return SplGrpChk(chk); }
    fopAc_ac_c* GetActorPointer(cBgS_PolyInfo& i_poly) const {
        return cBgS::GetActorPointer(i_poly);
    }

    dBgW* GetBgWPointer(cBgS_PolyInfo& i_poly) { return (dBgW*)cBgS::GetBgWPointer(i_poly); }

    virtual void Ct();
    virtual void Dt();

    void ClrMoveFlag();
    bool Regist(cBgW*, fopAc_ac_c*);
    bool ChkMoveBG(cBgS_PolyInfo&);
    bool ChkMoveBG_NoDABg(cBgS_PolyInfo&);
    int GetPolyId0(int, int, int, u32, u32);
    int GetPolyCamId(int, int);
    u32 GetMtrlSndId(cBgS_PolyInfo&);
    int GetExitId(cBgS_PolyInfo&);
    int GetPolyColor(cBgS_PolyInfo&);
    int GetGrpRoomInfId(cBgS_PolyInfo&);
    s32 GetGrpSoundId(cBgS_PolyInfo&);
    u32 ChkGrpInf(cBgS_PolyInfo&, u32);
    int GetPolyId1(int, int, int, u32, u32);
    int GetLinkNo(cBgS_PolyInfo&);
    int GetWallCode(cBgS_PolyInfo&);
    int GetSpecialCode(cBgS_PolyInfo&);
    s32 GetAttributeCodeDirect(cBgS_PolyInfo&);
    s32 GetAttributeCode(cBgS_PolyInfo&);
    int GetGroundCode(cBgS_PolyInfo&);
    int GetPolyId2(int, int, int, u32, u32);
    int GetCamMoveBG(cBgS_PolyInfo&);
    int GetRoomCamId(cBgS_PolyInfo&);
    int GetRoomPathId(cBgS_PolyInfo&);
    int GetRoomPathPntNo(cBgS_PolyInfo&);
    s32 GetRoomId(cBgS_PolyInfo&);
    u32 ChkPolyHSStick(cBgS_PolyInfo&);
    bool LineCrossNonMoveBG(cBgS_LinChk*);
    void WallCorrect(dBgS_Acch*);
    f32 RoofChk(dBgS_RoofChk*);
    bool SplGrpChk(dBgS_SplGrpChk*);
    bool SphChk(dBgS_SphChk*, void*);

    void MoveBgCrrPos(cBgS_PolyInfo&, bool, cXyz*, csXyz*, csXyz*);
    void MoveBgTransPos(cBgS_PolyInfo&, bool, cXyz*, csXyz*, csXyz*);
    void MoveBgMatrixCrrPos(cBgS_PolyInfo&, bool, cXyz*, csXyz*, csXyz*);
    void RideCallBack(cBgS_PolyInfo&, fopAc_ac_c*);
    fopAc_ac_c* PushPullCallBack(cBgS_PolyInfo&, fopAc_ac_c*, short, dBgW::PushPullLabel);
};  // Size: 0x1404

#endif
