// ps_vec.h - the paired-single vector SDK.
//
// `dolphin/mtx/vec.h:51-72` defines each VEC* name twice:
//
//     #if defined(DEBUG) || !defined(__MWERKS__)
//     #define VECMag C_VECMag            // sqrtf(z*z + ((x*x) + (y*y)))
//     #else
//     #define VECMag PSVECMag            // frsqrte + one Newton step, in paired singles
//     #endif
//
// A non-MWCC compiler picks the C arm; the shipped game ran the PS one. None of C_VECMag,
// C_VECSquareMag, C_VECSquareDistance, C_VECDotProduct, C_VECCrossProduct or C_VECScale is in the
// DOL. The decomp's bodies are `asm { ... }` blocks (src/dolphin/mtx/vec.c); ps_vec.cpp
// transcribes them instruction by instruction.
//
//   psq_l f, 0(p), 0, 0   loads two floats  -> f = (p[0], p[1])        ps0, ps1
//   psq_l f, 8(p), 1, 0   loads one          -> f = (p[2], 1.0)
//   lfs   f, 8(p)         loads one scalar and splats it into both lanes
//   ps_mul  d,a,c         d = (a0*c0, a1*c1)          each lane rounded to single
//   ps_madd d,a,c,b       d = (a0*c0+b0, a1*c1+b1)    each lane fused, one rounding
//   ps_msub d,a,c,b       d = (a0*c0-b0, a1*c1-b1)    each lane fused
//   ps_muls0 d,a,c        d = (a0*c0, a1*c0)          frC's ps0 against both of frA
//   ps_sum0 d,a,b,c       d = (a0+b1, c1)             the cross-lane add
//   ps_merge10 d,a,b      d = (a1, b0)   ps_merge01 d,a,b = (a0, b1)   ps_merge11 = (a1, b1)

#ifndef TWW_ENGINE_PS_VEC_H
#define TWW_ENGINE_PS_VEC_H

#include "dolphin/types.h"

f32 PSVECSquareMag(const Vec* v);
f32 PSVECSquareDistance(const Vec* a, const Vec* b);
f32 PSVECMag(const Vec* v);
f32 PSVECDotProduct(const Vec* a, const Vec* b);
void PSVECCrossProduct(const Vec* a, const Vec* b, Vec* axb);
void PSVECScale(const Vec* src, Vec* dst, f32 scale);
void PSVECSubtract(const Vec* a, const Vec* b, Vec* a_b);
void PSVECAdd(const Vec* a, const Vec* b, Vec* ab);

// The `#else` arm of dolphin/mtx/vec.h:62-72. Left undefined, the decomp's header would quietly
// supply the C arm.
#define VECSquareMag PSVECSquareMag
#define VECSquareDistance PSVECSquareDistance
#define VECMag PSVECMag
#define VECDotProduct PSVECDotProduct
#define VECCrossProduct PSVECCrossProduct
#define VECScale PSVECScale
#define VECSubtract PSVECSubtract
#define VECAdd PSVECAdd

#endif  // TWW_ENGINE_PS_VEC_H
