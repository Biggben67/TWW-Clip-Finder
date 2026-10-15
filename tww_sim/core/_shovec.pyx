# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""_shovec.pyx - native EXACT coupled Link-roll + Tetra CC-push engine (Phase T placement search).

One Tetra placement = one ``run_one``: replays the fixed slot-6 roll->CUT_F input schedule with the
FULL coupled dynamics -- Link's table-driven roll/cut moves (per-frame f32 displacement + cut lunge,
position-independent by construction, see harness/rollstab/fast_shove.py), the exact acch
``dBgS_Acch::CrrPos`` wall pass for BOTH actors (frsqrte-Newton ``sqrtf_c``, ``is_zero_x`` 2^-18,
WallHDirect latch), Link's animated Co-centre via the position-independent FK translate-chain
constants (``body_cyl.roll_co_chain_consts``), the ``dCcS::SetPosCorrect`` rank-split push pair, and
the full type-5 Zl1 idle/move follow port (console sin/cos/atan tables). Every op keeps the fp.py
single-precision semantics (`<double><float>` casts, fused fmadds), so the result is BIT-IDENTICAL
to the Python ``harness.rollstab.cc_stepper.couple_replay`` engine -- gated per placement in
tests/test_shove_fast.py, NOT a predictor.

Speed comes from three exact reductions: the static room cull (land.walls.cull_walls), a per-call
AABB candidate prefilter inside CrrPos (far tris are provable no-ops in both LineCheck and
WallCorrect; margin >> interaction reach), and the Link proc schedule folded to per-frame constants.
The acceptance is ``geometry_tetra.genuine_clip`` transcribed: LEGACY ``crr_pos_walls`` (1e-5
IsZero, correctly-rounded fsqrt) over the 4-tri barrier + the two seam plane tests.

