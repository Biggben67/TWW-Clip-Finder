// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_math.h - cM_rad2s, cM_atan2s, the cM_rnd family and the cM_scos / cM_ssin inlines
// (c_math.h:7, 8-10, 11-22, 35-41).

#ifndef TWW_PORT_C_MATH_H
#define TWW_PORT_C_MATH_H

#include "dolphin/types.h"
#include "JSystem/JMath/JMATrigonometric.h"

s16 cM_rad2s(float rad);

u16 U_GetAtanTable(float, float);
s16 cM_atan2s(float y, float x);
float cM_atan2f(float y, float x);

void cM_initRnd(int, int, int);

/**
 * Returns a pseudo-random float between 0.0f and 1.0f.
 */
float cM_rnd(void);

/**
 * Returns a pseudo-random float between 0.0f and max.
 * @param max The maximum value
 */
float cM_rndF(float max);

inline f32 cM_scos(s16 x) {
    return JMASCos(x);
}

inline f32 cM_ssin(s16 x) {
    return JMASSin(x);
}

#endif
