// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_poly_info.h - cBgS_PolyInfo, trimmed (c_bg_s_poly_info.h:9, 11-16, 18-41, 45-66,
// 67-70).

#ifndef TWW_PORT_C_BG_S_POLY_INFO_H
#define TWW_PORT_C_BG_S_POLY_INFO_H

#include "dolphin/types.h"
#include "engine/jut_assert.h"

class cBgW;

class cBgS_PolyInfo {
private:
    /* 0x00 */ u16 mPolyIndex;
    /* 0x02 */ u16 mBgIndex;
    /* 0x04 */ cBgW* mpBgW;
    /* 0x08 */ fpc_ProcID mActorId;

public:
    cBgS_PolyInfo() {
        ClearPi();
    }
    void ClearPi() {
        mPolyIndex = -1;
        mBgIndex = 0x100;
        mpBgW = NULL;
        mActorId = fpcM_ERROR_PROCESS_ID_e;
    }
    void SetPolyInfo(const cBgS_PolyInfo& other) {
        *this = other;
    }
    void SetActorInfo(int bg_index, void* bgw, fpc_ProcID actor_id) {
        JUT_ASSERT(0x59, 0 <= bg_index);
        mBgIndex = bg_index;
        mpBgW = (cBgW*)bgw;
        mActorId = actor_id;
    }
    bool ChkSafe(const void* bgw, fpc_ProcID pid) const {
        if (mpBgW == bgw && mActorId == pid)
            return true;
        return false;
    }

    int GetPolyIndex() const { return mPolyIndex; }
    int GetBgIndex() const { return mBgIndex; }
    bool ChkSetInfo() const {
        if (mPolyIndex == 0xFFFF || mBgIndex == 0x100) {
            return false;
        }

        return true;
    }
    bool ChkSetInf() const {
        if (mPolyIndex == 0xFFFF || mBgIndex == 0x100) {
            return false;
        }

        return true;
    }
    bool ChkBgIndex() const {
        if (mBgIndex == 0x100) {
            return false;
        }
        return true;
    }

    void SetPolyIndex(int poly_index) {
        JUT_ASSERT(0x7b, 0 <= poly_index);
        mPolyIndex = poly_index;
    }
};

#endif
