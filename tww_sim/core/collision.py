"""FP-faithful port of TWW's player WALL collision resolution.

Ports the horizontal-blocking parts of `dBgS_Acch::CrrPos` — the two barriers that stop or
redirect Link's XZ movement each frame:

  * **LineCheck** (swept): tests Link's centre-line ``old -> new`` against each wall triangle via
    ``cM3d_Cross_LinTri`` = plane crossing (``cM3d_Cross_LinPla``) + projected point-in-triangle
    (``cM3d_CrossX/Y/Z_Tri``). Front-to-back only (``frontFlag=1``). Runs only when the horizontal
    displacement exceeds the wall radius.
  * **WallCorrect** (static): pushes Link's wall cylinder (radius 35) out of any wall it overlaps at
    the NEW position (``dBgW::RwgWallCorrect`` + ``positionWallCorrect`` / ``cM2d_CrossCirLin``).

Given ``old_pos`` and the intended ``new_pos`` (= old + one frame of velocity), :func:`crr_pos_walls`
returns the position the game would resolve to. If it stays at ``new_pos`` the move "clipped"
(collision didn't interfere); otherwise Link was blocked / pushed.

**Bit-exact vs the console.** Arithmetic uses the fused-multiply-add single-precision ops in
:mod:`tww_sim.core.fp`. The one fused op in this path that a naive separate-rounding port gets
wrong is the plane function's dot product: ``PSVECDotProduct`` (paired-single) computes
``dot = fadds(fmadds(nx,px, fmuls(ny,py)), fmuls(nz,pz))`` — ``nx*px + ny*py`` is fused (rounds
once). ``cM3d_VectorProduct2d`` and the crossing interpolation (``cM3d_InDivPos1/2``) are NOT fused
in the compiled code, so they use separate rounds. Validated live on GZLJ01 (GanonL grand-staircase
seam): reproduces the game's per-triangle crossing points to f32 and every hit/miss (24/24 live
cases). See ``knowledge/mechanics/seam-clip.md``.

**Plane normals.** Each triangle's plane is *computed at room load* by ``cM3d_CalcPla``
(``normalize(cross(v1-v0, v2-v0))``, ``d=-dot(n,v0)``) — planes are NOT stored in the DZB
(``cBgW::ClassifyPlane`` -> ``cM3d_CalcPla``, c_bg_w.cpp). The two triangles of one wall quad
normalise independently and differ in the last mantissa bits, and that difference is exactly what
opens the seam gap. :func:`calc_pla` ports ``cM3d_CalcPla`` **bit-exactly** — verified against all
4506 Hyrule RAM planes (4506/4506, every field). Three console-faithful details make it exact:
(1) ``PSVECCrossProduct``'s exact paired-single lanes (the ``nx`` lane fuses ``a.y*b.z`` and
pre-rounds ``b.y*a.z``; asm @ 0x8030BC14); (2) the ``VECMag`` Newton step is the FUSED
``fnmsubs 3.0 - esq*sq``; (3) Gekko single-precision ``fmuls`` rounds its ``frC`` operand to 25
mantissa bits first (Dolphin ``Force25Bit``) — a no-op for f32 operands but essential for ``e*e``,
where ``e`` is the ~27-bit ``frsqrte`` estimate (see :func:`_force25`). This means the
synthetic-geometry path (arbitrary corner angles) is now trustworthy. Reading the plane from RAM
(``cBgW.pm_tri``, stride 0x18) via ``Tri(v0,v1,v2, plane=Plane(*n, d))`` is still the simplest path
for a real seam, but :func:`calc_pla` reproduces it.

Decomp refs: ``src/SSystem/SComponent/c_m3d.cpp`` (``cM3d_Cross_Lin*``, ``cM3d_CrossX/Y/Z_Tri``),
``c_m2d.cpp`` (``cM2d_CrossCirLin``), ``src/d/d_bg_w.cpp`` (``RwgWallCorrect``), ``src/d/d_bg_s_acch.cpp``
(``CrrPos``/``LineCheck``). Pure stdlib + ``core.fp``; no Dolphin dependency.
"""
import math
import struct

from .fp import f32 as _f, fadds, fsubs, fmuls, fdivs, fmadds, fmsubs, fnmsubs

# LEGACY IsZero threshold, frozen as live-validated (real console value is 2^-18 -- the acch_*
# layer uses that via is_zero_x; the two only differ in [2^-18, 1e-5), see wall-response.md).
G_CM3D_F_ABS_MIN = 1.0e-5


def is_zero(x):
    return abs(_f(x)) < G_CM3D_F_ABS_MIN


# Exact console threshold (2^-18) for the acch_* layer.
_IS0X = 2.0 ** -18


def is_zero_x(x):
    return abs(_f(x)) < _IS0X


def fsqrt(a):
    return _f(math.sqrt(_f(a)))


def sqrtf_msl(x):
    """``std::sqrtf`` AS THE GAME LINKS IT (MSL ``math.h``): ``__frsqrte`` then THREE
    double-precision Newton steps, then a single f32 round of ``x * guess`` -- **not** a
    correctly-rounded square root.

    Verified in the shipped JP binary (session 55): ``dCcS::SetPosCorrect`` 0x800AB444 inlines
    exactly this shape -- ``frsqrte``, then 3x ``fmul/fmul/fmul/fsub/fmul`` in double (op 63, no
    fused ``fmadd``), then ``fmul`` + the f32 store. Same inline sits in ``cM3d_Cross_CylCyl``.

    In practice the 3-step Newton residual is ~2^-32 relative, so this agrees with a correctly
    rounded ``sqrtf`` on all but pathological operands -- it is here because the push chain is a
    0-ULP surface and the primitive should be the game's, not because it is known to differ.
    :func:`fsqrt` stays for the other (separately live-gated) call sites."""
    x = float(_f(x))
    if x > 0.0:
        g = frsqrte(x)
        for _ in range(3):                 # 12 -> 24 -> 32 significant bits (the MSL comments)
            g = 0.5 * g * (3.0 - g * g * x)
        return _f(x * g)
    return _f(x)


