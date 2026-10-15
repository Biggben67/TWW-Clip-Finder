// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_bg_s_gnd_chk.cpp - cBgS_GndChk's constructor (c_bg_s_gnd_chk.cpp:9-14). mFlag = 3 turns
// on both of cBgS::GroundCross's prechecks.

#include "SSystem/SComponent/c_bg_s_gnd_chk.h"

/* 8024738C-80247418       .text __ct__11cBgS_GndChkFv */
cBgS_GndChk::cBgS_GndChk() {
    m_pos = cXyz::Zero;
    SetActorPid(fpcM_ERROR_PROCESS_ID_e);
    mFlag = 3;
}
