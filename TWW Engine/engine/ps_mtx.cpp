// ps_mtx.cpp - the paired-single matrix routines, transcribed from the DOL. See ps_mtx.h.

#include "engine/ps_mtx.h"

#include "engine/ppc_fp.h"

/// mtx.c:68-82. No arithmetic; bit-identical to C_MTXCopy.
///
///     psq_l  f0, 0(src), 0, 0        psq_st f0, 0(dst), 0, 0      ... x6
void PSMTXCopy(const f32 (*src)[4], MtxP dst) {
    dst[0][0] = src[0][0];
    dst[0][1] = src[0][1];
    dst[0][2] = src[0][2];
    dst[0][3] = src[0][3];
    dst[1][0] = src[1][0];
    dst[1][1] = src[1][1];
    dst[1][2] = src[1][2];
    dst[1][3] = src[1][3];
    dst[2][0] = src[2][0];
    dst[2][1] = src[2][1];
    dst[2][2] = src[2][2];
    dst[2][3] = src[2][3];
}

/// mtx.c:29-45, JP 0x8030ADE4. Stores only; bit-identical to C_MTXIdentity. The store order is
/// the asm's: paired stores of (0,0), (0,1) and (1,0) constants built by `ps_merge01/10`.
///
///     psq_st c_zero, 8(m)    ps_merge01 c_01, c_zero, c_one    psq_st c_zero, 24(m)
///     ps_merge10 c_10, c_one, c_zero    psq_st c_zero, 32(m)   psq_st c_01, 16(m)
///     psq_st c_10, 0(m)      psq_st c_10, 40(m)
void PSMTXIdentity(MtxP m) {
    m[0][2] = 0.0f;
    m[0][3] = 0.0f;
    m[1][2] = 0.0f;
    m[1][3] = 0.0f;
    m[2][0] = 0.0f;
    m[2][1] = 0.0f;
    m[1][0] = 0.0f;
    m[1][1] = 1.0f;
    m[0][0] = 1.0f;
    m[0][1] = 0.0f;
    m[2][2] = 1.0f;
    m[2][3] = 0.0f;
}

/// mtx.c:827-843. Stores only; bit-identical to C_MTXTrans. Store order is the asm's.
///
///     stfs xT, 12(m)   stfs yT, 28(m)   psq_st c0, 4(m), 0, 0    psq_st c0, 32(m), 0, 0
///     stfs c0, 16(m)   stfs c1, 20(m)   stfs c0, 24(m)
///     stfs c1, 40(m)   stfs zT, 44(m)   stfs c1, 0(m)
void PSMTXTrans(MtxP m, f32 xT, f32 yT, f32 zT) {
    m[0][3] = xT;
    m[1][3] = yT;
    m[0][1] = 0.0f;
    m[0][2] = 0.0f;
    m[2][0] = 0.0f;
    m[2][1] = 0.0f;
    m[1][0] = 0.0f;
    m[1][1] = 1.0f;
    m[1][2] = 0.0f;
    m[2][2] = 1.0f;
    m[2][3] = zT;
    m[0][0] = 1.0f;
}

