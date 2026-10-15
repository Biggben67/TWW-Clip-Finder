// The c_lib entry points the ported bodies call, declared as in the decomp's
// include/SSystem/SComponent/c_lib.h:20-22, :28 and :33.
#ifndef TWW_PORT_C_LIB_H
#define TWW_PORT_C_LIB_H

#include "dolphin/types.h"

f32 cLib_addCalc(f32* pValue, f32 target, f32 scale, f32 maxStep, f32 minStep);
s16 cLib_addCalcAngleS(s16* o_value, s16 target, s16 scale, s16 maxStep, s16 minStep);
s32 cLib_distanceAngleS(s16 x, s16 y);
int cLib_chaseF(f32* o_value, f32 target, f32 step);
s16 cLib_targetAngleY(cXyz* lhs, cXyz* rhs);

#endif
