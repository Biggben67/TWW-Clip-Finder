# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""_collc.pyx - native (Cython) fast path for the wall-collision hot loop of core.collision.

Bit-EXACT drop-in replacements for the repeatedly-called swept/static wall barriers:
``crr_pos_walls`` -> ``line_check`` (cM3d_Cross_LinTri = plane cross + projected point-in-tri) and
``wall_correct`` (dBgW::RwgWallCorrect + cM2d_CrossCirLin), plus the leaf ``len2dsq``. The
single-precision arithmetic is inlined as C ``<double><float>`` casts -- identical to _fpc.pyx / the
fp.py ctypes path, so MSVC /fp:precise does NOT contract a*b+c into a hardware FMA and round-half-to-
even matches Dolphin bit-for-bit. Moving the CALLERS of the fp ops into one translation unit is the
whole point: it collapses the millions of per-op Python calls (and per-vertex attribute reads) into
inline C over flat double[] arrays.

The fused-vs-separate-round distinction is load-bearing and preserved exactly: the plane dot product
(cM3d_Cross_LinPla via PSVECDotProduct) fuses ``nx*px + ny*py`` (one fmadds); cM3d_VectorProduct2d,
cM3d_InDivPos2 and the WallCorrect interpolations use SEPARATE rounds. Every ``>0.0`` / ``<=20.0`` /
``<0.008`` comparison and the AABB / front-back / winding branch structure is transcribed verbatim.

``calc_pla``/``frsqrte``/``vecmag`` run once per triangle at ``Tri`` construction (NOT in this hot
loop) and stay in Python; here each ``Tri``'s precomputed plane (nx,ny,nz,d) + three verts are read
into C locals at the top of every public function. Faithful transcription of collision.py -- verified
0-ULP against the pure path over thousands of varied line inputs (seam + synthetic geometries).

