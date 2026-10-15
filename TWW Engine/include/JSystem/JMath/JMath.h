// Generated from the zeldaret/tww decomp. Do not hand-edit.
// JMath.h - JMANewSinTable, JMAEulerToQuat and JMAHermiteInterpolation (JMath.h:7, 8-9,
// 10).

#ifndef TWW_PORT_JMATH_H
#define TWW_PORT_JMATH_H

#include "dolphin/types.h"

bool JMANewSinTable(u8 numBits);

void JMAEulerToQuat(s16 x, s16 y, s16 z, Quaternion* out);
void JMAQuatLerp(Quaternion* a, Quaternion* b, f32 t, Quaternion* out);

f32 JMAHermiteInterpolation(f32 frame, f32 time0, f32 value0, f32 tangent0, f32 time1, f32 value1, f32 tangent1);

#endif
