// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_chk.h - cBgS_GrpPassChk and cBgS_Chk, trimmed (c_bg_s_chk.h:7-12, 14-19, 22-34,
// 36-42).

#ifndef TWW_PORT_C_BG_S_CHK_H
#define TWW_PORT_C_BG_S_CHK_H

#include "global.h"
#include "dolphin/types.h"

class cBgS_GrpPassChk {
public:
    virtual ~cBgS_GrpPassChk() {}
};

class cBgS_PolyPassChk;

class cBgS_Chk {
private:
    /* 0x0 */ cBgS_PolyPassChk* mPolyPassChk;
    /* 0x4 */ cBgS_GrpPassChk* mGrpPassChk;
    /* 0x8 */ fpc_ProcID mActorPid;
    /* 0xC */ bool mSameActorChk;

public:
    cBgS_Chk() {
        mPolyPassChk = NULL;
        mGrpPassChk = NULL;
        mSameActorChk = true;
    }
    void SetExtChk(cBgS_Chk& other) {
        mPolyPassChk = other.mPolyPassChk;
        mGrpPassChk = other.mGrpPassChk;
        mActorPid = other.mActorPid;
        mSameActorChk = other.mSameActorChk;
    }
    bool ChkSameActorPid(fpc_ProcID) const;

    void SetActorPid(fpc_ProcID pid) { mActorPid = pid; }
    fpc_ProcID GetActorPid() const { return mActorPid; }
    void SetPolyPassChk(cBgS_PolyPassChk* p_chk) { mPolyPassChk = p_chk; }
    void SetGrpPassChk(cBgS_GrpPassChk* p_chk) { mGrpPassChk = p_chk; }
    cBgS_PolyPassChk* GetPolyPassChk() const { return mPolyPassChk; }
    cBgS_GrpPassChk* GetGrpPassChk() const { return mGrpPassChk; }
    void OffSameActorChk() { mSameActorChk = false; }
};

#endif
