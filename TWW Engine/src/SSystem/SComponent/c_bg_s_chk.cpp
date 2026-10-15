// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_chk.cpp - cBgS_Chk::ChkSameActorPid (c_bg_s_chk.cpp:13-20). The trimmed header
// declares no destructor, so none is carried.

#include "SSystem/SComponent/c_bg_s_chk.h"

/* 8024734C-8024738C       .text ChkSameActorPid__8cBgS_ChkCFUi */
bool cBgS_Chk::ChkSameActorPid(fpc_ProcID pid) const {
    if (mActorPid == fpcM_ERROR_PROCESS_ID_e || pid == fpcM_ERROR_PROCESS_ID_e || mSameActorChk == 0) {
        return FALSE;
    } else {
        return (mActorPid == pid) ? TRUE : FALSE;
    }
}
