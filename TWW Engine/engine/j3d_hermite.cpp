// j3d_hermite.cpp - J3DHermiteInterpolationS, the s16 keyframe Hermite, transcribed from the
// DOL (JP 0x802F06D8) because the decomp's body is an `asm {}` block.
//
// J3DAnimation.cpp:323-366 has a commented-out C expression and the real body under
// `#ifdef __MWERKS__`, computing into a `register f32 fout` the C never assigns; extracted as
// written it returns garbage on other compilers. The C is also different arithmetic: five of the
// asm's ops are fused.
//
// Each keyframe argument is loaded with `psq_l fN, 0(p), 1, 5`: one value through GQR5, which
// OSInitFastCast sets to S16 with scale 0 - a plain (float)s16 widening.

#include "engine/ppc_fp.h"
#include "dolphin/types.h"

/// J3DAnimation.cpp:323-366 / DOL 0x802F06D8, one line per instruction in the asm's order.
/// `fout` aliases the argument `t` until `psq_l fout, 0(tangent1)`, so `fsubs f6, fout, f0` must
/// read `t` before that load; hoisting the loads silently substitutes tangent1.
f32 J3DHermiteInterpolationS(f32 t, s16* time0, s16* value0, s16* tangent0,
                             s16* time1, s16* value1, s16* tangent1) {
    f32 f0 = (f32)*time0;                             // psq_l f0, 0(time0), 1, 5
    f32 f3 = (f32)*time1;                             // psq_l f3, 0(time1), 1, 5
    f32 f2 = (f32)*value0;                            // psq_l f2, 0(value0), 1, 5
    f32 f4 = ppc::fsubs(f3, f0);                      // fsubs f4, f3, f0
    f3 = (f32)*value1;                                // psq_l f3, 0(value1), 1, 5
    f32 f6 = ppc::fsubs(t, f0);                       // fsubs f6, fout, f0
    f32 fout = (f32)*tangent1;                        // psq_l fout, 0(tangent1), 1, 5
    f32 f5 = ppc::fsubs(f3, f2);                      // fsubs f5, f3, f2
    f6 = ppc::fdivs(f6, f4);                          // fdivs f6, f6, f4
    f0 = (f32)*tangent0;                              // psq_l f0, 0(tangent0), 1, 5
    fout = ppc::fmadds(fout, f4, f2);                 // fmadds fout, fout, f4, f2
    f32 f7 = ppc::fmuls(f6, f6);                      // fmuls f7, f6, f6
    f5 = ppc::fnmsubs(f4, f0, f5);                    // fnmsubs f5, f4, f0, f5
    fout = ppc::fsubs(fout, f3);                      // fsubs fout, fout, f3
    fout = ppc::fsubs(fout, f5);                      // fsubs fout, fout, f5
    f3 = ppc::fmuls(f7, fout);                        // fmuls f3, f7, fout
    fout = ppc::fmadds(f4, f0, f3);                   // fmadds fout, f4, f0, f3
    fout = ppc::fmadds(fout, f6, f2);                 // fmadds fout, fout, f6, f2
    fout = ppc::fmadds(f5, f7, fout);                 // fmadds fout, f5, f7, fout
    return ppc::fsubs(fout, f3);                      // fsubs fout, fout, f3
}
