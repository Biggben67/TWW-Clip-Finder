"""quat.py - the quaternion path Link's cl LOWER BODY (PART_UNDER: waist/legs/feet) uses to build
each joint's local matrix. This is NOT the euler J3DGetTranslateRotateMtx path -- the foot chain is
posed by mDoExt_MtxCalcAnmBlendTblOld::calc (m_Do_ext.cpp:1164), which for EVERY joint (even single
anim) does: euler s16 -> quaternion (JMAEulerToQuat) -> [blend via JMAQuatLerp] -> matrix (mDoMtx_quat
= PSMTXQuat) -> scale+translate applied (mDoExt_setJ3DData). So fk.tr_matrix (euler->mtx direct) is
only right for direct-J3DMtxCalcMaya joints; the foot chain must use this module.

Specs (tww/):
  JMAEulerToQuat (JMath.cpp:41): half-angle via s16/2 (integer div, truncates), JMASCos/JMASSin.
    w = cos0*c1c2 + sin0*s1s2 ; x = sin0*c1c2 - cos0*s1s2 ;
    y = cos2*(cos0*sin1) + sin2*(sin0*cos1) ; z = sin2*(cos0*cos1) - cos2*(sin0*sin1).
  JMAQuatLerp (JMath.cpp:59): dot in f32 (fmadds chain); if dot<0 negate b; then the lerp
    out.c = (1.0-t)*a.c + (f64)t*temp.c is computed in DOUBLE, stored to f32 (NO normalization).
  MTXQuat==PSMTXQuat (mtx.c:1016) — C_MTXQuat (mtx.c:970) gives the math:
    s = 2/(w²+z²+x²+y²); m00=1-(yy+zz) etc. IMPORTANT: the retail PS version computes s via `fres`
    (reciprocal estimate) + one Newton step + *2, NOT an fdivs -> can differ from 2/denom by ~1 ULP.
    This module has scale='fres' (bit-faithful) and scale='fdivs' (simple) modes; default fres.

fres emulation follows the PPC 750CL algorithm (12-bit table estimate + 1 Newton-Raphson refine),
matching Dolphin's Interpreter fres. See _fres below.
"""
import struct

from .. import fp
from .. import mathlib as S


# JMACos/JMASin on s16 BAM from SEPARATE baked console tables (sin is not a wrap-around view of cos;
# 816/4096 entries differ 1 ULP -> foot-toe.z error). See sim.py _SIN_TABLE, knowledge/model/sim.md.
def _cos(a):
    return S._COS_TABLE[(int(a) & 0xFFFF) >> 4]

def _sin(a):
    return S._SIN_TABLE[(int(a) & 0xFFFF) >> 4]


def euler_to_quat(rx, ry, rz):
    """(w,x,y,z) quaternion from s16 euler (JMAEulerToQuat, JMath.cpp:41). C `s16/2` truncates toward
    zero. JMAEulerToQuat is compiled WITHOUT FMA contraction: each component is `(a*b) +/- (c*d)` with
    BOTH products separately f32-rounded, THEN added/subtracted -- NOT fused (fmadds/fnmsubs). Confirmed
    bit-exact vs the live oldQuat array for every foot-chain joint (a fused x/y left jnt34 1 ULP off,
    which leaked into the ATN/waitturn foot-toe tails). See knowledge/model/sim.md.

    The parameters are **s16**, so each is SIGN-EXTENDED before the halving (session 56): a rotation
    that arrives as a raw u16 >= 0x8000 is a NEGATIVE angle, and halving it unsigned lands 2048 table
    entries (180 deg) away. That yields the mathematically EQUIVALENT negated quaternion -- which is
    why it stayed invisible for so long, negation being bit-neutral through `mtx_quat`'s pairwise
    products -- but `jmaSinTable`'s two entries are rounded independently, so the magnitudes differ by
    tens of ULP. Live-pinned on the Courtyard roll (`rollf` joint 0 at frame 11: u16 33160 = s16
    -32376, half -16188 not +16580), where it moved the neck world z 1 ULP and, through the Co-centre,
    the CC push. `foot_fk._local_from_old` already sign-extended its own callback angles for the same
    reason (session 16); doing it HERE covers every caller, including the animated rotations."""
    def half(a):
        a = int(a) & 0xFFFF                                  # the parameter is s16 -- sign-extend
        a = a - 0x10000 if a >= 0x8000 else a
        return a // 2 if a >= 0 else -((-a) // 2)
    c0, c1, c2 = _cos(half(rx)), _cos(half(ry)), _cos(half(rz))
    s0, s1, s2 = _sin(half(rx)), _sin(half(ry)), _sin(half(rz))
    c1c2 = fp.fmuls(c1, c2)
    s1s2 = fp.fmuls(s1, s2)
    w = fp.fadds(fp.fmuls(c0, c1c2), fp.fmuls(s0, s1s2))
    x = fp.fsubs(fp.fmuls(s0, c1c2), fp.fmuls(c0, s1s2))                     # sin0*c1c2 - cos0*s1s2
    y = fp.fadds(fp.fmuls(c2, fp.fmuls(c0, s1)), fp.fmuls(s2, fp.fmuls(s0, c1)))
    z = fp.fsubs(fp.fmuls(s2, fp.fmuls(c0, c1)), fp.fmuls(c2, fp.fmuls(s0, s1)))  # sin2*(c0c1) - cos2*(s0s1)
    return (w, x, y, z)


