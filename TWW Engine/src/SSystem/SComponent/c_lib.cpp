// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_lib.cpp - cLib_addCalc, cLib_addCalcAngleS, cLib_distanceAngleS, cLib_chaseF and
// cLib_targetAngleY (c_lib.cpp:21-53, 159-189, 363-366, 274-290, 342-345).

#include "SSystem/SComponent/c_lib.h"
#include "SSystem/SComponent/c_math.h"

#include <cmath>
#include <cstdlib>

/* 802528E4-802529A4       .text cLib_addCalc__FPfffff */
f32 cLib_addCalc(f32* pValue, f32 target, f32 scale, f32 maxStep, f32 minStep) {
    if (*pValue != target) {
        f32 step = scale * (target - *pValue);
        if (step >= minStep || step <= -minStep) {
            if (step > maxStep) {
                step = maxStep;
            }
            if (step < -maxStep) {
                step = -maxStep;
            }
            *pValue += step;
        } else {
            if (step > 0) {
                if (step < minStep) {
                    *pValue += minStep;
                    if (*pValue > target) {
                        *pValue = target;
                    }
                }
            } else {
                minStep = -minStep;
                if (step > minStep) {
                    *pValue += minStep;
                    if (*pValue < target) {
                        *pValue = target;
                    }
                }
            }
        }
    }
    return std::fabs(target - *pValue);
}

/* 802531A8-80253270       .text cLib_addCalcAngleS__FPsssss */
s16 cLib_addCalcAngleS(s16* pValue, s16 target, s16 scale, s16 maxStep, s16 minStep) {
    s16 diff = target - *pValue;
    if (*pValue != target) {
        s16 step = (diff) / scale;
        if (step > minStep || step < -minStep) {
            if (step > maxStep) {
                step = maxStep;
            }
            if (step < -maxStep) {
                step = -maxStep;
            }
            *pValue += step;
        } else {
            if (0 <= diff) {
                *pValue += minStep;
                diff = target - *pValue;
                if (0 >= diff) {
                    *pValue = target;
                }
            } else {
                *pValue -= minStep;
                diff = target - *pValue;
                if (0 <= diff) {
                    *pValue = target;
                }
            }
        }
    }
    return target - *pValue;
}

/* 8025397C-802539A4       .text cLib_distanceAngleS__Fss */
s32 cLib_distanceAngleS(s16 x, s16 y) {
    return abs(static_cast<s16>(x - y));
}


/* 80253440-802534AC       .text cLib_chaseF__FPfff */
int cLib_chaseF(f32* pValue, f32 target, f32 step) {
    if (step) {
        if (*pValue > target) {
            step = -step;
        }
        *pValue += step;
        if (step * (*pValue - target) >= 0) {
            *pValue = target;
            return 1;
        }
    } else if (*pValue == target) {
        return 1;
    }
    return 0;
}

/* 80253804-8025383C       .text cLib_targetAngleY__FP4cXyzP4cXyz */
s16 cLib_targetAngleY(cXyz* lhs, cXyz* rhs) {
    return cM_atan2s(rhs->x - lhs->x, rhs->z - lhs->z);
}
