// Generated from the zeldaret/tww decomp. Do not hand-edit.
// JMATrigonometric.h - JMASCos / JMASSin (JMATrigonometric.h:6-15). The game's cosine is a
// table lookup, so the table is built the decomp's way (JMath.cpp) rather than with
// std::cos.

#ifndef TWW_PORT_JMATRIGONOMETRIC_H
#define TWW_PORT_JMATRIGONOMETRIC_H

#include "dolphin/types.h"

extern u32 jmaSinShift;
extern f32 *jmaSinTable;
extern f32 *jmaCosTable;

inline f32 JMASCos(s16 v) {
    return jmaCosTable[static_cast<u16>(v) >> jmaSinShift];
}
inline f32 JMASSin(s16 v) {
    return jmaSinTable[static_cast<u16>(v) >> jmaSinShift];
}

#endif