/// mtx.c:119-168. The 3x4 product, with both adds of each element fused:
///
///     ab[i][j] = b[2][j]*a[i][2] + (b[1][j]*a[i][1] + b[0][j]*a[i][0])
///
/// plus `a[i][3]` through the (0.0, 1.0) constant `Unit01` for the translation column. `ab` may
/// alias `a` or `b` (mDoMtx_*rotM calls PSMTXConcat(now, tmp, now)): all loads precede stores.
///
///     psq_l     f0, 0(a), 0, 0            f0  = (a00, a01)
///     psq_l     f6, 0(b), 0, 0            f6  = (b00, b01)      f7 = (b02, b03)
///     psq_l     f31, 0(Unit01), 0, 0      f31 = (0.0, 1.0)
///     ps_muls0  f12, f6, f0               f12 = (b00*a00, b01*a00)
///     ps_madds1 f12, f8, f0, f12          f12 += (b10*a01, b11*a01)     FUSED
///     ps_madds0 f12, f10, f1, f12         f12 += (b20*a02, b21*a02)     FUSED
///     ps_madds1 f13, f31, f1, f13         f13 += (0.0*a03, 1.0*a03)     the translate
void PSMTXConcat(const f32 (*a)[4], const f32 (*b)[4], MtxP ab) {
    f32 out[3][4];
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 4; j++) {
            out[i][j] = ppc::fmadds(b[2][j], a[i][2],
                                    ppc::fmadds(b[1][j], a[i][1], ppc::fmuls(b[0][j], a[i][0])));
        }
        // `ps_madds1 f13, f31, f1, f13`: 0.0 * a[i][3] onto column 2, 1.0 * a[i][3] onto column 3.
        out[i][2] = ppc::fmadds(0.0f, a[i][3], out[i][2]);
        out[i][3] = ppc::fmadds(1.0f, a[i][3], out[i][3]);
    }
    PSMTXCopy(out, ab);
}

/// mtxvec.c:21-43. Associates differently from C_MTXMultVec, besides fusing: the lanes pair
/// (m[i][0], m[i][1]) with (x, y) and (m[i][2], m[i][3]) with (z, 1.0), so `ps_sum0` adds
///
///     (m[i][2]*z + m[i][0]*x)  +  (m[i][3] + m[i][1]*y)
///
/// where the C twin writes `m[i][3] + ((m[i][2]*z) + ((m[i][0]*x) + (m[i][1]*y)))`.
///
///     psq_l   f0, Vec.x(src), 0, 0     f0 = (x, y)
///     psq_l   f1, Vec.z(src), 1, 0     f1 = (z, 1.0)
///     psq_l   f2, 0(m), 0, 0           f2 = (m00, m01)     f3 = (m02, m03)
///     ps_mul  f4, f2, f0               f4 = (m00*x, m01*y)
///     ps_madd f5, f3, f1, f4           f5 = (m02*z + m00*x, m03*1.0 + m01*y)   FUSED
///     ps_sum0 f6, f5, f6, f5           f6.ps0 = f5.ps0 + f5.ps1
///     psq_st  f6, Vec.x(dst), 1, 0
void PSMTXMultVec(const f32 (*m)[4], const Vec* src, Vec* dst) {
    const f32 x = src->x;
    const f32 y = src->y;
    const f32 z = src->z;
    f32 out[3];
    for (int i = 0; i < 3; i++) {
        const f32 lo = ppc::fmadds(m[i][2], z, ppc::fmuls(m[i][0], x));
        const f32 hi = ppc::fmadds(m[i][3], 1.0f, ppc::fmuls(m[i][1], y));
        out[i] = ppc::fadds(lo, hi);
    }
    // Written back at the end: dst may alias src.
    dst->x = out[0];
    dst->y = out[1];
    dst->z = out[2];
}

/// mtxvec.c:136-160. Associates as its C twin does, `(m02*z) + ((m00*x) + (m01*y))`, but the last
/// product is fused.
///
///     psq_l   f0, 0x0(m), 0, 0      f0 = (m00, m01)      f6 = (x, y)
///     psq_l   f7, 0x8(src), 1, 0    f7 = (z, 1.0)
///     ps_mul  f8, f0, f6            f8 = (m00*x, m01*y)
///     ps_sum0 f8, f8, f8, f8        f8.ps0 = m00*x + m01*y
///     ps_madd f9, f1, f7, f8        f9.ps0 = m02*z + that          FUSED
///     psq_st  f9, 0x0(dst), 1, 0
void PSMTXMultVecSR(const f32 (*m)[4], const Vec* src, Vec* dst) {
    const f32 x = src->x;
    const f32 y = src->y;
    const f32 z = src->z;
    f32 out[3];
    for (int i = 0; i < 3; i++) {
        out[i] = ppc::fmadds(m[i][2], z, ppc::fadds(ppc::fmuls(m[i][0], x), ppc::fmuls(m[i][1], y)));
    }
    dst->x = out[0];
    dst->y = out[1];
    dst->z = out[2];
}