# surface classification -- wall/ground/roof (WallCorrect vs GroundCross) = a pure face-normal-Y test,
# NOT a stored attribute. Decomp cBgW_CheckB* (c_bg_w.h); rationale: knowledge/mechanics/collision.md.
BG_GROUND_NY = 0.5             # cBgW_CheckBGround: ny >= 0.5  -> ground
BG_ROOF_NY = -4.0 / 5.0        # cBgW_CheckBRoof:   ny < -0.8  -> roof


def bg_is_ground(ny):
    return ny >= BG_GROUND_NY


def bg_is_roof(ny):
    return ny < BG_ROOF_NY


def bg_is_wall(ny):
    """cBgW_CheckBWall: neither ground nor roof, i.e. -0.8 <= ny < 0.5. This is the class whose
    triangles form clippable wall seams (NOT the old |ny|<0.03 near-vertical-only heuristic -- that
    dropped sloped walls the game braces against; see knowledge/mechanics/seam-clip-scanner.md)."""
    return not bg_is_ground(ny) and not bg_is_roof(ny)


def bg_blocks_crrpos(ny):
    """The XZ-blocking set the game's CrrPos actually walks: WallCorrectRp / RwgWallCrrPos process a
    block's WALL *and* ROOF poly lists (d_bg_w.cpp), i.e. everything that is NOT ground. Near-flat
    roofs self-skip inside wall_correct (their nx^2+nz^2 is-zero). Feed THIS set to crr_pos_walls."""
    return not bg_is_ground(ny)


# Gekko frsqrte (reciprocal-sqrt estimate) — Dolphin's exact table + algorithm. VECMag/cM3d_CalcPla
# normalise via frsqrte+Newton (not correctly-rounded sqrt); the ~1-ULP difference flips seam clips.
_FRSQRTE = [
    (0x1a7e800,-0x568),(0x17cb800,-0x4f3),(0x1552800,-0x48d),(0x130c000,-0x435),
    (0x10f2000,-0x3e7),(0x0eff000,-0x3a2),(0x0d2e000,-0x365),(0x0b7c000,-0x32e),
    (0x09e5000,-0x2fc),(0x0867000,-0x2d0),(0x06ff000,-0x2a8),(0x05ab800,-0x283),
    (0x046a000,-0x261),(0x0339800,-0x243),(0x0218800,-0x226),(0x0105800,-0x20b),
    (0x3ffa000,-0x7a4),(0x3c29000,-0x700),(0x38aa000,-0x670),(0x3572000,-0x5f2),
    (0x3279000,-0x584),(0x2fb7000,-0x524),(0x2d26000,-0x4cc),(0x2ac0000,-0x47e),
    (0x2881000,-0x43a),(0x2665000,-0x3fa),(0x2468000,-0x3c2),(0x2287000,-0x38e),
    (0x20c1000,-0x35e),(0x1f12000,-0x332),(0x1d79000,-0x30a),(0x1bf4000,-0x2e6),
]

