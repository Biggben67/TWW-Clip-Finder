"""_acchc.pxi -- `dBgS_Acch::CrrPos` (the per-frame BG wall pass) as pure `noexcept nogil` C, for
inclusion into `_anmc.pyx` so a coupled step can brace BOTH actors inside the frame.

Faithful transcription of `core/collision.py`'s **acch_** layer -- `acch_line_check` (the
whd-latching LineCheck with the VECAdd normal push and the ground-classed poly branch),
`acch_wall_correct` (RwgWallCorrect + the endpoint push-out with the offset f32 round-trip) and
`acch_crr_pos` (LineCheck -> WallCorrect -> re-LineCheck when a wall corrected). Python is the
ORACLE: every routine here is gated `_bits`-equal against it (`tests/test_acch_native.py`), and a
disagreement is this file's bug, never collision.py's.

NOT the `crr_pos_walls` family in `_collc.pyx`: that one snaps the line without the normal add and
without the wall-height latch, which is a DIFFERENT function (the genuine-clip acceptance test), and
using it for an actor's per-frame pass would brace them a normal's length short.

A near-twin of `_shovec.pyx`'s `_acch_*` block, which is the same transcription for the shove sweep.
They are not shared, deliberately: `_shovec` seeds its `sqrtf_c` from the `__frsqrte` TABLE, and its
own `_sqrtf_msl_c` docstring records an UNDIAGNOSED access violation from calling the table-seeded one
at a second site. This file therefore uses `_anmc`'s math-accurate-seed `_sqrtf_c` (provably the same
value after the 3 Newton refines, and gated as such), so unifying the two would have to resolve that
bug first rather than inherit it.

Mesh contract: WALL tris in the game's WallCorrect traversal order (order is only visible when two
non-coplanar walls engage in one frame). No AABB prefilter -- a room mesh is tens of tris and the
whole pass is far under the pose FK, so every tri is tested and exactness is structural.
"""

# collision.G_CM3D_F_ABS_MIN (the legacy cM3d_IsZero) and the exact console 2^-18 the acch layer uses.
DEF _AC_IS0 = 1.0e-5
DEF _AC_IS0X = 3.814697265625e-06


cdef inline bint _ac_is_zero(double x) noexcept nogil:
    return _c_fabs(f32(x)) < _AC_IS0


cdef inline bint _ac_is_zero_x(double x) noexcept nogil:
    return _c_fabs(f32(x)) < _AC_IS0X


cdef inline double _ac_len2dsq(double x0, double y0, double x1, double y1) noexcept nogil:
    return fadds(fmuls(fsubs(x0, x1), fsubs(x0, x1)), fmuls(fsubs(y0, y1), fsubs(y0, y1)))


cdef inline double _ac_plane_func(double nx, double ny, double nz, double d,
                                  double px, double py, double pz) noexcept nogil:
    """getPlaneFunc via PSVECDotProduct: nx*px + ny*py is FUSED (one ps_madd lane)."""
    cdef double ny_py = fmuls(ny, py)
    cdef double nz_pz = fmuls(nz, pz)
    cdef double dot = fadds(fmadds(nx, px, ny_py), nz_pz)
    return fadds(d, dot)


cdef inline bint _ac_cross_proc(double av, double bv,
                                double sx, double sy, double sz,
                                double ex, double ey, double ez, double* dst) noexcept nogil:
    """collision._cross_proc + cM3d_InDivPos2 (three SEPARATE rounds, never fused)."""
    if _ac_is_zero(fsubs(av, bv)):
        dst[0] = ex; dst[1] = ey; dst[2] = ez
        return False
    cdef double scale = fdivs(av, fsubs(av, bv))
    dst[0] = fadds(sx, fmuls(fsubs(ex, sx), scale))
    dst[1] = fadds(sy, fmuls(fsubs(ey, sy), scale))
    dst[2] = fadds(sz, fmuls(fsubs(ez, sz), scale))
    return True


cdef inline bint _ac_cross_lin_pla(double sx, double sy, double sz,
                                   double ex, double ey, double ez,
                                   double nx, double ny, double nz, double d,
                                   double* dst) noexcept nogil:
    """cM3d_Cross_LinPla at the acch call's flags (a=frontFlag True, b=backFlag False)."""
    dst[0] = ex; dst[1] = ey; dst[2] = ez
    cdef double sv = _ac_plane_func(nx, ny, nz, d, sx, sy, sz)
    cdef double ev = _ac_plane_func(nx, ny, nz, d, ex, ey, ez)
    if fmuls(sv, ev) > 0.0:
        return False
    if sv >= 0.0 and ev <= 0.0:              # front -> back only
        return _ac_cross_proc(sv, ev, sx, sy, sz, ex, ey, ez, dst)
    return False