def quat_concat(a, b):
    """``mDoMtx_QuatConcat(a, b)`` -- the quaternion product the ``jointBeforeCB`` adjusts use
    (the BODY_CHN counter-twist and the head-look callback). (w, x, y, z), each component f32."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (fp.f32(aw * bw - ax * bx - ay * by - az * bz),
            fp.f32(aw * bx + ax * bw + ay * bz - az * by),
            fp.f32(aw * by - ax * bz + ay * bw + az * bx),
            fp.f32(aw * bz + ax * by - ay * bx + az * bw))


def quat_lerp(a, b, t):
    """JMAQuatLerp: (w,x,y,z). dot in f32; sign-flip b; lerp in f64 -> f32. Not normalized."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    # dot = ax*bx + ay*by + az*bz + aw*bw  (f32, source order x,y,z,w)
    dot = fp.fmadds(aw, bw, fp.fmadds(az, bz, fp.fmadds(ay, by, fp.fmuls(ax, bx))))
    if dot < 0.0:
        bw, bx, by, bz = -bw, -bx, -by, -bz
    td = float(t)
    om = 1.0 - td
    def lerp(ac, tc):
        return fp.f32(om * ac + td * tc)     # computed in f64, rounded to f32
    return (lerp(aw, bw), lerp(ax, bx), lerp(ay, by), lerp(az, bz))


# --- fres: PPC 750CL reciprocal estimate + 1 Newton step (matches Dolphin Interpreter) ----------
_FRES_BASE = [
    0x7ff800, 0x783800, 0x70ea00, 0x6a0800, 0x638800, 0x5d6200, 0x579000, 0x520800,
    0x4cc800, 0x47ca00, 0x430800, 0x3e8000, 0x3a2c00, 0x360800, 0x321400, 0x2e4a00,
    0x2aa800, 0x272c00, 0x23d600, 0x209e00, 0x1d8800, 0x1a9000, 0x17ae00, 0x14f800,
    0x124400, 0x0fbe00, 0x0d3800, 0x0ade00, 0x088400, 0x065000, 0x041c00, 0x020c00,
]
_FRES_DEC = [
    0x3e1, 0x3a7, 0x371, 0x340, 0x313, 0x2ea, 0x2c4, 0x2a0,
    0x27f, 0x261, 0x245, 0x22a, 0x212, 0x1fb, 0x1e5, 0x1d1,
    0x1be, 0x1ac, 0x19b, 0x18b, 0x17c, 0x16e, 0x15b, 0x15b,
    0x143, 0x143, 0x12d, 0x12d, 0x11a, 0x11a, 0x108, 0x106,
]

def _bits2d(u):
    return struct.unpack('>d', struct.pack('>Q', u & 0xFFFFFFFFFFFFFFFF))[0]

