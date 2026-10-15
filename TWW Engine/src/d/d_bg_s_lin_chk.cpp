// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_bg_s_lin_chk.cpp - dBgS_LinChk::Set (d_bg_s_lin_chk.cpp:9-18).

#include "d/d_bg_s_lin_chk.h"

#include "boundary/game_boundary.h"

/* 800A5678-800A56B8       .text Set__11dBgS_LinChkFP4cXyzP4cXyzP10fopAc_ac_c */
void dBgS_LinChk::Set(cXyz* pi_start, cXyz* pi_end, fopAc_ac_c* pi_actor) {
    u32 id;
    if (pi_actor != NULL) {
        id = fopAcM_GetID(pi_actor);
    } else {
        id = fpcM_ERROR_PROCESS_ID_e;
    }
    Set2(pi_start, pi_end, id);
}