cdef inline double _ac_vprod2d(double x1, double y1, double x2, double y2,
                               double x3, double y3) noexcept nogil:
    return fsubs(fmuls(fsubs(x2, x1), fsubs(y3, y1)), fmuls(fsubs(y2, y1), fsubs(x3, x1)))


cdef inline bint _ac_incl_box2d(double ax, double ay, double bx, double by,
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


cdef inline bint _ac_tri_in_2d(double ax, double ay, double bx, double by,
                               double cx, double cy, double px, double py) noexcept nogil:
    if not _ac_incl_box2d(ax, ay, bx, by, cx, cy, px, py):
        return False
    cdef double f12 = _ac_vprod2d(ax, ay, bx, by, px, py)
    if (f12 <= 20.0
            and _ac_vprod2d(bx, by, cx, cy, px, py) <= 20.0
            and _ac_vprod2d(cx, cy, ax, ay, px, py) <= 20.0):
        return True
    if (f12 >= -20.0
            and _ac_vprod2d(bx, by, cx, cy, px, py) >= -20.0
            and _ac_vprod2d(cx, cy, ax, ay, px, py) >= -20.0):
        return True
    return False


cdef inline bint _ac_cross_lin_tri(double sx, double sy, double sz,
                                   double ex, double ey, double ez,
                                   double* tv, double* tp, double* dst) noexcept nogil:
    """cM3d_Cross_LinTri: plane crossing, then point-in-triangle in each projection whose normal
    component is significant (|n_axis| >= 0.008) and non-zero (crossX/Y/Z_tri)."""
    if not _ac_cross_lin_pla(sx, sy, sz, ex, ey, ez, tp[0], tp[1], tp[2], tp[3], dst):
        return False
    cdef bint okx = (_c_fabs(tp[0]) < 0.008) or (not _ac_is_zero(tp[0])
        and _ac_tri_in_2d(tv[1], tv[2], tv[4], tv[5], tv[7], tv[8], dst[1], dst[2]))
    cdef bint oky = (_c_fabs(tp[1]) < 0.008) or (not _ac_is_zero(tp[1])
        and _ac_tri_in_2d(tv[2], tv[0], tv[5], tv[3], tv[8], tv[6], dst[2], dst[0]))
    cdef bint okz = (_c_fabs(tp[2]) < 0.008) or (not _ac_is_zero(tp[2])
        and _ac_tri_in_2d(tv[0], tv[1], tv[3], tv[4], tv[6], tv[7], dst[0], dst[1]))
    return okx and oky and okz


cdef inline bint _ac_len2dsq_pnt_seg(double xp, double yp, double x0, double y0,
                                     double x1, double y1,
                                     double* outx, double* outy, double* seg) noexcept nogil:
    """cM3d_Len2dSqPntAndSegLine -> on_segment, with the foot point + its squared distance."""
    cdef double xd = fsubs(x1, x0)
    cdef double yd = fsubs(y1, y0)
    cdef double dot = fadds(fmuls(xd, xd), fmuls(yd, yd))
    if _ac_is_zero(dot):
        outx[0] = x0; outy[0] = y0; seg[0] = 0.0
        return False
    cdef double mag = fdivs(fadds(fmuls(xd, fsubs(xp, x0)), fmuls(yd, fsubs(yp, y0))), dot)
    cdef bint on = (0.0 <= mag <= 1.0)
    outx[0] = fadds(x0, fmuls(xd, mag))
    outy[0] = fadds(y0, fmuls(yd, mag))
    seg[0] = _ac_len2dsq(outx[0], outy[0], xp, yp)
    return on


cdef inline void _ac_cir_lin(double cx, double cy, double r,
                             double x0, double y0, double dirx, double diry,
                             double* opx, double* opy) noexcept nogil:
    """cM2d_CrossCirLin at the acch thresholds (collision._cross_cir_lin_x): IsZero 2^-18 and the
    MSL console sqrtf. Furthest intersection of the ray with the circle."""
    cdef double fv1 = fsubs(x0, cx), fv15 = fsubs(y0, cy)
    cdef double d13 = fadds(fmuls(dirx, dirx), fmuls(diry, diry))
    cdef double d14 = fmuls(2.0, fadds(fmuls(dirx, fv1), fmuls(diry, fv15)))
    cdef double c = fsubs(fadds(fmuls(fv1, fv1), fmuls(fv15, fv15)), fmuls(r, r))
    cdef double t = 0.0
    cdef double disc, k, s, r1, r2
    if _ac_is_zero_x(d13):
        if not _ac_is_zero_x(d14):
            t = fdivs(f32(-c), d14)
    else:
        disc = fsubs(fmuls(d14, d14), fmuls(fmuls(4.0, d13), c))
        if _ac_is_zero_x(disc):
            t = fdivs(f32(-d14), fmuls(2.0, d13))
        elif disc >= 0.0:
            k = fdivs(1.0, fmuls(2.0, d13))
            s = _sqrtf_c(disc)
            r1 = fmuls(k, fadds(f32(-d14), s))
            r2 = fmuls(k, fsubs(f32(-d14), s))
            t = r1 if r1 > r2 else r2
    if _ac_is_zero_x(t):
        opx[0] = x0; opy[0] = y0
        return
    opx[0] = fadds(x0, fmuls(t, dirx))
    opy[0] = fadds(y0, fmuls(t, diry))


# ---- dBgS_Acch::LineCheck (d_bg_s_acch.cpp:175), full wall response ----------------------------
cdef bint _ac_line_check(double o0, double o1, double o2,
                         double* ppx, double* ppy, double* ppz,
                         double* vtx, double* pla, int* cand, int nc,
                         double* wh, int nh, double* whd, bint* whd_set) noexcept nogil:
    """Twin of `collision.acch_line_check`: sweep old->pos at each cylinder height, and on the
    NEAREST front crossing snap pos to it, VECAdd the plane normal, latch whd[i] = pos.y when the
    normal has an XZ part (SetWallHDirect), then y -= wallH. A ground-classed poly (n.y >= 0.5)
    takes the y -= 1 branch instead."""
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
            if _ac_cross_lin_tri(sx, sy, sz, cex, cey, cez, vtx + ti * 9, pla + ti * 4, dst):
                cex = dst[0]; cey = dst[1]; cez = dst[2]
                hit_ti = ti
        if hit_ti >= 0:
            hit_any = True
            px = cex; py = cey; pz = cez
            nx = pla[hit_ti * 4 + 0]; ny = pla[hit_ti * 4 + 1]; nz = pla[hit_ti * 4 + 2]
            if not (ny >= 0.5):                  # !cBgW_CheckBGround -> wall response
                px = fadds(px, nx)
                py = fadds(py, ny)
                pz = fadds(pz, nz)
                if not _ac_is_zero_x(_sqrtf_c(fadds(fmuls(nx, nx), fmuls(nz, nz)))):
                    whd[hi] = py
                    whd_set[hi] = True
                py = fsubs(py, h)
            else:
                py = fsubs(py, 1.0)
    ppx[0] = px; ppy[0] = py; ppz[0] = pz
    return hit_any


# ---- dBgS::WallCorrect -> dBgW::RwgWallCorrect (d_bg_w.cpp:187) --------------------------------
cdef bint _ac_wall_correct(double* ppx, double py, double* ppz, double speed_y,
                           double* vtx, double* pla, double* sp68x, double* sp6cx,
                           int* cand, int nc,
                           double* wh, int nh, double wall_r,
                           double* whd, bint* whd_set,
                           bint* cir_hit, long long* cir_ang) noexcept nogil:
    """Twin of `collision.acch_wall_correct` (add_y = 0: GetWallAddY is 0 on flat ground). Slice
    height sp7C = whd[i] when LineCheck latched it (ChkWallHDirect), else (pos.y + h) - speed_y with
    the MID-FRAME dipped y. `cir_hit`/`cir_ang` collect SetWallCirHit / SetWallAngleY per cylinder
    (pass NULL when the caller has no proc reading them, e.g. Tetra)."""
    cdef double px = ppx[0], pz = ppz[0]
    cdef double wrr = fmuls(wall_r, wall_r)      # CalcWallRR
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
        # sp68/sp6C are per-tri constants of the plane normal, precomputed at mesh build with the
        # identical ops and hoisted out of the hot loop.
        sp68 = sp68x[ti]
        if _ac_is_zero_x(sp68):
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
            zc = ((1 if _ac_is_zero_x(s0) else 0) + (1 if _ac_is_zero_x(s1) else 0)
                  + (1 if _ac_is_zero_x(s2) else 0))
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
            if _ac_is_zero_x(sp90) or _ac_is_zero_x(sp94):
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
            on = _ac_len2dsq_pnt_seg(px, pz, cx0o, cy0o, cx1o, cy1o, &ccx, &ccy, &seg)
            d4 = fsubs(ccx, px); d8 = fsubs(ccy, pz)
            if seg > wrr or fadds(fmuls(d4, sp50x), fmuls(d8, sp50z)) < 0.0:
                continue
            if on:                                       # positionWallCorrect
                move = fmuls(_sqrtf_c(seg), sp6C)
                px = fadds(px, fmuls(move, nx))
                pz = fadds(pz, fmuls(move, nz))
            else:                                        # endpoint (seam-vertex) push-out
                # The decomp SUBTRACTS the offset back off the shifted endpoints -- an f32
                # round-trip, and f32((c+off)-off) != c in general, so keep the round-trip.
                cx0 = fsubs(cx0o, sp50x); cy0 = fsubs(cy0o, sp50z)
                cx1 = fsubs(cx1o, sp50x); cy1 = fsubs(cy1o, sp50z)
                e0 = _ac_len2dsq(cx0, cy0, px, pz)
                e1 = _ac_len2dsq(cx1, cy1, px, pz)
                onx = f32(-nx); ony = f32(-nz)
                if e0 < e1:
                    if e0 > wrr or _c_fabs(fsubs(e0, wrr)) < 0.008:
                        continue
                    _ac_cir_lin(px, pz, wall_r, cx0, cy0, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx0, fx)); pz = fadds(pz, fsubs(cy0, fy))
                else:
                    if e1 > wrr or _c_fabs(fsubs(e1, wrr)) < 0.008:
                        continue
                    _ac_cir_lin(px, pz, wall_r, cx1, cy1, onx, ony, &fx, &fy)
                    px = fadds(px, fsubs(cx1, fx)); pz = fadds(pz, fsubs(cy1, fy))
            agg = True                                   # SetWallHit (all three branches)
            if cir_hit != NULL:
                cir_hit[hi] = True                       # SetWallCirHit
                cir_ang[hi] = _cm_atan2s_c(nx, nz)       # SetWallAngleY
    ppx[0] = px; ppz[0] = pz
    return agg