Build: ``python _build_native.py _shovec``. Optional accelerator: absent .pyd, use the Python
couple_replay path (same result, ~3 orders slower).
"""

from libc.stdlib cimport malloc, free
from libc.math cimport sqrt as _c_sqrt, fabs as _c_fabs
from cython.parallel cimport prange, parallel

cdef double G_CM3D_F_ABS_MIN = 1.0e-5        # legacy cM3d_IsZero
cdef double IS0X = 3.814697265625e-06        # 2^-18, console IsZero (acch layer)

# ---- single-precision primitives ---------------------------------------------------------------
cdef inline double f32(double x) noexcept nogil: return <double><float>x
cdef inline double fmuls(double a, double b) noexcept nogil: return <double><float>(a * b)
cdef inline double fadds(double a, double b) noexcept nogil: return <double><float>(a + b)
cdef inline double fsubs(double a, double b) noexcept nogil: return <double><float>(a - b)
cdef inline double fdivs(double a, double b) noexcept nogil: return <double><float>(a / b)
cdef inline double fmadds(double a, double b, double c) noexcept nogil: return <double><float>(a * b + c)

cdef inline bint is_zero_c(double x) noexcept nogil:
    return _c_fabs(f32(x)) < G_CM3D_F_ABS_MIN

cdef inline bint is_zero_x(double x) noexcept nogil:
    return _c_fabs(f32(x)) < IS0X

cdef inline double fsqrt_l(double a) noexcept nogil:      # legacy fsqrt: f32(sqrt(f32(a)))
    return f32(_c_sqrt(f32(a)))

# ---- Gekko frsqrte + MSL sqrtf (console sqrt, acch layer) ---------------------------------------
cdef long long _FRS_BASE[32]
cdef long long _FRS_DEC[32]
_FRS_BASE[0] = 0x1a7e800; _FRS_DEC[0] = -0x568
_FRS_BASE[1] = 0x17cb800; _FRS_DEC[1] = -0x4f3
_FRS_BASE[2] = 0x1552800; _FRS_DEC[2] = -0x48d
_FRS_BASE[3] = 0x130c000; _FRS_DEC[3] = -0x435
_FRS_BASE[4] = 0x10f2000; _FRS_DEC[4] = -0x3e7
_FRS_BASE[5] = 0x0eff000; _FRS_DEC[5] = -0x3a2
_FRS_BASE[6] = 0x0d2e000; _FRS_DEC[6] = -0x365
_FRS_BASE[7] = 0x0b7c000; _FRS_DEC[7] = -0x32e
_FRS_BASE[8] = 0x09e5000; _FRS_DEC[8] = -0x2fc
_FRS_BASE[9] = 0x0867000; _FRS_DEC[9] = -0x2d0
_FRS_BASE[10] = 0x06ff000; _FRS_DEC[10] = -0x2a8
_FRS_BASE[11] = 0x05ab800; _FRS_DEC[11] = -0x283
_FRS_BASE[12] = 0x046a000; _FRS_DEC[12] = -0x261
_FRS_BASE[13] = 0x0339800; _FRS_DEC[13] = -0x243
_FRS_BASE[14] = 0x0218800; _FRS_DEC[14] = -0x226
_FRS_BASE[15] = 0x0105800; _FRS_DEC[15] = -0x20b
_FRS_BASE[16] = 0x3ffa000; _FRS_DEC[16] = -0x7a4
_FRS_BASE[17] = 0x3c29000; _FRS_DEC[17] = -0x700
_FRS_BASE[18] = 0x38aa000; _FRS_DEC[18] = -0x670
_FRS_BASE[19] = 0x3572000; _FRS_DEC[19] = -0x5f2
_FRS_BASE[20] = 0x3279000; _FRS_DEC[20] = -0x584
_FRS_BASE[21] = 0x2fb7000; _FRS_DEC[21] = -0x524
_FRS_BASE[22] = 0x2d26000; _FRS_DEC[22] = -0x4cc
_FRS_BASE[23] = 0x2ac0000; _FRS_DEC[23] = -0x47e
_FRS_BASE[24] = 0x2881000; _FRS_DEC[24] = -0x43a
_FRS_BASE[25] = 0x2665000; _FRS_DEC[25] = -0x3fa
_FRS_BASE[26] = 0x2468000; _FRS_DEC[26] = -0x3c2
_FRS_BASE[27] = 0x2287000; _FRS_DEC[27] = -0x38e
_FRS_BASE[28] = 0x20c1000; _FRS_DEC[28] = -0x35e
_FRS_BASE[29] = 0x1f12000; _FRS_DEC[29] = -0x332
_FRS_BASE[30] = 0x1d79000; _FRS_DEC[30] = -0x30a
_FRS_BASE[31] = 0x1bf4000; _FRS_DEC[31] = -0x2e6

cdef double _frsqrte(double val) noexcept nogil:
    cdef unsigned long long integral = (<unsigned long long*>&val)[0]
    cdef unsigned long long mantissa = integral & ((<unsigned long long>1 << 52) - 1)
    cdef unsigned long long sign = integral & (<unsigned long long>1 << 63)
    cdef long long exponent = <long long>(integral & (<unsigned long long>0x7FF << 52))
    cdef double out
    if mantissa == 0 and exponent == 0:      # +-0 -> +-inf (never hit on our positive inputs)
        integral = sign | (<unsigned long long>0x7FF << 52)
        return (<double*>&integral)[0]
    if exponent == (<long long>0x7FF << 52):
        if mantissa == 0:
            if sign:
                integral = <unsigned long long>0xFFF8000000000000
                return (<double*>&integral)[0]
            return 0.0
        return val
    if sign:
        integral = <unsigned long long>0xFFF8000000000000
        return (<double*>&integral)[0]
    if exponent == 0:                        # subnormal normalize
        while not (mantissa & (<unsigned long long>1 << 52)):
            exponent -= (<long long>1 << 52)
            mantissa <<= 1
        mantissa &= (<unsigned long long>1 << 52) - 1
        exponent += (<long long>1 << 52)
    cdef unsigned long long exponent_lsb = <unsigned long long>exponent & (<unsigned long long>1 << 52)
    cdef long long ediff = exponent - (<long long>0x3FE << 52)
    cdef long long half = ediff / 2 if ediff >= 0 else -((-ediff) / 2)   # C trunc division
    cdef unsigned long long newexp = (<unsigned long long>((<long long>0x3FF << 52) - half)) & (<unsigned long long>0x7FF << 52)
    integral = sign | newexp
    cdef unsigned long long i = (exponent_lsb | mantissa) >> 37
    cdef long long entry = _FRS_BASE[i // 2048] + _FRS_DEC[i // 2048] * <long long>(i % 2048)
    integral = integral | (<unsigned long long>entry << 26)
    return (<double*>&integral)[0]


cdef inline double _sqrtf_msl_c(double x) noexcept nogil:
    """MSL ``std::sqrtf`` (frsqrte seed + 3 double Newton steps, then f32(x*g)) with a MATH-ACCURATE
    seed -- bit-identical to the frsqrte-seeded form, which is the point of the 3 refines: Python's
    table-seeded `collision.sqrtf_msl` and this agree on 400k random operands, and the native push is
    gated against Python bit-for-bit in `tests/test_cc_push_native.py` (40k pairs).

    Why not the table-seeded `sqrtf_c` right below: calling THAT from the Co-push block faults the
    process (Windows access violation in `tests/test_pushaside_clip.py`, clean rebuild, reproducible).
    The values are provably identical, so this is not a fidelity compromise -- but `_frsqrte` corrupting
    memory from one call site is a REAL latent bug that also sits under the acch/WallCorrect sites
    (0x8024C4.. `sqrtf_c` at lines ~297/467/549/668/856), and it is UNDIAGNOSED. See the README
    `## Plan / status` session-55 box; do not assume it is benign because those tests pass today.
    """
    x = f32(x)
    cdef double g
    if x > 0.0:
        g = 1.0 / _c_sqrt(x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        return f32(x * g)
    return x

cdef inline double sqrtf_c(double x) noexcept nogil:
    """MSL std::sqrtf: frsqrte double estimate + 3 Newton iterations in DOUBLE, then f32(x*g)."""
    x = f32(x)
    cdef double g
    if x > 0.0:
        g = _frsqrte(x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        return f32(x * g)
    return x

# ---- shared geometry leaves (identical to _collc.pyx / collision.py) ----------------------------
cdef inline double _len2dsq(double x0, double y0, double x1, double y1) noexcept nogil:
    return fadds(fmuls(fsubs(x0, x1), fsubs(x0, x1)), fmuls(fsubs(y0, y1), fsubs(y0, y1)))

cdef inline double _plane_func(double nx, double ny, double nz, double d,
                               double px, double py, double pz) noexcept nogil:
    cdef double ny_py = fmuls(ny, py)
    cdef double nz_pz = fmuls(nz, pz)
    cdef double dot = fadds(fmadds(nx, px, ny_py), nz_pz)
    return fadds(d, dot)

cdef inline bint _cross_proc(double av, double bv,
                             double sx, double sy, double sz,
                             double ex, double ey, double ez, double* dst) noexcept nogil:
    if is_zero_c(fsubs(av, bv)):
        dst[0] = ex; dst[1] = ey; dst[2] = ez
        return False
    cdef double scale = fdivs(av, fsubs(av, bv))
    dst[0] = fadds(sx, fmuls(fsubs(ex, sx), scale))
    dst[1] = fadds(sy, fmuls(fsubs(ey, sy), scale))
    dst[2] = fadds(sz, fmuls(fsubs(ez, sz), scale))
    return True

cdef inline bint _cross_lin_pla(double sx, double sy, double sz,
                                double ex, double ey, double ez,
                                double nx, double ny, double nz, double d,
                                double* dst) noexcept nogil:
    dst[0] = ex; dst[1] = ey; dst[2] = ez
    cdef double sv = _plane_func(nx, ny, nz, d, sx, sy, sz)
    cdef double ev = _plane_func(nx, ny, nz, d, ex, ey, ez)
    if fmuls(sv, ev) > 0.0:
        return False
    if sv >= 0.0 and ev <= 0.0:              # front -> back only (frontFlag)
        return _cross_proc(sv, ev, sx, sy, sz, ex, ey, ez, dst)
    return False

cdef inline double _vprod2d(double x1, double y1, double x2, double y2,
                            double x3, double y3) noexcept nogil:
    return fsubs(fmuls(fsubs(x2, x1), fsubs(y3, y1)), fmuls(fsubs(y2, y1), fsubs(x3, x1)))

cdef inline bint _incl_box2d(double ax, double ay, double bx, double by,
                             double cx, double cy, double px, double py) noexcept nogil:
    cdef double f31, f30
    if ax < bx:
        f31 = ax; f30 = bx
    else:
        f31 = bx; f30 = ax
    if f31 > cx: f31 = cx
    elif f30 < cx: f30 = cx
    if f31 > px or f30 < px: return False
    if ay < by:
        f31 = ay; f30 = by
    else:
        f31 = by; f30 = ay
    if f31 > cy: f31 = cy
    elif f30 < cy: f30 = cy
    if f31 > py or f30 < py: return False
    return True

cdef inline bint _tri_in_2d(double ax, double ay, double bx, double by,
                            double cx, double cy, double px, double py) noexcept nogil:
    if not _incl_box2d(ax, ay, bx, by, cx, cy, px, py):
        return False
    cdef double f12 = _vprod2d(ax, ay, bx, by, px, py)
    if (f12 <= 20.0
            and _vprod2d(bx, by, cx, cy, px, py) <= 20.0
            and _vprod2d(cx, cy, ax, ay, px, py) <= 20.0):
        return True
    if (f12 >= -20.0
            and _vprod2d(bx, by, cx, cy, px, py) >= -20.0
            and _vprod2d(cx, cy, ax, ay, px, py) >= -20.0):
        return True
    return False

cdef inline bint _cross_lin_tri(double sx, double sy, double sz,
                                double ex, double ey, double ez,
                                double* tv, double* tp, double* dst) noexcept nogil:
    if not _cross_lin_pla(sx, sy, sz, ex, ey, ez, tp[0], tp[1], tp[2], tp[3], dst):
        return False
    cdef bint okx = (_c_fabs(tp[0]) < 0.008) or (not is_zero_c(tp[0])
        and _tri_in_2d(tv[1], tv[2], tv[4], tv[5], tv[7], tv[8], dst[1], dst[2]))
    cdef bint oky = (_c_fabs(tp[1]) < 0.008) or (not is_zero_c(tp[1])
        and _tri_in_2d(tv[2], tv[0], tv[5], tv[3], tv[8], tv[6], dst[2], dst[0]))
    cdef bint okz = (_c_fabs(tp[2]) < 0.008) or (not is_zero_c(tp[2])
        and _tri_in_2d(tv[0], tv[1], tv[3], tv[4], tv[6], tv[7], dst[0], dst[1]))
    return okx and oky and okz

cdef inline bint _len2dsq_pnt_seg(double xp, double yp, double x0, double y0,
                                  double x1, double y1,
                                  double* outx, double* outy, double* seg) noexcept nogil:
    cdef double xd = fsubs(x1, x0)
    cdef double yd = fsubs(y1, y0)
    cdef double dot = fadds(fmuls(xd, xd), fmuls(yd, yd))
    if is_zero_c(dot):
        outx[0] = x0; outy[0] = y0; seg[0] = 0.0
        return False
    cdef double mag = fdivs(fadds(fmuls(xd, fsubs(xp, x0)), fmuls(yd, fsubs(yp, y0))), dot)
    cdef bint on = (0.0 <= mag <= 1.0)
    outx[0] = fadds(x0, fmuls(xd, mag))
    outy[0] = fadds(y0, fmuls(yd, mag))
    seg[0] = _len2dsq(outx[0], outy[0], xp, yp)
    return on

# ---- cM2d_CrossCirLin, LEGACY (is_zero 1e-5, correctly-rounded fsqrt) ---------------------------
cdef inline void _cir_lin_l(double cx, double cy, double r,
                            double x0, double y0, double dirx, double diry,
                            double* opx, double* opy) noexcept nogil:
    cdef double fv1 = fsubs(x0, cx), fv15 = fsubs(y0, cy)
    cdef double d13 = fadds(fmuls(dirx, dirx), fmuls(diry, diry))
    cdef double d14 = fmuls(2.0, fadds(fmuls(dirx, fv1), fmuls(diry, fv15)))
    cdef double c = fsubs(fadds(fmuls(fv1, fv1), fmuls(fv15, fv15)), fmuls(r, r))
    cdef double t = 0.0
    cdef double disc, k, s, r1, r2
    if is_zero_c(d13):
        if not is_zero_c(d14):
            t = fdivs(f32(-c), d14)
    else:
        disc = fsubs(fmuls(d14, d14), fmuls(fmuls(4.0, d13), c))
        if is_zero_c(disc):
            t = fdivs(f32(-d14), fmuls(2.0, d13))
        elif disc < 0.0:
            t = 0.0
        else:
            k = fdivs(1.0, fmuls(2.0, d13))
            s = fsqrt_l(disc)
            r1 = fmuls(k, fadds(f32(-d14), s))
            r2 = fmuls(k, fsubs(f32(-d14), s))
            t = r1 if r1 > r2 else r2
    if is_zero_c(t):
        opx[0] = x0; opy[0] = y0
        return
    opx[0] = fadds(x0, fmuls(t, dirx))
    opy[0] = fadds(y0, fmuls(t, diry))

# ---- cM2d_CrossCirLin, ACCH (is_zero_x 2^-18, console sqrtf_c) ----------------------------------
cdef inline void _cir_lin_x(double cx, double cy, double r,
                            double x0, double y0, double dirx, double diry,
                            double* opx, double* opy) noexcept nogil:
    cdef double fv1 = fsubs(x0, cx), fv15 = fsubs(y0, cy)
    cdef double d13 = fadds(fmuls(dirx, dirx), fmuls(diry, diry))
    cdef double d14 = fmuls(2.0, fadds(fmuls(dirx, fv1), fmuls(diry, fv15)))
    cdef double c = fsubs(fadds(fmuls(fv1, fv1), fmuls(fv15, fv15)), fmuls(r, r))
    cdef double t = 0.0
    cdef double disc, k, s, r1, r2
    if is_zero_x(d13):
        if not is_zero_x(d14):
            t = fdivs(f32(-c), d14)
    else:
        disc = fsubs(fmuls(d14, d14), fmuls(fmuls(4.0, d13), c))
        if is_zero_x(disc):
            t = fdivs(f32(-d14), fmuls(2.0, d13))
        elif disc >= 0.0:
            k = fdivs(1.0, fmuls(2.0, d13))
            s = sqrtf_c(disc)
            r1 = fmuls(k, fadds(f32(-d14), s))
            r2 = fmuls(k, fsubs(f32(-d14), s))
            t = r1 if r1 > r2 else r2
    if is_zero_x(t):
        opx[0] = x0; opy[0] = y0
        return
    opx[0] = fadds(x0, fmuls(t, dirx))
    opy[0] = fadds(y0, fmuls(t, diry))

# ---- LEGACY line_check / wall_correct (genuine acceptance; == collision.crr_pos_walls) ----------
cdef bint _line_check_l(double o0, double o1, double o2,
                        double* ppx, double* ppy, double* ppz,
                        double* vtx, double* pla, int n,
                        double* wh, int nh) noexcept nogil:
    cdef double px = ppx[0], py = ppy[0], pz = ppz[0]
    cdef bint hit_any = False
    cdef int hi, ti
    cdef double h, sx, sy, sz, cex, cey, cez
    cdef double dst[3]
    cdef bint hit_here
    for hi in range(nh):
        h = wh[hi]
        sx = o0; sy = fadds(o1, h); sz = o2
        cex = px; cey = fadds(py, h); cez = pz
        hit_here = False
        for ti in range(n):
            if _cross_lin_tri(sx, sy, sz, cex, cey, cez, vtx + ti * 9, pla + ti * 4, dst):
                cex = dst[0]; cey = dst[1]; cez = dst[2]
                hit_here = True
        if hit_here:
            hit_any = True
            px = cex; pz = cez
            py = fsubs(cey, h)
    ppx[0] = px; ppy[0] = py; ppz[0] = pz
    return hit_any

cdef bint _wall_correct_l(double* ppx, double py, double* ppz, double speed_y,
                          double* vtx, double* pla, int n,
                          double* wh, int nh, double wall_r) noexcept nogil:
    cdef double px = ppx[0], pz = ppz[0]
    cdef double wrr = fmuls(wall_r, wall_r)
    cdef bint hit = False
    cdef int ti, hi
    cdef double* tv
    cdef double* tp
    cdef double nx, nz
    cdef double sp68, sp6C, h, sp78, sp50x, sp50z, sp7C
    cdef double s0, s1, s2
    cdef double ss[3]
    cdef int zc, i0, i1, i2
    cdef double sp90, sp94, sp98, sp9C
    cdef double vx[3]
    cdef double vz[3]
    cdef double cx0, cy0, cx1, cy1, cx0o, cy0o, cx1o, cy1o
    cdef double ccx, ccy, seg, d4, d8, move, e0, e1, onx, ony, fx, fy
    cdef bint on
    for ti in range(n):
        tv = vtx + ti * 9
        tp = pla + ti * 4
        nx = tp[0]; nz = tp[2]
        sp68 = fsqrt_l(fadds(fmuls(nx, nx), fmuls(nz, nz)))
        if is_zero_c(sp68):
            continue
        sp6C = fdivs(1.0, sp68)
        for hi in range(nh):
            h = wh[hi]
            sp78 = fmuls(sp6C, wall_r)
            sp50x = fmuls(sp78, nx); sp50z = fmuls(sp78, nz)
            sp7C = fsubs(fadds(0.0, fadds(py, h)), speed_y)
            s0 = fsubs(tv[1], sp7C)
            s1 = fsubs(tv[4], sp7C)
            s2 = fsubs(tv[7], sp7C)
            if (s0 > 0.0 and s1 > 0.0 and s2 > 0.0) or (s0 < 0.0 and s1 < 0.0 and s2 < 0.0):
                continue
            zc = (1 if is_zero_c(s0) else 0) + (1 if is_zero_c(s1) else 0) + (1 if is_zero_c(s2) else 0)
            if zc == 1:
                continue
            if (s0 > 0.0 and s1 <= 0.0 and s2 <= 0.0) or (s0 < 0.0 and s1 >= 0.0 and s2 >= 0.0):
                i0 = 0; i1 = 1; i2 = 2
            elif (s1 > 0.0 and s0 <= 0.0 and s2 <= 0.0) or (s1 < 0.0 and s0 >= 0.0 and s2 >= 0.0):
                i0 = 1; i1 = 0; i2 = 2
            else:
                i0 = 2; i1 = 0; i2 = 1
            ss[0] = s0; ss[1] = s1; ss[2] = s2
            sp90 = fsubs(ss[i0], ss[i1]); sp94 = fsubs(ss[i0], ss[i2])
            if is_zero_c(sp90) or is_zero_c(sp94):
                continue
            sp98 = fdivs(f32(-ss[i1]), sp90); sp9C = fdivs(f32(-ss[i2]), sp94)
            vx[0] = tv[0]; vx[1] = tv[3]; vx[2] = tv[6]
            vz[0] = tv[2]; vz[1] = tv[5]; vz[2] = tv[8]
            cx0 = fadds(vx[i1], fmuls(sp98, fsubs(vx[i0], vx[i1])))
            cy0 = fadds(vz[i1], fmuls(sp98, fsubs(vz[i0], vz[i1])))
            cx1 = fadds(vx[i2], fmuls(sp9C, fsubs(vx[i0], vx[i2])))
            cy1 = fadds(vz[i2], fmuls(sp9C, fsubs(vz[i0], vz[i2])))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            on = _len2dsq_pnt_seg(px, pz, cx0o, cy0o, cx1o, cy1o, &ccx, &ccy, &seg)
            d4 = fsubs(ccx, px); d8 = fsubs(ccy, pz)
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:
                move = fmuls(sp6C, fsqrt_l(seg))
                px = fadds(px, fmuls(move, nx))
                pz = fadds(pz, fmuls(move, nz))
                hit = True
            else:
                # LEGACY endpoint: raw (un-offset) chord endpoints (collision.wall_correct).
                e0 = _len2dsq(cx0, cy0, px, pz)
                e1 = _len2dsq(cx1, cy1, px, pz)
                onx = f32(-nx); ony = f32(-nz)
                if e0 < e1:
                    if e0 > wrr or _c_fabs(fsubs(e0, wrr)) < 0.008:
                        continue
                    _cir_lin_l(px, pz, wall_r, cx0, cy0, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx0, fx)); pz = fadds(pz, fsubs(cy0, fy))
                    hit = True
                else:
                    if e1 > wrr or _c_fabs(fsubs(e1, wrr)) < 0.008:
                        continue
                    _cir_lin_l(px, pz, wall_r, cx1, cy1, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx1, fx)); pz = fadds(pz, fsubs(cy1, fy))
                    hit = True
    ppx[0] = px; ppz[0] = pz
    return hit

cdef bint _crr_blocked_l(double o0, double o1, double o2,
                         double nx0, double ny0, double nz0,
                         double* vtx, double* pla, int n,
                         double* wh, int nh, double wr) noexcept nogil:
    """LEGACY crr_pos_walls -> (line_hit or wall_hit), == geometry_tetra.genuine_clip's block test."""
    cdef double px = nx0, py = ny0, pz = nz0
    cdef bint line_hit = False, ran = False, wall_hit
    if _len2dsq(o0, o2, px, pz) > fmuls(wr, wr):
        ran = True
        line_hit = _line_check_l(o0, o1, o2, &px, &py, &pz, vtx, pla, n, wh, nh)
    if line_hit:
        return True
    wall_hit = _wall_correct_l(&px, py, &pz, 0.0, vtx, pla, n, wh, nh, wr)
    return wall_hit