Build: _build_native.py (cythonize --inplace). When the .pyd is absent collision.py falls back to its
own pure implementations (bit-identical, just slower), so this is an optional accelerator, never a
dependency.
"""

from libc.stdlib cimport malloc, free
from libc.math cimport sqrt as _c_sqrt, fabs as _c_fabs

# cM3d_IsZero threshold (kZero, c_m3d.h).
cdef double G_CM3D_F_ABS_MIN = 1.0e-5

# ---- single-precision primitives (identical to _fpc.pyx) -------------------------------------
cdef inline double f32(double x) nogil: return <double><float>x
cdef inline double fmuls(double a, double b) nogil: return <double><float>(a * b)
cdef inline double fadds(double a, double b) nogil: return <double><float>(a + b)
cdef inline double fsubs(double a, double b) nogil: return <double><float>(a - b)
cdef inline double fdivs(double a, double b) nogil: return <double><float>(a / b)
cdef inline double fmadds(double a, double b, double c) nogil: return <double><float>(a * b + c)
cdef inline double fmsubs(double a, double b, double c) nogil: return <double><float>(a * b - c)

cdef inline bint is_zero_c(double x) nogil:
    return _c_fabs(f32(x)) < G_CM3D_F_ABS_MIN

cdef inline double fsqrt_c(double a) nogil:
    return f32(_c_sqrt(f32(a)))


# ---- leaf: len2dsq (public + reused) ----------------------------------------------------------
cdef inline double _len2dsq(double x0, double y0, double x1, double y1) nogil:
    return fadds(fmuls(fsubs(x0, x1), fsubs(x0, x1)), fmuls(fsubs(y0, y1), fsubs(y0, y1)))


cpdef double len2dsq(double x0, double y0, double x1, double y1):
    return _len2dsq(x0, y0, x1, y1)


# ---- plane func: getPlaneFunc via PSVECDotProduct (nx*px + ny*py FUSED) ------------------------
cdef inline double _plane_func(double nx, double ny, double nz, double d,
                               double px, double py, double pz) nogil:
    cdef double ny_py = fmuls(ny, py)
    cdef double nz_pz = fmuls(nz, pz)
    cdef double dot = fadds(fmadds(nx, px, ny_py), nz_pz)   # nx*px + ny*py FUSED (ps_madd lane)
    return fadds(d, dot)


# ---- cM3d_Cross_LinPla / _cross_proc (writes crossing point into dst[3]) ----------------------
cdef inline bint _cross_proc(double av, double bv,
                             double sx, double sy, double sz,
                             double ex, double ey, double ez, double* dst) nogil:
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
                                bint a, bint b, double* dst) nogil:
    dst[0] = ex; dst[1] = ey; dst[2] = ez
    cdef double sv = _plane_func(nx, ny, nz, d, sx, sy, sz)
    cdef double ev = _plane_func(nx, ny, nz, d, ex, ey, ez)
    if fmuls(sv, ev) > 0.0:
        return False
    if sv >= 0.0 and ev <= 0.0:        # front -> back
        if a:
            return _cross_proc(sv, ev, sx, sy, sz, ex, ey, ez, dst)
    else:                               # back -> front
        if b:
            return _cross_proc(sv, ev, sx, sy, sz, ex, ey, ez, dst)
    return False


# ---- projected point-in-triangle: vprod2d / incl_box2d / _tri_in_2d ---------------------------
cdef inline double _vprod2d(double x1, double y1, double x2, double y2,
                            double x3, double y3) nogil:
    return fsubs(fmuls(fsubs(x2, x1), fsubs(y3, y1)), fmuls(fsubs(y2, y1), fsubs(x3, x1)))


cdef inline bint _incl_box2d(double ax, double ay, double bx, double by,
                             double cx, double cy, double px, double py) nogil:
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
                            double cx, double cy, double px, double py) nogil:
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


# ---- cM3d_CrossX/Y/Z_Tri (tv = this tri's 9 verts, tp = its 4 plane vals) ----------------------
cdef inline bint _crossX(double* tv, double* tp, double* pos) nogil:
    if is_zero_c(tp[0]): return False
    return _tri_in_2d(tv[1], tv[2], tv[4], tv[5], tv[7], tv[8], pos[1], pos[2])


cdef inline bint _crossY(double* tv, double* tp, double* pos) nogil:
    if is_zero_c(tp[1]): return False
    return _tri_in_2d(tv[2], tv[0], tv[5], tv[3], tv[8], tv[6], pos[2], pos[0])


cdef inline bint _crossZ(double* tv, double* tp, double* pos) nogil:
    if is_zero_c(tp[2]): return False
    return _tri_in_2d(tv[0], tv[1], tv[3], tv[4], tv[6], tv[7], pos[0], pos[1])


# ---- cM3d_Cross_LinTri ------------------------------------------------------------------------
cdef inline bint _cross_lin_tri(double sx, double sy, double sz,
                                double ex, double ey, double ez,
                                double* tv, double* tp, double* dst) nogil:
    cdef bint crossed = _cross_lin_pla(sx, sy, sz, ex, ey, ez,
                                       tp[0], tp[1], tp[2], tp[3], True, False, dst)
    if not crossed:
        return False
    cdef bint okx = (_c_fabs(tp[0]) < 0.008) or _crossX(tv, tp, dst)
    cdef bint oky = (_c_fabs(tp[1]) < 0.008) or _crossY(tv, tp, dst)
    cdef bint okz = (_c_fabs(tp[2]) < 0.008) or _crossZ(tv, tp, dst)
    return okx and oky and okz


# ---- cM2d_CrossCirLin -------------------------------------------------------------------------
cdef inline void _cross_cir_lin(double cx, double cy, double r,
                                double x0, double y0, double dirx, double diry,
                                double* opx, double* opy) nogil:
    cdef double fv1 = fsubs(x0, cx)
    cdef double fv15 = fsubs(y0, cy)
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
            s = fsqrt_c(disc)
            r1 = fmuls(k, fadds(f32(-d14), s))
            r2 = fmuls(k, fsubs(f32(-d14), s))
            t = r1 if r1 > r2 else r2
    if is_zero_c(t):
        opx[0] = x0; opy[0] = y0
        return
    opx[0] = fadds(x0, fmuls(t, dirx))
    opy[0] = fadds(y0, fmuls(t, diry))


# ---- cM3d_Len2dSqPntAndSegLine ----------------------------------------------------------------
cdef inline bint _len2dsq_pnt_seg(double xp, double yp, double x0, double y0,
                                  double x1, double y1,
                                  double* outx, double* outy, double* seg) nogil:
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


# ---- LineCheck (mutates px/py/pz in place) ----------------------------------------------------
cdef bint _line_check_c(double o0, double o1, double o2,
                        double* ppx, double* ppy, double* ppz,
                        double* vtx, double* pla, int n,
                        double* wh, int nh) nogil:
    cdef double px = ppx[0], py = ppy[0], pz = ppz[0]
    cdef bint hit_any = False
    cdef int hi, ti
    cdef double h, sx, sy, sz, cex, cey, cez
    cdef double dst[3]
    cdef bint hit_here, crossed
    for hi in range(nh):
        h = wh[hi]
        sx = o0; sy = fadds(o1, h); sz = o2
        cex = px; cey = fadds(py, h); cez = pz
        hit_here = False
        for ti in range(n):
            crossed = _cross_lin_tri(sx, sy, sz, cex, cey, cez, vtx + ti * 9, pla + ti * 4, dst)
            if crossed:
                cex = dst[0]; cey = dst[1]; cez = dst[2]
                hit_here = True
        if hit_here:
            hit_any = True
            px = cex
            pz = cez
            py = fsubs(cey, h)
    ppx[0] = px; ppy[0] = py; ppz[0] = pz
    return hit_any


# ---- WallCorrect (mutates px/pz in place; py held) --------------------------------------------
cdef bint _wall_correct_c(double* ppx, double py, double* ppz, double speed_y,
                          double* vtx, double* pla, int n,
                          double* wh, int nh, double wall_r) nogil:
    cdef double px = ppx[0], pz = ppz[0]
    cdef double wrr = fmuls(wall_r, wall_r)
    cdef bint hit = False
    cdef int ti, hi
    cdef double* tv
    cdef double* tp
    cdef double nx, ny, nz
    cdef double sp68, sp6C, h, sp78, sp50x, sp50z, sp7C
    cdef double s0, s1, s2, ss[3]
    cdef int zc, i0, i1, i2
    cdef double sp90, sp94, sp98, sp9C
    cdef double vx0, vx1, vx2, vz0, vz1, vz2
    cdef double cx0, cy0, cx1, cy1, cx0o, cy0o, cx1o, cy1o
    cdef double ccx, ccy, seg, d4, d8, move, e0, e1, onx, ony, fx, fy
    cdef bint on
    for ti in range(n):
        tv = vtx + ti * 9
        tp = pla + ti * 4
        nx = tp[0]; ny = tp[1]; nz = tp[2]
        sp68 = fsqrt_c(fadds(fmuls(nx, nx), fmuls(nz, nz)))
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
            vx0 = tv[0]; vx1 = tv[3]; vx2 = tv[6]
            vz0 = tv[2]; vz1 = tv[5]; vz2 = tv[8]
            if i0 == 0:
                cx0 = fadds(vx1, fmuls(sp98, fsubs(vx0, vx1))); cy0 = fadds(vz1, fmuls(sp98, fsubs(vz0, vz1)))
                cx1 = fadds(vx2, fmuls(sp9C, fsubs(vx0, vx2))); cy1 = fadds(vz2, fmuls(sp9C, fsubs(vz0, vz2)))
            elif i0 == 1:
                cx0 = fadds(vx0, fmuls(sp98, fsubs(vx1, vx0))); cy0 = fadds(vz0, fmuls(sp98, fsubs(vz1, vz0)))
                cx1 = fadds(vx2, fmuls(sp9C, fsubs(vx1, vx2))); cy1 = fadds(vz2, fmuls(sp9C, fsubs(vz1, vz2)))
            else:
                cx0 = fadds(vx0, fmuls(sp98, fsubs(vx2, vx0))); cy0 = fadds(vz0, fmuls(sp98, fsubs(vz2, vz0)))
                cx1 = fadds(vx1, fmuls(sp9C, fsubs(vx2, vx1))); cy1 = fadds(vz1, fmuls(sp9C, fsubs(vz2, vz1)))
            cx0o = fadds(cx0, sp50x); cy0o = fadds(cy0, sp50z)
            cx1o = fadds(cx1, sp50x); cy1o = fadds(cy1, sp50z)
            on = _len2dsq_pnt_seg(px, pz, cx0o, cy0o, cx1o, cy1o, &ccx, &ccy, &seg)
            d4 = fsubs(ccx, px); d8 = fsubs(ccy, pz)
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:
                move = fmuls(sp6C, fsqrt_c(seg))
                px = fadds(px, fmuls(move, nx))
                pz = fadds(pz, fmuls(move, nz))
                hit = True
            else:
                e0 = _len2dsq(cx0, cy0, px, pz)
                e1 = _len2dsq(cx1, cy1, px, pz)
                onx = f32(-nx); ony = f32(-nz)
                if e0 < e1:
                    if e0 > wrr or _c_fabs(fsubs(e0, wrr)) < 0.008:
                        continue
                    _cross_cir_lin(px, pz, wall_r, cx0, cy0, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx0, fx)); pz = fadds(pz, fsubs(cy0, fy))
                    hit = True
                else:
                    if e1 > wrr or _c_fabs(fsubs(e1, wrr)) < 0.008:
                        continue
                    _cross_cir_lin(px, pz, wall_r, cx1, cy1, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx1, fx)); pz = fadds(pz, fsubs(cy1, fy))
                    hit = True
    ppx[0] = px; ppz[0] = pz
    return hit


# ---- tri/wall_h extraction (Python objects -> flat C arrays) ----------------------------------
cdef int _load_tris(object tris, double** pvtx, double** ppla) except -1:
    cdef int n = len(tris)
    cdef double* vtx = <double*>malloc(n * 9 * sizeof(double))
    cdef double* pla = <double*>malloc(n * 4 * sizeof(double))
    if vtx == NULL or pla == NULL:
        free(vtx); free(pla)
        raise MemoryError()
    cdef int i
    cdef object tri, p, v0, v1, v2
    for i in range(n):
        tri = tris[i]
        v0 = tri.v0; v1 = tri.v1; v2 = tri.v2
        vtx[i * 9 + 0] = v0[0]; vtx[i * 9 + 1] = v0[1]; vtx[i * 9 + 2] = v0[2]
        vtx[i * 9 + 3] = v1[0]; vtx[i * 9 + 4] = v1[1]; vtx[i * 9 + 5] = v1[2]
        vtx[i * 9 + 6] = v2[0]; vtx[i * 9 + 7] = v2[1]; vtx[i * 9 + 8] = v2[2]
        p = tri.pla
        pla[i * 4 + 0] = p.nx; pla[i * 4 + 1] = p.ny; pla[i * 4 + 2] = p.nz; pla[i * 4 + 3] = p.d
    pvtx[0] = vtx; ppla[0] = pla
    return n


cdef double* _load_wh(object wall_h, int* pnh) except NULL:
    cdef int nh = len(wall_h)
    cdef double* wh = <double*>malloc(nh * sizeof(double))
    if wh == NULL:
        raise MemoryError()
    cdef int i
    for i in range(nh):
        wh[i] = wall_h[i]
    pnh[0] = nh
    return wh


# ---- public: line_check -----------------------------------------------------------------------
cpdef line_check(old_pos, new_pos, tris, wall_h):
    """dBgS_Acch::LineCheck over the wall cylinders. Returns (hit, snapped_new_pos)."""
    cdef double* vtx
    cdef double* pla
    cdef double* wh
    cdef int nh
    cdef int n = _load_tris(tris, &vtx, &pla)
    wh = _load_wh(wall_h, &nh)
    cdef double px = new_pos[0], py = new_pos[1], pz = new_pos[2]
    cdef bint hit_any = _line_check_c(old_pos[0], old_pos[1], old_pos[2],
                                      &px, &py, &pz, vtx, pla, n, wh, nh)
    free(vtx); free(pla); free(wh)
    return bool(hit_any), (px, py, pz)


# ---- public: wall_correct ---------------------------------------------------------------------
cpdef wall_correct(new_pos, speed_y, tris, wall_h, wall_r):
    """dBgW::RwgWallCorrect over all tris x cylinders. Returns (corrected_pos, wall_hit)."""
    cdef double* vtx
    cdef double* pla
    cdef double* wh
    cdef int nh
    cdef int n = _load_tris(tris, &vtx, &pla)
    wh = _load_wh(wall_h, &nh)
    cdef double px = new_pos[0], py = new_pos[1], pz = new_pos[2]
    cdef bint hit = _wall_correct_c(&px, py, &pz, speed_y, vtx, pla, n, wh, nh, wall_r)
    free(vtx); free(pla); free(wh)
    return (px, py, pz), bool(hit)


# ---- public: crr_pos_walls --------------------------------------------------------------------
cpdef crr_pos_walls(old_pos, new_pos, tris, wall_h=(30.1, 89.9, 125.0), wall_r=35.0, speed_y=0.0):
    """Wall-relevant part of dBgS_Acch::CrrPos. Returns (corrected_pos, info)."""
    cdef double* vtx
    cdef double* pla
    cdef double* wh
    cdef int nh
    cdef int n = _load_tris(tris, &vtx, &pla)
    wh = _load_wh(wall_h, &nh)
    cdef double o0 = old_pos[0], o1 = old_pos[1], o2 = old_pos[2]
    cdef double px = new_pos[0], py = new_pos[1], pz = new_pos[2]
    cdef double wr = wall_r, sy = speed_y
    cdef double dxz2 = _len2dsq(o0, o2, px, pz)
    cdef bint ran_line = dxz2 > fmuls(wr, wr)
    cdef bint line_hit = False
    cdef bint wall_hit, lh2
    if ran_line:
        line_hit = _line_check_c(o0, o1, o2, &px, &py, &pz, vtx, pla, n, wh, nh)
    wall_hit = _wall_correct_c(&px, py, &pz, sy, vtx, pla, n, wh, nh, wr)
    if wall_hit and ran_line:
        lh2 = _line_check_c(o0, o1, o2, &px, &py, &pz, vtx, pla, n, wh, nh)
        line_hit = line_hit or lh2
    free(vtx); free(pla); free(wh)
    return (px, py, pz), {"line_hit": bool(line_hit), "wall_hit": bool(wall_hit),
                          "ran_line": bool(ran_line)}


# ---- f32-lattice ring search (native port of gap_search.first_f32_clip) -----------------------
# The seam-clip locator's hot loop: for a fixed settled ``old`` and a continuous ``new_center`` just
# past the seam, enumerate f32-representable ``new`` on Chebyshev ULP rings out from ``new_center``
# and return the FIRST that clips (line + wall both miss). The pure-Python ring tops out at ~40-95k
# CrrPos/s because every candidate re-enters _load_tris (malloc + per-vertex Python attribute reads).
# Loading the trilist ONCE and running the ring entirely in C collapses that overhead; verified 0-ULP
# against the pure ring (same candidate order → identical FIRST hit and n_calls).

cdef inline double _next_f32_c(double x, int d) nogil:
    """The f32 that is ``d`` ULPs from f32 ``x`` (magnitude-directed: +d moves away from 0).
    Bit-identical to gap_search._next_f32 (unsigned 32-bit wrap == Python's ``& 0xFFFFFFFF``)."""
    cdef float fx = <float>x
    cdef unsigned int b = (<unsigned int*>&fx)[0]
    if x >= 0.0:
        b = b + <unsigned int>d
    else:
        b = b - <unsigned int>d
    cdef float out
    (<unsigned int*>&out)[0] = b
    return <double>out


cdef inline bint _crr_clips(double o0, double o1, double o2,
                            double nx0, double ny0, double nz0,
                            double* vtx, double* pla, int n,
                            double* wh, int nh, double wr) nogil:
    """True iff CrrPos on old=(o0,o1,o2) -> new=(nx0,ny0,nz0) misses BOTH the swept LineCheck and
    WallCorrect (a seam clip). Inlined crr_pos_walls with speed_y = 0, SHORT-CIRCUITED: only the
    clip boolean is needed, not the corrected pos, so the moment either check hits we know it is not
    a clip and stop. This skips the (expensive) WallCorrect on every line-blocked candidate — the
    dominant case for a genuinely-unclippable corner (the budget-drainers), so it is where the win
    lands. Bit-identical clip verdict to crr_pos_walls: a first-LineCheck hit or a WallCorrect hit
    both force ``(not line_hit_final) ∧ (not wall_hit)`` False regardless of the skipped work."""
    cdef double px = nx0, py = ny0, pz = nz0
    cdef double dxz2 = _len2dsq(o0, o2, px, pz)
    if dxz2 > fmuls(wr, wr):
        if _line_check_c(o0, o1, o2, &px, &py, &pz, vtx, pla, n, wh, nh):
            return False              # first LineCheck hit -> line_hit_final True -> not a clip
    if _wall_correct_c(&px, py, &pz, 0.0, vtx, pla, n, wh, nh, wr):
        return False                  # WallCorrect hit -> not a clip (second LineCheck irrelevant)
    return True                       # both missed -> clip


cpdef first_f32_clip(old_pos, new_center, link_y, tris, wall_h=(30.1, 89.9, 125.0),
                     wall_r=35.0, int box_ulps=120, max_calls=None):
    """Native EXISTENCE search: FIRST clipping f32 ``new`` on ULP rings out from ``new_center``.

    ``old_pos`` = settled f32 (x,y,z); ``new_center`` = (x,z) guess just past the seam; ``link_y`` =
    floor Y for ``new``. Returns ``(hit, n_calls)`` where ``hit`` = ``dict(disp, new, old)`` or None
    (matches gap_search.first_f32_clip). ``max_calls`` caps CrrPos evaluations (None = box only)."""
    cdef double* vtx
    cdef double* pla
    cdef double* wh
    cdef int nh
    cdef int n = _load_tris(tris, &vtx, &pla)
    wh = _load_wh(wall_h, &nh)
    cdef double o0 = old_pos[0], o1 = old_pos[1], o2 = old_pos[2]
    cdef double ly = link_y, wr = wall_r
    cdef double cx = <double><float>new_center[0]
    cdef double cz = <double><float>new_center[1]
    cdef long maxc = -1 if max_calls is None else <long>max_calls
    cdef long ncalls = 0
    cdef int r, i, j, k
    cdef double nx, nz
    cdef int state = 0          # 0 = keep going, 1 = found, 2 = capped
    cdef double hnx = 0.0, hnz = 0.0
    for r in range(0, box_ulps + 1):
        i = -r
        while i <= r:
            # abs(i) == r → full j sweep [-r, r]; else only the two edge rows j ∈ {-r, r}
            k = 0
            while True:
                if i == r or i == -r:
                    j = -r + k
                    if j > r:
                        break
                else:
                    if k == 0:
                        j = -r
                    elif k == 1:
                        j = r
                    else:
                        break
                if maxc >= 0 and ncalls >= maxc:
                    state = 2
                    break
                nx = _next_f32_c(cx, i)
                nz = _next_f32_c(cz, j)
                ncalls += 1
                if _crr_clips(o0, o1, o2, nx, ly, nz, vtx, pla, n, wh, nh, wr):
                    state = 1
                    hnx = nx; hnz = nz
                    break
                k += 1
            if state != 0:
                break
            i += 1
        if state != 0:
            break
    free(vtx); free(pla); free(wh)
    if state == 1:
        disp = ((hnx - o0) ** 2 + (hnz - o2) ** 2) ** 0.5
        return dict(disp=disp, new=(hnx, hnz), old=(o0, o2)), ncalls
    return None, ncalls
