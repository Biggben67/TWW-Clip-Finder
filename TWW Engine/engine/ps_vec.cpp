// ps_vec.cpp - the asm blocks of src/dolphin/mtx/vec.c, transcribed. See ps_vec.h.

#include "engine/ps_vec.h"

#include "engine/ppc_fp.h"

/// vec.c:128-140. `sqmag = (z*z + x*x) + y*y`, first add fused. The C twin associates
/// `z*z + ((x*x) + (y*y))` with three separate roundings.
///
///     psq_l   vxy, 0x0(v), 0, 0        vxy = (x, y)
///     ps_mul  vxy, vxy, vxy            vxy = (x*x, y*y)
///     lfs     vzz, 0x8(v)              vzz = (z, z)
///     ps_madd sqmag, vzz, vzz, vxy     sqmag.ps0 = z*z + x*x   FUSED
///     ps_sum0 sqmag, sqmag, vxy, vxy   sqmag.ps0 = that + y*y
f32 PSVECSquareMag(const Vec* v) {
    const f32 xx = ppc::fmuls(v->x, v->x);
    const f32 yy = ppc::fmuls(v->y, v->y);
    return ppc::fadds(ppc::fmadds(v->z, v->z, xx), yy);
}

/// vec.c:299-317, JP 0x8030BDFC. `(dx*dx + dy*dy) + dz*dz`, first add fused; the C twin has the
/// same association but three separate roundings.
///
///     psq_l   v0yz, 0x4(a), 0, 0     v0yz = (a.y, a.z)
///     psq_l   v1yz, 0x4(b), 0, 0     v1yz = (b.y, b.z)
///     ps_sub  dyz, v0yz, v1yz        dyz  = (dy, dz)
///     psq_l   v0xy, 0x0(a), 0, 0     v0xy = (a.x, a.y)
///     psq_l   v1xy, 0x0(b), 0, 0     v1xy = (b.x, b.y)
///     ps_mul  dyz, dyz, dyz          dyz  = (dy*dy, dz*dz)
///     ps_sub  dxy, v0xy, v1xy        dxy  = (dx, dy)
///     ps_madd sqd, dxy, dxy, dyz     sqd.ps0 = dx*dx + dy*dy   FUSED
///     ps_sum0 sqd, sqd, dyz, dyz     sqd.ps0 = that + dz*dz
f32 PSVECSquareDistance(const Vec* a, const Vec* b) {
    const f32 dx = ppc::fsubs(a->x, b->x);
    const f32 dy = ppc::fsubs(a->y, b->y);
    const f32 dz = ppc::fsubs(a->z, b->z);
    const f32 dyy = ppc::fmuls(dy, dy);
    const f32 dzz = ppc::fmuls(dz, dz);
    return ppc::fadds(ppc::fmadds(dx, dx, dyy), dzz);
}

/// vec.c:149-181. `frsqrte`, one Newton step, and a multiply back up.
///
///     ps_mul   vxy, vxy, vxy              (x*x, y*y)
///     ps_madd  sqmag, vzz, vzz, vxy       z*z + x*x  FUSED
///     ps_sum0  sqmag, sqmag, vxy, vxy     + y*y
///     fcmpu / beq                         sqmag == 0 returns sqmag, before the estimate
///     frsqrte  rmag, sqmag                the ~26-bit estimate
///     fmuls    nwork0, rmag, rmag         frC = rmag: 25-bit rounding, not a no-op here
///     fmuls    nwork1, rmag, c_half       frC = 0.5, exact
///     fnmsubs  nwork0, nwork0, sqmag, c_three     = 3.0 - (rmag*rmag)*sqmag   FUSED
///     fmuls    rmag, nwork0, nwork1
///     fmuls    sqmag, sqmag, rmag
///
/// `beq` against +0.0 is also true for -0.0, and sqmag itself is returned, so -0.0 stays -0.0.
f32 PSVECMag(const Vec* v) {
    const f32 xx = ppc::fmuls(v->x, v->x);
    const f32 yy = ppc::fmuls(v->y, v->y);
    const f32 sqmag = ppc::fadds(ppc::fmadds(v->z, v->z, xx), yy);
    if (sqmag == 0.0f) {
        return sqmag;
    }
    const double rmag = ppc::frsqrte(sqmag);
    const f32 nwork0 = ppc::fmuls_fpr(rmag, rmag);   // frA = frC = the raw estimate
    const f32 nwork1 = ppc::fmuls_fpr(rmag, 0.5);
    const f32 refined = ppc::fnmsubs(nwork0, sqmag, 3.0f);
    return ppc::fmuls(sqmag, ppc::fmuls(refined, nwork1));
}