/// mtx.c:404-467. The general 3x4 affine inverse. Where `C_MTXInverse` divides by the
/// determinant, this takes `fres` and one Newton step, so the low bits are the table's (see
/// `ppc::fres`). Not replaceable by a transpose: JMASin/JMACos rotations are not exactly
/// orthonormal off the axes.
///
/// `det == 0` returns 0 and writes nothing (the asm's early `blr`). `inv` may alias `src`
/// (`mDoMtx_stack_c::inverse()` is `MTXInverse(now, now)`): all loads precede stores.
///
///     ps_merge10 f6, f1, f0         f6 = (m02, m00)      the cofactor lanes are built by merges
///     ps_mul   f11, f3, f6          f11 = (m11*m02, m12*m00)
///     ps_msub  f11, f1, f7, f11     f11 = (m01*m12 - m11*m02, m02*m10 - m12*m00)   A02 | B12
///     ps_msub  f13, f3, f8, f13     f13 = (A00, B10)
///     ps_msub  f12, f5, f6, f12     f12 = (A01, B11)
///     ps_msub  f10, f2, f5, f10     f10.ps0 = A20        ps1 is junk and never stored
///     ps_msub  f9,  f1, f4, f9      f9.ps0  = A21
///     ps_msub  f8,  f0, f3, f8      f8.ps0  = A22
///     ps_madd  f7, f4, f11, f7      f7.ps0  = det = m20*A02 + (m10*A01 + m00*A00)
///     ps_cmpo0 cr0, f7, f6 / bne    det == 0 -> li r3, 0 ; blr
///     fres     f0, f7               the estimate
///     ps_add   f6, f0, f0           2*est
///     ps_mul   f5, f0, f0           est*est
///     ps_nmsub f0, f7, f5, f6       recip = 2*est - det*est*est       ONE Newton step
///     ps_muls0 f13, f13, f0         every cofactor *= recip
///     ps_mul   f6, f13, f1          the translation column, FUSED down the three terms
///     ps_madd  f6, f12, f2, f6
///     ps_nmadd f6, f11, f3, f6      inv[i][3] = -(A02r*m23 + (A01r*m13 + A00r*m03))
u32 PSMTXInverse(const f32 (*src)[4], MtxP inv) {
    const f32 m00 = src[0][0], m01 = src[0][1], m02 = src[0][2], m03 = src[0][3];
    const f32 m10 = src[1][0], m11 = src[1][1], m12 = src[1][2], m13 = src[1][3];
    const f32 m20 = src[2][0], m21 = src[2][1], m22 = src[2][2], m23 = src[2][3];

    // Cofactors, paired as the asm pairs them: row-0 in ps0, row-1 in ps1.
    const f32 A00 = ppc::fmsubs(m11, m22, ppc::fmuls(m21, m12));   // f13.ps0
    const f32 B10 = ppc::fmsubs(m12, m20, ppc::fmuls(m22, m10));   // f13.ps1
    const f32 A01 = ppc::fmsubs(m21, m02, ppc::fmuls(m01, m22));   // f12.ps0
    const f32 B11 = ppc::fmsubs(m22, m00, ppc::fmuls(m02, m20));   // f12.ps1
    const f32 A02 = ppc::fmsubs(m01, m12, ppc::fmuls(m11, m02));   // f11.ps0
    const f32 B12 = ppc::fmsubs(m02, m10, ppc::fmuls(m12, m00));   // f11.ps1
    const f32 A20 = ppc::fmsubs(m10, m21, ppc::fmuls(m11, m20));   // f10.ps0
    const f32 A21 = ppc::fmsubs(m01, m20, ppc::fmuls(m00, m21));   // f9.ps0
    const f32 A22 = ppc::fmsubs(m00, m11, ppc::fmuls(m01, m10));   // f8.ps0

    const f32 det = ppc::fmadds(m20, A02, ppc::fmadds(m10, A01, ppc::fmuls(m00, A00)));
    if (det == 0.0f) {
        return 0;
    }

    // `fres` writes a single-precision result, so the f32 here loses nothing.
    const f32 est = (f32)ppc::fres((double)det);
    const f32 recip = ppc::fnmsubs(det, ppc::fmuls(est, est), ppc::fadds(est, est));

    inv[0][0] = ppc::fmuls(A00, recip);
    inv[0][1] = ppc::fmuls(A01, recip);
    inv[0][2] = ppc::fmuls(A02, recip);
    inv[1][0] = ppc::fmuls(B10, recip);
    inv[1][1] = ppc::fmuls(B11, recip);
    inv[1][2] = ppc::fmuls(B12, recip);
    inv[2][0] = ppc::fmuls(A20, recip);
    inv[2][1] = ppc::fmuls(A21, recip);
    inv[2][2] = ppc::fmuls(A22, recip);

    for (int i = 0; i < 3; i++) {
        inv[i][3] = ppc::fnmadds(inv[i][2], m23,
                                 ppc::fmadds(inv[i][1], m13, ppc::fmuls(inv[i][0], m03)));
    }
    return 1;
}

