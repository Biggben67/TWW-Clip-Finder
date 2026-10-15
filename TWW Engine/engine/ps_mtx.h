// ps_mtx.h - the paired-single matrix SDK.
//
// `dolphin/mtx/mtx.h:58-72` and `dolphin/mtx/mtxvec.h` define each MTX* name twice, as vec.h does
// (see ps_vec.h): a non-MWCC compiler picks the C_ arm, but the DOL links only the PS versions.
// The two arms differ beyond fusion: C_MTXMultVec associates `m03 + ((m02*z) + ((m00*x) +
// (m01*y)))` while PSMTXMultVec computes `(m02*z + m00*x) + (m03 + m01*y)`.
//
//     PSMTXConcat      0x8030AE44, 51 instructions, 12 paired fused
//     PSMTXMultVec     0x8030B860, 3 paired fused, 3 ps-arith
//     PSMTXMultVecSR   0x8030B8C0, 3 paired fused, 3 ps-arith
//     PSMTXTrans       0x8030B360, 13 instructions, no arithmetic
//     PSMTXCopy        0x8030AE10, 13 instructions, no arithmetic
//
// PSMTXTrans and PSMTXCopy are bit-identical to their C twins; they are here so every MTX* name
// resolves to one arm. The decomp's bodies are `asm { ... }` blocks (src/dolphin/mtx/mtx.c,
// mtxvec.c); ps_mtx.cpp transcribes them instruction by instruction.
//
// Operand order: `ps_madd frD, frA, frC, frB` is `frD = frA * frC + frB` (frC before frB).
// `ps_sum0 frD, frA, frC, frB` is `frD_ps0 = frA_ps0 + frB_ps1`, `frD_ps1 = frC_ps1`, so
// `ps_sum0 f6, f5, f6, f5` does not read f6's ps0.
//
//   psq_l f, 0(p), 0, 0   loads two floats  -> f = (p[0], p[1])      ps0, ps1
//   psq_l f, 8(p), 1, 0   loads one          -> f = (p[2], 1.0)
//   psq_st f, 0(p), 1, 0  stores one         -> p[0] = f.ps0
//   ps_muls0 d,a,c        d = (a0*c0, a1*c0)        frC's ps0 against both of frA
//   ps_madds0 d,a,c,b     d = (a0*c0+b0, a1*c0+b1)  each lane fused
//   ps_madds1 d,a,c,b     d = (a0*c1+b0, a1*c1+b1)  each lane fused, frC's ps1
//   ps_sum0 d,a,c,b       d = (a0+b1, c1)           the cross-lane add

#ifndef TWW_ENGINE_PS_MTX_H
#define TWW_ENGINE_PS_MTX_H

#include "dolphin/types.h"

void PSMTXCopy(const f32 (*src)[4], MtxP dst);
void PSMTXIdentity(MtxP m);
void PSMTXTrans(MtxP m, f32 xT, f32 yT, f32 zT);
void PSMTXConcat(const f32 (*a)[4], const f32 (*b)[4], MtxP ab);
void PSMTXMultVec(const f32 (*m)[4], const Vec* src, Vec* dst);
void PSMTXMultVecSR(const f32 (*m)[4], const Vec* src, Vec* dst);
/// Uses `fres` plus one Newton step where its C twin divides. Returns 0 for a singular matrix.
u32 PSMTXInverse(const f32 (*src)[4], MtxP inv);
/// Quaternion to rotation; divides by the squared norm via `fres` plus one Newton step.
void PSMTXQuat(MtxP m, const Quaternion* q);

// The `#else` arm of mtx.h:58-72 and mtxvec.h. Left undefined, the decomp's header would quietly
// supply the C arm.
#define MTXCopy PSMTXCopy
#define MTXIdentity PSMTXIdentity
#define MTXTrans PSMTXTrans
#define MTXConcat PSMTXConcat
#define MTXMultVec PSMTXMultVec
#define MTXMultVecSR PSMTXMultVecSR
#define MTXInverse PSMTXInverse
#define MTXQuat PSMTXQuat

#endif