/// vec.c:194-203. `(a.x*b.x + a.y*b.y) + a.z*b.z`, first add fused.
///
///     psq_l   f2, Vec.y(a), 0, 0     f2 = (a.y, a.z)
///     psq_l   f3, Vec.y(b), 0, 0     f3 = (b.y, b.z)
///     ps_mul  f2, f2, f3             f2 = (a.y*b.y, a.z*b.z)
///     psq_l   f5, Vec.x(a), 0, 0     f5 = (a.x, a.y)
///     psq_l   f4, Vec.x(b), 0, 0     f4 = (b.x, b.y)
///     ps_madd f3, f5, f4, f2         f3.ps0 = a.x*b.x + a.y*b.y   FUSED
///     ps_sum0 f1, f3, f2, f2         f1.ps0 = that + f2.ps1 = + a.z*b.z
f32 PSVECDotProduct(const Vec* a, const Vec* b) {
    const f32 yy = ppc::fmuls(a->y, b->y);
    const f32 zz = ppc::fmuls(a->z, b->z);
    return ppc::fadds(ppc::fmadds(a->x, b->x, yy), zz);
}

/// vec.c:222-237. Each component is `p*q - r*s` with the first product fused into the subtract and
/// the second rounded on its own. A symmetric `(p*q) - (r*s)` disagrees on 620 of 1,942 console
/// planes (tests/test_calc_pla.cpp).
///
///     psq_l      f1, Vec.x(b), 0, 0     f1 = (b.x, b.y)
///     lfs        f2, Vec.z(a)           f2 = (a.z, a.z)
///     psq_l      f0, Vec.x(a), 0, 0     f0 = (a.x, a.y)
///     ps_merge10 f6, f1, f1             f6 = (b.y, b.x)
///     lfs        f3, Vec.z(b)           f3 = (b.z, b.z)
///     ps_mul     f4, f1, f2             f4 = (b.x*a.z, b.y*a.z)        separately rounded
///     ps_muls0   f7, f1, f0             f7 = (b.x*a.x, b.y*a.x)        separately rounded
///     ps_msub    f5, f0, f3, f4         f5 = (a.x*b.z - f4.0, a.y*b.z - f4.1)   FUSED
///     ps_msub    f8, f0, f6, f7         f8 = (a.x*b.y - f7.0, a.y*b.x - f7.1)   FUSED
///     ps_merge11 f9,  f5, f5            f9.ps0  = f5.ps1
///     ps_merge01 f10, f5, f8            f10 = (f5.ps0, f8.ps1)
///     psq_st     f9,  Vec.x(axb), 1, 0  axb.x =  a.y*b.z - b.y*a.z
///     ps_neg     f10, f10
///     psq_st     f10, Vec.y(axb), 0, 0  axb.y = -(a.x*b.z - b.x*a.z), axb.z = -(a.y*b.x - b.y*a.x)
///
/// `f8.ps0` is computed and discarded by the merge, so it is omitted here.
void PSVECCrossProduct(const Vec* a, const Vec* b, Vec* axb) {
    const f32 x = ppc::fmsubs(a->y, b->z, ppc::fmuls(b->y, a->z));
    const f32 y = -ppc::fmsubs(a->x, b->z, ppc::fmuls(b->x, a->z));
    const f32 z = -ppc::fmsubs(a->y, b->x, ppc::fmuls(b->y, a->x));
    axb->x = x;
    axb->y = y;
    axb->z = z;
}

/// vec.c:58-70. The scale is frC, so 25-bit rounding applies - a no-op for an f32. `dst` may
/// alias `src`.
///
///     psq_l    vxy, 0x0(src), 0, 0
///     psq_l    vz,  0x8(src), 1, 0
///     ps_muls0 rxy, vxy, scale
///     ps_muls0 rz,  vz,  scale
void PSVECScale(const Vec* src, Vec* dst, f32 scale) {
    const f32 x = ppc::fmuls(src->x, scale);
    const f32 y = ppc::fmuls(src->y, scale);
    const f32 z = ppc::fmuls(src->z, scale);
    dst->x = x;
    dst->y = y;
    dst->z = z;
}

/// vec.c:36-47. Two `ps_sub`s; each lane rounds as `fsubs` does.
void PSVECSubtract(const Vec* a, const Vec* b, Vec* a_b) {
    const f32 x = ppc::fsubs(a->x, b->x);
    const f32 y = ppc::fsubs(a->y, b->y);
    const f32 z = ppc::fsubs(a->z, b->z);
    a_b->x = x;
    a_b->y = y;
    a_b->z = z;
}

/// vec.c:16-25. Two `ps_add`s; each lane rounds as `fadds` does. `cXyz::operator+=` uses it.
void PSVECAdd(const Vec* a, const Vec* b, Vec* ab) {
    const f32 x = ppc::fadds(a->x, b->x);
    const f32 y = ppc::fadds(a->y, b->y);
    const f32 z = ppc::fadds(a->z, b->z);
    ab->x = x;
    ab->y = y;
    ab->z = z;
}