# ---- ACCH LineCheck / WallCorrect / CrrPos (the per-frame player/Tetra pass) --------------------
cdef bint _acch_line_check(double o0, double o1, double o2,
                           double* ppx, double* ppy, double* ppz,
                           double* vtx, double* pla, int* cand, int nc,
                           double* wh, int nh, double* whd, bint* whd_set) noexcept nogil:
    cdef double px = ppx[0], py = ppy[0], pz = ppz[0]
    cdef bint hit_any = False
    cdef int hi, ci, ti, hit_ti
    cdef double h, sx, sy, sz, cex, cey, cez
    cdef double dst[3]
    cdef double nx, ny, nz
    for hi in range(nh):
        h = wh[hi]
        sx = o0; sy = fadds(o1, h); sz = o2
        cex = px; cey = fadds(py, h); cez = pz
        hit_ti = -1
        for ci in range(nc):
            ti = cand[ci]
            if _cross_lin_tri(sx, sy, sz, cex, cey, cez, vtx + ti * 9, pla + ti * 4, dst):
                cex = dst[0]; cey = dst[1]; cez = dst[2]
                hit_ti = ti
        if hit_ti >= 0:
            hit_any = True
            px = cex; py = cey; pz = cez
            nx = pla[hit_ti * 4 + 0]; ny = pla[hit_ti * 4 + 1]; nz = pla[hit_ti * 4 + 2]
            if not (ny >= 0.5):                  # wall response: VECAdd normal + WallHDirect latch
                px = fadds(px, nx)
                py = fadds(py, ny)
                pz = fadds(pz, nz)
                if not is_zero_x(sqrtf_c(fadds(fmuls(nx, nx), fmuls(nz, nz)))):
                    whd[hi] = py
                    whd_set[hi] = True
                py = fsubs(py, h)
            else:                                # ground-classed poly under the line
                py = fsubs(py, 1.0)
    ppx[0] = px; ppy[0] = py; ppz[0] = pz
    return hit_any