/// mtx.c:1016-1063, JP 0x8030B408: quaternion to 3x4 rotation. Runs once per joint per frame
/// (`mDoExt_MtxCalcAnmBlendTbl::calc` ends in `MTXQuat`). Blended quaternions are not
/// renormalised, so the denominator falls below 1.0 and reaches `fres` entries unit ones do not.
///
/// The Quaternion is read as two pairs, (x, y) and (z, w), so its member order matters
/// (dolphin/types.h). The scale `2 / (x2+y2+z2+w2)` takes three roundings, as in the asm:
/// the estimate, one Newton step, then a multiply by 2.0.
///
///     ps_mul   tmp2, tmp0, tmp0      (xx, yy)
///     ps_merge10 tmp5, tmp0, tmp0    (y, x)
///     ps_madd  tmp4, tmp1, tmp1, tmp2    (zz+xx, ww+yy)          FUSED
///     ps_mul   tmp3, tmp1, tmp1      (zz, ww)
///     ps_sum0  scale, tmp4, tmp4, tmp4   ps0 = the denominator, cross-lane
///     ps_muls1 tmp7, tmp5, tmp1      (y*w, x*w)                  frC's ps1 against both lanes
///     fres     tmp9, scale           the estimate
///     ps_sum1  tmp4, tmp3, tmp4, tmp2    (zz+xx, zz+yy)
///     ps_nmsub scale, scale, tmp9, c_two   2 - denom*est         ONE Newton step, FUSED
///     ps_mul   scale, tmp9, scale    recip
///     fmuls    scale, scale, c_two   s = 2*recip                 a THIRD rounding
///     ps_madd  tmp8, tmp0, tmp5, tmp6    (xy+zw, yx+ww)          FUSED
///     ps_msub  tmp6, tmp0, tmp5, tmp6    (xy-zw, yx-ww)          FUSED
///     ps_nmsub tmp2, tmp2, scale, c_one  1-(xx+yy)*s             FUSED
///     ps_nmsub tmp4, tmp4, scale, c_one  the other two diagonals  FUSED
///     ps_madds0 tmp5, tmp0, tmp1, tmp7   (xz+yw, yz+xw)          FUSED, frC's ps0
///     ps_nmsub tmp7, tmp7, c_two, tmp5   (xz-yw, yz-xw)          FUSED - the sign pair is one
///                                                                op, not a second product
void PSMTXQuat(MtxP m, const Quaternion* q) {
    // psq_l tmp0, 0(q) / psq_l tmp1, 8(q) - the two paired loads, and the only reads of `q`.
    const f32 x = q->x, y = q->y, z = q->z, w = q->w;

    // Computed as the asm does: `fsubs c_zero, c_one, c_one`, `fadds c_two, c_one, c_one`.
    const f32 c_one = 1.0f;
    const f32 c_zero = ppc::fsubs(c_one, c_one);
    const f32 c_two = ppc::fadds(c_one, c_one);

    const f32 xx = ppc::fmuls(x, x);              // tmp2.ps0
    const f32 yy = ppc::fmuls(y, y);              // tmp2.ps1
    const f32 zz = ppc::fmuls(z, z);              // tmp3.ps0
    const f32 ww = ppc::fmuls(w, w);              // tmp3.ps1

    const f32 zz_xx = ppc::fmadds(z, z, xx);      // tmp4.ps0
    const f32 ww_yy = ppc::fmadds(w, w, yy);      // tmp4.ps1
    const f32 denom = ppc::fadds(zz_xx, ww_yy);   // ps_sum0: the cross-lane add

    const f32 yw = ppc::fmuls(y, w);              // tmp7.ps0   ps_muls1 against tmp1.ps1 = w
    const f32 xw = ppc::fmuls(x, w);              // tmp7.ps1

    // `fres` writes a single-precision result, so the f32 here is what the register holds.
    const f32 est = (f32)ppc::fres((double)denom);
    const f32 recip = ppc::fmuls(est, ppc::fnmsubs(denom, est, c_two));
    const f32 s = ppc::fmuls(recip, c_two);

    const f32 zz_yy = ppc::fadds(zz, yy);         // ps_sum1's lane: tmp3.ps0 + tmp2.ps1
    const f32 zw = ppc::fmuls(z, w);              // tmp6.ps0   ps_muls1 against tmp1.ps1 = w
    const f32 xx_yy = ppc::fadds(xx, yy);         // ps_sum0 on tmp2

    const f32 xy_plus_zw = ppc::fmadds(x, y, zw);   // tmp8.ps0   ps_madd, one rounding
    const f32 xy_minus_zw = ppc::fmsubs(x, y, zw);  // tmp6.ps0   ps_msub, one rounding

    const f32 m22 = ppc::fnmsubs(xx_yy, s, c_one);
    const f32 m11 = ppc::fnmsubs(zz_xx, s, c_one);
    const f32 m00 = ppc::fnmsubs(zz_yy, s, c_one);

    const f32 m10 = ppc::fmuls(xy_plus_zw, s);
    const f32 m01 = ppc::fmuls(xy_minus_zw, s);

    const f32 xz_plus_yw = ppc::fmadds(x, z, yw);   // tmp5.ps0   ps_madds0 against tmp1.ps0 = z
    const f32 yz_plus_xw = ppc::fmadds(y, z, xw);   // tmp5.ps1

    // ps_nmsub tmp7, tmp7, c_two, tmp5: minus pair = plus pair - 2*cross term, one fused op.
    const f32 xz_minus_yw = ppc::fnmsubs(yw, c_two, xz_plus_yw);
    const f32 yz_minus_xw = ppc::fnmsubs(xw, c_two, yz_plus_xw);

    const f32 m02 = ppc::fmuls(xz_plus_yw, s);
    const f32 m21 = ppc::fmuls(yz_plus_xw, s);
    const f32 m20 = ppc::fmuls(xz_minus_yw, s);
    const f32 m12 = ppc::fmuls(yz_minus_xw, s);

    m[0][0] = m00; m[0][1] = m01; m[0][2] = m02; m[0][3] = c_zero;
    m[1][0] = m10; m[1][1] = m11; m[1][2] = m12; m[1][3] = c_zero;
    m[2][0] = m20; m[2][1] = m21; m[2][2] = m22; m[2][3] = c_zero;
}