# ---- dBgS_Acch::CrrPos (d_bg_s_acch.cpp:209), the wall part ------------------------------------
cdef bint _ac_crr_pos(double o0, double o1, double o2,
                      double* px, double* py, double* pz, double speed_y,
                      double* vtx, double* pla, double* sp68x, double* sp6cx,
                      int* cand, int nc,
                      double* wh, int nh, double wall_r,
                      bint* cir_hit, long long* cir_ang, bint* out_line_hit) noexcept nogil:
    """Twin of `collision.acch_crr_pos` at the PLAYER's flags: LineCheck runs unconditionally (the
    LINE_CHECK bit is set for both actors here, so `line_check_flag` short-circuits the distance
    tests), then WallCorrect, then a re-LineCheck iff a wall corrected. Returns wall_hit; the
    nullable out-params carry the rest of the `info` dict the Python twin returns, so no field of it
    is silently dropped on the way into C."""
    cdef double whd[8]
    cdef bint whd_set[8]
    cdef int hi
    # collision.acch_crr_pos rounds BOTH endpoints to f32 on entry (`_f(c)` over old_pos/new_pos) --
    # the console has no f64 to hand it. Keep the rounds so an f64-precision caller cannot open a
    # 1-ULP gap against the Python oracle.
    o0 = f32(o0); o1 = f32(o1); o2 = f32(o2)
    px[0] = f32(px[0]); py[0] = f32(py[0]); pz[0] = f32(pz[0])
    for hi in range(nh):
        whd_set[hi] = False
        whd[hi] = 0.0
    if cir_hit != NULL:
        for hi in range(nh):
            cir_hit[hi] = False
            cir_ang[hi] = 0
    cdef bint line_hit = _ac_line_check(o0, o1, o2, px, py, pz, vtx, pla, cand, nc,
                                        wh, nh, whd, whd_set)
    cdef bint wall_hit = _ac_wall_correct(px, py[0], pz, speed_y, vtx, pla, sp68x, sp6cx,
                                          cand, nc, wh, nh, wall_r, whd, whd_set,
                                          cir_hit, cir_ang)
    if wall_hit:
        if _ac_line_check(o0, o1, o2, px, py, pz, vtx, pla, cand, nc, wh, nh, whd, whd_set):
            line_hit = True
    if out_line_hit != NULL:
        out_line_hit[0] = line_hit
    return wall_hit