cdef bint _acch_wall_correct(double* ppx, double py, double* ppz, double speed_y,
                             double* vtx, double* pla, double* sp68x, double* sp6cx,
                             int* cand, int nc,
                             double* wh, int nh, double wall_r,
                             double* whd, bint* whd_set) noexcept nogil:
    cdef double px = ppx[0], pz = ppz[0]
    cdef double wrr = fmuls(wall_r, wall_r)
    cdef bint agg = False
    cdef int ci, ti, hi
    cdef double* tv
    cdef double* tp
    cdef double nx, nz
    cdef double sp68, sp6C, h, sp78, sp50x, sp50z, sp7C
    cdef double s0, s1, s2
    cdef double ss[3]
    cdef int zc, i0, i1, i2
    cdef double sp90, sp94, sp98, sp9C
    cdef double vx[3]
    cdef double vz[3]
    cdef double cx0, cy0, cx1, cy1, cx0o, cy0o, cx1o, cy1o
    cdef double ccx, ccy, seg, d4, d8, move, e0, e1, onx, ony, fx, fy
    cdef bint on
    for ci in range(nc):
        ti = cand[ci]
        tv = vtx + ti * 9
        tp = pla + ti * 4
        nx = tp[0]; nz = tp[2]
        # sp68/sp6C are per-tri constants (sqrtf_c of the plane normal) -- precomputed at ctx init
        # with the identical ops, hoisted out of the hot loop.
        sp68 = sp68x[ti]
        if is_zero_x(sp68):
            continue
        sp6C = sp6cx[ti]
        for hi in range(nh):
            h = wh[hi]
            sp78 = fmuls(sp6C, wall_r)
            sp50x = fmuls(sp78, nx); sp50z = fmuls(sp78, nz)
            if whd_set[hi]:
                sp7C = whd[hi]
            else:
                sp7C = fsubs(fadds(0.0, fadds(py, h)), speed_y)
            s0 = fsubs(tv[1], sp7C)
            s1 = fsubs(tv[4], sp7C)
            s2 = fsubs(tv[7], sp7C)
            if (s0 > 0.0 and s1 > 0.0 and s2 > 0.0) or (s0 < 0.0 and s1 < 0.0 and s2 < 0.0):
                continue
            zc = (1 if is_zero_x(s0) else 0) + (1 if is_zero_x(s1) else 0) + (1 if is_zero_x(s2) else 0)
            if zc == 1:
                continue
            if (s0 > 0.0 and s1 <= 0.0 and s2 <= 0.0) or (s0 < 0.0 and s1 >= 0.0 and s2 >= 0.0):
                i0 = 0; i1 = 1; i2 = 2
            elif (s1 > 0.0 and s0 <= 0.0 and s2 <= 0.0) or (s1 < 0.0 and s0 >= 0.0 and s2 >= 0.0):
                i0 = 1; i1 = 0; i2 = 2
            else:
                i0 = 2; i1 = 0; i2 = 1
            ss[0] = s0; ss[1] = s1; ss[2] = s2
            sp90 = fsubs(ss[i0], ss[i1]); sp94 = fsubs(ss[i0], ss[i2])
            if is_zero_x(sp90) or is_zero_x(sp94):
                continue
            sp98 = fdivs(f32(-ss[i1]), sp90); sp9C = fdivs(f32(-ss[i2]), sp94)
            vx[0] = tv[0]; vx[1] = tv[3]; vx[2] = tv[6]
            vz[0] = tv[2]; vz[1] = tv[5]; vz[2] = tv[8]
            cx0 = fadds(vx[i1], fmuls(sp98, fsubs(vx[i0], vx[i1])))
            cy0 = fadds(vz[i1], fmuls(sp98, fsubs(vz[i0], vz[i1])))
            cx1 = fadds(vx[i2], fmuls(sp9C, fsubs(vx[i0], vx[i2])))
            cy1 = fadds(vz[i2], fmuls(sp9C, fsubs(vz[i0], vz[i2])))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            on = _len2dsq_pnt_seg(px, pz, cx0o, cy0o, cx1o, cy1o, &ccx, &ccy, &seg)
            d4 = fsubs(ccx, px); d8 = fsubs(ccy, pz)
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:
                move = fmuls(sqrtf_c(seg), sp6C)
                px = fadds(px, fmuls(move, nx))
                pz = fadds(pz, fmuls(move, nz))
            else:
                # ACCH endpoint: the decomp SUBTRACTS the offset back off (f32 round-trip).
                cx0 = fsubs(cx0o, sp50x); cy0 = fsubs(cy0o, sp50z)
                cx1 = fsubs(cx1o, sp50x); cy1 = fsubs(cy1o, sp50z)
                e0 = _len2dsq(cx0, cy0, px, pz)
                e1 = _len2dsq(cx1, cy1, px, pz)
                onx = f32(-nx); ony = f32(-nz)
                if e0 < e1:
                    if e0 > wrr or _c_fabs(fsubs(e0, wrr)) < 0.008:
                        continue
                    _cir_lin_x(px, pz, wall_r, cx0, cy0, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx0, fx)); pz = fadds(pz, fsubs(cy0, fy))
                else:
                    if e1 > wrr or _c_fabs(fsubs(e1, wrr)) < 0.008:
                        continue
                    _cir_lin_x(px, pz, wall_r, cx1, cy1, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx1, fx)); pz = fadds(pz, fsubs(cy1, fy))
            agg = True
    ppx[0] = px; ppz[0] = pz
    return agg

# Precomputed WallCorrect slice (the whd-unset, standard-py fast path): for a FIXED slice height
# sp7C every per-tri quantity of _acch_wall_correct up to the point-vs-chord test is constant.
# Layout per (tri, height): [skip, cx0o, cy0o, cx1o, cy1o, cx0, cy0, cx1, cy1, sp50x, sp50z].
DEF PCW = 11

cdef void _precompute_slices(double* vtx, double* pla, double* sp68x, double* sp6cx, int n,
                             double* wh, int nh, double wall_r, double py, double speed_y,
                             double* pc) noexcept nogil:
    cdef int ti, hi
    cdef double* tv
    cdef double* tp
    cdef double* dst
    cdef double nx, nz, sp68, sp6C, h, sp78, sp50x, sp50z, sp7C
    cdef double s0, s1, s2
    cdef double ss[3]
    cdef int zc, i0, i1, i2
    cdef double sp90, sp94, sp98, sp9C
    cdef double vx[3]
    cdef double vz[3]
    cdef double cx0, cy0, cx1, cy1, cx0o, cy0o, cx1o, cy1o
    for ti in range(n):
        tv = vtx + ti * 9
        tp = pla + ti * 4
        nx = tp[0]; nz = tp[2]
        sp68 = sp68x[ti]
        sp6C = sp6cx[ti]
        for hi in range(nh):
            dst = pc + (ti * nh + hi) * PCW
            dst[0] = 1.0                          # default: skip
            if is_zero_x(sp68):
                continue
            h = wh[hi]
            sp78 = fmuls(sp6C, wall_r)
            sp50x = fmuls(sp78, nx); sp50z = fmuls(sp78, nz)
            sp7C = fsubs(fadds(0.0, fadds(py, h)), speed_y)
            s0 = fsubs(tv[1], sp7C)
            s1 = fsubs(tv[4], sp7C)
            s2 = fsubs(tv[7], sp7C)
            if (s0 > 0.0 and s1 > 0.0 and s2 > 0.0) or (s0 < 0.0 and s1 < 0.0 and s2 < 0.0):
                continue
            zc = (1 if is_zero_x(s0) else 0) + (1 if is_zero_x(s1) else 0) + (1 if is_zero_x(s2) else 0)
            if zc == 1:
                continue
            if (s0 > 0.0 and s1 <= 0.0 and s2 <= 0.0) or (s0 < 0.0 and s1 >= 0.0 and s2 >= 0.0):
                i0 = 0; i1 = 1; i2 = 2
            elif (s1 > 0.0 and s0 <= 0.0 and s2 <= 0.0) or (s1 < 0.0 and s0 >= 0.0 and s2 >= 0.0):
                i0 = 1; i1 = 0; i2 = 2
            else:
                i0 = 2; i1 = 0; i2 = 1
            ss[0] = s0; ss[1] = s1; ss[2] = s2
            sp90 = fsubs(ss[i0], ss[i1]); sp94 = fsubs(ss[i0], ss[i2])
            if is_zero_x(sp90) or is_zero_x(sp94):
                continue
            sp98 = fdivs(f32(-ss[i1]), sp90); sp9C = fdivs(f32(-ss[i2]), sp94)
            vx[0] = tv[0]; vx[1] = tv[3]; vx[2] = tv[6]
            vz[0] = tv[2]; vz[1] = tv[5]; vz[2] = tv[8]
            cx0 = fadds(vx[i1], fmuls(sp98, fsubs(vx[i0], vx[i1])))
            cy0 = fadds(vz[i1], fmuls(sp98, fsubs(vz[i0], vz[i1])))
            cx1 = fadds(vx[i2], fmuls(sp9C, fsubs(vx[i0], vx[i2])))
            cy1 = fadds(vz[i2], fmuls(sp9C, fsubs(vz[i0], vz[i2])))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            dst[0] = 0.0
            dst[1] = cx0o; dst[2] = cy0o; dst[3] = cx1o; dst[4] = cy1o
            # the ACCH endpoint push-out uses the offset ROUND-TRIP endpoints
            dst[5] = fsubs(cx0o, sp50x); dst[6] = fsubs(cy0o, sp50z)
            dst[7] = fsubs(cx1o, sp50x); dst[8] = fsubs(cy1o, sp50z)
            dst[9] = sp50x; dst[10] = sp50z

