// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_lin_chk.cpp - cBgS_LinChk::ct and Set2 (c_bg_s_lin_chk.cpp:10-18, 21-27).

#include "SSystem/SComponent/c_bg_s_lin_chk.h"


void cBgS_LinChk::ct() {
    cXyz zero = cXyz::Zero;
    mLin.SetStartEnd(zero, zero);
    field_0x40 = zero;
    SetActorPid(fpcM_ERROR_PROCESS_ID_e);
    mFlag = 0;
    mFrontFlag = 1;
    mBackFlag = 0;
}

void cBgS_LinChk::Set2(cXyz* pi_start, cXyz* pi_end, fpc_ProcID pi_actor) {
    mLin.SetStartEnd(*pi_start, *pi_end);
    field_0x40 = *pi_end;
    SetActorPid(pi_actor);
    ClrHit();
    ClearPi();
}