def _ctrunc_div2(a):
    return int(a/2) if a >= 0 else -((-a)//2)   # C s64 /2 (truncate toward zero)

def frsqrte(val):
    integral = struct.unpack("<q", struct.pack("<d", val))[0]
    mantissa = integral & ((1<<52)-1)
    sign = integral & (1<<63)
    exponent = integral & (0x7FF<<52)
    if mantissa == 0 and exponent == 0:
        return float("-inf") if sign else float("inf")
    if exponent == (0x7FF<<52):
        return (float("nan") if sign else 0.0) if mantissa == 0 else val
    if sign:
        return float("nan")
    if not exponent:
        while not (mantissa & (1<<52)):
            exponent -= 1<<52; mantissa <<= 1
        mantissa &= (1<<52)-1
        exponent += 1<<52
    exponent_lsb = exponent & (1<<52)
    exponent = ((0x3FF<<52) - _ctrunc_div2(exponent - (0x3FE<<52))) & (0x7FF<<52)
    integral = sign | exponent
    i = (exponent_lsb | mantissa) >> 37
    base, dec = _FRSQRTE[i//2048]
    integral = (integral | ((base + dec*(i%2048)) << 26)) & ((1<<64)-1)
    return struct.unpack("<d", struct.pack("<Q", integral))[0]

def _force25(d):
    """Round ``d`` to 25 mantissa bits, matching Dolphin ``Force25Bit`` (Interpreter_FPUtils.h): the
    Gekko rounds a single-precision op's ``frC`` operand to 25 bits first. See seam-clip.md FP note."""
    MASK = (1 << 64) - 1
    i = struct.unpack("<Q", struct.pack("<d", d))[0]
    if (i & (0x7FF << 52)) == 0 and (i & ((1 << 52) - 1)) != 0:
        # subnormal: shift the keep-mask/round bit right until the fraction is "normal"
        frac = i & ((1 << 52) - 1)
        shift = (64 - frac.bit_length()) - 11
        keep = ((0xFFFFFFFFF8000000 | ~MASK) >> shift) & MASK   # arithmetic >> of the s64 mask
        rnd = 0x8000000 >> shift
        i = ((i & keep) + (i & rnd)) & MASK
    else:
        i = ((i & 0xFFFFFFFFF8000000) + (i & 0x8000000)) & MASK
    return struct.unpack("<d", struct.pack("<Q", i))[0]


def vecmag(x, y, z):
    """PSVECMag: sqrt via frsqrte + one Newton step. sq = ((z*z+x*x)[fused] + y*y)."""
    sq = fadds(fmadds(z, z, fmuls(x, x)), fmuls(y, y))
    if sq == 0.0:
        return 0.0
    e = frsqrte(sq)
    esq = fmuls(e, _force25(e))      # fmuls e,e: Gekko rounds the frC operand (e) to 25 bits first
    half_e = fmuls(e, 0.5)           # frC = 0.5 (exact) -> Force25Bit is a no-op here
    t = fnmsubs(esq, sq, 3.0)        # fnmsubs nwork0, nwork0, sqmag, c_three: FUSED 3.0 - esq*sq
    return fmuls(sq, fmuls(t, half_e))


# --------------------------------------------------------------------------- plane
class Plane:
    """A wall triangle's plane: unit-ish normal (nx,ny,nz) + offset d, matching the game's stored
    ``cM3dGPla``. ``func(p) = d + n.p`` reproduces ``getPlaneFunc`` via ``PSVECDotProduct``."""
    __slots__ = ("nx", "ny", "nz", "d")

    def __init__(self, nx, ny, nz, d):
        self.nx = _f(nx); self.ny = _f(ny); self.nz = _f(nz); self.d = _f(d)

    def func(self, p):
        ny_py = fmuls(self.ny, p[1])
        nz_pz = fmuls(self.nz, p[2])
        dot = fadds(fmadds(self.nx, p[0], ny_py), nz_pz)   # nx*px + ny*py FUSED (ps_madd lane)
        return fadds(self.d, dot)


def calc_pla(v0, v1, v2):
    """``cM3d_CalcPla``, bit-exact to the console. normalize(cross(v1-v0, v2-v0)); d = -dot(n, v0),
    with the cross as fused ``-(a*b - c)``, magnitude via :func:`vecmag` (frsqrte), reciprocal via
    ``fdivs``, and the dot as the fused ``PSVECDotProduct``. Reproduces the game's stored planes
    bit-for-bit (verified vs RAM at the GanonL seam)."""
    v0 = tuple(_f(c) for c in v0); v1 = tuple(_f(c) for c in v1); v2 = tuple(_f(c) for c in v2)
    ax, ay, az = fsubs(v1[0], v0[0]), fsubs(v1[1], v0[1]), fsubs(v1[2], v0[2])
    bx, by, bz = fsubs(v2[0], v0[0]), fsubs(v2[1], v0[1]), fsubs(v2[2], v0[2])
    # cross = PSVECCrossProduct's exact paired-single lanes (asm @ 0x8030BC14 JP; see seam-clip.md FP
    # note): the fused term is a.?*b.?, the OTHER product is pre-rounded by a separate ps_mul.
    nx = _f(fmsubs(ay, bz, fmuls(by, az)))
    ny = _f(-fmsubs(ax, bz, fmuls(bx, az)))
    nz = _f(-fmsubs(ay, bx, fmuls(by, ax)))
    t = vecmag(nx, ny, nz)
    if abs(_f(t)) >= 0.02:
        inv = fdivs(1.0, t)
        nx = fmuls(nx, inv); ny = fmuls(ny, inv); nz = fmuls(nz, inv)
        # d = -VECDotProduct(n, v0)  (fused PSVECDotProduct)
        d = _f(-fadds(fmadds(nx, v0[0], fmuls(ny, v0[1])), fmuls(nz, v0[2])))
        return Plane(nx, ny, nz, d)
    return Plane(0.0, 0.0, 0.0, 0.0)


class Tri:
    """Wall triangle: three world verts + a plane. Pass ``plane=Plane(*n, d)`` with the game's
    STORED plane for bit-exact results; otherwise :func:`calc_pla` is used (reference only)."""
    __slots__ = ("v0", "v1", "v2", "pla")

    def __init__(self, v0, v1, v2, plane=None):
        self.v0 = tuple(_f(c) for c in v0)
        self.v1 = tuple(_f(c) for c in v1)
        self.v2 = tuple(_f(c) for c in v2)
        self.pla = plane if plane is not None else calc_pla(self.v0, self.v1, self.v2)


# ------------------------------------------------------------------ line vs plane
def indiv_pos2(v0, v1, scale):
    """cM3d_InDivPos2/1: v0 + (v1-v0)*scale, per component (VECSubtract, VECScale, VECAdd — each
    a separate round; not fused)."""
    return (fadds(v0[0], fmuls(fsubs(v1[0], v0[0]), scale)),
            fadds(v0[1], fmuls(fsubs(v1[1], v0[1]), scale)),
            fadds(v0[2], fmuls(fsubs(v1[2], v0[2]), scale)))


def cross_lin_pla(start, end, pla, a=True, b=False):
    """cM3d_Cross_LinPla -> (crossed, point). a=frontFlag, b=backFlag."""
    sv = pla.func(start)
    ev = pla.func(end)
    if fmuls(sv, ev) > 0.0:
        return False, end
    if sv >= 0.0 and ev <= 0.0:        # front -> back
        if a:
            return _cross_proc(sv, ev, start, end)
    else:                               # back -> front
        if b:
            return _cross_proc(sv, ev, start, end)
    return False, end


def _cross_proc(a, b, pA, pB):
    if is_zero(fsubs(a, b)):
        return False, pB
    return True, indiv_pos2(pA, pB, fdivs(a, fsubs(a, b)))


# ------------------------------------------------------ projected point-in-triangle
def vprod2d(x1, y1, x2, y2, x3, y3):
    """cM3d_VectorProduct2d = (x2-x1)*(y3-y1) - (y2-y1)*(x3-x1). Separate rounds (not fused)."""
    return fsubs(fmuls(fsubs(x2, x1), fsubs(y3, y1)), fmuls(fsubs(y2, y1), fsubs(x3, x1)))


def incl_box2d(ax, ay, bx, by, cx, cy, px, py):
    """cM3d_InclusionCheckPosIn3PosBox2d: point within the AABB of the 3 projected verts (strict)."""
    if ax < bx: f31, f30 = ax, bx
    else:       f31, f30 = bx, ax
    if f31 > cx: f31 = cx
    elif f30 < cx: f30 = cx
    if f31 > px or f30 < px: return False
    if ay < by: f31, f30 = ay, by
    else:       f31, f30 = by, ay
    if f31 > cy: f31 = cy
    elif f30 < cy: f30 = cy
    if f31 > py or f30 < py: return False
    return True


def _tri_in_2d(ax, ay, bx, by, cx, cy, px, py):
    """Shared body of CrossX/Y/Z_Tri: AABB gate + signed-area edge tests with a +/-20 area tolerance
    on BOTH windings."""
    if not incl_box2d(ax, ay, bx, by, cx, cy, px, py):
        return False
    f12 = vprod2d(ax, ay, bx, by, px, py)
    if (f12 <= 20.0
            and vprod2d(bx, by, cx, cy, px, py) <= 20.0
            and vprod2d(cx, cy, ax, ay, px, py) <= 20.0):
        return True
    if (f12 >= -20.0
            and vprod2d(bx, by, cx, cy, px, py) >= -20.0
            and vprod2d(cx, cy, ax, ay, px, py) >= -20.0):
        return True
    return False


def crossX_tri(tri, pos):
    if is_zero(tri.pla.nx): return False
    v0, v1, v2 = tri.v0, tri.v1, tri.v2
    return _tri_in_2d(v0[1], v0[2], v1[1], v1[2], v2[1], v2[2], pos[1], pos[2])


def crossY_tri(tri, pos):
    if is_zero(tri.pla.ny): return False
    v0, v1, v2 = tri.v0, tri.v1, tri.v2
    return _tri_in_2d(v0[2], v0[0], v1[2], v1[0], v2[2], v2[0], pos[2], pos[0])


def crossZ_tri(tri, pos):
    if is_zero(tri.pla.nz): return False
    v0, v1, v2 = tri.v0, tri.v1, tri.v2
    return _tri_in_2d(v0[0], v0[1], v1[0], v1[1], v2[0], v2[1], pos[0], pos[1])


def cross_y_tri_front(v0, v1, v2, px, pz):
    """cM3d_CrossY_Tri_Front (c_m3d.cpp): the game's GROUND point-in-triangle. Projects to (z, x),
    strict AABB gate (``incl_box2d``), then all three ``vprod2d >= -20`` (the FRONT winding only --
    NOT the two-winding ``_tri_in_2d`` used by the swept wall crossing). This is exactly the test
    ``cBgW::RwgGroundCheckCommon`` runs to decide whether Link stands on a ground poly, so it is the
    faithful standability predicate: a point a hair past a floor edge (where a settled ``old`` parks,
    WallCorrect having braced it against a seam wall that overhangs the floor lip) is rejected here
    exactly as GroundCross rejects it -- unlike a loose barycentric eps. See seam-clip-scanner.md."""
    if not incl_box2d(v0[2], v0[0], v1[2], v1[0], v2[2], v2[0], pz, px):
        return False
    return (vprod2d(v0[2], v0[0], v1[2], v1[0], pz, px) >= -20.0
            and vprod2d(v1[2], v1[0], v2[2], v2[0], pz, px) >= -20.0
            and vprod2d(v2[2], v2[0], v0[2], v0[0], pz, px) >= -20.0)


def ground_cross_y(pla, px, pz):
    """cM3dGPla::getCrossY_NonIsZero: the Y where (px, y, pz) lies on the plane (assumes ny != 0).
    ``y = (-nx*px - nz*pz - d) / ny`` -- the game's ground height at an XZ point."""
    return fdivs(fsubs(fsubs(fmuls(_f(-pla.nx), px), fmuls(pla.nz, pz)), pla.d), pla.ny)


def cross_lin_tri(start, end, tri, a=True, b=False):
    """cM3d_Cross_LinTri -> (hit, point). Plane crossing + point-in-triangle in the projections
    whose normal component is significant (|n_axis| >= 0.008)."""
    crossed, dst = cross_lin_pla(start, end, tri.pla, a, b)
    if not crossed:
        return False, dst
    n = tri.pla
    okx = (abs(n.nx) < 0.008) or crossX_tri(tri, dst)
    oky = (abs(n.ny) < 0.008) or crossY_tri(tri, dst)
    okz = (abs(n.nz) < 0.008) or crossZ_tri(tri, dst)
    return (okx and oky and okz), dst


# --------------------------------------------------------------------- LineCheck
def line_check(old_pos, new_pos, tris, wall_h):
    """dBgS_Acch::LineCheck over the wall cylinders. Returns (hit, snapped_new_pos). For a vertical
    wall the XZ crossing is height-independent, but all cylinder heights are run for fidelity."""
    pos = list(new_pos)
    hit_any = False
    for h in wall_h:
        start = (old_pos[0], fadds(old_pos[1], h), old_pos[2])
        end = (pos[0], fadds(pos[1], h), pos[2])
        cur_end = end
        hit_here = False
        for tri in tris:                          # LineCross: nearest front crossing shrinks the line
            crossed, pt = cross_lin_tri(start, cur_end, tri, a=True, b=False)
            if crossed:
                cur_end = pt
                hit_here = True
        if hit_here:
            hit_any = True
            pos[0] = cur_end[0]
            pos[2] = cur_end[2]
            pos[1] = fsubs(cur_end[1], h)
    return hit_any, tuple(pos)


# ------------------------------------------------------------------- WallCorrect
def len2dsq(x0, y0, x1, y1):
    return fadds(fmuls(fsubs(x0, x1), fsubs(x0, x1)), fmuls(fsubs(y0, y1), fsubs(y0, y1)))


def len2dsq_pnt_seg(xp, yp, x0, y0, x1, y1):
    """cM3d_Len2dSqPntAndSegLine -> (on_segment, outx, outy, seg_sqdist)."""
    xd = fsubs(x1, x0); yd = fsubs(y1, y0)
    dot = fadds(fmuls(xd, xd), fmuls(yd, yd))
    if is_zero(dot):
        return False, x0, y0, 0.0
    mag = fdivs(fadds(fmuls(xd, fsubs(xp, x0)), fmuls(yd, fsubs(yp, y0))), dot)
    on = (0.0 <= mag <= 1.0)
    outx = fadds(x0, fmuls(xd, mag))
    outy = fadds(y0, fmuls(yd, mag))
    return on, outx, outy, len2dsq(outx, outy, xp, yp)


def cross_cir_lin(cx, cy, r, x0, y0, dirx, diry):
    """cM2d_CrossCirLin -> (px, py): furthest intersection of the ray (x0,y0)+t*(dirx,diry) with the
    circle (cx,cy,r)."""
    fv1 = fsubs(x0, cx); fv15 = fsubs(y0, cy)
    d13 = fadds(fmuls(dirx, dirx), fmuls(diry, diry))
    d14 = fmuls(2.0, fadds(fmuls(dirx, fv1), fmuls(diry, fv15)))
    c = fsubs(fadds(fmuls(fv1, fv1), fmuls(fv15, fv15)), fmuls(r, r))
    t = 0.0
    if is_zero(d13):
        if not is_zero(d14):
            t = fdivs(_f(-c), d14)
    else:
        disc = fsubs(fmuls(d14, d14), fmuls(fmuls(4.0, d13), c))
        if is_zero(disc):
            t = fdivs(_f(-d14), fmuls(2.0, d13))
        elif disc < 0.0:
            t = 0.0
        else:
            k = fdivs(1.0, fmuls(2.0, d13))
            s = fsqrt(disc)
            r1 = fmuls(k, fadds(_f(-d14), s))
            r2 = fmuls(k, fsubs(_f(-d14), s))
            t = r1 if r1 > r2 else r2
    if is_zero(t):
        return x0, y0
    return fadds(x0, fmuls(t, dirx)), fadds(y0, fmuls(t, diry))


def wall_correct(new_pos, speed_y, tris, wall_h, wall_r):
    """dBgW::RwgWallCorrect over all tris x cylinders (static cylinder at ``new_pos``). Assumes no
    ground-find (GetWallAddY == 0) and ChkWallHDirect false. Returns (corrected_pos, wall_hit)."""
    pos = list(new_pos)
    wrr = fmuls(wall_r, wall_r)
    hit = False
    for tri in tris:
        n = tri.pla
        sp68 = fsqrt(fadds(fmuls(n.nx, n.nx), fmuls(n.nz, n.nz)))
        if is_zero(sp68):
            continue
        sp6C = fdivs(1.0, sp68)
        for h in wall_h:
            sp78 = fmuls(sp6C, wall_r)
            sp50x = fmuls(sp78, n.nx); sp50z = fmuls(sp78, n.nz)
            sp7C = fsubs(fadds(0.0, fadds(pos[1], h)), speed_y)
            s0 = fsubs(tri.v0[1], sp7C)
            s1 = fsubs(tri.v1[1], sp7C)
            s2 = fsubs(tri.v2[1], sp7C)
            if (s0 > 0.0 and s1 > 0.0 and s2 > 0.0) or (s0 < 0.0 and s1 < 0.0 and s2 < 0.0):
                continue
            zc = is_zero(s0) + is_zero(s1) + is_zero(s2)
            if zc == 1:
                continue
            if (s0 > 0.0 and s1 <= 0.0 and s2 <= 0.0) or (s0 < 0.0 and s1 >= 0.0 and s2 >= 0.0):
                i0, i1, i2 = 0, 1, 2
            elif (s1 > 0.0 and s0 <= 0.0 and s2 <= 0.0) or (s1 < 0.0 and s0 >= 0.0 and s2 >= 0.0):
                i0, i1, i2 = 1, 0, 2
            else:
                i0, i1, i2 = 2, 0, 1
            s = (s0, s1, s2)
            sp90 = fsubs(s[i0], s[i1]); sp94 = fsubs(s[i0], s[i2])
            if is_zero(sp90) or is_zero(sp94):
                continue
            sp98 = fdivs(_f(-s[i1]), sp90); sp9C = fdivs(_f(-s[i2]), sp94)
            V = (tri.v0, tri.v1, tri.v2)
            vx = [V[0][0], V[1][0], V[2][0]]; vz = [V[0][2], V[1][2], V[2][2]]
            if i0 == 0:
                cx0 = fadds(vx[1], fmuls(sp98, fsubs(vx[0], vx[1]))); cy0 = fadds(vz[1], fmuls(sp98, fsubs(vz[0], vz[1])))
                cx1 = fadds(vx[2], fmuls(sp9C, fsubs(vx[0], vx[2]))); cy1 = fadds(vz[2], fmuls(sp9C, fsubs(vz[0], vz[2])))
            elif i0 == 1:
                cx0 = fadds(vx[0], fmuls(sp98, fsubs(vx[1], vx[0]))); cy0 = fadds(vz[0], fmuls(sp98, fsubs(vz[1], vz[0])))
                cx1 = fadds(vx[2], fmuls(sp9C, fsubs(vx[1], vx[2]))); cy1 = fadds(vz[2], fmuls(sp9C, fsubs(vz[1], vz[2])))
            else:
                cx0 = fadds(vx[0], fmuls(sp98, fsubs(vx[2], vx[0]))); cy0 = fadds(vz[0], fmuls(sp98, fsubs(vz[2], vz[0])))
                cx1 = fadds(vx[1], fmuls(sp9C, fsubs(vx[2], vx[1]))); cy1 = fadds(vz[1], fmuls(sp9C, fsubs(vz[2], vz[1])))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            on, ccx, ccy, seg = len2dsq_pnt_seg(pos[0], pos[2], cx0o, cy0o, cx1o, cy1o)
            d4 = fsubs(ccx, pos[0]); d8 = fsubs(ccy, pos[2])
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:
                move = fmuls(sp6C, fsqrt(seg))
                pos[0] = fadds(pos[0], fmuls(move, n.nx))
                pos[2] = fadds(pos[2], fmuls(move, n.nz))
                hit = True
            else:
                e0 = len2dsq(cx0, cy0, pos[0], pos[2])
                e1 = len2dsq(cx1, cy1, pos[0], pos[2])
                onx = _f(-n.nx); ony = _f(-n.nz)
                if e0 < e1:
                    if e0 > wrr or abs(fsubs(e0, wrr)) < 0.008:
                        continue
                    fx, fy = cross_cir_lin(pos[0], pos[2], wall_r, cx0, cy0, onx, ony)
                    pos[0] = fadds(pos[0], fsubs(cx0, fx)); pos[2] = fadds(pos[2], fsubs(cy0, fy))
                    hit = True
                else:
                    if e1 > wrr or abs(fsubs(e1, wrr)) < 0.008:
                        continue
                    fx, fy = cross_cir_lin(pos[0], pos[2], wall_r, cx1, cy1, onx, ony)
                    pos[0] = fadds(pos[0], fsubs(cx1, fx)); pos[2] = fadds(pos[2], fsubs(cy1, fy))
                    hit = True
    return tuple(pos), hit


# --------------------------------------------------------------------- CrrPos
def crr_pos_walls(old_pos, new_pos, tris, wall_h=(30.1, 89.9, 125.0), wall_r=35.0, speed_y=0.0):
    """Wall-relevant part of dBgS_Acch::CrrPos. Returns (corrected_pos, info)."""
    dxz2 = len2dsq(old_pos[0], old_pos[2], new_pos[0], new_pos[2])
    ran_line = dxz2 > fmuls(wall_r, wall_r)
    pos = tuple(new_pos)
    line_hit = False
    if ran_line:
        line_hit, pos = line_check(old_pos, pos, tris, wall_h)
    pos, wall_hit = wall_correct(pos, speed_y, tris, wall_h, wall_r)
    if wall_hit and ran_line:
        lh2, pos = line_check(old_pos, pos, tris, wall_h)
        line_hit = line_hit or lh2
    return pos, {"line_hit": line_hit, "wall_hit": wall_hit, "ran_line": ran_line}


# Player-faithful per-frame CrrPos (the acch_* layer, ROADMAP Phase W). Model + differences
# from the frozen crr_pos_walls above: knowledge/mechanics/wall-response.md.

def sqrtf_c(x):
    """MSL std::sqrtf (math.h:89): frsqrte double estimate + 3 Newton iterations in DOUBLE,
    then f32(x*guess). NOT correctly rounded -- differs from f32(math.sqrt) at boundary cases."""
    x = _f(x)
    if x > 0.0:
        g = frsqrte(float(x))
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        return _f(x * g)
    return x


def _cross_cir_lin_x(cx, cy, r, x0, y0, dirx, diry):
    """cM2d_CrossCirLin with the exact console sqrtf + IsZero threshold (the acch twin of
    cross_cir_lin above). Furthest intersection of ray (x0,y0)+t*(dir) with circle (cx,cy,r)."""
    fv1 = fsubs(x0, cx); fv15 = fsubs(y0, cy)
    d13 = fadds(fmuls(dirx, dirx), fmuls(diry, diry))
    d14 = fmuls(2.0, fadds(fmuls(dirx, fv1), fmuls(diry, fv15)))
    c = fsubs(fadds(fmuls(fv1, fv1), fmuls(fv15, fv15)), fmuls(r, r))
    t = 0.0
    if is_zero_x(d13):
        if not is_zero_x(d14):
            t = fdivs(_f(-c), d14)
    else:
        disc = fsubs(fmuls(d14, d14), fmuls(fmuls(4.0, d13), c))
        if is_zero_x(disc):
            t = fdivs(_f(-d14), fmuls(2.0, d13))
        elif disc >= 0.0:
            k = fdivs(1.0, fmuls(2.0, d13))
            s = sqrtf_c(disc)
            r1 = fmuls(k, fadds(_f(-d14), s))
            r2 = fmuls(k, fsubs(_f(-d14), s))
            t = r1 if r1 > r2 else r2
    if is_zero_x(t):
        return x0, y0
    return fadds(x0, fmuls(t, dirx)), fadds(y0, fmuls(t, diry))


def acch_line_check(old_pos, pos, tris, wall_h, whd):
    """dBgS_Acch::LineCheck (d_bg_s_acch.cpp:175), full wall response. Sweeps the centre line
    old->pos at each cylinder height; on the NEAREST front crossing: snap pos to it, add the
    plane normal (VECAdd), latch whd[i] = pos.y (SetWallHDirect) if the normal has an XZ part,
    then y -= wallH. Ground-classed polys (n.y >= 0.5) take the y -= 1 branch (the mid-line
    GroundCheck is not modeled -- pass WALL tris only). Mutates whd; returns (hit_any, pos)."""
    pos = list(pos)
    hit_any = False
    for i, h in enumerate(wall_h):
        start = (old_pos[0], fadds(old_pos[1], h), old_pos[2])
        end = (pos[0], fadds(pos[1], h), pos[2])
        cur_end = end
        hit_tri = None
        for tri in tris:                     # LineCross: each front crossing shrinks the line,
            crossed, pt = cross_lin_tri(start, cur_end, tri, a=True, b=False)
            if crossed:                      # so the last accepted crossing is the nearest
                cur_end = pt
                hit_tri = tri
        if hit_tri is not None:
            hit_any = True
            pos[0], pos[1], pos[2] = cur_end
            n = hit_tri.pla
            if not (n.ny >= 0.5):            # !cBgW_CheckBGround -> wall response
                pos[0] = fadds(pos[0], n.nx)               # VECAdd(pos, normal, pos)
                pos[1] = fadds(pos[1], n.ny)
                pos[2] = fadds(pos[2], n.nz)
                if not is_zero_x(sqrtf_c(fadds(fmuls(n.nx, n.nx), fmuls(n.nz, n.nz)))):
                    whd[i] = pos[1]                        # SetWallHDirect(pm_pos->y)
                pos[1] = fsubs(pos[1], h)
            else:                            # ground-classed poly under the line
                pos[1] = fsubs(pos[1], 1.0)
    return hit_any, tuple(pos)


def acch_wall_correct(pos, tris, wall_h, wall_r, speed_y, whd, add_y=0.0):
    """dBgS::WallCorrect -> dBgW::RwgWallCorrect over `tris` (game traversal order) x cylinders,
    exact response. Slice height sp7C = whd[i] if LineCheck latched it, else
    (add_y + (pos.y + h)) - speed_y with the MID-FRAME dipped pos.y/speed.y (WallCorrect runs
    before the ground snap). Returns (pos, cir_hit[3], cir_angle[3], wall_hit)."""
    from .mathlib import cM_atan2s
    pos = list(pos)
    wrr = fmuls(wall_r, wall_r)              # CalcWallRR
    ncir = len(wall_h)
    cir_hit = [False] * ncir
    cir_ang = [0] * ncir
    agg = False
    for tri in tris:
        n = tri.pla
        sp68 = sqrtf_c(fadds(fmuls(n.nx, n.nx), fmuls(n.nz, n.nz)))
        if is_zero_x(sp68):
            continue
        sp6C = fdivs(1.0, sp68)
        for i in range(ncir):
            h = wall_h[i]
            sp78 = fmuls(sp6C, wall_r)
            sp50x = fmuls(sp78, n.nx); sp50z = fmuls(sp78, n.nz)
            if whd[i] is not None:                       # ChkWallHDirect
                sp7C = whd[i]
            else:
                sp7C = fsubs(fadds(add_y, fadds(pos[1], h)), speed_y)
            s0 = fsubs(tri.v0[1], sp7C)
            s1 = fsubs(tri.v1[1], sp7C)
            s2 = fsubs(tri.v2[1], sp7C)
            if (s0 > 0.0 and s1 > 0.0 and s2 > 0.0) or (s0 < 0.0 and s1 < 0.0 and s2 < 0.0):
                continue
            zc = is_zero_x(s0) + is_zero_x(s1) + is_zero_x(s2)
            if zc == 1:
                continue
            if (s0 > 0.0 and s1 <= 0.0 and s2 <= 0.0) or (s0 < 0.0 and s1 >= 0.0 and s2 >= 0.0):
                i0, i1, i2 = 0, 1, 2
            elif (s1 > 0.0 and s0 <= 0.0 and s2 <= 0.0) or (s1 < 0.0 and s0 >= 0.0 and s2 >= 0.0):
                i0, i1, i2 = 1, 0, 2
            else:
                i0, i1, i2 = 2, 0, 1
            s = (s0, s1, s2)
            sp90 = fsubs(s[i0], s[i1]); sp94 = fsubs(s[i0], s[i2])
            if is_zero_x(sp90) or is_zero_x(sp94):
                continue
            sp98 = fdivs(_f(-s[i1]), sp90); sp9C = fdivs(_f(-s[i2]), sp94)
            V = (tri.v0, tri.v1, tri.v2)
            vx = (V[0][0], V[1][0], V[2][0]); vz = (V[0][2], V[1][2], V[2][2])
            a, b, c = i0, i1, i2
            cx0 = fadds(vx[b], fmuls(sp98, fsubs(vx[a], vx[b])))
            cy0 = fadds(vz[b], fmuls(sp98, fsubs(vz[a], vz[b])))
            cx1 = fadds(vx[c], fmuls(sp9C, fsubs(vx[a], vx[c])))
            cy1 = fadds(vz[c], fmuls(sp9C, fsubs(vz[a], vz[c])))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            on, ccx, ccy, seg = len2dsq_pnt_seg(pos[0], pos[2], cx0o, cy0o, cx1o, cy1o)
            d4 = fsubs(ccx, pos[0]); d8 = fsubs(ccy, pos[2])
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:                                       # positionWallCorrect
                move = fmuls(sqrtf_c(seg), sp6C)
                pos[0] = fadds(pos[0], fmuls(move, n.nx))
                pos[2] = fadds(pos[2], fmuls(move, n.nz))
            else:                                        # endpoint (seam-vertex) push-out
                # The decomp SUBTRACTS the offset back off the shifted endpoints (d_bg_w.cpp:187)
                # -- an f32 round-trip, f32((c+off)-off) != c in general, so keep the round-trip.
                cx0 = fsubs(cx0o, sp50x); cy0 = fsubs(cy0o, sp50z)
                cx1 = fsubs(cx1o, sp50x); cy1 = fsubs(cy1o, sp50z)
                e0 = len2dsq(cx0, cy0, pos[0], pos[2])
                e1 = len2dsq(cx1, cy1, pos[0], pos[2])
                onx = _f(-n.nx); ony = _f(-n.nz)
                if e0 < e1:
                    if e0 > wrr or abs(fsubs(e0, wrr)) < 0.008:
                        continue
                    fx, fy = _cross_cir_lin_x(pos[0], pos[2], wall_r, cx0, cy0, onx, ony)
                    pos[0] = fadds(pos[0], fsubs(cx0, fx)); pos[2] = fadds(pos[2], fsubs(cy0, fy))
                else:
                    if e1 > wrr or abs(fsubs(e1, wrr)) < 0.008:
                        continue
                    fx, fy = _cross_cir_lin_x(pos[0], pos[2], wall_r, cx1, cy1, onx, ony)
                    pos[0] = fadds(pos[0], fsubs(cx1, fx)); pos[2] = fadds(pos[2], fsubs(cy1, fy))
            agg = True                                   # SetWallHit (all three branches)
            cir_hit[i] = True                            # SetWallCirHit
            cir_ang[i] = cM_atan2s(n.nx, n.nz)           # SetWallAngleY
    return tuple(pos), cir_hit, cir_ang, agg


def acch_crr_pos(old_pos, new_pos, tris, speed_y=0.0, wall_h=(30.1, 89.9, 125.0), wall_r=35.0,
                 ground_check_offset=60.0, line_check_flag=True, add_y=0.0):
    """The wall part of dBgS_Acch::CrrPos (d_bg_s_acch.cpp:209) as the player runs it:
    conditional LineCheck (always, for the player: line_check_flag == the LINE_CHECK bit) ->
    WallCorrect -> re-LineCheck if a wall corrected. `new_pos` is the POST-integration,
    PRE-ground-snap position (y dipped by gravity); `speed_y` the post-gravity speed.y.
    Returns (pos, info) with per-cylinder hit flags + wall angles for the procs."""
    old = tuple(_f(c) for c in old_pos)
    pos = tuple(_f(c) for c in new_pos)
    whd = [None] * len(wall_h)
    lowH_R = _f(wall_r)                      # GetWallAllLowH_R: R of the lowest-height cylinder
    line_hit = False
    ran = False
    if not is_zero_x(lowH_R):
        distXZ2 = len2dsq(old[0], old[2], pos[0], pos[2])
        temp7 = fadds(min(wall_h), old[1])                 # lowH + old.y
        temp8 = fadds(ground_check_offset, pos[1])
        distY = fsubs(old[1], pos[1])
        if (distXZ2 > fmuls(lowH_R, lowH_R) or temp7 > temp8
                or distY > ground_check_offset or line_check_flag):
            ran = True
            line_hit, pos = acch_line_check(old, pos, tris, wall_h, whd)
    pos, cir_hit, cir_ang, wall_hit = acch_wall_correct(pos, tris, wall_h, wall_r,
                                                        speed_y, whd, add_y)
    if wall_hit and ran:
        lh2, pos = acch_line_check(old, pos, tris, wall_h, whd)
        line_hit = line_hit or lh2
    return pos, {"wall_hit": wall_hit, "cir_hit": cir_hit, "wall_angle": cir_ang,
                 "line_hit": line_hit, "ran_line": ran}


# FAST PATH: native Cython (tww_sim/core/_collc.pyx) ports the crr_pos_walls hot path, bit-IDENTICAL
# (0 ULP, ~38x). Absent .pyd -> pure defs above (same result). Build: _build_native.py _collc.
try:
    from ._collc import (crr_pos_walls, line_check, wall_correct,  # noqa: F401,F811
                         len2dsq)
except ImportError:
    pass