cdef bint _acch_wall_correct_pc(double* ppx, double* ppz,
                                double* pla, double* sp6cx, double* pc,
                                int* cand, int nc, int nh, double wall_r) noexcept nogil:
    """The whd-unset standard-py WallCorrect: identical result to _acch_wall_correct, all
    per-(tri,height) slice constants precomputed."""
    cdef double px = ppx[0], pz = ppz[0]
    cdef double wrr = fmuls(wall_r, wall_r)
    cdef bint agg = False
    cdef int ci, ti, hi
    cdef double* b
    cdef double nx, nz, sp6C
    cdef double ccx, ccy, seg, d4, d8, move, e0, e1, onx, ony, fx, fy
    cdef bint on
    for ci in range(nc):
        ti = cand[ci]
        nx = pla[ti * 4 + 0]; nz = pla[ti * 4 + 2]
        sp6C = sp6cx[ti]
        for hi in range(nh):
            b = pc + (ti * nh + hi) * PCW
            if b[0] != 0.0:
                continue
            on = _len2dsq_pnt_seg(px, pz, b[1], b[2], b[3], b[4], &ccx, &ccy, &seg)
            d4 = fsubs(ccx, px); d8 = fsubs(ccy, pz)
            if seg > wrr or fadds(fmuls(d4, b[9]), fmuls(d8, b[10])) < 0.0:
                continue
            if on:
                move = fmuls(sqrtf_c(seg), sp6C)
                px = fadds(px, fmuls(move, nx))
                pz = fadds(pz, fmuls(move, nz))
            else:
                e0 = _len2dsq(b[5], b[6], px, pz)
                e1 = _len2dsq(b[7], b[8], px, pz)
                onx = f32(-nx); ony = f32(-nz)
                if e0 < e1:
                    if e0 > wrr or _c_fabs(fsubs(e0, wrr)) < 0.008:
                        continue
                    _cir_lin_x(px, pz, wall_r, b[5], b[6], onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(b[5], fx)); pz = fadds(pz, fsubs(b[6], fy))
                else:
                    if e1 > wrr or _c_fabs(fsubs(e1, wrr)) < 0.008:
                        continue
                    _cir_lin_x(px, pz, wall_r, b[7], b[8], onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(b[7], fx)); pz = fadds(pz, fsubs(b[8], fy))
            agg = True
    ppx[0] = px; ppz[0] = pz
    return agg

cdef void _acch_crr_pos(double o0, double o1, double o2,
                        double* px, double* py, double* pz, double speed_y,
                        double* vtx, double* pla, double* aabb,
                        double* sp68x, double* sp6cx, int n,
                        double* wh, int nh, double wall_r, double margin,
                        int* candbuf, double* pc, double std_py) noexcept nogil:
    """acch_crr_pos with the exact-no-op AABB candidate prefilter. line_check_flag is always True
    for both actors here (the player's LINE_CHECK bit; Tetra's ObjAcch runs the same core)."""
    cdef double whd[8]
    cdef bint whd_set[8]
    cdef int hi
    for hi in range(nh):
        whd_set[hi] = False
        whd[hi] = 0.0
    # candidate prefilter: tris whose XZ AABB intersects the old/new box expanded by margin.
    cdef double bx0 = o0 if o0 < px[0] else px[0]
    cdef double bx1 = o0 if o0 > px[0] else px[0]
    cdef double bz0 = o2 if o2 < pz[0] else pz[0]
    cdef double bz1 = o2 if o2 > pz[0] else pz[0]
    bx0 -= margin; bx1 += margin; bz0 -= margin; bz1 += margin
    cdef int nc = 0, ti
    for ti in range(n):
        if aabb[ti * 4 + 1] < bx0 or aabb[ti * 4 + 0] > bx1:
            continue
        if aabb[ti * 4 + 3] < bz0 or aabb[ti * 4 + 2] > bz1:
            continue
        candbuf[nc] = ti
        nc += 1
    if nc == 0:
        return
    cdef bint line_hit = _acch_line_check(o0, o1, o2, px, py, pz, vtx, pla, candbuf, nc,
                                          wh, nh, whd, whd_set)
    cdef bint any_whd = False
    for hi in range(nh):
        if whd_set[hi]:
            any_whd = True
    cdef bint wall_hit
    if pc != NULL and not any_whd and py[0] == std_py:
        # fast path: every slice constant precomputed for this exact py/speed_y (bit-identical)
        wall_hit = _acch_wall_correct_pc(px, pz, pla, sp6cx, pc, candbuf, nc, nh, wall_r)
    else:
        wall_hit = _acch_wall_correct(px, py[0], pz, speed_y, vtx, pla, sp68x, sp6cx,
                                      candbuf, nc, wh, nh, wall_r, whd, whd_set)
    if wall_hit:
        _acch_line_check(o0, o1, o2, px, py, pz, vtx, pla, candbuf, nc, wh, nh, whd, whd_set)

# ---- console trig tables + cLib helpers ---------------------------------------------------------
cdef inline int _s16(int x) noexcept nogil:
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x

cdef int _add_calc_angle_s(int value, int target, int scale, int max_step, int min_step) noexcept nogil:
    value = _s16(value)
    target = _s16(target)
    cdef int diff = _s16(target - value)
    cdef int step, nv
    if value == target:
        return value
    step = diff / scale                      # C division truncates toward zero
    if step > min_step or step < -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        return _s16(value + step)
    if diff >= 0:
        nv = _s16(value + min_step)
        return target if _s16(target - nv) <= 0 else nv
    nv = _s16(value - min_step)
    return target if _s16(target - nv) >= 0 else nv

cdef double _chase_f(double value, double target, double step) noexcept nogil:
    value = f32(value)
    target = f32(target)
    if step == 0.0:
        return value
    cdef double s = f32(-step) if value > target else f32(step)
    cdef double nv = fadds(value, s)
    if fmuls(s, fsubs(nv, target)) >= 0.0:
        return target
    return nv