# ---- the mesh, as flat C arrays shared by every core that walks it ------------------------------
cdef class WallMesh:
    """An ordered WALL trilist flattened to C arrays: verts (n*9), planes (n*4), the per-tri
    `sqrtf_c(nx^2+nz^2)` and its reciprocal, and the identity candidate list.

    IMMUTABLE once built, so a `LandCore.clone()` shares it by reference and a parallel fan-out
    reads it concurrently from every thread -- exactly the `AnimData` contract. Build it ONCE per
    mesh as a module-level list and hand the same object
    to every core; rebuilding per core would copy 48 tris per node of a beam."""
    cdef double* _vtx
    cdef double* _pla
    cdef double* _sp68
    cdef double* _sp6c
    cdef int* _cand
    cdef int _n

    def __cinit__(self, tris):
        cdef int n = len(tris)
        self._n = n
        self._vtx = <double*>malloc(n * 9 * sizeof(double))
        self._pla = <double*>malloc(n * 4 * sizeof(double))
        self._sp68 = <double*>malloc(n * sizeof(double))
        self._sp6c = <double*>malloc(n * sizeof(double))
        self._cand = <int*>malloc(n * sizeof(int))
        if (self._vtx == NULL or self._pla == NULL or self._sp68 == NULL
                or self._sp6c == NULL or self._cand == NULL):
            raise MemoryError()
        cdef int i
        cdef double nx, nz, sp68
        for i in range(n):
            tri = tris[i]
            v0 = tri.v0; v1 = tri.v1; v2 = tri.v2
            self._vtx[i * 9 + 0] = v0[0]; self._vtx[i * 9 + 1] = v0[1]; self._vtx[i * 9 + 2] = v0[2]
            self._vtx[i * 9 + 3] = v1[0]; self._vtx[i * 9 + 4] = v1[1]; self._vtx[i * 9 + 5] = v1[2]
            self._vtx[i * 9 + 6] = v2[0]; self._vtx[i * 9 + 7] = v2[1]; self._vtx[i * 9 + 8] = v2[2]
            p = tri.pla
            nx = p.nx; nz = p.nz
            self._pla[i * 4 + 0] = nx; self._pla[i * 4 + 1] = p.ny
            self._pla[i * 4 + 2] = nz; self._pla[i * 4 + 3] = p.d
            sp68 = _sqrtf_c(fadds(fmuls(nx, nx), fmuls(nz, nz)))
            self._sp68[i] = sp68
            self._sp6c[i] = fdivs(1.0, sp68) if not _ac_is_zero_x(sp68) else 0.0
            self._cand[i] = i

    def __dealloc__(self):
        free(self._vtx); free(self._pla); free(self._sp68); free(self._sp6c); free(self._cand)

    @property
    def size(self):
        return self._n

    def crr_pos(self, old_pos, new_pos, wall_h, double wall_r, double speed_y=0.0):
        """`collision.acch_crr_pos` through THIS mesh -- the leaf the 0-ULP gate diffs against the
        Python original. Returns ``(pos, info)`` with the same `info` keys the Python twin fills
        (`wall_hit`, `cir_hit`, `wall_angle`, `line_hit`; `ran_line` is always True at these flags)."""
        cdef double wh[8]
        cdef int nh = len(wall_h)
        cdef int i
        if nh > 8:
            raise ValueError("at most 8 wall cylinders")
        for i in range(nh):
            wh[i] = wall_h[i]
        cdef double px = new_pos[0], py = new_pos[1], pz = new_pos[2]
        cdef bint ch[8]
        cdef long long ca[8]
        cdef bint lh = False
        cdef bint hit = _ac_crr_pos(old_pos[0], old_pos[1], old_pos[2], &px, &py, &pz, speed_y,
                                    self._vtx, self._pla, self._sp68, self._sp6c,
                                    self._cand, self._n, wh, nh, wall_r, ch, ca, &lh)
        return ((px, py, pz), {"wall_hit": bool(hit),
                               "cir_hit": [bool(ch[i]) for i in range(nh)],
                               "wall_angle": [int(ca[i]) for i in range(nh)],
                               "line_hit": bool(lh), "ran_line": True})