def _fres(x):
    """Hardware `fres` single-precision reciprocal estimate of x (no Newton). Matches Dolphin's
    Common::ApproximateReciprocal (750CL 5-bit-base + 10-bit-interp table)."""
    integral = struct.unpack('>Q', struct.pack('>d', x))[0]
    mantissa = integral & ((1 << 52) - 1)
    sign = integral & (1 << 63)
    exponent = integral & (0x7FF << 52)
    if mantissa == 0 and exponent == 0:
        return _bits2d(sign | (0x7FF << 52))          # 1/0 -> +-inf
    if exponent == (0x7FF << 52):
        return _bits2d(sign) if mantissa == 0 else 0.0 + x   # 1/inf=+-0; nan->nan
    if exponent < (895 << 52):
        return _bits2d(sign | (0x7FF << 52))          # tiny -> inf
    if exponent >= (1149 << 52):
        return _bits2d(sign)                          # huge -> 0
    i = mantissa >> 37                                 # top 15 mantissa bits
    base = _FRES_BASE[i >> 10]                         # top 5 bits index the base/dec table
    dec = _FRES_DEC[i >> 10]
    out = sign
    out |= ((0x7FD - (exponent >> 52)) << 52)
    out |= ((base - (dec * (i % 1024) + 1) // 2) << 29)
    return _bits2d(out)


def _recip2(denom):
    """2/denom via fres + one Newton refine + *2, matching PSMTXQuat's asm:
       est=fres(denom); r = est*(2 - denom*est); return r*2."""
    est = fp.f32(_fres(denom))
    r = fp.fmuls(est, fp.fnmsubs(denom, est, 2.0))   # est * (2 - denom*est)
    return fp.fmuls(r, 2.0)


def _recip2_of(denom, mode):
    """The PSMTXQuat scale s = 2/denom, in the requested rounding model:
      'fres' (default -- the true console path): the literal hardware `fres` table seed + one Newton
        multiply-refine `est*(2 - denom*est)`, then *2, exactly as the PSMTXQuat asm (mtx.c:1016) does.
        Bit-exact vs the live anmMtx once `_FRES_BASE` matches Dolphin's `fres_expected` (it now does;
        the old table had 8 wrong high-index entries -> the seed was ~1 ULP off for denom<1, which only
        the WALK<->DASH BLEND poses hit, since JMAQuatLerp doesn't renormalize -> a lerped quat's
        denom = w2+x2+y2+z2 drops below 1 -> the high table indices. Single-anim poses have denom~=1
        -> index 0, always correct, which is why non-blend frames looked fine with the broken table).
      'newton': one Newton refine seeded by an ACCURATE fdivs 1/denom instead of the crude `fres` table.
        Matches the console on most denoms but NOT the WALK<->DASH blend poses (an accurate seed refined
        once lands on the other side of a rounding boundary from the crude fres seed there).
      'fdivs': raw IEEE 2/denom (differs from the console by 1 ULP at half-ULP division midpoints)."""
    if mode == 'fdivs':
        return fp.fdivs(2.0, denom)
    if mode == 'fres':
        return _recip2(denom)
    est = fp.fdivs(1.0, denom)                        # accurate seed (>= console fres+refine accuracy)
    r = fp.fmuls(est, fp.fnmsubs(denom, est, 2.0))    # est * (2 - denom*est): the console's Newton refine
    return fp.fmuls(r, 2.0)


# --- paired-single register ops (each reg = [ps0, ps1]); scalar single ops broadcast to both lanes ---
def _psmul(a, c):    return [fp.fmuls(a[0], c[0]), fp.fmuls(a[1], c[1])]
def _psmadd(a, c, b):return [fp.fmadds(a[0], c[0], b[0]), fp.fmadds(a[1], c[1], b[1])]
def _psmsub(a, c, b):return [fp.fmsubs(a[0], c[0], b[0]), fp.fmsubs(a[1], c[1], b[1])]
def _psnmsub(a, c, b):return [fp.fnmsubs(a[0], c[0], b[0]), fp.fnmsubs(a[1], c[1], b[1])]
def _psmadds0(a, c, b):return [fp.fmadds(a[0], c[0], b[0]), fp.fmadds(a[1], c[0], b[1])]  # frC.ps0 both lanes
def _psmuls1(a, c):  return [fp.fmuls(a[0], c[1]), fp.fmuls(a[1], c[1])]                  # frC.ps1 both lanes
def _pssum0(a, c, b):return [fp.fadds(a[0], b[1]), c[1]]                                   # ps0=A.ps0+B.ps1; ps1=C.ps1
def _pssum1(a, c, b):return [c[0], fp.fadds(a[0], b[1])]                                   # ps0=C.ps0; ps1=A.ps0+B.ps1


def psmtx_quat(q, scale_mode='fres'):
    """Literal paired-single port of the retail **PSMTXQuat** asm (mtx.c:1016), which is what
    `mDoMtx_quat` (and thus the CL foot chain) actually uses -- NOT `C_MTXQuat`. The off-diagonals are
    computed **fused then scaled** (`m[0][1]=(x*y - z*w)*s` via ps_msub, one rounding on the product-
    difference), unlike `mtx_quat`'s element-wise `x*(y*s)-w*(z*s)`. This is bit-exact vs the live
    `anmMtx` rotation for all-nonzero quats (validated element-wise vs jnt0). q=(w,x,y,z) -> 3x4 (trans=0).

    scale_mode: 'fres' (default -- the true console path) uses the hardware `fres` table seed + one Newton
    refine, exactly as the asm. This is bit-exact vs the live anmMtx for ALL poses, single-anim AND
    WALK<->DASH blend, now that `_FRES_BASE` matches Dolphin's `fres_expected` (see _recip2_of; the old
    table's 8 wrong high-index entries only bit the blend poses, whose un-renormalized lerped quat has
    denom<1 -> high table index). Combined with a WORLD-space foot FK (fk.world_base -- the game quantizes
    the foot matrices at world magnitude ~764), the leg chain jnt0..jnt33 is BIT-EXACT vs the live anmMtx.
    See knowledge/model/sim.md (world-space FK + fres sections).

    HISTORY: the "planted foot jnt34/39 ~1 ULP" was two stacked bugs, both fixed. (1) `euler_to_quat` fused
    x/y (JMAEulerToQuat is NON-fused). (2) the blend-frame residual that survived was NOT matrix-accumulation
    rounding (PSMTXConcat/PSMTXMultVec were verified against the asm and are exact) -- it was the wrong
    `_FRES_BASE` table (here) PLUS a fused translate/scale blend in foot_fk (m_Do_ext.cpp:1183 is non-fused).
    With all three fixed, the walk-blend foot toe is bit-exact vs the live anmMtx/field_0x018. A residual
    remains only at the ENTRY-morf frames (jnt0.z ~5 ULP, decaying with the morf rate) -- a separate
    calc_transform/Hermite sub-ULP, not this path. See knowledge/model/sim.md."""
    w, x, y, z = q
    tmp0 = [x, y]; tmp1 = [z, w]
    c_one = [1.0, 1.0]
    _z = fp.fsubs(1.0, 1.0); c_zero = [_z, _z]
    _t = fp.fadds(1.0, 1.0); c_two = [_t, _t]
    tmp2 = _psmul(tmp0, tmp0)
    tmp5 = [tmp0[1], tmp0[0]]                      # ps_merge10(tmp0,tmp0) = [y, x]
    tmp4 = _psmadd(tmp1, tmp1, tmp2)
    tmp3 = _psmul(tmp1, tmp1)
    scale = _pssum0(tmp4, tmp4, tmp4)             # scale.ps0 = denom = x*x+y*y+z*z+w*w
    tmp7 = _psmuls1(tmp5, tmp1)
    denom = scale[0]
    s = _recip2_of(denom, scale_mode)
    scale = [s, s]
    tmp4 = _pssum1(tmp3, tmp4, tmp2)
    tmp6 = _psmuls1(tmp1, tmp1)                   # [z*w, w*w]
    tmp2 = _pssum0(tmp2, tmp2, tmp2)             # [x*x+y*y, y*y]
    tmp8 = _psmadd(tmp0, tmp5, tmp6)             # [x*y+z*w, y*x+w*w]
    tmp6 = _psmsub(tmp0, tmp5, tmp6)             # [x*y-z*w, y*x-w*w]
    m = [[0.0]*4 for _ in range(3)]
    tmp2 = _psnmsub(tmp2, scale, c_one)          # m[2][2] = 1-(xx+yy)*s
    tmp4 = _psnmsub(tmp4, scale, c_one)          # [1-(zz+xx)*s, 1-(zz+yy)*s]
    tmp8 = _psmul(tmp8, scale); tmp6 = _psmul(tmp6, scale)
    m[2][2] = tmp2[0]
    tmp5 = _psmadds0(tmp0, tmp1, tmp7)           # [x*z+y*w, y*z+x*w]
    tmp1b = [tmp8[0], tmp4[0]]                    # [m10, m11]
    tmp7 = _psnmsub(tmp7, c_two, tmp5)           # [x*z-y*w, y*z-x*w]
    tmp0b = [tmp4[1], tmp6[0]]                    # [m00, m01]
    m[1][0] = tmp1b[0]; m[1][1] = tmp1b[1]
    tmp5 = _psmul(tmp5, scale); tmp7 = _psmul(tmp7, scale)
    m[0][0] = tmp0b[0]; m[0][1] = tmp0b[1]; m[0][2] = tmp5[0]
    tmp3 = [tmp7[1], c_zero[0]]                   # [m12, 0]
    tmp9 = [tmp7[0], tmp5[1]]                     # [m20, m21]
    m[1][2] = tmp3[0]; m[2][0] = tmp9[0]; m[2][1] = tmp9[1]
    return m


# Optional native (bit-exact) hot quat ops (anim/_anmc.pyx); absent -> the pure-Python defs above run.
# psmtx_quat's non-default scale modes stay on the Python path (off the foot loop). See fp-faithfulness.md.
try:
    from . import _anmc as _N
    _N.init_tables(S._COS_TABLE, S._SIN_TABLE)
    euler_to_quat = _N.euler_to_quat
    quat_lerp = _N.quat_lerp
    _py_psmtx_quat = psmtx_quat

    def psmtx_quat(q, scale_mode='fres'):        # noqa: F811 - native dispatcher over the Python impl
        return _N.psmtx_quat(q) if scale_mode == 'fres' else _py_psmtx_quat(q, scale_mode)
except ImportError:
    pass


def mtx_quat(q, scale_mode='fres'):
    """C_MTXQuat math (mtx.c:970), fused ops. q=(w,x,y,z). Returns 3x4 rotation matrix (trans=0).

    NOTE: the CL foot chain actually uses PSMTXQuat (see psmtx_quat above) whose off-diagonal grouping
    differs by ~1 ULP; this element-wise form is kept for the direct-euler / non-foot paths."""
    w, x, y, z = q
    denom = fp.fadds(fp.fmuls(w, w), fp.fadds(fp.fmuls(z, z), fp.fadds(fp.fmuls(x, x), fp.fmuls(y, y))))
    if scale_mode == 'fdivs':
        s = fp.fdivs(2.0, denom)
    else:
        s = _recip2(denom)
    xs, ys, zs = fp.fmuls(x, s), fp.fmuls(y, s), fp.fmuls(z, s)
    wx, wy, wz = fp.fmuls(w, xs), fp.fmuls(w, ys), fp.fmuls(w, zs)
    xx, xy, xz = fp.fmuls(x, xs), fp.fmuls(x, ys), fp.fmuls(x, zs)
    yy, yz, zz = fp.fmuls(y, ys), fp.fmuls(y, zs), fp.fmuls(z, zs)
    m = [[0.0]*4 for _ in range(3)]
    m[0][0] = fp.fsubs(1.0, fp.fadds(yy, zz))
    m[0][1] = fp.fsubs(xy, wz)
    m[0][2] = fp.fadds(xz, wy)
    m[1][0] = fp.fadds(xy, wz)
    m[1][1] = fp.fsubs(1.0, fp.fadds(xx, zz))
    m[1][2] = fp.fsubs(yz, wx)
    m[2][0] = fp.fsubs(xz, wy)
    m[2][1] = fp.fadds(yz, wx)
    m[2][2] = fp.fsubs(1.0, fp.fadds(xx, yy))
    return m