# ---- the coupled context ------------------------------------------------------------------------
cdef class ShoveCtx:
    """One fixed input schedule (anchor + thrust/placement timing family) compiled to C tables.

    Built by ``harness.rollstab.fast_shove.build_ctx``. ``run_one``/``sweep`` then evaluate Tetra
    placements bit-identically to ``couple_replay`` (gated in tests/test_shove_fast.py)."""
    cdef double* vtx          # culled wall tris (shared by both actors), flat 9/tri
    cdef double* pla          # their planes, flat 4/tri
    cdef double* aabb         # per-tri XZ AABB (xmin,xmax,zmin,zmax)
    cdef double* sp68x        # per-tri sqrtf_c(nx^2+nz^2) (acch WallCorrect constant)
    cdef double* sp6cx        # its fdivs reciprocal
    cdef double* pc_link      # precomputed WallCorrect slices, Link's standard slice y
    cdef double* pc_tet       # ... Tetra's (ground-clamped) slice y
    cdef double link_std_py   # the ymid those slices assume (fadds(link_y, grav))
    cdef double tet_std_py    # f32(ground_y)
    cdef int ntris
    # barrier (legacy genuine acceptance)
    cdef double* bvtx
    cdef double* bpla
    cdef int nbar
    cdef double wa[4]
    cdef double wb[4]
    cdef double link_geo_y    # geometry_tetra.LINK_Y
    # trig tables
    cdef double* sin_t        # 4096
    cdef double* cos_t        # 4096
    cdef int* atn_t           # 1025
    # Link schedule
    cdef int nsteps
    cdef int cut_step         # index of the CUT entry step (acceptance + stop)
    cdef double* dx           # per-step speedF move x
    cdef double* dz
    cdef double* cutx         # cut lunge add (only at cut_step, 0 elsewhere)
    cdef double* cutz
    cdef int* is_roll_pose    # centre = chain consts (1) vs feet (0)
    cdef int nlvl             # chain levels (root 1 + neck k), flattened
    cdef double* chx          # per-step chain consts x: [root..., neck...] nlvl per step
    cdef double* chz
    cdef int nroot            # how many of nlvl belong to the root chain
    cdef double link_x0, link_z0, link_y
    cdef double link_wh[3]
    cdef double link_r, link_grav
    # Tetra seed + params
    cdef double tet_x0, tet_y0, tet_z0
    cdef int tet_ang0
    cdef double tet_speedF0
    cdef int tet_stt0
    cdef double tet_wh[1]
    cdef double tet_r
    cdef double ground_y
    # CC push params
    cdef double co_r_sum      # link R + tetra R
    cdef double link_co_h, tet_co_h
    cdef double share1, share2   # push_shares(link_w, tetra_w)
    cdef double margin

    def __cinit__(self, walls, barrier, wa, wb, link_geo_y,
                  sin_table, cos_table, atan_table,
                  dx, dz, cutx, cutz, is_roll_pose, chx, chz, nroot, cut_step,
                  link_x0, link_z0, link_y, link_wh, link_r, link_grav,
                  tet_seed, tet_wh, tet_r, ground_y,
                  link_co_r, link_co_h, tet_co_r, tet_co_h, share1, share2,
                  margin=200.0):
        cdef int i, j, n
        n = len(walls)
        self.ntris = n
        self.vtx = <double*>malloc(n * 9 * sizeof(double))
        self.pla = <double*>malloc(n * 4 * sizeof(double))
        self.aabb = <double*>malloc(n * 4 * sizeof(double))
        self.sp68x = <double*>malloc(n * sizeof(double))
        self.sp6cx = <double*>malloc(n * sizeof(double))
        for i in range(n):
            t = walls[i]
            for j, v in enumerate((t.v0, t.v1, t.v2)):
                self.vtx[i * 9 + j * 3 + 0] = v[0]
                self.vtx[i * 9 + j * 3 + 1] = v[1]
                self.vtx[i * 9 + j * 3 + 2] = v[2]
            p = t.pla
            self.pla[i * 4 + 0] = p.nx; self.pla[i * 4 + 1] = p.ny
            self.pla[i * 4 + 2] = p.nz; self.pla[i * 4 + 3] = p.d
            self.aabb[i * 4 + 0] = min(t.v0[0], t.v1[0], t.v2[0])
            self.aabb[i * 4 + 1] = max(t.v0[0], t.v1[0], t.v2[0])
            self.aabb[i * 4 + 2] = min(t.v0[2], t.v1[2], t.v2[2])
            self.aabb[i * 4 + 3] = max(t.v0[2], t.v1[2], t.v2[2])
            self.sp68x[i] = sqrtf_c(fadds(fmuls(p.nx, p.nx), fmuls(p.nz, p.nz)))
            self.sp6cx[i] = fdivs(1.0, self.sp68x[i]) if not is_zero_x(self.sp68x[i]) else 0.0
        n = len(barrier)
        self.nbar = n
        self.bvtx = <double*>malloc(n * 9 * sizeof(double))
        self.bpla = <double*>malloc(n * 4 * sizeof(double))
        for i in range(n):
            t = barrier[i]
            for j, v in enumerate((t.v0, t.v1, t.v2)):
                self.bvtx[i * 9 + j * 3 + 0] = v[0]
                self.bvtx[i * 9 + j * 3 + 1] = v[1]
                self.bvtx[i * 9 + j * 3 + 2] = v[2]
            p = t.pla
            self.bpla[i * 4 + 0] = p.nx; self.bpla[i * 4 + 1] = p.ny
            self.bpla[i * 4 + 2] = p.nz; self.bpla[i * 4 + 3] = p.d
        for i in range(4):
            self.wa[i] = (wa.nx, wa.ny, wa.nz, wa.d)[i]
            self.wb[i] = (wb.nx, wb.ny, wb.nz, wb.d)[i]
        self.link_geo_y = link_geo_y
        self.sin_t = <double*>malloc(4096 * sizeof(double))
        self.cos_t = <double*>malloc(4096 * sizeof(double))
        self.atn_t = <int*>malloc(1025 * sizeof(int))
        for i in range(4096):
            self.sin_t[i] = sin_table[i]
            self.cos_t[i] = cos_table[i]
        for i in range(1025):
            self.atn_t[i] = atan_table[i]
        n = len(dx)
        self.nsteps = n
        self.cut_step = cut_step
        self.dx = <double*>malloc(n * sizeof(double))
        self.dz = <double*>malloc(n * sizeof(double))
        self.cutx = <double*>malloc(n * sizeof(double))
        self.cutz = <double*>malloc(n * sizeof(double))
        self.is_roll_pose = <int*>malloc(n * sizeof(int))
        self.nlvl = len(chx[0])
        self.nroot = nroot
        self.chx = <double*>malloc(n * self.nlvl * sizeof(double))
        self.chz = <double*>malloc(n * self.nlvl * sizeof(double))
        for i in range(n):
            self.dx[i] = dx[i]; self.dz[i] = dz[i]
            self.cutx[i] = cutx[i]; self.cutz[i] = cutz[i]
            self.is_roll_pose[i] = is_roll_pose[i]
            for j in range(self.nlvl):
                self.chx[i * self.nlvl + j] = chx[i][j]
                self.chz[i * self.nlvl + j] = chz[i][j]
        self.link_x0 = link_x0; self.link_z0 = link_z0; self.link_y = link_y
        for i in range(3):
            self.link_wh[i] = link_wh[i]
        self.link_r = link_r
        self.link_grav = link_grav
        self.tet_x0, self.tet_y0, self.tet_z0 = tet_seed[0], tet_seed[1], tet_seed[2]
        self.tet_ang0 = tet_seed[3]
        self.tet_speedF0 = tet_seed[4]
        self.tet_stt0 = tet_seed[5]
        self.tet_wh[0] = tet_wh[0]
        self.tet_r = tet_r
        self.ground_y = ground_y
        self.co_r_sum = fadds(link_co_r, tet_co_r)
        self.link_co_h = link_co_h
        self.tet_co_h = tet_co_h
        self.share1 = share1
        self.share2 = share2
        self.margin = margin
        # precomputed WallCorrect slices for the standard (whd-unset) slice heights
        self.link_std_py = fadds(self.link_y, self.link_grav)
        self.tet_std_py = f32(self.ground_y)
        self.pc_link = <double*>malloc(self.ntris * 3 * PCW * sizeof(double))
        self.pc_tet = <double*>malloc(self.ntris * 1 * PCW * sizeof(double))
        _precompute_slices(self.vtx, self.pla, self.sp68x, self.sp6cx, self.ntris,
                           self.link_wh, 3, self.link_r, self.link_std_py, self.link_grav,
                           self.pc_link)
        _precompute_slices(self.vtx, self.pla, self.sp68x, self.sp6cx, self.ntris,
                           self.tet_wh, 1, self.tet_r, self.tet_std_py, 0.0, self.pc_tet)

    def set_link_schedule(self, dx, dz, cutx, cutz, is_roll_pose, chx, chz, nroot, cut_step):
        """Rewrite ONLY Link's baked schedule, keeping the compiled world.

        Everything expensive in a ctx is the world: the culled mesh, its planes/AABBs, and the
        `_precompute_slices` WallCorrect tables. The schedule is ~20 doubles a step. A search that
        varies the roll's momentum or lean rebuilds the whole ctx per group and pays 1.5 ms of world
        for a few microseconds of schedule -- so this swaps the schedule in place instead.

        Bit-exactness is not an argument, it is a gate: a ctx re-scheduled to a configuration must
        sweep identically to one BUILT at it
        (`tests/test_entry_search.py::test_a_re_scheduled_ctx_is_a_freshly_built_one`)."""
        cdef int i, j, n
        n = len(dx)
        if n != self.nsteps or len(chx[0]) != self.nlvl:
            free(self.dx); free(self.dz); free(self.cutx); free(self.cutz)
            free(self.is_roll_pose); free(self.chx); free(self.chz)
            self.nsteps = n
            self.nlvl = len(chx[0])
            self.dx = <double*>malloc(n * sizeof(double))
            self.dz = <double*>malloc(n * sizeof(double))
            self.cutx = <double*>malloc(n * sizeof(double))
            self.cutz = <double*>malloc(n * sizeof(double))
            self.is_roll_pose = <int*>malloc(n * sizeof(int))
            self.chx = <double*>malloc(n * self.nlvl * sizeof(double))
            self.chz = <double*>malloc(n * self.nlvl * sizeof(double))
        self.cut_step = cut_step
        self.nroot = nroot
        for i in range(n):
            self.dx[i] = dx[i]; self.dz[i] = dz[i]
            self.cutx[i] = cutx[i]; self.cutz[i] = cutz[i]
            self.is_roll_pose[i] = is_roll_pose[i]
            for j in range(self.nlvl):
                self.chx[i * self.nlvl + j] = chx[i][j]
                self.chz[i * self.nlvl + j] = chz[i][j]

    def __dealloc__(self):
        free(self.vtx); free(self.pla); free(self.aabb)
        free(self.sp68x); free(self.sp6cx)
        free(self.pc_link); free(self.pc_tet)
        free(self.bvtx); free(self.bpla)
        free(self.sin_t); free(self.cos_t); free(self.atn_t)
        free(self.dx); free(self.dz); free(self.cutx); free(self.cutz)
        free(self.is_roll_pose); free(self.chx); free(self.chz)

    cdef int _atan2s(self, double y, double x) noexcept nogil:
        """cM_atan2s(f0=y, f1=x) -- table atan2, u16."""
        cdef double f0 = f32(y), f1 = f32(x)
        cdef int r
        if _c_fabs(f0) < G_CM3D_F_ABS_MIN:
            return 0 if f1 >= 0.0 else 0x8000
        if _c_fabs(f1) < G_CM3D_F_ABS_MIN:
            return 0x4000 if f0 >= 0.0 else 0xC000
        if f0 >= 0.0:
            if f1 >= 0.0:
                if f1 >= f0:
                    r = self.atn_t[<int>fmuls(fdivs(f0, f1), 1024.0)]
                else:
                    r = 0x4000 - self.atn_t[<int>fmuls(fdivs(f1, f0), 1024.0)]
            else:
                if -f1 < f0:
                    r = self.atn_t[<int>fmuls(fdivs(-f1, f0), 1024.0)] + 0x4000
                else:
                    r = 0x8000 - self.atn_t[<int>fmuls(fdivs(f0, -f1), 1024.0)]
        elif f1 < 0.0:
            if f1 <= f0:
                r = self.atn_t[<int>fmuls(fdivs(-f0, -f1), 1024.0)] + 0x8000
            else:
                r = 0xC000 - self.atn_t[<int>fmuls(fdivs(-f1, -f0), 1024.0)]
        else:
            if f1 < -f0:
                r = self.atn_t[<int>fmuls(fdivs(f1, -f0), 1024.0)] + 0xC000
            else:
                r = -self.atn_t[<int>fmuls(fdivs(-f0, f1), 1024.0)]
        return r & 0xFFFF

    cdef inline double _ssin(self, int ang) noexcept nogil:
        return self.sin_t[(ang & 0xFFFF) >> 4]

    cdef inline double _scos(self, int ang) noexcept nogil:
        return self.cos_t[(ang & 0xFFFF) >> 4]

    cdef int _run(self, double place_x, double place_z, int placed_step,
                  double* out, double* trace, int* candbuf,
                  double link_x0, double link_z0,
                  double seed_spd, int seed_ang, int seed_stt) noexcept nogil:
        """The coupled roll from entry through the CUT entry step. ``out`` (16 doubles):
        [genuine, old_x, old_z, new_x, new_z, push_x, push_z, engaged, tet_x, tet_z, behindA, behindB,
        co_x, co_z, tet_x_cut, tet_z_cut] -- the last four being the CONTACT PAIR on the frame whose
        push the cut consumes (``cut_step - 1``): the animation-posed Co centre and where she is
        standing. They exist because a search is BLIND without them: with no overlap the push is zero
        and the depth stops depending on her placement at all, so the objective goes flat exactly
        where a climb needs a gradient to walk her into contact.
        ``trace`` (optional, nsteps*4): per-step (link_x, link_z, tet_x, tet_z). ``link_x0/z0`` =
        Link's roll-entry position (a SEARCH KNOB: the schedule tables are position-independent,
        so shifting the entry point -- roll timing along the approach line, or a lateral offset --
        reuses the same compiled schedule). ``placed_step=0`` seeds Tetra as an INITIAL condition
        (no mid-run write).

        ``seed_stt < 0`` seeds her AT REST (speedF 0, `STT_IDLE`, her facing left at the ctx's
        `tet_seed` angle) -- the historical behaviour and the default. Otherwise the placement is
        seeded WITH MOTION: speedF ``seed_spd``, facing ``seed_ang``, action state ``seed_stt``.
        That axis exists because her cut-frame distance is otherwise an EJECTION EQUILIBRIUM: the
        plow throws her out at half the overlap per frame, and a contact that CLOSES under her own
        follow momentum is the only thing an ejection cannot undo. Returns 0."""
        cdef double lx = f32(link_x0), lz = f32(link_z0), ly = self.link_y
        cdef double tx = self.tet_x0, ty = self.tet_y0, tz = self.tet_z0
        cdef int tang = self.tet_ang0
        cdef double tspd = self.tet_speedF0
        cdef int tstt = self.tet_stt0
        cdef double lpend_x = 0.0, lpend_z = 0.0
        cdef bint lpend_has = False
        cdef double tpend_x = 0.0, tpend_z = 0.0
        cdef bint engaged = False
        cdef int k, j, ang_to
        cdef double px0, pz0, ny, ymid, ddx, ddz, dy, dist2, temp, vt
        cdef double cx, cz, tx_r, tz_r, tx_n, tz_n
        cdef double odx, odz, dist_sq, cross_len, ff, sx_, sz_
        cdef double old_x = 0.0, old_z = 0.0
        cdef double pred_x = 0.0, pred_z = 0.0
        cdef double push_cons_x = 0.0, push_cons_z = 0.0
        cdef double engage2 = 52900.0            # f32(230*230), exact
        cdef double keep2 = 16900.0              # f32(130*130), exact
        out[12] = 0.0; out[13] = 0.0; out[14] = 0.0; out[15] = 0.0
        for k in range(self.nsteps):
            if k == placed_step:
                tx = f32(place_x); tz = f32(place_z); ty = f32(self.ground_y)
                if seed_stt < 0:
                    tspd = 0.0
                    tstt = 3
                else:
                    tspd = f32(seed_spd)
                    tang = seed_ang & 0xFFFF
                    tstt = seed_stt
                tpend_x = 0.0; tpend_z = 0.0
                lpend_has = False
            # ---- Link step (FRONT_ROLL / CUT): speedF move -> cc push -> cut lunge -> CrrPos
            px0 = lx; pz0 = lz
            if k == self.cut_step:
                old_x = px0; old_z = pz0
                push_cons_x = lpend_x if lpend_has else 0.0
                push_cons_z = lpend_z if lpend_has else 0.0
            lx = fadds(lx, self.dx[k])
            lz = fadds(lz, self.dz[k])
            if lpend_has:
                lx = fadds(lx, lpend_x)
                lz = fadds(lz, lpend_z)
                lpend_has = False
            if k == self.cut_step:
                lx = fadds(lx, self.cutx[k])
                lz = fadds(lz, self.cutz[k])
                pred_x = lx                      # the un-walled cut endpoint (pre-CrrPos): the
                pred_z = lz                      # threading metric -- CrrPos only ever pulls it back
            ymid = fadds(ly, self.link_grav)
            _acch_crr_pos(px0, ly, pz0, &lx, &ymid, &lz, self.link_grav,
                          self.vtx, self.pla, self.aabb, self.sp68x, self.sp6cx, self.ntris,
                          self.link_wh, 3, self.link_r, self.margin, candbuf,
                          self.pc_link, self.link_std_py)
            # ---- Tetra step (Zl1 idle/move + CC recoil + her CrrPos + ground clamp)
            ddx = fsubs(f32(lx), tx)
            dy = fsubs(f32(ly), ty)
            ddz = fsubs(f32(lz), tz)
            dist2 = fadds(fmadds(ddz, ddz, fmuls(ddx, ddx)), fmuls(dy, dy))
            ang_to = self._atan2s(fsubs(f32(lx), tx), fsubs(f32(lz), tz))
            if tstt == 3:                        # optn_1 idle
                if dist2 >= engage2:
                    tang = _add_calc_angle_s(tang, ang_to, 4, 0x800, 0x80)
                    if abs(_s16(ang_to - tang)) < 0x1800:
                        tstt = 4
                        engaged = True
            elif tstt == 4:                      # optn_2 move
                temp = fsubs(dist2, keep2)
                vt = 0.0
                if temp > 0.0:
                    vt = fmuls(0.03999999910593033, fsqrt_l(temp))
                    if vt > 10.0:
                        vt = 10.0
                tang = _add_calc_angle_s(tang, ang_to, 4, 0x800, 0x80)
                tspd = _chase_f(tspd, vt, 1.0)
                if <int>vt == 0 and <int>tspd == 0:
                    tstt = 3
                    tspd = 0.0
            px0 = tx; pz0 = tz
            sx_ = fmuls(tspd, self._ssin(tang))
            sz_ = fmuls(tspd, self._scos(tang))
            tx = fadds(fadds(tx, sx_), f32(tpend_x))
            tz = fadds(fadds(tz, sz_), f32(tpend_z))
            ny = ty                              # ground path: speed_y = 0
            _acch_crr_pos(px0, ty, pz0, &tx, &ny, &tz, 0.0,
                          self.vtx, self.pla, self.aabb, self.sp68x, self.sp6cx, self.ntris,
                          self.tet_wh, 1, self.tet_r, self.margin, candbuf,
                          self.pc_tet, self.tet_std_py)
            ty = f32(self.ground_y)
            # ---- CC check (end-of-frame settled positions -> next frame's pushes)
            if self.is_roll_pose[k]:
                tx_r = lx; tz_r = lz
                for j in range(self.nroot):
                    tx_r = fadds(self.chx[k * self.nlvl + j], tx_r)
                    tz_r = fadds(self.chz[k * self.nlvl + j], tz_r)
                tx_n = lx; tz_n = lz
                for j in range(self.nroot, self.nlvl):
                    tx_n = fadds(self.chx[k * self.nlvl + j], tx_n)
                    tz_n = fadds(self.chz[k * self.nlvl + j], tz_n)
                cx = fmuls(0.5, fadds(tx_r, tx_n))
                cz = fmuls(0.5, fadds(tz_r, tz_n))
            else:
                cx = lx; cz = lz
            if k == self.cut_step - 1:       # the contact pair the CUT frame's push comes from
                out[12] = cx; out[13] = cz
                out[14] = tx; out[15] = tz
            # cyl_cyl overlap (link Co cyl vs tetra cyl; y ranges always overlap on the flat floor)
            odx = fsubs(cx, tx)
            odz = fsubs(cz, tz)
            # UNFUSED (dx*dx)+(dz*dz) and the MSL sqrtf -- cM3d_Cross_CylCyl / dCcS::SetPosCorrect
            # as the JP binary compiles them (fmuls/fmuls/fadds at 0x8024C44C, 0x800AB430; frsqrte+
            # 3 Newton at 0x800AB444). Mirrors core/cc_push.py; see its FP note (session 55).
            dist_sq = fadds(fmuls(odx, odx), fmuls(odz, odz))
            lpend_x = 0.0; lpend_z = 0.0
            tpend_x = 0.0; tpend_z = 0.0
            lpend_has = True                     # co_move_pair returns zeros when no overlap
            if dist_sq <= fmuls(self.co_r_sum, self.co_r_sum):
                if not (fadds(ly, self.link_co_h) < ty or ly > fadds(ty, self.tet_co_h)):
                    cross_len = fsubs(self.co_r_sum, _sqrtf_msl_c(dist_sq))
                    if not is_zero_c(cross_len):
                        odx = fsubs(tx, cx)      # objsDist = obj2 - obj1
                        odz = fsubs(tz, cz)
                        temp = _sqrtf_msl_c(fadds(fmuls(odx, odx), fmuls(odz, odz)))
                        if not is_zero_c(temp):
                            ff = fdivs(cross_len, temp)
                            sx_ = fmuls(odx, ff)
                            sz_ = fmuls(odz, ff)
                            lpend_x = fmuls(sx_, fsubs(0.0, self.share2))
                            lpend_z = fmuls(sz_, fsubs(0.0, self.share2))
                            tpend_x = fmuls(sx_, self.share1)
                            tpend_z = fmuls(sz_, self.share1)
                        else:                    # coincident centres: +x degenerate branch
                            temp = cross_len
                            lpend_x = fmuls(fsubs(0.0, temp), self.share2)
                            tpend_x = fmuls(temp, self.share1)
            if trace != NULL:
                trace[k * 4 + 0] = lx; trace[k * 4 + 1] = lz
                trace[k * 4 + 2] = tx; trace[k * 4 + 3] = tz
            if k == self.cut_step:
                break
        # ---- acceptance: genuine_clip(old, new) over the legacy barrier + seam planes
        cdef double gy = self.link_geo_y
        cdef double ox = f32(old_x), oz = f32(old_z)
        cdef double nx = f32(lx), nz = f32(lz)
        cdef bint genuine = False
        cdef double fa, fb
        if not _crr_blocked_l(ox, gy, oz, nx, gy, nz, self.bvtx, self.bpla, self.nbar,
                              self.link_wh, 3, self.link_r):
            if (_plane_func(self.wa[0], self.wa[1], self.wa[2], self.wa[3], ox, gy, oz) > 0.0
                    and _plane_func(self.wb[0], self.wb[1], self.wb[2], self.wb[3], ox, gy, oz) > 0.0):
                fa = _plane_func(self.wa[0], self.wa[1], self.wa[2], self.wa[3], nx, gy, nz)
                fb = _plane_func(self.wb[0], self.wb[1], self.wb[2], self.wb[3], nx, gy, nz)
                if fa < 0.0 or fb < 0.0:
                    genuine = True
        out[0] = 1.0 if genuine else 0.0
        out[1] = old_x; out[2] = old_z
        out[3] = lx; out[4] = lz
        out[5] = push_cons_x; out[6] = push_cons_z
        out[7] = 1.0 if engaged else 0.0
        out[8] = tx; out[9] = tz
        # pred = the PRE-CrrPos cut endpoint's seam-plane values (the threading closeness metric;
        # genuine still requires the post-CrrPos unblocked test above).
        out[10] = _plane_func(self.wa[0], self.wa[1], self.wa[2], self.wa[3], f32(pred_x), self.link_geo_y, f32(pred_z))
        out[11] = _plane_func(self.wb[0], self.wb[1], self.wb[2], self.wb[3], f32(pred_x), self.link_geo_y, f32(pred_z))
        return 0

    def run_one(self, double place_x, double place_z, int placed_step,
                link_x0=None, link_z0=None, seed=None):
        """One placement -> dict(genuine, old, new, push, engaged, tetra, behind).
        ``link_x0/z0`` override Link's roll-entry position (default: the schedule's); ``seed`` =
        ``(speedF, facing, stt)`` seeds her WITH MOTION instead of at rest (see `_run`)."""
        cdef double out[16]
        cdef double lx0 = self.link_x0 if link_x0 is None else link_x0
        cdef double lz0 = self.link_z0 if link_z0 is None else link_z0
        cdef double sspd = 0.0 if seed is None else seed[0]
        cdef int sang = 0 if seed is None else int(seed[1])
        cdef int sstt = -1 if seed is None else int(seed[2])
        cdef int* cb = <int*>malloc(self.ntris * sizeof(int))
        self._run(place_x, place_z, placed_step, out, NULL, cb, lx0, lz0, sspd, sang, sstt)
        free(cb)
        return dict(genuine=bool(out[0]), old=(out[1], out[2]), new=(out[3], out[4]),
                    push=(out[5], out[6]), engaged=bool(out[7]), tetra=(out[8], out[9]),
                    behind=(out[10], out[11]))

    def run_trace(self, double place_x, double place_z, int placed_step,
                  link_x0=None, link_z0=None, seed=None):
        """One placement -> (result_dict, per-step [(link_x, link_z, tet_x, tet_z), ...])."""
        cdef double out[16]
        cdef double lx0 = self.link_x0 if link_x0 is None else link_x0
        cdef double lz0 = self.link_z0 if link_z0 is None else link_z0
        cdef double sspd = 0.0 if seed is None else seed[0]
        cdef int sang = 0 if seed is None else int(seed[1])
        cdef int sstt = -1 if seed is None else int(seed[2])
        cdef double* tr = <double*>malloc(self.nsteps * 4 * sizeof(double))
        cdef int* cb = <int*>malloc(self.ntris * sizeof(int))
        self._run(place_x, place_z, placed_step, out, tr, cb, lx0, lz0, sspd, sang, sstt)
        free(cb)
        steps = [(tr[k * 4], tr[k * 4 + 1], tr[k * 4 + 2], tr[k * 4 + 3])
                 for k in range(self.cut_step + 1)]
        free(tr)
        return (dict(genuine=bool(out[0]), old=(out[1], out[2]), new=(out[3], out[4]),
                     push=(out[5], out[6]), engaged=bool(out[7]), tetra=(out[8], out[9]),
                     behind=(out[10], out[11])), steps)

    def sweep(self, placements, int placed_step, link_x0=None, link_z0=None, seed=None):
        """Evaluate many placements (single-threaded); returns list of (genuine, old_x, old_z,
        new_x, new_z, push_x, push_z, engaged, behindA, behindB) per placement."""
        cdef double out[16]
        cdef double px, pz
        cdef double lx0 = self.link_x0 if link_x0 is None else link_x0
        cdef double lz0 = self.link_z0 if link_z0 is None else link_z0
        cdef double sspd = 0.0 if seed is None else seed[0]
        cdef int sang = 0 if seed is None else int(seed[1])
        cdef int sstt = -1 if seed is None else int(seed[2])
        cdef int* cb = <int*>malloc(self.ntris * sizeof(int))
        res = []
        for (px, pz) in placements:
            self._run(px, pz, placed_step, out, NULL, cb, lx0, lz0, sspd, sang, sstt)
            res.append((bool(out[0]), out[1], out[2], out[3], out[4],
                        out[5], out[6], bool(out[7]), out[10], out[11]))
        free(cb)
        return res

    def sweep_par(self, placements, int placed_step, link_x0=None, link_z0=None, seed=None,
                  bint extra=False):
        """OpenMP parallel sweep over placements (bit-identical to sweep; runs are independent).
        Also accepts per-item 4-tuples (px, pz, lx0, lz0) to vary Link's entry point in the same
        sweep (the plow-aside search: Tetra initial spot x Link entry), or 7-tuples
        (px, pz, lx0, lz0, speedF, facing, stt) to vary HER SEED MOTION too -- the axis that fights
        the plow's ejection equilibrium (`_run`). ``seed`` sets the motion for every item that does
        not carry its own. Returns the same tuple list."""
        cdef Py_ssize_t n = len(placements), i
        cdef double* pxz = <double*>malloc(n * 7 * sizeof(double))
        cdef double* outs = <double*>malloc(n * 16 * sizeof(double))
        cdef int nt = self.ntris
        cdef double dlx0 = self.link_x0 if link_x0 is None else link_x0
        cdef double dlz0 = self.link_z0 if link_z0 is None else link_z0
        cdef double dspd = 0.0 if seed is None else seed[0]
        cdef double dang = 0.0 if seed is None else int(seed[1])
        cdef double dstt = -1.0 if seed is None else int(seed[2])
        cdef int* cb
        for i in range(n):
            it = placements[i]
            pxz[i * 7 + 0] = it[0]
            pxz[i * 7 + 1] = it[1]
            pxz[i * 7 + 2] = it[2] if len(it) > 2 else dlx0
            pxz[i * 7 + 3] = it[3] if len(it) > 2 else dlz0
            pxz[i * 7 + 4] = it[4] if len(it) > 4 else dspd
            pxz[i * 7 + 5] = it[5] if len(it) > 4 else dang
            pxz[i * 7 + 6] = it[6] if len(it) > 4 else dstt
        with nogil, parallel():
            cb = <int*>malloc(nt * sizeof(int))    # thread-private candidate buffer
            for i in prange(n, schedule='static'):
                self._run(pxz[i * 7], pxz[i * 7 + 1], placed_step, outs + i * 16, NULL, cb,
                          pxz[i * 7 + 2], pxz[i * 7 + 3], pxz[i * 7 + 4],
                          <int>pxz[i * 7 + 5], <int>pxz[i * 7 + 6])
            free(cb)
        if extra:
            res = [(bool(outs[i * 16]), outs[i * 16 + 1], outs[i * 16 + 2], outs[i * 16 + 3],
                    outs[i * 16 + 4], outs[i * 16 + 5], outs[i * 16 + 6], bool(outs[i * 16 + 7]),
                    outs[i * 16 + 10], outs[i * 16 + 11], outs[i * 16 + 12], outs[i * 16 + 13],
                    outs[i * 16 + 14], outs[i * 16 + 15]) for i in range(n)]
        else:
            res = [(bool(outs[i * 16]), outs[i * 16 + 1], outs[i * 16 + 2], outs[i * 16 + 3],
                    outs[i * 16 + 4], outs[i * 16 + 5], outs[i * 16 + 6], bool(outs[i * 16 + 7]),
                    outs[i * 16 + 10], outs[i * 16 + 11]) for i in range(n)]
        free(pxz); free(outs)
        return res

    @property
    def entry(self):
        """(link_x0, link_z0, cut_step): the schedule's default roll-entry point + cut step."""
        return (self.link_x0, self.link_z0, self.cut_step)
