# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""_anmc.pyx - native (Cython) fast path for the land-walk anim hot loop.

Bit-EXACT drop-in replacements for the hottest pure-numeric functions of the foot-FK / quaternion /
Hermite chain (fk.mtx_concat / mtx_mult_vec, quat.euler_to_quat / quat_lerp / psmtx_quat,
j3d_eval.hermite_s16 / hermite_f32). The single-precision arithmetic is inlined as C `<double><float>`
casts -- identical to _fpc.pyx and to fp.py's ctypes path, so no FMA contraction and round-half-to-even
match Dolphin bit-for-bit. Moving the CALLERS of the fp ops into the same translation unit is the whole
point: it collapses millions of per-op Python calls into inline C.

The console cos/sin BAM tables are copied once (init_tables) into C arrays; euler_to_quat and the
quat scale/inverse read them directly. Everything here is a faithful transcription of the pure-Python
originals -- verified against the 0-ULP golden suite + the perf_land fingerprint.

Build: _build_native.py (cythonize --inplace). When the .pyd is absent the Python modules fall back to
their own pure implementations (same result), so this is an optional accelerator, never a dependency.
"""

from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from libc.math cimport (sqrt as _c_sqrt, hypot as _c_hypot, atan2 as _c_atan2,
                        fabs as _c_fabs, copysign as _c_copysign, fmod as _c_fmod,
                        rint as _c_rint, floor as _c_floor)

# ---- single-precision primitives (identical to _fpc.pyx) -------------------------------------
cdef inline double f32(double x) noexcept nogil: return <double><float>x
cdef inline double fmuls(double a, double b) noexcept nogil: return <double><float>(a * b)
cdef inline double fadds(double a, double b) noexcept nogil: return <double><float>(a + b)
cdef inline double fsubs(double a, double b) noexcept nogil: return <double><float>(a - b)
cdef inline double fdivs(double a, double b) noexcept nogil: return <double><float>(a / b)
cdef inline double fmadds(double a, double b, double c) noexcept nogil: return <double><float>(a * b + c)
cdef inline double fmsubs(double a, double b, double c) noexcept nogil: return <double><float>(a * b - c)
cdef inline double fnmadds(double a, double b, double c) noexcept nogil: return <double><float>(-(a * b + c))
cdef inline double fnmsubs(double a, double b, double c) noexcept nogil: return <double><float>(-(a * b - c))

# ---- console BAM cos/sin tables (populated by init_tables from mathlib) -----------------------
cdef double COS_TABLE[4096]
cdef double SIN_TABLE[4096]
cdef bint _TABLES_READY = False


def init_tables(cos_table, sin_table):
    """Copy the console jmaCosTable / jmaSinTable (4096 f32 values each) into C arrays. Idempotent."""
    global _TABLES_READY
    cdef int i
    for i in range(4096):
        COS_TABLE[i] = cos_table[i]
        SIN_TABLE[i] = sin_table[i]
    _TABLES_READY = True


def tables_ready():
    return _TABLES_READY


# ---- cM_atan2s: the TABLE atan2 -> u16 angle (c_math.cpp:118) ----------------------------------
# Distinct from the stick-decode atan2f: U_GetAtanTable is a 1025-entry table indexed by the f32
# (int)(a/b * 1024). Bit-exact twin of mathlib.cM_atan2s -- the cone gate + setShapeAngleToAtnActor
# re-aim need it. Populated by init_atan_table from mathlib._ATN_TABLE.
cdef unsigned short _ATAN_TABLE[1025]
cdef bint _ATAN_READY = False
DEF _CM3D_ABS_MIN = 3.814697265625e-06        # 2^-18 (mathlib G_CM3D_F_ABS_MIN)


def init_atan_table(table):
    """Copy mathlib._ATN_TABLE (1025 u16 entries) into C. Idempotent."""
    global _ATAN_READY
    cdef int i
    for i in range(1025):
        _ATAN_TABLE[i] = <unsigned short>(<int>table[i])
    _ATAN_READY = True


cdef inline long long _atab(double a, double b) noexcept nogil:
    """U_GetAtanTable(a, b): _ATN_TABLE[(int)f32(f32(a/b) * 1024)]."""
    cdef int idx = <int>f32(fmuls(fdivs(a, b), 1024.0))
    return <long long>_ATAN_TABLE[idx]


cdef long long _cm_atan2s_c(double f0, double f1) noexcept nogil:
    """cM_atan2s (c_math.cpp:118). Bit-exact port of mathlib.cM_atan2s."""
    f0 = f32(f0); f1 = f32(f1)
    cdef double a0 = f0 if f0 >= 0.0 else -f0
    cdef double a1 = f1 if f1 >= 0.0 else -f1
    if a0 < _CM3D_ABS_MIN:
        return 0 if f1 >= 0.0 else 0x8000
    if a1 < _CM3D_ABS_MIN:
        return 0x4000 if f0 >= 0.0 else 0xC000
    cdef long long r
    if f0 >= 0.0:
        if f1 >= 0.0:
            r = _atab(f0, f1) if f1 >= f0 else 0x4000 - _atab(f1, f0)
        else:
            r = (_atab(-f1, f0) + 0x4000) if -f1 < f0 else 0x8000 - _atab(f0, -f1)
    elif f1 < 0.0:
        r = (_atab(-f0, -f1) + 0x8000) if f1 <= f0 else 0xC000 - _atab(-f1, -f0)
    else:
        r = (_atab(f1, -f0) + 0xC000) if f1 < -f0 else -_atab(-f0, f1)
    return r & 0xFFFF


def cm_atan2s(f0, f1):
    """Public wrapper over the native cM_atan2s (for gating vs mathlib.cM_atan2s)."""
    if not _ATAN_READY:
        raise RuntimeError("init_atan_table() must be called first")
    return _cm_atan2s_c(f0, f1)


cdef inline double jma_cos(long long a) noexcept nogil:
    return COS_TABLE[(a & 0xFFFF) >> 4]

cdef inline double jma_sin(long long a) noexcept nogil:
    return SIN_TABLE[(a & 0xFFFF) >> 4]


# ---- fres: PPC 750CL reciprocal estimate (matches Dolphin ApproximateReciprocal) -------------
cdef unsigned int _FRES_BASE[32]
cdef unsigned int _FRES_DEC[32]
cdef bint _FRES_INIT = False

cdef void _init_fres() noexcept nogil:
    global _FRES_INIT
    cdef unsigned int base[32]
    cdef unsigned int dec[32]
    base[0]=0x7ff800; base[1]=0x783800; base[2]=0x70ea00; base[3]=0x6a0800
    base[4]=0x638800; base[5]=0x5d6200; base[6]=0x579000; base[7]=0x520800
    base[8]=0x4cc800; base[9]=0x47ca00; base[10]=0x430800; base[11]=0x3e8000
    base[12]=0x3a2c00; base[13]=0x360800; base[14]=0x321400; base[15]=0x2e4a00
    base[16]=0x2aa800; base[17]=0x272c00; base[18]=0x23d600; base[19]=0x209e00
    base[20]=0x1d8800; base[21]=0x1a9000; base[22]=0x17ae00; base[23]=0x14f800
    base[24]=0x124400; base[25]=0x0fbe00; base[26]=0x0d3800; base[27]=0x0ade00
    base[28]=0x088400; base[29]=0x065000; base[30]=0x041c00; base[31]=0x020c00
    dec[0]=0x3e1; dec[1]=0x3a7; dec[2]=0x371; dec[3]=0x340
    dec[4]=0x313; dec[5]=0x2ea; dec[6]=0x2c4; dec[7]=0x2a0
    dec[8]=0x27f; dec[9]=0x261; dec[10]=0x245; dec[11]=0x22a
    dec[12]=0x212; dec[13]=0x1fb; dec[14]=0x1e5; dec[15]=0x1d1
    dec[16]=0x1be; dec[17]=0x1ac; dec[18]=0x19b; dec[19]=0x18b
    dec[20]=0x17c; dec[21]=0x16e; dec[22]=0x15b; dec[23]=0x15b
    dec[24]=0x143; dec[25]=0x143; dec[26]=0x12d; dec[27]=0x12d
    dec[28]=0x11a; dec[29]=0x11a; dec[30]=0x108; dec[31]=0x106
    cdef int i
    for i in range(32):
        _FRES_BASE[i] = base[i]
        _FRES_DEC[i] = dec[i]
    _FRES_INIT = True

cdef inline unsigned long long _d2u(double x) noexcept nogil:
    return (<unsigned long long*>&x)[0]

cdef inline double _u2d(unsigned long long u) noexcept nogil:
    return (<double*>&u)[0]

cdef double _fres(double x) noexcept nogil:
    """Hardware fres estimate of x (no Newton). Bit-identical to quat._fres."""
    if not _FRES_INIT:
        _init_fres()
    cdef unsigned long long integral = _d2u(x)
    cdef unsigned long long mantissa = integral & ((<unsigned long long>1 << 52) - 1)
    cdef unsigned long long sign = integral & (<unsigned long long>1 << 63)
    cdef unsigned long long exponent = integral & (<unsigned long long>0x7FF << 52)
    cdef unsigned long long i, base, dec, out
    if mantissa == 0 and exponent == 0:
        return _u2d(sign | (<unsigned long long>0x7FF << 52))
    if exponent == (<unsigned long long>0x7FF << 52):
        return _u2d(sign) if mantissa == 0 else 0.0 + x
    if exponent < (<unsigned long long>895 << 52):
        return _u2d(sign | (<unsigned long long>0x7FF << 52))
    if exponent >= (<unsigned long long>1149 << 52):
        return _u2d(sign)
    i = mantissa >> 37
    base = _FRES_BASE[i >> 10]
    dec = _FRES_DEC[i >> 10]
    out = sign
    out |= ((<unsigned long long>0x7FD - (exponent >> 52)) << 52)
    out |= ((base - (dec * (i % 1024) + 1) // 2) << 29)
    return _u2d(out)

cdef inline double _recip2(double denom) noexcept nogil:
    """2/denom via fres + one Newton refine + *2 (PSMTXQuat asm)."""
    cdef double est = f32(_fres(denom))
    cdef double r = fmuls(est, fnmsubs(denom, est, 2.0))
    return fmuls(r, 2.0)


# ---- euler s16 -> quaternion (JMAEulerToQuat, non-fused) --------------------------------------
cdef inline long long _half(long long a) noexcept nogil:
    # The parameter is s16: SIGN-EXTEND before halving (session 56 -- an unsigned half lands 2048
    # table entries away, giving the equivalent NEGATED quat whose table magnitudes differ by tens
    # of ULP; see quat.euler_to_quat). C `s16/2` then truncates toward zero (Python's // truncates
    # toward -inf, so replicate that here).
    a = a & 0xFFFF
    if a >= 0x8000:
        a -= 0x10000
    return a // 2 if a >= 0 else -((-a) // 2)

cdef void _euler_to_quat_c(long long rx, long long ry, long long rz, double* out) noexcept nogil:
    """out[0..3] = (w,x,y,z). Bit-exact core of quat.euler_to_quat."""
    cdef double c0 = jma_cos(_half(rx)), c1 = jma_cos(_half(ry)), c2 = jma_cos(_half(rz))
    cdef double s0 = jma_sin(_half(rx)), s1 = jma_sin(_half(ry)), s2 = jma_sin(_half(rz))
    cdef double c1c2 = fmuls(c1, c2)
    cdef double s1s2 = fmuls(s1, s2)
    out[0] = fadds(fmuls(c0, c1c2), fmuls(s0, s1s2))
    out[1] = fsubs(fmuls(s0, c1c2), fmuls(c0, s1s2))
    out[2] = fadds(fmuls(c2, fmuls(c0, s1)), fmuls(s2, fmuls(s0, c1)))
    out[3] = fsubs(fmuls(s2, fmuls(c0, c1)), fmuls(c2, fmuls(s0, s1)))

def euler_to_quat(rx, ry, rz):
    """(w,x,y,z) from s16 euler. Bit-exact port of quat.euler_to_quat."""
    cdef double q[4]
    _euler_to_quat_c(rx, ry, rz, q)
    return (q[0], q[1], q[2], q[3])


# ---- quaternion lerp (JMAQuatLerp: f32 dot, sign-flip, f64 lerp -> f32) ------------------------
cdef void _quat_lerp_c(double* a, double* b, double t, double* out) noexcept nogil:
    """out[0..3] = lerp(a,b,t). a/b are (w,x,y,z). Bit-exact core of quat.quat_lerp."""
    cdef double aw = a[0], ax = a[1], ay = a[2], az = a[3]
    cdef double bw = b[0], bx = b[1], by = b[2], bz = b[3]
    cdef double dot = fmadds(aw, bw, fmadds(az, bz, fmadds(ay, by, fmuls(ax, bx))))
    if dot < 0.0:
        bw = -bw; bx = -bx; by = -by; bz = -bz
    cdef double om = 1.0 - t
    out[0] = f32(om * aw + t * bw)
    out[1] = f32(om * ax + t * bx)
    out[2] = f32(om * ay + t * by)
    out[3] = f32(om * az + t * bz)

def quat_lerp(a, b, t):
    cdef double ca[4]
    cdef double cb[4]
    cdef double out[4]
    ca[0] = a[0]; ca[1] = a[1]; ca[2] = a[2]; ca[3] = a[3]
    cb[0] = b[0]; cb[1] = b[1]; cb[2] = b[2]; cb[3] = b[3]
    _quat_lerp_c(ca, cb, t, out)
    return (out[0], out[1], out[2], out[3])


# ---- quaternion concat (mDoMtx_QuatConcat: plain f64 products, single f32 round) ---------------
cdef void _quat_concat_c(double* a, double* b, double* out) noexcept nogil:
    """out = a (x) b (Hamilton product). a/b/out are (w,x,y,z). Bit-exact core of
    foot_fk.FootFK._quat_concat -- each component is a plain f64 expression rounded ONCE to f32
    (the products of f32 inputs are exact in f64, so the single round matches the game). out may
    NOT alias a or b."""
    cdef double aw = a[0], ax = a[1], ay = a[2], az = a[3]
    cdef double bw = b[0], bx = b[1], by = b[2], bz = b[3]
    out[0] = f32(aw * bw - ax * bx - ay * by - az * bz)
    out[1] = f32(aw * bx + ax * bw + ay * bz - az * by)
    out[2] = f32(aw * by - ax * bz + ay * bw + az * bx)
    out[3] = f32(aw * bz + ax * by - ay * bx + az * bw)


# ---- PSMTXQuat (retail paired-single asm), fres scale mode ------------------------------------
cdef void _psmtx_quat_c(double* q, double* m) noexcept nogil:
    """m[0..11] = 3x4 rotation matrix (row-major, trans cols = m[3],m[7],m[11] set to 0) from
    q=(w,x,y,z) via the retail PSMTXQuat asm, fres scale. Line-for-line core of quat.psmtx_quat."""
    cdef double w = q[0], x = q[1], y = q[2], z = q[3]
    cdef double t0a = x, t0b = y, t1a = z, t1b = w
    cdef double t2a = fmuls(t0a, t0a), t2b = fmuls(t0b, t0b)
    cdef double t5a = t0b, t5b = t0a
    cdef double t4a = fmadds(t1a, t1a, t2a), t4b = fmadds(t1b, t1b, t2b)
    cdef double t3a = fmuls(t1a, t1a)
    cdef double denom = fadds(t4a, t4b)
    cdef double t7a = fmuls(t5a, t1b), t7b = fmuls(t5b, t1b)
    cdef double s = _recip2(denom)
    t4b = fadds(t3a, t2b)
    cdef double t6a = fmuls(t1a, t1b), t6b = fmuls(t1b, t1b)
    t2a = fadds(t2a, t2b)
    cdef double t8a = fmadds(t0a, t5a, t6a), t8b = fmadds(t0b, t5b, t6b)
    t6a = fmsubs(t0a, t5a, t6a); t6b = fmsubs(t0b, t5b, t6b)
    t2a = fnmsubs(t2a, s, 1.0)
    t4a = fnmsubs(t4a, s, 1.0); t4b = fnmsubs(t4b, s, 1.0)
    t8a = fmuls(t8a, s); t8b = fmuls(t8b, s)
    t6a = fmuls(t6a, s); t6b = fmuls(t6b, s)
    cdef double m22 = t2a
    t5a = fmadds(t0a, t1a, t7a); t5b = fmadds(t0b, t1a, t7b)
    cdef double m10 = t8a, m11 = t4a
    t7a = fnmsubs(t7a, 2.0, t5a); t7b = fnmsubs(t7b, 2.0, t5b)
    cdef double m00 = t4b, m01 = t6a
    t5a = fmuls(t5a, s); t5b = fmuls(t5b, s)
    t7a = fmuls(t7a, s); t7b = fmuls(t7b, s)
    cdef double m02 = t5a
    cdef double m12 = t7b, m20 = t7a, m21 = t5b
    m[0] = m00; m[1] = m01; m[2] = m02; m[3] = 0.0
    m[4] = m10; m[5] = m11; m[6] = m12; m[7] = 0.0
    m[8] = m20; m[9] = m21; m[10] = m22; m[11] = 0.0


def psmtx_quat(q):
    """3x4 rotation matrix (trans=0) from q=(w,x,y,z) via the retail PSMTXQuat asm, fres scale."""
    cdef double cq[4]
    cdef double m[12]
    cq[0] = q[0]; cq[1] = q[1]; cq[2] = q[2]; cq[3] = q[3]
    _psmtx_quat_c(cq, m)
    return [[m[0], m[1], m[2], m[3]], [m[4], m[5], m[6], m[7]], [m[8], m[9], m[10], m[11]]]


# ---- fused per-joint blend: euler->quat x2 -> lerp -> morf -> psmtx_quat -> scale/trans ---------
def blend_joint(i0, i1, double ratio, double rate, bint apply_morf,
                old_quat, old_trans, old_scale):
    """One foot-chain joint's local 3x4 matrix + its posed (quat, trans, scale) for the old-pose store.
    Fused bit-exact port of foot_fk._blend_joint + _pose_frame's scale-column multiply. i0/i1 are the
    two calc_transform dicts (rotation[3] s16 ints, translate[3]/scale[3] f32). `apply_morf` gates the
    oldframe-morf toward (old_quat, old_trans, old_scale). Returns (mtx3x4, q3, trans, scale)."""
    cdef long long r0x = i0['rotation'][0], r0y = i0['rotation'][1], r0z = i0['rotation'][2]
    cdef long long r1x = i1['rotation'][0], r1y = i1['rotation'][1], r1z = i1['rotation'][2]
    cdef double i0t0 = i0['translate'][0], i0t1 = i0['translate'][1], i0t2 = i0['translate'][2]
    cdef double i1t0 = i1['translate'][0], i1t1 = i1['translate'][1], i1t2 = i1['translate'][2]
    cdef double i0s0 = i0['scale'][0], i0s1 = i0['scale'][1], i0s2 = i0['scale'][2]
    cdef double i1s0 = i1['scale'][0], i1s1 = i1['scale'][1], i1s2 = i1['scale'][2]

    cdef double q0[4]
    cdef double q1[4]
    cdef double q3[4]
    _euler_to_quat_c(r0x, r0y, r0z, q0)
    _euler_to_quat_c(r1x, r1y, r1z, q1)
    _quat_lerp_c(q0, q1, ratio, q3)

    cdef double r30 = fsubs(1.0, ratio)
    # translate/scale blend is NON-fused (m_Do_ext.cpp:1183): each product separately f32-rounded.
    cdef double tr0 = fadds(fmuls(i0t0, r30), fmuls(i1t0, ratio))
    cdef double tr1 = fadds(fmuls(i0t1, r30), fmuls(i1t1, ratio))
    cdef double tr2 = fadds(fmuls(i0t2, r30), fmuls(i1t2, ratio))
    cdef double sc0 = fadds(fmuls(i0s0, r30), fmuls(i1s0, ratio))
    cdef double sc1 = fadds(fmuls(i0s1, r30), fmuls(i1s1, ratio))
    cdef double sc2 = fadds(fmuls(i0s2, r30), fmuls(i1s2, ratio))

    cdef double oq[4]
    cdef double f31
    if apply_morf:
        f31 = fsubs(1.0, rate)
        oq[0] = old_quat[0]; oq[1] = old_quat[1]; oq[2] = old_quat[2]; oq[3] = old_quat[3]
        _quat_lerp_c(oq, q3, f31, q3)
        tr0 = fadds(fmuls(tr0, f31), fmuls(<double>old_trans[0], rate))
        tr1 = fadds(fmuls(tr1, f31), fmuls(<double>old_trans[1], rate))
        tr2 = fadds(fmuls(tr2, f31), fmuls(<double>old_trans[2], rate))
        sc0 = fadds(fmuls(sc0, f31), fmuls(<double>old_scale[0], rate))
        sc1 = fadds(fmuls(sc1, f31), fmuls(<double>old_scale[1], rate))
        sc2 = fadds(fmuls(sc2, f31), fmuls(<double>old_scale[2], rate))

    cdef double m[12]
    _psmtx_quat_c(q3, m)
    # M = R * diag(scale): scale column j by scale[j]; trans column = f32(trans).
    m[0] = fmuls(m[0], sc0); m[1] = fmuls(m[1], sc1); m[2] = fmuls(m[2], sc2); m[3] = f32(tr0)
    m[4] = fmuls(m[4], sc0); m[5] = fmuls(m[5], sc1); m[6] = fmuls(m[6], sc2); m[7] = f32(tr1)
    m[8] = fmuls(m[8], sc0); m[9] = fmuls(m[9], sc1); m[10] = fmuls(m[10], sc2); m[11] = f32(tr2)
    mtx = [[m[0], m[1], m[2], m[3]], [m[4], m[5], m[6], m[7]], [m[8], m[9], m[10], m[11]]]
    return mtx, (q3[0], q3[1], q3[2], q3[3]), (tr0, tr1, tr2), (sc0, sc1, sc2)


# ---- 3x4 matrix concat / mult-vec (PSMTXConcat / PSMTXMultVec) --------------------------------
cdef void _concat_c(double* a, double* b, double* out) noexcept nogil:
    """out = a*b (3x4 affine, row-major 12 doubles), fused accumulation. out must not alias a or b."""
    cdef int i, j, r
    for i in range(3):
        r = i * 4
        for j in range(3):
            out[r + j] = fmadds(a[r + 2], b[8 + j], fmadds(a[r + 1], b[4 + j], fmuls(a[r + 0], b[0 + j])))
        out[r + 3] = fadds(
            fmadds(a[r + 2], b[11], fmadds(a[r + 1], b[7], fmuls(a[r + 0], b[3]))), a[r + 3])

cdef void _read_mtx(object m, double* out):
    """Read a 3x4 Python matrix (list of 3 rows of 4) into a row-major double[12]."""
    cdef object row
    cdef int i
    for i in range(3):
        row = m[i]
        out[i*4+0] = row[0]; out[i*4+1] = row[1]; out[i*4+2] = row[2]; out[i*4+3] = row[3]

cdef _mtx_list(double* m):
    return [[m[0], m[1], m[2], m[3]], [m[4], m[5], m[6], m[7]], [m[8], m[9], m[10], m[11]]]

def mtx_concat(a, b):
    """ab = a*b (3x4 affine), fused accumulation. Bit-exact port of fk.mtx_concat."""
    cdef double ca[12]
    cdef double cb[12]
    cdef double out[12]
    _read_mtx(a, ca); _read_mtx(b, cb)
    _concat_c(ca, cb, out)
    return _mtx_list(out)

def chain_concat(base, m37b4, locals_list):
    """World-space foot-chain accumulation in one call: m37b4 * (base * L0 * L1 * ... * Ln).
    `locals_list` = the chain's local 3x4 matrices in root->foot order. Bit-exact fold of the
    per-joint fk.mtx_concat sequence in foot_fk._chain_mtx (base copy -> chain -> m37b4)."""
    cdef double bufA[12]
    cdef double bufB[12]
    cdef double lb[12]
    cdef double* cur = bufA
    cdef double* nxt = bufB
    cdef double* swp
    cdef Py_ssize_t n = len(locals_list), k
    _read_mtx(base, cur)
    for k in range(n):
        _read_mtx(locals_list[k], lb)
        _concat_c(cur, lb, nxt)
        swp = cur; cur = nxt; nxt = swp
    _read_mtx(m37b4, nxt)          # reuse nxt buffer to hold m37b4
    cdef double out[12]
    _concat_c(nxt, cur, out)
    return _mtx_list(out)


def mtx_mult_vec(m, v):
    """dst = (m0*sx + m2*sz) + (m1*sy + m3), per row (ps_sum0 grouping). Bit-exact port."""
    cdef double sx = v[0], sy = v[1], sz = v[2]
    cdef double mi[4]
    cdef object row
    cdef double pa, pb
    cdef double o0, o1, o2
    cdef int i
    cdef double out[3]
    for i in range(3):
        row = m[i]
        mi[0] = row[0]; mi[1] = row[1]; mi[2] = row[2]; mi[3] = row[3]
        pa = fmadds(mi[2], sz, fmuls(mi[0], sx))
        pb = fadds(fmuls(mi[1], sy), mi[3])
        out[i] = fadds(pa, pb)
    return (out[0], out[1], out[2])


# ---- body-Co centre (setCollision root/neck midpoint) in one C call ---------------------------
# Neck chain foot_fk.NECK_CHAIN=[0,1,2,3,4,14] in calc order; SSC slots 3,4,5 scale by 1/parentS
# (parent = slot i-1). See co_center's docstring + foot_fk.FootFK.body_co_center for the full law.
cdef bint _NECK_SSC[6]
_NECK_SSC[0]=False; _NECK_SSC[1]=False; _NECK_SSC[2]=False
_NECK_SSC[3]=True;  _NECK_SSC[4]=True;  _NECK_SSC[5]=True

cdef void _co_center_impl(double px, double py, double pz, long long facing, long long lean,
                          long long body_x, double* q6, double* t6, double* s6,
                          double* out) noexcept nogil:
    """Link's body-Co cylinder centre (out[0]=cx, out[1]=cz) -- setCollision's root/neck world
    midpoint -- rebuilt from the STORED old pose. Shared nogil core of the module-level `co_center`
    (marshals Python lists) AND `PoseEngine._body_co_center` (reads the C stores). Bit-exact port of
    foot_fk.FootFK.body_co_center's Python loop.

    ``q6``/``t6``/``s6`` are FLAT arrays in chain order [0,1,2,3,4,14]: q6[i*4+k] (w,x,y,z),
    t6[i*3+k] (x,y,z), s6[i*3+k] (x,y,z). ``body_x`` = sign-extended -mBodyAngle.z (BODY_CHN twist
    on chain idx 2 = joint 2)."""
    # --- build the leaned worldBase (fk.world_base): transS(p) . YrotM(facing) [. ZrotM(lean)] ---
    cdef long long fc = facing & 0xFFFF, lc = lean & 0xFFFF
    cdef double c = jma_cos(fc), s = jma_sin(fc), ns = f32(-s)
    cdef double base[12]
    base[0] = c;   base[1] = 0.0; base[2] = s;   base[3] = f32(px)
    base[4] = 0.0; base[5] = 1.0; base[6] = 0.0; base[7] = f32(py)
    base[8] = ns;  base[9] = 0.0; base[10] = c;  base[11] = f32(pz)
    cdef double rz[12]
    cdef double leaned[12]
    cdef double cz_, sz_
    if lc != 0:
        cz_ = jma_cos(lc); sz_ = jma_sin(lc)
        rz[0] = cz_; rz[1] = f32(-sz_); rz[2] = 0.0; rz[3] = 0.0
        rz[4] = sz_; rz[5] = cz_;       rz[6] = 0.0; rz[7] = 0.0
        rz[8] = 0.0; rz[9] = 0.0;       rz[10] = 1.0; rz[11] = 0.0
        _concat_c(base, rz, leaned)
        memcpy(base, leaned, 12 * sizeof(double))

    # --- accumulate the neck chain, capturing root (slot 0) and neck (slot 5) world translates ----
    cdef double bufA[12]
    cdef double bufB[12]
    cdef double q[4]
    cdef double tw[4]
    cdef double q2[4]
    cdef double m[12]
    cdef double* cur = bufA
    cdef double* nxt = bufB
    cdef double* swp
    cdef double s0, s1, s2, inv, ps0, ps1, ps2
    cdef int i
    cdef double root_x = 0.0, root_z = 0.0
    memcpy(cur, base, 12 * sizeof(double))
    for i in range(6):
        # rebuild the local 3x4 from the stored old pose
        q[0] = q6[i*4+0]; q[1] = q6[i*4+1]; q[2] = q6[i*4+2]; q[3] = q6[i*4+3]
        if i == 2 and body_x != 0:
            _euler_to_quat_c(body_x, 0, 0, tw)
            _quat_concat_c(q, tw, q2)
            _psmtx_quat_c(q2, m)
        else:
            _psmtx_quat_c(q, m)
        s0 = s6[i*3+0]; s1 = s6[i*3+1]; s2 = s6[i*3+2]
        # M = R . diag(anim scale): column j scaled by scale[j]
        m[0] = fmuls(m[0], s0); m[1] = fmuls(m[1], s1); m[2] = fmuls(m[2], s2)
        m[4] = fmuls(m[4], s0); m[5] = fmuls(m[5], s1); m[6] = fmuls(m[6], s2)
        m[8] = fmuls(m[8], s0); m[9] = fmuls(m[9], s1); m[10] = fmuls(m[10], s2)
        # SSC: row r of the local 3x3 scaled by 1/parentS[r] (parent = slot i-1)
        if _NECK_SSC[i]:
            ps0 = s6[(i-1)*3+0]; ps1 = s6[(i-1)*3+1]; ps2 = s6[(i-1)*3+2]
            if ps0 != 1.0 or ps1 != 1.0 or ps2 != 1.0:
                inv = fdivs(1.0, ps0)
                m[0] = fmuls(m[0], inv); m[1] = fmuls(m[1], inv); m[2] = fmuls(m[2], inv)
                inv = fdivs(1.0, ps1)
                m[4] = fmuls(m[4], inv); m[5] = fmuls(m[5], inv); m[6] = fmuls(m[6], inv)
                inv = fdivs(1.0, ps2)
                m[8] = fmuls(m[8], inv); m[9] = fmuls(m[9], inv); m[10] = fmuls(m[10], inv)
        m[3] = f32(t6[i*3+0]); m[7] = f32(t6[i*3+1]); m[11] = f32(t6[i*3+2])
        _concat_c(cur, m, nxt)
        swp = cur; cur = nxt; nxt = swp
        if i == 0:
            root_x = cur[3]; root_z = cur[11]
    out[0] = fmuls(0.5, fadds(root_x, cur[3]))
    out[1] = fmuls(0.5, fadds(root_z, cur[11]))


# ---- head-top (mHeadTopPos) in one C call -----------------------------------------------------
# foot_fk.HEAD_CHAIN=[0,1,2,3,4,14,15] in calc order -- the neck chain plus the HEAD joint. SSC is
# foot_fk.BODY_CO_SSC=(3,4,14) == chain slots 3,4,5; the head (slot 6) is not an SSC joint.
#
# WHY THIS EXISTS (session 127): Tetra's `Zl1Look` reads exactly one thing from Link that is not a
# position -- his exec-pass mHeadTopPos.y (`dNpc_playerEyePos`) -- and her eyePos is what Link's
# proc-9 re-aim consumes. That single Y is the whole reason a coupled rollout could not run in C:
# the native step reproduces the wired one 0-ULP when csangle and the eye are injected, csangle is
# free (a per-node constant across an aim fan), but the eye needed a Python pose FK. It does not
# any more.
cdef bint _HEAD_SSC[7]
_HEAD_SSC[0]=False; _HEAD_SSC[1]=False; _HEAD_SSC[2]=False
_HEAD_SSC[3]=True;  _HEAD_SSC[4]=True;  _HEAD_SSC[5]=True; _HEAD_SSC[6]=False

#: head_offset (d_a_player_main.cpp:11589) -- foot_fk.HEAD_TOP_OFF.
cdef double _HEAD_TOP_OFF_X = 40.0

cdef void _head_mtx_impl(double px, double py, double pz, long long facing, long long lean,
                         long long body_x, long long nlx, long long nly, long long nlz,
                         double* q7, double* t7, double* s7, double* out) noexcept nogil:
    """The WORLD head anm matrix (``getAnmMtx(CL_JNT_HEAD_JNT_e)``, out = 3x4 flat) rebuilt from the
    STORED old pose -- the `_co_center_impl` accumulation carried one joint further. Bit-exact port
    of `foot_fk.FootFK.head_mtx`. `_head_top_impl` is this plus the head-offset multiply, and the
    NECK model measures this matrix (the cached previous-frame value) to find its current angles.

    ``q7``/``t7``/``s7`` are flat, chain order [0,1,2,3,4,14,15]. ``body_x`` = the sign-extended
    -mBodyAngle.z BODY_CHN twist on chain slot 2, exactly as in `_co_center_impl`. ``nlx/nly/nlz``
    = `NeckLook.local_38()` (m3564.y, m3564.z, m3564.x), the jointBeforeCB HEAD twist: the decomp
    applies it as TWO quat concats -- Q(x, y, 0) then Q(0, 0, z) -- each SKIPPED when its terms are
    zero (:353-362), which is not the same matrix as one combined rotation."""
    cdef long long fc = facing & 0xFFFF, lc = lean & 0xFFFF
    cdef double c = jma_cos(fc), s = jma_sin(fc), ns = f32(-s)
    cdef double base[12]
    base[0] = c;   base[1] = 0.0; base[2] = s;   base[3] = f32(px)
    base[4] = 0.0; base[5] = 1.0; base[6] = 0.0; base[7] = f32(py)
    base[8] = ns;  base[9] = 0.0; base[10] = c;  base[11] = f32(pz)
    cdef double rz[12]
    cdef double leaned[12]
    cdef double cz_, sz_
    if lc != 0:
        cz_ = jma_cos(lc); sz_ = jma_sin(lc)
        rz[0] = cz_; rz[1] = f32(-sz_); rz[2] = 0.0; rz[3] = 0.0
        rz[4] = sz_; rz[5] = cz_;       rz[6] = 0.0; rz[7] = 0.0
        rz[8] = 0.0; rz[9] = 0.0;       rz[10] = 1.0; rz[11] = 0.0
        _concat_c(base, rz, leaned)
        memcpy(base, leaned, 12 * sizeof(double))

    cdef double bufA[12]
    cdef double bufB[12]
    cdef double q[4]
    cdef double tw[4]
    cdef double q2[4]
    cdef double m[12]
    cdef double* cur = bufA
    cdef double* nxt = bufB
    cdef double* swp
    cdef double s0, s1, s2, inv, ps0, ps1, ps2
    cdef int i
    memcpy(cur, base, 12 * sizeof(double))
    for i in range(7):
        q[0] = q7[i*4+0]; q[1] = q7[i*4+1]; q[2] = q7[i*4+2]; q[3] = q7[i*4+3]
        if i == 2 and body_x != 0:
            _euler_to_quat_c(body_x, 0, 0, tw)
            _quat_concat_c(q, tw, q2)
            q[0] = q2[0]; q[1] = q2[1]; q[2] = q2[2]; q[3] = q2[3]
        elif i == 6:
            if nlx != 0 or nly != 0:
                _euler_to_quat_c(nlx, nly, 0, tw)
                _quat_concat_c(q, tw, q2)
                q[0] = q2[0]; q[1] = q2[1]; q[2] = q2[2]; q[3] = q2[3]
            if nlz != 0:
                _euler_to_quat_c(0, 0, nlz, tw)
                _quat_concat_c(q, tw, q2)
                q[0] = q2[0]; q[1] = q2[1]; q[2] = q2[2]; q[3] = q2[3]
        _psmtx_quat_c(q, m)
        s0 = s7[i*3+0]; s1 = s7[i*3+1]; s2 = s7[i*3+2]
        m[0] = fmuls(m[0], s0); m[1] = fmuls(m[1], s1); m[2] = fmuls(m[2], s2)
        m[4] = fmuls(m[4], s0); m[5] = fmuls(m[5], s1); m[6] = fmuls(m[6], s2)
        m[8] = fmuls(m[8], s0); m[9] = fmuls(m[9], s1); m[10] = fmuls(m[10], s2)
        if _HEAD_SSC[i]:
            ps0 = s7[(i-1)*3+0]; ps1 = s7[(i-1)*3+1]; ps2 = s7[(i-1)*3+2]
            if ps0 != 1.0 or ps1 != 1.0 or ps2 != 1.0:
                inv = fdivs(1.0, ps0)
                m[0] = fmuls(m[0], inv); m[1] = fmuls(m[1], inv); m[2] = fmuls(m[2], inv)
                inv = fdivs(1.0, ps1)
                m[4] = fmuls(m[4], inv); m[5] = fmuls(m[5], inv); m[6] = fmuls(m[6], inv)
                inv = fdivs(1.0, ps2)
                m[8] = fmuls(m[8], inv); m[9] = fmuls(m[9], inv); m[10] = fmuls(m[10], inv)
        m[3] = f32(t7[i*3+0]); m[7] = f32(t7[i*3+1]); m[11] = f32(t7[i*3+2])
        _concat_c(cur, m, nxt)
        swp = cur; cur = nxt; nxt = swp
    memcpy(out, cur, 12 * sizeof(double))


cdef void _head_top_impl(double px, double py, double pz, long long facing, long long lean,
                         long long body_x, long long nlx, long long nly, long long nlz,
                         double* q7, double* t7, double* s7, double* out) noexcept nogil:
    """Link's ``mHeadTopPos`` (out[0..2] = x, y, z): `_head_mtx_impl` then the head-offset multiply
    (``cMtx_multVec(anmMtx(HEAD), head_offset)``, d_a_player_main.cpp:11592)."""
    cdef double m[12]
    _head_mtx_impl(px, py, pz, facing, lean, body_x, nlx, nly, nlz, q7, t7, s7, m)
    _mv_c(m, _HEAD_TOP_OFF_X, 0.0, 0.0, out)


def head_top(double px, double py, double pz, long long facing, long long lean,
             long long body_x, old_q, old_t, old_s, neck=None):
    """Link's ``mHeadTopPos`` (x, y, z) rebuilt from the STORED old pose in one native call --
    bit-exact drop-in for `foot_fk.FootFK.head_top`.

    ``old_q``/``old_t``/``old_s`` are length-7 sequences in chain order [0,1,2,3,4,14,15]. ``neck``
    = `NeckLook.local_38()` or None (untwisted). Y is the payload (Tetra's look-at reads it as
    ``dNpc_playerEyePos``); x/z are returned for gating."""
    cdef double q7[28]
    cdef double t7[21]
    cdef double s7[21]
    cdef int i
    for i in range(7):
        q7[i*4+0] = old_q[i][0]; q7[i*4+1] = old_q[i][1]
        q7[i*4+2] = old_q[i][2]; q7[i*4+3] = old_q[i][3]
        t7[i*3+0] = old_t[i][0]; t7[i*3+1] = old_t[i][1]; t7[i*3+2] = old_t[i][2]
        s7[i*3+0] = old_s[i][0]; s7[i*3+1] = old_s[i][1]; s7[i*3+2] = old_s[i][2]
    cdef long long nlx = 0, nly = 0, nlz = 0
    if neck is not None:
        nlx = _s16c(<long long>int(neck[0]) & 0xFFFF)
        nly = _s16c(<long long>int(neck[1]) & 0xFFFF)
        nlz = _s16c(<long long>int(neck[2]) & 0xFFFF)
    cdef double out[3]
    _head_top_impl(px, py, pz, facing, lean, body_x, nlx, nly, nlz, q7, t7, s7, out)
    return (out[0], out[1], out[2])


def co_center(double px, double py, double pz, long long facing, long long lean,
              long long body_x, old_q, old_t, old_s):
    """Link's body-Co cylinder centre (cx, cz) -- setCollision's root/neck world midpoint -- rebuilt
    from the STORED old pose in one native call. Bit-exact drop-in for
    foot_fk.FootFK.body_co_center's Python loop.

    ``px/py/pz`` world pos, ``facing``/``lean`` s16 (lean = the base ZrotM, shape_angle.z), ``body_x``
    the sign-extended -mBodyAngle.z (the BODY_CHN twist on joint 2). ``old_q``/``old_t``/``old_s`` are
    length-6 sequences (chain order [0,1,2,3,4,14]): old_q[i]=(w,x,y,z), old_t[i]=(x,y,z),
    old_s[i]=(x,y,z). Returns (cx, cz)."""
    cdef double q6[24]
    cdef double t6[18]
    cdef double s6[18]
    cdef int i
    for i in range(6):
        q6[i*4+0] = old_q[i][0]; q6[i*4+1] = old_q[i][1]
        q6[i*4+2] = old_q[i][2]; q6[i*4+3] = old_q[i][3]
        t6[i*3+0] = old_t[i][0]; t6[i*3+1] = old_t[i][1]; t6[i*3+2] = old_t[i][2]
        s6[i*3+0] = old_s[i][0]; s6[i*3+1] = old_s[i][1]; s6[i*3+2] = old_s[i][2]
    cdef double out[2]
    _co_center_impl(px, py, pz, facing, lean, body_x, q6, t6, s6, out)
    return (out[0], out[1])


# ---- dCcS::SetPosCorrect Co push (cc_push.co_move_pair) ----------------------------------------
# The CC push: obj1 and obj2 each ejected half the overlap depth, exact
# opposites for a same-rank pair. Bit-exact twin of tww_sim.core.cc_push.co_move_pair (XZ only,
# dy=0). Rank table (d_cc_s.cpp:138) + GetRank (:153) inlined; is_zero threshold = collision 1e-5.
DEF _CC_ISZERO = 1.0e-5               # collision.G_CM3D_F_ABS_MIN (NOT the mathlib 2^-18)
cdef int _RANK_TBL[11][11]
cdef bint _RANK_READY = False


def init_rank_table(tbl):
    """Copy cc_push.RANK_TBL (11x11) into C. Idempotent."""
    global _RANK_READY
    cdef int i, j
    for i in range(11):
        for j in range(11):
            _RANK_TBL[i][j] = <int>tbl[i][j]
    _RANK_READY = True


cdef inline int _get_rank_c(int w) noexcept nogil:
    """dCcS::GetRank (d_cc_s.cpp:153): raw weight u8 -> rank 0..10."""
    w = w & 0xFF
    if w == 0xFF: return 10
    if w == 0xFE: return 9
    if w >= 0xD9: return 8
    if w >= 0xB5: return 7
    if w >= 0x91: return 6
    if w >= 0x6D: return 5
    if w >= 0x49: return 4
    if w >= 0x25: return 3
    if w >= 0x02: return 2
    if w == 0x01: return 1
    return 0


cdef int _co_move_pair_c(double c1x, double c1z, double r1, double h1,
                         double c2x, double c2z, double r2, double h2,
                         int w1, int w2, double* out) noexcept nogil:
    """co_move_pair XZ core: fills out[0..3] = (v1x, v1z, v2x, v2z) -- obj1 (c1) and obj2 (c2)
    accumulated moves. Returns 1 if a push was applied, 0 (out zeroed) on no-overlap / deadzone /
    both-immovable. Callers here share the whole Y span (flat floor), so the Y-overlap
    gate always passes; callers that need it must add it. Bit-exact port of cc_push.co_move_pair."""
    out[0] = 0.0; out[1] = 0.0; out[2] = 0.0; out[3] = 0.0
    cdef double dx = fsubs(c1x, c2x)
    cdef double dz = fsubs(c1z, c2z)
    # UNFUSED (dx*dx)+(dz*dz) + the MSL sqrtf -- cM3d_Cross_CylCyl / dCcS::SetPosCorrect as the JP
    # binary compiles them (fmuls/fmuls/fadds at 0x8024C44C and 0x800AB430; frsqrte + 3 double Newton
    # at 0x800AB444). Mirrors core/cc_push.py; see its FP note (session 55).
    cdef double dist_sq = fadds(fmuls(dx, dx), fmuls(dz, dz))
    cdef double rsum = fadds(r1, r2)
    if dist_sq > fmuls(rsum, rsum):
        return 0
    cdef double cross_len = fsubs(rsum, _sqrtf_c(dist_sq))
    cdef double acl = cross_len if cross_len >= 0.0 else -cross_len
    if acl < _CC_ISZERO:
        return 0
    cdef int a = w1 & 0xFF, b = w2 & 0xFF
    if (a == 0 and b == 0) or (a == 0xFF and b == 0xFF):
        return 0
    cdef int rank = _RANK_TBL[_get_rank_c(a)][_get_rank_c(b)]   # obj1's push %
    cdef double obj1_w = fmuls(<double>rank, 0.01)
    cdef double obj2_w = fmuls(<double>(100 - rank), 0.01)
    # objsDist = ppos2 - ppos1 = (c2 - c1); scale to cross_len; vec1 = -objsDist*obj2_w, vec2 = +*obj1_w.
    cdef double ox = fsubs(c2x, c1x)
    cdef double oz = fsubs(c2z, c1z)
    cdef double dist = _sqrtf_c(fadds(fmuls(ox, ox), fmuls(oz, oz)))
    cdef double f, sx, sz, mag
    if not (dist < _CC_ISZERO):
        f = fdivs(cross_len, dist)
        sx = fmuls(ox, f); sz = fmuls(oz, f)
        out[0] = fmuls(sx, fsubs(0.0, obj2_w)); out[1] = fmuls(sz, fsubs(0.0, obj2_w))
        out[2] = fmuls(sx, obj1_w);             out[3] = fmuls(sz, obj1_w)
    else:
        mag = cross_len if acl >= _CC_ISZERO else 1.0
        out[0] = fmuls(fsubs(0.0, mag), obj2_w); out[1] = 0.0
        out[2] = fmuls(mag, obj1_w);             out[3] = 0.0
    return 1


def co_move_pair_xz(double c1x, double c1z, double r1, double h1,
                    double c2x, double c2z, double r2, double h2, int w1, int w2):
    """Public wrapper over the native co_move_pair (XZ, dy=0), for gating vs cc_push.co_move_pair.
    Pass the cylinder centres UNPACKED (c1x, c1z, ...); returns ((v1x, 0.0, v1z), (v2x, 0.0, v2z))."""
    if not _RANK_READY:
        raise RuntimeError("init_rank_table() must be called first")
    cdef double out[4]
    _co_move_pair_c(c1x, c1z, r1, h1, c2x, c2z, r2, h2, w1, w2, out)
    return ((out[0], 0.0, out[1]), (out[2], 0.0, out[3]))


# ---- Hermite interpolation (s16 asm path + f32 path) ------------------------------------------
cdef double _hermite_s16_c(double t, double time0, double value0, double tan0,
                           double time1, double value1, double tan1) noexcept nogil:
    """s16 rotation Hermite (J3DAnimation.cpp:342-363 asm). Bit-exact core of j3d_eval.hermite_s16."""
    cdef double f0 = time0
    cdef double f3 = time1
    cdef double f2 = value0
    cdef double f4 = fsubs(f3, f0)
    f3 = value1
    cdef double f6 = fsubs(t, f0)
    cdef double fout = tan1
    cdef double f5 = fsubs(f3, f2)
    f6 = fdivs(f6, f4)
    f0 = tan0
    fout = fmadds(fout, f4, f2)
    cdef double f7 = fmuls(f6, f6)
    f5 = fnmsubs(f4, f0, f5)
    fout = fsubs(fout, f3)
    fout = fsubs(fout, f5)
    f3 = fmuls(f7, fout)
    fout = fmadds(f4, f0, f3)
    fout = fmadds(fout, f6, f2)
    fout = fmadds(f5, f7, fout)
    fout = fsubs(fout, f3)
    return fout

cdef double _hermite_f32_c(double frame, double time0, double value0, double tan0,
                           double time1, double value1, double tan1) noexcept nogil:
    """f32 scale/translate Hermite (JMAHermiteInterpolation). Bit-exact core of j3d_eval.hermite_f32."""
    cdef double length = fsubs(time1, time0)
    cdef double f9 = fsubs(frame, time0)
    cdef double f1 = fdivs(1.0, length)
    cdef double f2 = fmuls(fmuls(f9, f9), f1)
    cdef double f10 = fmuls(f2, f1)
    cdef double f11 = fmuls(f9, f10)
    cdef double f12 = fmuls(f11, f1)
    cdef double a = fmadds(value0, fadds(1.0, fmsubs(2.0, f12, fmuls(3.0, f10))), 0.0)
    cdef double b = fmuls(value1, fmadds(-2.0, f12, fmuls(3.0, f10)))
    cdef double c = fmuls(tan0, fadds(f9, fnmsubs(2.0, f2, f11)))
    cdef double d = fmuls(tan1, fsubs(f11, f2))
    return fadds(fadds(fadds(a, b), c), d)

# ---- worldBase + PSMTXInverse (per-frame foot-FK base build) ----------------------------------
cdef void _psmtx_inverse_c(double* m, double* inv) noexcept nogil:
    """PSMTXInverse (dolphin/mtx/mtx.c:404): cofactor/det inverse, det reciprocal via fres + one
    Newton refine. Bit-exact core of fk.psmtx_inverse. m/inv are row-major 3x4 (12 doubles)."""
    cdef double m00 = m[0], m01 = m[1], m02 = m[2], m03 = m[3]
    cdef double m10 = m[4], m11 = m[5], m12 = m[6], m13 = m[7]
    cdef double m20 = m[8], m21 = m[9], m22 = m[10], m23 = m[11]
    cdef double A00 = fmsubs(m11, m22, fmuls(m21, m12))
    cdef double A01 = fmsubs(m21, m02, fmuls(m01, m22))
    cdef double A02 = fmsubs(m01, m12, fmuls(m11, m02))
    cdef double A20 = fmsubs(m10, m21, fmuls(m11, m20))
    cdef double A21 = fmsubs(m01, m20, fmuls(m00, m21))
    cdef double A22 = fmsubs(m00, m11, fmuls(m01, m10))
    cdef double B10 = fmsubs(m12, m20, fmuls(m22, m10))
    cdef double B11 = fmsubs(m22, m00, fmuls(m02, m20))
    cdef double B12 = fmsubs(m02, m10, fmuls(m12, m00))
    cdef double det = fmadds(m20, A02, fmadds(m10, A01, fmuls(m00, A00)))
    cdef double est = f32(_fres(det))
    cdef double recip = fnmsubs(det, fmuls(est, est), fadds(est, est))
    inv[0] = fmuls(A00, recip); inv[1] = fmuls(A01, recip); inv[2] = fmuls(A02, recip)
    inv[4] = fmuls(B10, recip); inv[5] = fmuls(B11, recip); inv[6] = fmuls(B12, recip)
    inv[8] = fmuls(A20, recip); inv[9] = fmuls(A21, recip); inv[10] = fmuls(A22, recip)
    inv[3] = fnmadds(inv[2], m23, fmadds(inv[1], m13, fmuls(inv[0], m03)))
    inv[7] = fnmadds(inv[6], m23, fmadds(inv[5], m13, fmuls(inv[4], m03)))
    inv[11] = fnmadds(inv[10], m23, fmadds(inv[9], m13, fmuls(inv[8], m03)))

def world_base(px, py, pz, facing):
    """(worldBase, m37B4) for the CL setBaseTRMtx: base = transS(px,py,pz).ZXYrotM(0,facing,0) on flat
    ground; m37B4 = PSMTXInverse(base). Bit-exact port of fk.world_base. Returns two 3x4 lists."""
    cdef long long fc = (<long long>facing) & 0xFFFF
    cdef double c = jma_cos(fc), s = jma_sin(fc)
    cdef double ns = f32(-s)
    cdef double base[12]
    cdef double inv[12]
    base[0] = c;   base[1] = 0.0; base[2] = s;   base[3] = f32(px)
    base[4] = 0.0; base[5] = 1.0; base[6] = 0.0; base[7] = f32(py)
    base[8] = ns;  base[9] = 0.0; base[10] = c;  base[11] = f32(pz)
    _psmtx_inverse_c(base, inv)
    return (_mtx_list(base), _mtx_list(inv))


def hermite_s16(t, time0, value0, tan0, time1, value1, tan1):
    return _hermite_s16_c(t, time0, value0, tan0, time1, value1, tan1)

def hermite_f32(frame, time0, value0, tan0, time1, value1, tan1):
    return _hermite_f32_c(frame, time0, value0, tan0, time1, value1, tan1)


# ==== full C-resident pose engine ==============================================================
# One call per frame does calc_transform + the 12-joint blend/morf/PSMTXQuat pose + both foot chain
# FKs + the toe/heel PSMTXMultVec, with ALL state (keyframe data, skeleton chains, old pose, morf
# counter) resident in C -- no per-frame Python object churn. Replaces foot_fk._pose_frame/_chain_mtx/
# _toe/_blend_joint + the MorfState on the world-space FK path. Bit-exact port; see fp-faithfulness.md.

# CHAIN_JOINTS (foot_fk): union of both foot chains in calc order; slot s poses joint _CJ[s].
cdef int _CJ[12]
_CJ[0]=0; _CJ[1]=1; _CJ[2]=29; _CJ[3]=30; _CJ[4]=31; _CJ[5]=32
_CJ[6]=33; _CJ[7]=34; _CJ[8]=36; _CJ[9]=37; _CJ[10]=38; _CJ[11]=39
# body_co pose set = CHAIN_JOINTS (slots 0-11, == _CJ) + BODY_CO_EXTRA (slots 12-16, the neck/head
# extras); AnimData registers all 17 so pose_chain samples them from C. See foot_fk body_co_center.
cdef int _NALL = 17
cdef int _CJALL[17]
_CJALL[0]=0; _CJALL[1]=1; _CJALL[2]=29; _CJALL[3]=30; _CJALL[4]=31; _CJALL[5]=32
_CJALL[6]=33; _CJALL[7]=34; _CJALL[8]=36; _CJALL[9]=37; _CJALL[10]=38; _CJALL[11]=39
_CJALL[12]=2; _CJALL[13]=3; _CJALL[14]=4; _CJALL[15]=14; _CJALL[16]=15

# l_toe / l_heel in Lfoot-joint local space (fk.L_TOE / L_HEEL, d_a_player_main_data.inc:18-19).
cdef double _TOE_X = 6.0, _TOE_Y = 3.25, _HEEL_X = -6.0, _HEEL_Y = 3.25

cdef inline long long _as_s32c(long long x) noexcept nogil:
    # (s32) cast: reinterpret the low 32 bits as signed (two's complement), then widen.
    cdef unsigned int u = <unsigned int>x
    return <long long><int>u

cdef double _keyframe_interp_c(double frame, int cnt, int tt, double* data, int base, int is_s16) noexcept nogil:
    """Endpoint clamp + bisect + Hermite (J3DGetKeyFrameInterpolation[S]). Bit-exact core of
    j3d_eval._keyframe_interp; `data` holds the flat track (rot values are stored as exact doubles)."""
    cdef int stride = 3 if tt == 0 else 4
    cdef double d0 = data[base]
    if frame < d0:
        return data[base + 1]
    cdef int last = base + stride * (cnt - 1)
    if data[last] <= frame:
        return data[last + 1]
    cdef int p = base, num = cnt, mid
    while num > 1:
        mid = num // 2
        if frame >= data[p + stride * mid]:
            p += stride * mid
            num -= mid
        else:
            num = mid
    if stride == 3:
        if is_s16:
            return _hermite_s16_c(frame, data[p], data[p+1], data[p+2], data[p+3], data[p+4], data[p+5])
        return _hermite_f32_c(frame, data[p], data[p+1], data[p+2], data[p+3], data[p+4], data[p+5])
    if is_s16:
        return _hermite_s16_c(frame, data[p], data[p+1], data[p+3], data[p+4], data[p+5], data[p+6])
    return _hermite_f32_c(frame, data[p], data[p+1], data[p+3], data[p+4], data[p+5], data[p+6])

cdef inline void _mv_c(double* m, double vx, double vy, double vz, double* out) noexcept nogil:
    """PSMTXMultVec: out[0..2] = m * (vx,vy,vz) with the ps_sum0 grouping."""
    cdef int i, r
    cdef double pa, pb
    for i in range(3):
        r = i * 4
        pa = fmadds(m[r + 2], vz, fmuls(m[r + 0], vx))
        pb = fadds(fmuls(m[r + 1], vy), m[r + 3])
        out[i] = fadds(pa, pb)


# ---- native anim-state machine (UnderAnimState port) constants -------------------------------
# Fixed anim CODES (match anim_state.ANIM_ORDER). The machine works in these; pose_toe maps code ->
# data-index via PoseEngine._code2idx. Direction enum matches anim_state.DIR_*.
DEF C_WAITS=0
DEF C_WALK=1
DEF C_DASH=2
DEF C_ROLLF=3
DEF C_ROT=4
DEF C_SLIP=5
DEF C_ATNWLS=6
DEF C_ATNWRS=7
DEF C_ATNLS=8
DEF C_ATNRS=9
DEF C_ATNDLS=10
DEF C_ATNDRS=11
DEF C_ATNWB=12
DEF C_ATNDB=13
DEF C_FREEB=14
# The SWORD-DRAWN under-body pair: with mEquipItem == daPyItem_SWORD_e, getAnmData
# (d_a_player_main.cpp:12950) serves ANM_WALK/ANM_DASH out of mSwordAnmIndexTable, i.e. WALKS/DASHS.
# Feet-only difference, but posMoveFromFootPos reads the feet -- selected by `_sword`/`set_sword`.
DEF C_WALKS=15
DEF C_DASHS=16
# ANM_WAITATOB: the low-life wait A->B transition procWait_init plays as a SINGLE instead of the
# WAITS idle blend when checkRestHPAnime() holds (6072). knowledge/model/wait-stop-pose.md.
DEF C_WAITATOB=17
DEF N_ANIM=18
DEF D_FORWARD=0
DEF D_BACKWARD=1
DEF D_LEFT=2

cdef double _MMAX[N_ANIM]             # frameMax per anim code
cdef int _MATTR[N_ANIM]               # J3DFrameCtrl attribute (EMode) per anim code
cdef double _H_MAXSPEED, _H_2C, _H_30, _H_38, _H_40, _H_48, _H_60
cdef double _H_10, _H_68, _H_6C, _H_70      # the ANM_WAITATOB single: end / rate / start / morf
cdef double _ATN_1C, _ATN_20, _ATN_24, _ATN_28, _ATN_2C
cdef double _ATNB_1C, _ATNB_20, _ATNB_24, _ATNB_28
cdef bint _ANIM_CONSTS_READY = False


def init_anim_consts(meta_max, meta_attr, hio):
    """Copy ANIM_META (frameMax + attribute per code) + the f32 HIO tuning constants from anim_state
    into C. Idempotent; called once when the first fused engine is built."""
    global _ANIM_CONSTS_READY
    global _H_MAXSPEED, _H_2C, _H_30, _H_38, _H_40, _H_48, _H_60
    global _H_10, _H_68, _H_6C, _H_70
    global _ATN_1C, _ATN_20, _ATN_24, _ATN_28, _ATN_2C, _ATNB_1C, _ATNB_20, _ATNB_24, _ATNB_28
    cdef int i
    for i in range(N_ANIM):
        _MMAX[i] = meta_max[i]; _MATTR[i] = meta_attr[i]
    _H_MAXSPEED = hio['maxspeed']; _H_2C = hio['h2c']; _H_30 = hio['h30']; _H_38 = hio['h38']
    _H_40 = hio['h40']; _H_48 = hio['h48']; _H_60 = hio['h60']
    _H_10 = hio['h10']; _H_68 = hio['h68']; _H_6C = hio['h6c']; _H_70 = hio['h70']
    _ATN_1C = hio['atn1c']; _ATN_20 = hio['atn20']; _ATN_24 = hio['atn24']; _ATN_28 = hio['atn28']
    _ATN_2C = hio['atn2c']; _ATNB_1C = hio['atnb1c']; _ATNB_20 = hio['atnb20']
    _ATNB_24 = hio['atnb24']; _ATNB_28 = hio['atnb28']
    _ANIM_CONSTS_READY = True


cdef void _fc_update(int attr, double start, double end, double loop,
                     double* frame, double* rate) noexcept nogil:
    """J3DFrameCtrl::update: frame += rate then wrap/clamp per attribute (f32). Bit-exact port of
    anim_state.FrameCtrl.update. The loop-guard subtractions are f64 (like Python), the frame math f32."""
    cdef double fr = fadds(frame[0], rate[0])
    cdef double rt = rate[0]
    if attr == 0:                     # EMode_NONE
        if fr < start:
            fr = start; rt = 0.0
        if fr >= end:
            fr = fsubs(end, 0.001); rt = 0.0
    elif attr == 1:                   # EMode_RESET
        if fr < start:
            fr = start; rt = 0.0
        if fr >= end:
            fr = start; rt = 0.0
    elif attr == 2:                   # EMode_LOOP
        while fr < start:
            if loop - start <= 0.0:
                break
            fr = fadds(fr, fsubs(loop, start))
        while fr >= end:
            if end - loop <= 0.0:
                break
            fr = fsubs(fr, fsubs(end, loop))
    elif attr == 3:                   # EMode_REVERSE
        if fr >= end:
            fr = fsubs(end, 0.001); rt = -rt
        if fr < start:
            fr = start; rt = 0.0
    elif attr == 4:                   # EMode_LOOP_REVERSE
        if fr >= end:
            fr = fsubs(end, 0.001); rt = -rt
        if fr < start:
            fr = start; rt = -rt
    frame[0] = fr; rate[0] = rt


cdef inline int _meta_at(int* m, int anim, int slot, int srt, int axis, int fld) noexcept nogil:
    """Flat index into AnimData._meta[20][17][3][3][3] (via the raw pointer cached on PoseEngine),
    so the nogil pose path reaches the keyframe metadata without a void*->AnimData cast (which this
    Cython refcounts, forbidden under nogil)."""
    return m[((((anim * 17 + slot) * 3 + srt) * 3 + axis) * 3) + fld]


cdef class AnimData:
    """IMMUTABLE registered keyframe data + foot chains, shared across all PoseEngine instances (and
    thus every A* clone). Built once per parsed anim set and cached -- avoids re-copying ~90k keyframe
    values into C on every LandState.clone(). Read-only after set-up."""
    cdef int _meta[20][17][3][3][3]     # [anim<=20][slot; 0-11 feet, 12-16 body_co extras][s/r/t][axis][cnt,off,tt]
    #                                     anim cap 20: the land set is 17 (was 16 -> native engine off).
    cdef double* _sdata[20]
    cdef double* _rdata[20]
    cdef double* _tdata[20]
    cdef int _dec[20]
    cdef int _chain34[12]
    cdef int _n34
    cdef int _chain39[12]
    cdef int _n39

    def __cinit__(self):
        cdef int i
        for i in range(20):
            self._sdata[i] = NULL; self._rdata[i] = NULL; self._tdata[i] = NULL

    def __dealloc__(self):
        cdef int i
        for i in range(20):
            if self._sdata[i] != NULL: free(self._sdata[i])
            if self._rdata[i] != NULL: free(self._rdata[i])
            if self._tdata[i] != NULL: free(self._tdata[i])

    def add_anim(self, int idx, anm):
        """Register a parsed BCK (j3d_eval anm dict) at index `idx`. Copies the keyframe data into C
        arrays (rotation ints stored as exact doubles) + the per-chain-joint track metadata."""
        cdef list sd = anm['scale_data'], rd = anm['rot_data'], td = anm['trans_data']
        cdef int ns = len(sd), nr = len(rd), nt = len(td), i, slot, track, axis, jnt
        self._sdata[idx] = <double*>malloc(ns * sizeof(double))
        self._rdata[idx] = <double*>malloc(nr * sizeof(double))
        self._tdata[idx] = <double*>malloc(nt * sizeof(double))
        for i in range(ns): self._sdata[idx][i] = sd[i]
        for i in range(nr): self._rdata[idx][i] = <double>(<long long>rd[i])
        for i in range(nt): self._tdata[idx][i] = td[i]
        self._dec[idx] = anm['dec_shift']
        cdef list joints = anm['joints']
        cdef list keys = ['s', 'r', 't']
        for slot in range(_NALL):
            jnt = _CJALL[slot]
            j = joints[jnt]
            for track in range(3):
                trk = j[keys[track]]
                for axis in range(3):
                    m = trk[axis]
                    self._meta[idx][slot][track][axis][0] = m[0]
                    self._meta[idx][slot][track][axis][1] = m[1]
                    self._meta[idx][slot][track][axis][2] = m[2]

    def set_chains(self, chain34, chain39):
        """The two foot FK chains as JOINT indices (root->foot); stored internally as slot indices."""
        cdef int k, s
        self._n34 = len(chain34)
        self._n39 = len(chain39)
        for k in range(self._n34):
            for s in range(12):
                if _CJ[s] == chain34[k]:
                    self._chain34[k] = s; break
        for k in range(self._n39):
            for s in range(12):
                if _CJ[s] == chain39[k]:
                    self._chain39[k] = s; break


cdef class PoseEngine:
    """C-resident foot-FK pose + toe engine (world-space path). Holds a reference to a shared, immutable
    AnimData + the per-instance MUTABLE state (old pose, morf counter, worldBase). One per FootFK; cheap
    to build per clone (no keyframe re-copy). Call set_pos() then pose_toe() per frame."""
    cdef AnimData data
    # Raw C pointers into the (immutable, `data`-owned) AnimData arrays, cached under the GIL in
    # __cinit__. The nogil pose path reads THESE, never `data` itself -- a void*->AnimData cast
    # refcounts, which is forbidden without the GIL.
    cdef int* _meta_p               # flat &data._meta[0][0][0][0][0]
    cdef double** _sdata_p          # &data._sdata[0]
    cdef double** _rdata_p          # &data._rdata[0]
    cdef double** _tdata_p          # &data._tdata[0]
    cdef int* _dec_p                # &data._dec[0]
    cdef int* _chain39_p            # &data._chain39[0]
    cdef int* _chain34_p            # &data._chain34[0]
    cdef int _n39c, _n34c
    cdef double _oldq[12][4]
    cdef double _oldt[12][3]
    cdef double _olds[12][3]
    cdef bint _has_old[12]
    # body_co store: the neck/head extras (BODY_CO_EXTRA slots 12-16 = joints 2,3,4,14,15), posed
    # each frame with the SAME blend state as the feet (the exec-pass centre). Index i =
    # slot 12+i. The foot path leaves these untouched; only set when `_body_co` is on.
    cdef double _oldq_bc[5][4]
    cdef double _oldt_bc[5][3]
    cdef double _olds_bc[5][3]
    cdef bint _has_old_bc[5]
    cdef bint _body_co              # pose the body_co extras each frame (off for a plain walk)
    cdef double _m_counter, _m_f8, _m_rate, _m_f10, _m_f14
    cdef double _base[12]           # worldBase (set by set_pos)
    cdef double _inv[12]            # m37B4 = PSMTXInverse(worldBase)
    # ---- fused anim-state machine + toe-stream state (UnderAnimState + FootSpeedF port) --------
    cdef int _code2idx[N_ANIM]      # anim code -> AnimData data-index (set by init_anim)
    cdef bint _sword                # mEquipItem == SWORD: walk/dash pose as WALKS/DASHS (getAnmData)
    cdef bint _fused_ready          # init_anim done
    cdef int _fc0_attr, _fc1_attr
    cdef double _fc0_start, _fc0_end, _fc0_loop, _fc0_rate, _fc0_frame
    cdef double _fc1_start, _fc1_end, _fc1_loop, _fc1_rate, _fc1_frame
    cdef int _move0, _move1         # anim codes (-1 = None)
    cdef int _m34C3
    cdef double _a_ratio            # getRatio(1)
    cdef double _m3598
    cdef double _t1[12]             # toe drawn last frame
    cdef double _t2[12]             # toe drawn the frame before
    cdef double _prev_f312, _m35B4
    # Deferred draw (FootSpeedF.defer_draw): the game draws the model at frame END, from the
    # POST-posMove base, while the compose that consumes t1/t2 runs mid-frame -- so the pose is
    # stashed here and `_finish_draw_c` lands it once the caller has moved. See finish_draw.
    cdef bint _defer_draw, _has_pd
    cdef int _pd_m0, _pd_m1
    cdef double _pd_f0, _pd_f1, _pd_ratio, _pd_morf, _pd_f312, _pd_msd
    cdef bint _started, _stopped
    cdef double _idle_frame
    cdef int _idle_code
    cdef bint _single_entered
    cdef double _pending_morf       # >=0 => pending; use _has_pending gate
    cdef bint _has_pending

    def __cinit__(self, AnimData data):
        cdef int i
        self.data = data
        # cache raw C pointers to the immutable AnimData arrays (GIL held here) for the nogil path
        self._meta_p = &data._meta[0][0][0][0][0]
        self._sdata_p = &data._sdata[0]
        self._rdata_p = &data._rdata[0]
        self._tdata_p = &data._tdata[0]
        self._dec_p = &data._dec[0]
        self._chain39_p = &data._chain39[0]
        self._chain34_p = &data._chain34[0]
        self._n39c = data._n39
        self._n34c = data._n34
        for i in range(12):
            self._has_old[i] = False
        for i in range(5):
            self._has_old_bc[i] = False
        self._body_co = False
        self._m_counter = self._m_f8 = self._m_rate = self._m_f10 = self._m_f14 = 0.0
        self._fused_ready = False
        self._has_pending = False

    def reset_old(self):
        cdef int i
        for i in range(12):
            self._has_old[i] = False
        for i in range(5):
            self._has_old_bc[i] = False

    def clone_state(self):
        """Full memberwise state-copy sharing the immutable AnimData -- makes a MID-WALK clone
        bit-exact: the toe stream (_t1/_t2/_prev_f312/_m35B4), the oldframe-morf counter, the two
        frame ctrls + old pose are all carried. Contrast __cinit__, which starts a fresh engine at
        rest (valid to clone only PRE-walk). The old pose/toe are model-local (worldBase is applied
        downstream), so the copy is position-independent. See land.LandState.clone."""
        cdef PoseEngine c = PoseEngine(self.data)     # shares the immutable keyframe data
        cdef int i, j
        for i in range(12):
            c._has_old[i] = self._has_old[i]
            for j in range(4):
                c._oldq[i][j] = self._oldq[i][j]
            for j in range(3):
                c._oldt[i][j] = self._oldt[i][j]
                c._olds[i][j] = self._olds[i][j]
            c._base[i] = self._base[i]
            c._inv[i] = self._inv[i]
            c._t1[i] = self._t1[i]
            c._t2[i] = self._t2[i]
        c._body_co = self._body_co
        for i in range(5):
            c._has_old_bc[i] = self._has_old_bc[i]
            for j in range(4):
                c._oldq_bc[i][j] = self._oldq_bc[i][j]
            for j in range(3):
                c._oldt_bc[i][j] = self._oldt_bc[i][j]
                c._olds_bc[i][j] = self._olds_bc[i][j]
        c._m_counter = self._m_counter; c._m_f8 = self._m_f8; c._m_rate = self._m_rate
        c._m_f10 = self._m_f10; c._m_f14 = self._m_f14
        for i in range(N_ANIM):
            c._code2idx[i] = self._code2idx[i]
        c._fused_ready = self._fused_ready
        c._sword = self._sword
        c._fc0_attr = self._fc0_attr; c._fc1_attr = self._fc1_attr
        c._fc0_start = self._fc0_start; c._fc0_end = self._fc0_end; c._fc0_loop = self._fc0_loop
        c._fc0_rate = self._fc0_rate; c._fc0_frame = self._fc0_frame
        c._fc1_start = self._fc1_start; c._fc1_end = self._fc1_end; c._fc1_loop = self._fc1_loop
        c._fc1_rate = self._fc1_rate; c._fc1_frame = self._fc1_frame
        c._move0 = self._move0; c._move1 = self._move1
        c._m34C3 = self._m34C3; c._a_ratio = self._a_ratio; c._m3598 = self._m3598
        c._prev_f312 = self._prev_f312; c._m35B4 = self._m35B4
        c._started = self._started; c._stopped = self._stopped
        c._idle_frame = self._idle_frame; c._idle_code = self._idle_code
        c._single_entered = self._single_entered
        c._pending_morf = self._pending_morf; c._has_pending = self._has_pending
        c._defer_draw = self._defer_draw; c._has_pd = self._has_pd
        c._pd_m0 = self._pd_m0; c._pd_m1 = self._pd_m1
        c._pd_f0 = self._pd_f0; c._pd_f1 = self._pd_f1; c._pd_ratio = self._pd_ratio
        c._pd_morf = self._pd_morf; c._pd_f312 = self._pd_f312; c._pd_msd = self._pd_msd
        return c

    @property
    def phase(self):
        """Read-only anim-phase fingerprint (diagnostic): the two frame-ctrl frames, the oldframe-morf
        counter + morf tuning, and the toe-stream scalars. Determines the walk pose (hence the freeze
        coast) for a given position -- used by the freeze planner's delta-prediction to characterize a
        start seq's full-speed phase. See _notes/chained-freeze-probes."""
        return (self._fc0_frame, self._fc1_frame, self._m_counter, self._m_f8, self._m_rate,
                self._m_f10, self._m_f14, self._prev_f312, self._m35B4, self._a_ratio, self._m3598)

    cdef void _set_pos_c(self, double px, double py, double pz, long long facing,
                         long long lean) noexcept nogil:
        """worldBase = transS(p) . YrotM(facing) [. ZrotM(lean)] + its PSMTXInverse. `lean` is
        shape_angle.z (the m351C>>1 MOVE turn lean): mDoMtx_ZXYrotM concats the Z rotation onto the
        Y-rotated base, skipped entirely at 0 -- the same build as `_co_center_impl` and the Python
        `fk.world_base`. It only moves the pose by ULPs (the base is cancelled by m37B4 afterwards),
        but those ULPs ARE the toe stream's last digits."""
        cdef long long fc = facing & 0xFFFF, lc = lean & 0xFFFF
        cdef double c = jma_cos(fc), s = jma_sin(fc), ns = f32(-s)
        self._base[0] = c;   self._base[1] = 0.0; self._base[2] = s;   self._base[3] = f32(px)
        self._base[4] = 0.0; self._base[5] = 1.0; self._base[6] = 0.0; self._base[7] = f32(py)
        self._base[8] = ns;  self._base[9] = 0.0; self._base[10] = c;  self._base[11] = f32(pz)
        cdef double rz[12]
        cdef double leaned[12]
        cdef double cz_, sz_
        if lc != 0:
            cz_ = jma_cos(lc); sz_ = jma_sin(lc)
            rz[0] = cz_; rz[1] = f32(-sz_); rz[2] = 0.0;  rz[3] = 0.0
            rz[4] = sz_; rz[5] = cz_;       rz[6] = 0.0;  rz[7] = 0.0
            rz[8] = 0.0; rz[9] = 0.0;       rz[10] = 1.0; rz[11] = 0.0
            _concat_c(self._base, rz, leaned)
            memcpy(self._base, leaned, 12 * sizeof(double))
        _psmtx_inverse_c(self._base, self._inv)

    def set_pos(self, px, py, pz, facing, lean=0):
        """Set Link's world pose for the frame about to be posed: build worldBase + m37B4 into C
        (was fk.world_base + a Python list round-trip per frame). `lean` = shape_angle.z (0 = the
        flat base = transS.ZXYrotM(Y))."""
        self._set_pos_c(<double>px, <double>py, <double>pz, (<long long>facing) & 0xFFFF,
                        (<long long>lean) & 0xFFFF)

    cdef void _init_morf(self, double i_morf) noexcept nogil:
        i_morf = f32(i_morf)
        if i_morf > 0.0:
            self._m_counter = i_morf
            self._m_f8 = fdivs(1.0, i_morf)
            self._m_rate = 1.0
            self._m_f10 = 1.0
            self._m_f14 = 1.0
            self._morf_dec()
        else:
            self._m_counter = self._m_f8 = self._m_rate = self._m_f10 = self._m_f14 = 0.0

    cdef void _morf_dec(self) noexcept nogil:
        if not (self._m_counter > 0.0):
            return
        self._m_counter = fsubs(self._m_counter, 1.0)
        if self._m_counter <= 0.0:
            self._m_counter = 0.0; self._m_f8 = 0.0; self._m_rate = 0.0
        self._m_f14 = self._m_f10
        self._m_f10 = fmuls(self._m_counter, self._m_f8)
        if self._m_f14 > 0.0:
            self._m_rate = fsubs(1.0, fdivs(fsubs(self._m_f14, self._m_f10), self._m_f14))
        else:
            self._m_rate = 0.0

    cdef void _calc_transform_c(self, int anim, int slot, double frame,
                                double* scale, long long* rot, double* trans) noexcept nogil:
        cdef int* m = self._meta_p
        cdef int axis, cnt, off, tt, dec = self._dec_p[anim]
        cdef double v
        cdef double* sd = self._sdata_p[anim]
        cdef double* rd = self._rdata_p[anim]
        cdef double* td = self._tdata_p[anim]
        for axis in range(3):
            cnt = _meta_at(m, anim, slot, 0, axis, 0)
            off = _meta_at(m, anim, slot, 0, axis, 1)
            tt = _meta_at(m, anim, slot, 0, axis, 2)
            if cnt == 0:
                scale[axis] = 1.0
            elif cnt == 1:
                scale[axis] = f32(sd[off])
            else:
                scale[axis] = _keyframe_interp_c(frame, cnt, tt, sd, off, 0)
            cnt = _meta_at(m, anim, slot, 1, axis, 0)
            off = _meta_at(m, anim, slot, 1, axis, 1)
            tt = _meta_at(m, anim, slot, 1, axis, 2)
            if cnt == 0:
                rot[axis] = 0
            elif cnt == 1:
                rot[axis] = _as_s32c((<long long>rd[off]) << dec)
            else:
                v = _keyframe_interp_c(frame, cnt, tt, rd, off, 1)
                rot[axis] = _as_s32c((<long long>v) << dec)
            cnt = _meta_at(m, anim, slot, 2, axis, 0)
            off = _meta_at(m, anim, slot, 2, axis, 1)
            tt = _meta_at(m, anim, slot, 2, axis, 2)
            if cnt == 0:
                trans[axis] = 0.0
            elif cnt == 1:
                trans[axis] = f32(td[off])
            else:
                trans[axis] = _keyframe_interp_c(frame, cnt, tt, td, off, 0)

    cdef void _chain_fk(self, double* base, double* inv, int* chain, int n,
                        double* local, double* out) noexcept nogil:
        """out = inv * (base * local[chain[0]] * ... * local[chain[n-1]]). `local` is 12 slots x 12."""
        cdef double bufA[12]
        cdef double bufB[12]
        cdef double* cur = bufA
        cdef double* nxt = bufB
        cdef double* swp
        cdef int k
        memcpy(cur, base, 12 * sizeof(double))
        for k in range(n):
            _concat_c(cur, local + chain[k] * 12, nxt)
            swp = cur; cur = nxt; nxt = swp
        _concat_c(inv, cur, out)

    cdef void _pose_toe_core(self, int m0, int m1, double f0, double f1, double ratio,
                             double i_morf, double* toes) noexcept nogil:
        """Pose all 12 chain joints (blend m0@f0 with m1@f1, oldframe-morf, PSMTXQuat, scale/trans),
        FK both feet from the worldBase set by set_pos(), remove the base with m37B4, and fill
        toes[0..11] = [Rtoe, Ltoe, Rheel, Lheel] x (x,y,z) (index 0 = right jnt39, 1 = left jnt34).
        The reusable core shared by pose_toe() and the fused walk/atn/single step methods."""
        cdef double rate
        if i_morf >= 0.0:
            self._init_morf(i_morf)
        rate = self._m_rate

        cdef double local[144]                     # 12 slots x 12 doubles
        cdef double q0[4]
        cdef double q1[4]
        cdef double q3[4]
        cdef double mtx[12]
        cdef double s0[3]
        cdef double t0[3]
        cdef double s1[3]
        cdef double t1[3]
        cdef long long r0[3]
        cdef long long r1[3]
        cdef double tr[3]
        cdef double scl[3]
        cdef int slot, k, base_off, bci
        cdef bint apply_morf
        cdef double r30, f31
        cdef bint morf_on = rate > 0.0

        for slot in range(12):
            self._calc_transform_c(m0, slot, f0, s0, r0, t0)
            self._calc_transform_c(m1, slot, f1, s1, r1, t1)
            _euler_to_quat_c(r0[0], r0[1], r0[2], q0)
            _euler_to_quat_c(r1[0], r1[1], r1[2], q1)
            _quat_lerp_c(q0, q1, ratio, q3)
            r30 = fsubs(1.0, ratio)
            for k in range(3):
                tr[k] = fadds(fmuls(t0[k], r30), fmuls(t1[k], ratio))
                scl[k] = fadds(fmuls(s0[k], r30), fmuls(s1[k], ratio))
            apply_morf = morf_on and self._has_old[slot]   # all chain joints are < MORF_END (0x2A)
            if apply_morf:
                f31 = fsubs(1.0, rate)
                _quat_lerp_c(self._oldq[slot], q3, f31, q3)
                for k in range(3):
                    tr[k] = fadds(fmuls(tr[k], f31), fmuls(self._oldt[slot][k], rate))
                    scl[k] = fadds(fmuls(scl[k], f31), fmuls(self._olds[slot][k], rate))
            _psmtx_quat_c(q3, mtx)
            base_off = slot * 12
            local[base_off + 0] = fmuls(mtx[0], scl[0]); local[base_off + 1] = fmuls(mtx[1], scl[1])
            local[base_off + 2] = fmuls(mtx[2], scl[2]); local[base_off + 3] = f32(tr[0])
            local[base_off + 4] = fmuls(mtx[4], scl[0]); local[base_off + 5] = fmuls(mtx[5], scl[1])
            local[base_off + 6] = fmuls(mtx[6], scl[2]); local[base_off + 7] = f32(tr[1])
            local[base_off + 8] = fmuls(mtx[8], scl[0]); local[base_off + 9] = fmuls(mtx[9], scl[1])
            local[base_off + 10] = fmuls(mtx[10], scl[2]); local[base_off + 11] = f32(tr[2])
            for k in range(4):
                self._oldq[slot][k] = q3[k]
            for k in range(3):
                self._oldt[slot][k] = tr[k]
                self._olds[slot][k] = scl[k]
            self._has_old[slot] = True

        # body_co extras (slots 12-16 = joints 2,3,4,14,15): same blend state as the feet this
        # frame (same m0,m1,f0,f1,ratio,rate), stored LOCAL (no FK) for the exec-centre co_center.
        # Mirrors foot_fk._pose_frame's neck-chain pass (which poses all 17 joints in one call).
        if self._body_co:
            for slot in range(12, 17):
                bci = slot - 12
                self._calc_transform_c(m0, slot, f0, s0, r0, t0)
                self._calc_transform_c(m1, slot, f1, s1, r1, t1)
                _euler_to_quat_c(r0[0], r0[1], r0[2], q0)
                _euler_to_quat_c(r1[0], r1[1], r1[2], q1)
                _quat_lerp_c(q0, q1, ratio, q3)
                r30 = fsubs(1.0, ratio)
                for k in range(3):
                    tr[k] = fadds(fmuls(t0[k], r30), fmuls(t1[k], ratio))
                    scl[k] = fadds(fmuls(s0[k], r30), fmuls(s1[k], ratio))
                apply_morf = morf_on and self._has_old_bc[bci]   # all body_co joints < MORF_END
                if apply_morf:
                    f31 = fsubs(1.0, rate)
                    _quat_lerp_c(self._oldq_bc[bci], q3, f31, q3)
                    for k in range(3):
                        tr[k] = fadds(fmuls(tr[k], f31), fmuls(self._oldt_bc[bci][k], rate))
                        scl[k] = fadds(fmuls(scl[k], f31), fmuls(self._olds_bc[bci][k], rate))
                for k in range(4):
                    self._oldq_bc[bci][k] = q3[k]
                for k in range(3):
                    self._oldt_bc[bci][k] = tr[k]
                    self._olds_bc[bci][k] = scl[k]
                self._has_old_bc[bci] = True

        self._morf_dec()

        cdef double cur39[12]
        cdef double cur34[12]
        self._chain_fk(self._base, self._inv, self._chain39_p, self._n39c, local, cur39)
        self._chain_fk(self._base, self._inv, self._chain34_p, self._n34c, local, cur34)

        _mv_c(cur39, _TOE_X, _TOE_Y, 0.0, toes + 0)
        _mv_c(cur34, _TOE_X, _TOE_Y, 0.0, toes + 3)
        _mv_c(cur39, _HEEL_X, _HEEL_Y, 0.0, toes + 6)
        _mv_c(cur34, _HEEL_X, _HEEL_Y, 0.0, toes + 9)

    def pose_toe(self, int m0, int m1, double f0, double f1, double ratio, double i_morf):
        """Pose one frame and return the flat 12-tuple [Rtoe, Ltoe, Rheel, Lheel] x (x,y,z)
        (index 0 = right jnt39, 1 = left jnt34). Thin wrapper over _pose_toe_core."""
        cdef double toes[12]
        self._pose_toe_core(m0, m1, f0, f1, ratio, i_morf, toes)
        return (toes[0], toes[1], toes[2], toes[3], toes[4], toes[5],
                toes[6], toes[7], toes[8], toes[9], toes[10], toes[11])

    cdef void _body_co_center(self, double px, double py, double pz, long long facing,
                              long long lean, long long body_x, double* out) noexcept nogil:
        """Link's exec-pass body-Co centre (out[0]=cx, out[1]=cz) from THIS engine's posed neck
        chain: chain [0,1,2,3,4,14] = foot slots 0,1 (_oldq[0..1]) + body_co slots 12,13,14,15
        (_oldq_bc[0..3]). Bit-exact twin of foot_fk.body_co_center / the module `co_center`, reading
        the C stores directly (no Python round-trip) -- requires `_body_co` (the extras were posed)."""
        cdef double q6[24]
        cdef double t6[18]
        cdef double s6[18]
        cdef int k
        for k in range(4):
            q6[0*4+k] = self._oldq[0][k]
            q6[1*4+k] = self._oldq[1][k]
            q6[2*4+k] = self._oldq_bc[0][k]
            q6[3*4+k] = self._oldq_bc[1][k]
            q6[4*4+k] = self._oldq_bc[2][k]
            q6[5*4+k] = self._oldq_bc[3][k]
        for k in range(3):
            t6[0*3+k] = self._oldt[0][k];    s6[0*3+k] = self._olds[0][k]
            t6[1*3+k] = self._oldt[1][k];    s6[1*3+k] = self._olds[1][k]
            t6[2*3+k] = self._oldt_bc[0][k]; s6[2*3+k] = self._olds_bc[0][k]
            t6[3*3+k] = self._oldt_bc[1][k]; s6[3*3+k] = self._olds_bc[1][k]
            t6[4*3+k] = self._oldt_bc[2][k]; s6[4*3+k] = self._olds_bc[2][k]
            t6[5*3+k] = self._oldt_bc[3][k]; s6[5*3+k] = self._olds_bc[3][k]
        _co_center_impl(px, py, pz, facing, lean, body_x, q6, t6, s6, out)

    cdef void _head_chain(self, double* q7, double* t7, double* s7) noexcept nogil:
        """This engine's posed HEAD chain as flat arrays -- the `_body_co_center` read carried one
        joint further: chain [0,1,2,3,4,14,15] = foot slots 0,1 (`_oldq[0..1]`) + body_co slots
        12..16 (`_oldq_bc[0..4]`). Joint 15 is already posed with the body_co extras, so the head
        costs one more matrix concat and NO extra pose work. Requires `_body_co`."""
        cdef int k, i
        for k in range(4):
            q7[0*4+k] = self._oldq[0][k]
            q7[1*4+k] = self._oldq[1][k]
            for i in range(5):
                q7[(2+i)*4+k] = self._oldq_bc[i][k]
        for k in range(3):
            t7[0*3+k] = self._oldt[0][k]; s7[0*3+k] = self._olds[0][k]
            t7[1*3+k] = self._oldt[1][k]; s7[1*3+k] = self._olds[1][k]
            for i in range(5):
                t7[(2+i)*3+k] = self._oldt_bc[i][k]
                s7[(2+i)*3+k] = self._olds_bc[i][k]

    cdef void _head_top(self, double px, double py, double pz, long long facing,
                        long long lean, long long body_x,
                        long long nlx, long long nly, long long nlz,
                        double* out) noexcept nogil:
        """Link's exec-pass ``mHeadTopPos`` (out[0..2]) from THIS engine's posed chain."""
        cdef double q7[28]
        cdef double t7[21]
        cdef double s7[21]
        self._head_chain(q7, t7, s7)
        _head_top_impl(px, py, pz, facing, lean, body_x, nlx, nly, nlz, q7, t7, s7, out)

    cdef void _head_mtx(self, double px, double py, double pz, long long facing,
                        long long lean, long long body_x,
                        long long nlx, long long nly, long long nlz,
                        double* out) noexcept nogil:
        """The exec-pass WORLD head anm matrix (out = 3x4 flat) from THIS engine's posed chain --
        what the NEXT frame's `setNeckAngle` measures its current head angles from."""
        cdef double q7[28]
        cdef double t7[21]
        cdef double s7[21]
        self._head_chain(q7, t7, s7)
        _head_mtx_impl(px, py, pz, facing, lean, body_x, nlx, nly, nlz, q7, t7, s7, out)

    def head_top_at(self, double px, double py, double pz, long long facing, long long lean,
                    long long body_x, neck=None):
        """`_head_top` from Python -- the gate's handle on it (0-ULP vs `foot_fk.FootFK.head_top`
        for the pose this engine last posed). ``neck`` = `NeckLook.local_38()` or None."""
        cdef long long nlx = 0, nly = 0, nlz = 0
        if neck is not None:
            nlx = _s16c(<long long>int(neck[0]) & 0xFFFF)
            nly = _s16c(<long long>int(neck[1]) & 0xFFFF)
            nlz = _s16c(<long long>int(neck[2]) & 0xFFFF)
        cdef double out[3]
        self._head_top(px, py, pz, facing, lean, body_x, nlx, nly, nlz, out)
        return (out[0], out[1], out[2])

    def head_mtx_at(self, double px, double py, double pz, long long facing, long long lean,
                    long long body_x, neck=None):
        """`_head_mtx` from Python as a 3x4 nested tuple -- `foot_fk.FootFK.head_mtx`'s shape."""
        cdef long long nlx = 0, nly = 0, nlz = 0
        if neck is not None:
            nlx = _s16c(<long long>int(neck[0]) & 0xFFFF)
            nly = _s16c(<long long>int(neck[1]) & 0xFFFF)
            nlz = _s16c(<long long>int(neck[2]) & 0xFFFF)
        cdef double m[12]
        self._head_mtx(px, py, pz, facing, lean, body_x, nlx, nly, nlz, m)
        return ((m[0], m[1], m[2], m[3]), (m[4], m[5], m[6], m[7]), (m[8], m[9], m[10], m[11]))

    def pose_chain(self, int m0, int m1, double f0, double f1, double ratio, double rate,
                   object slots, object oldq, object oldt, object olds,
                   double f030_0, double f030_1):
        """Batched native fold of foot_fk._pose_frame for the body_co joint set (the ONE call the
        Python pose loop becomes): sample both anims from the shared AnimData, blend + oldframe-morf,
        build the local 3x4, per joint -- in C, no per-joint calc_transform dicts / Python call.

        `slots` = a list of (slot, jnt) in pose order (foot chain slots 0-11 then the neck/head extras
        12-16; == enumerate(CHAIN_JOINTS + BODY_CO_EXTRA)). `oldq/oldt/olds` = the caller's old-pose
        dicts (jnt -> tuple); read for the morf and UPDATED IN PLACE with this frame's posed pose (the
        store body_co_center / the next frame's morf read). `rate` = the morf rate (>0 => morf on;
        the caller owns the morf counter, exactly like _pose_frame). `f030_0`/`f030_1` = the CLOTCH
        leg-lift (mFootData[0]->jnt36, [1]->jnt31); 0.0 skips. Returns {jnt: 3x4 local matrix}.

        Bit-exact with foot_fk._pose_frame's native (blend_joint) branch: _calc_transform_c is the
        0-ULP twin of j3d_eval.calc_transform (the fused foot path is gated on it) and the inner
        blend math is copied verbatim from blend_joint. Gated by tests/test_pose_chain_native.py
        (differential vs _force_slow) + test_from_f0.py (the live 0-ULP end-to-end oracle)."""
        cdef double s0[3]
        cdef double t0[3]
        cdef double s1[3]
        cdef double t1[3]
        cdef long long r0[3]
        cdef long long r1[3]
        cdef double q0[4]
        cdef double q1[4]
        cdef double q3[4]
        cdef double oq[4]
        cdef double m[12]
        cdef double r30, f31, tr0, tr1, tr2, sc0, sc1, sc2
        cdef int slot, jnt
        cdef bint morf_on = rate > 0.0
        cdef bint apply_morf
        cdef object prev, ot, os_
        local = {}
        for slot, jnt in slots:
            self._calc_transform_c(m0, slot, f0, s0, r0, t0)
            self._calc_transform_c(m1, slot, f1, s1, r1, t1)
            _euler_to_quat_c(r0[0], r0[1], r0[2], q0)
            _euler_to_quat_c(r1[0], r1[1], r1[2], q1)
            _quat_lerp_c(q0, q1, ratio, q3)
            r30 = fsubs(1.0, ratio)
            # translate/scale blend is NON-fused (m_Do_ext.cpp:1183): each product separately rounded.
            tr0 = fadds(fmuls(t0[0], r30), fmuls(t1[0], ratio))
            tr1 = fadds(fmuls(t0[1], r30), fmuls(t1[1], ratio))
            tr2 = fadds(fmuls(t0[2], r30), fmuls(t1[2], ratio))
            sc0 = fadds(fmuls(s0[0], r30), fmuls(s1[0], ratio))
            sc1 = fadds(fmuls(s0[1], r30), fmuls(s1[1], ratio))
            sc2 = fadds(fmuls(s0[2], r30), fmuls(s1[2], ratio))
            # every body_co joint is < MORF_END (0x2A), so the range gate reduces to "has old pose".
            apply_morf = morf_on and (jnt in oldq)
            if apply_morf:
                f31 = fsubs(1.0, rate)
                prev = oldq[jnt]
                oq[0] = prev[0]; oq[1] = prev[1]; oq[2] = prev[2]; oq[3] = prev[3]
                _quat_lerp_c(oq, q3, f31, q3)
                ot = oldt[jnt]; os_ = olds[jnt]
                tr0 = fadds(fmuls(tr0, f31), fmuls(<double>ot[0], rate))
                tr1 = fadds(fmuls(tr1, f31), fmuls(<double>ot[1], rate))
                tr2 = fadds(fmuls(tr2, f31), fmuls(<double>ot[2], rate))
                sc0 = fadds(fmuls(sc0, f31), fmuls(<double>os_[0], rate))
                sc1 = fadds(fmuls(sc1, f31), fmuls(<double>os_[1], rate))
                sc2 = fadds(fmuls(sc2, f31), fmuls(<double>os_[2], rate))
            _psmtx_quat_c(q3, m)
            # M = R * diag(scale): scale column j by scale[j]; trans column = f32(trans).
            m[0] = fmuls(m[0], sc0); m[1] = fmuls(m[1], sc1); m[2] = fmuls(m[2], sc2); m[3] = f32(tr0)
            m[4] = fmuls(m[4], sc0); m[5] = fmuls(m[5], sc1); m[6] = fmuls(m[6], sc2); m[7] = f32(tr1)
            m[8] = fmuls(m[8], sc0); m[9] = fmuls(m[9], sc1); m[10] = fmuls(m[10], sc2); m[11] = f32(tr2)
            local[jnt] = [[m[0], m[1], m[2], m[3]], [m[4], m[5], m[6], m[7]], [m[8], m[9], m[10], m[11]]]
            oldq[jnt] = (q3[0], q3[1], q3[2], q3[3])
            oldt[jnt] = (tr0, tr1, tr2)
            olds[jnt] = (sc0, sc1, sc2)
        # _apply_foot030: jointBeforeCB per-leg CLOTCH lift (local translate.x -= mFootData[i].0x030).
        if f030_0 != 0.0 and 36 in local:
            local[36][0][3] = fsubs(local[36][0][3], f030_0)
        if f030_1 != 0.0 and 31 in local:
            local[31][0][3] = fsubs(local[31][0][3], f030_1)
        return local

    # ==== fused anim-state machine + posMoveFromFootPos (FootSpeedF + UnderAnimState port) =======
    # Every per-frame land walk/atn/turn/roll step becomes ONE native call: the anim FrameCtrl
    # advance + setBlendMoveAnime regime pick + the 12-joint pose + both foot FKs + posMoveFromFootPos
    # compose, with all state resident in C. Bit-exact drop-in for the Python FootSpeedF hot path.

    def init_anim(self, code2idx):
        """Register the anim CODE -> AnimData data-index map (from foot_fk._anim_idx). Requires
        init_anim_consts() to have been called for the ANIM_META + HIO tables."""
        cdef int i
        if not _ANIM_CONSTS_READY:
            raise RuntimeError("init_anim_consts() must be called before init_anim()")
        for i in range(N_ANIM):
            self._code2idx[i] = code2idx[i]
        self._fused_ready = True

    def set_sword(self, bint sword):
        """mEquipItem == daPyItem_SWORD_e: the under-body walk/dash anims come from
        `mSwordAnmIndexTable` (ANM_WALK -> WALKS, ANM_DASH -> DASHS; getAnmData,
        d_a_player_main.cpp:12950). Everything else in the set maps to itself (the table
        ends at ANM_CUTTURNPWLR 0x1A, so ANM_ROLLF 0x32 falls through to mAnmDataTable), so this
        flag only re-points the two walk codes. Mirrors `FootSpeedF(sword=)`."""
        self._sword = sword

    def w_init(self, int idle_code, double idle_frame, draw0):
        """Seed the fused toe-stream + anim state at the rest anchor. `draw0` is the flat 12-tuple
        the Python seeding (FootFK.seed + step_feet) already posed -- its side effect left this
        engine's old-pose correct, so w_init only captures draw0 and inits the UnderAnimState fields."""
        cdef int i
        for i in range(12):
            self._t1[i] = draw0[i]; self._t2[i] = draw0[i]
        self._prev_f312 = 0.0
        self._m35B4 = 0.0
        self._started = False
        self._stopped = False
        self._single_entered = False
        self._has_pending = False
        self._idle_code = idle_code
        self._idle_frame = idle_frame
        self._move0 = idle_code
        self._move1 = -1
        self._m34C3 = 0
        self._a_ratio = 0.0
        self._m3598 = 0.0
        self._fc0_attr = _MATTR[idle_code]
        self._fc0_start = 0.0; self._fc0_end = _MMAX[idle_code]; self._fc0_loop = 0.0
        self._fc0_rate = 0.0; self._fc0_frame = idle_frame
        self._fc1_attr = 2                        # FrameCtrl defaults (EMode_LOOP, [0,1))
        self._fc1_start = 0.0; self._fc1_end = 1.0; self._fc1_loop = 0.0
        self._fc1_rate = 0.0; self._fc1_frame = 0.0

    cdef void _anim_set_move(self, double f27, double f28, double f25, int r27, int r28, int r29) noexcept nogil:
        """daPy_lk_c::setMoveAnime (12723): r27->MOVE0, r28->MOVE1 at ratio f27; preserve phase, set the
        two frame-ctrl rates. i_morf is vestigial here (the FK morf is driven by FootSpeedF). Port of
        UnderAnimState._set_move_anime."""
        cdef double f31
        if self._m34C3 == 0 or self._m34C3 == 9 or self._m34C3 == 10:
            f31 = 0.0
        else:
            f31 = fdivs(self._fc0_frame, _MMAX[self._move0])
        self._a_ratio = f27
        cdef double f3 = _MMAX[r27]
        cdef double f26 = _MMAX[r28]
        cdef double f30 = fdivs(1.0, f3)
        cdef double f27r = fadds(f28, fmuls(f27, fsubs(fdivs(fmuls(f25, f3), f26), f28)))
        self._fc0_attr = _MATTR[r27]
        self._fc0_start = 0.0; self._fc0_end = f3; self._fc0_rate = f27r
        self._fc0_frame = fmuls(f31, f3)
        self._fc0_loop = 0.0 if f27r >= 0.0 else f3
        self._fc1_attr = _MATTR[r28]
        self._fc1_start = 0.0; self._fc1_end = f26
        self._fc1_rate = fmuls(f30, fmuls(f27r, f26))
        self._fc1_frame = fmuls(f31, f26)
        self._fc1_loop = 0.0 if self._fc1_rate >= 0.0 else f26
        self._move0 = r27; self._move1 = r28; self._m34C3 = r29

    cdef void _anim_blend_move(self, double nspeed, double cos) noexcept nogil:
        """setBlendMoveAnime flat free-walk path (2966). Port of UnderAnimState._set_blend_move_anime."""
        cdef double an = fmuls(nspeed, cos)
        if an < 0.0:
            an = -an
        cdef double f30 = fdivs(an, _H_MAXSPEED)
        cdef double f25_2, f1
        # getAnmData: sword equipped -> the WALKS/DASHS pair (see set_sword).
        cdef int cw = C_WALKS if self._sword else C_WALK
        cdef int cd = C_DASHS if self._sword else C_DASH
        if f30 < _H_2C:
            f25_2 = fdivs(f30, _H_2C)
            self._m3598 = fsubs(1.0, fmuls(fsubs(1.0, _H_60), f25_2))
            self._anim_set_move(f25_2, _H_38, _H_40, C_WAITS, cw, 1)
        elif f30 < _H_30:
            f1 = fdivs(fsubs(f30, _H_2C), fsubs(_H_30, _H_2C))
            self._anim_set_move(f1, _H_40, _H_48, cw, cd, 1)
            self._m3598 = fmuls(_H_60, fsubs(1.0, f1))
        else:
            self._anim_set_move(1.0, _H_48, _H_48, cd, cd, 1)
            self._m3598 = 0.0

    cdef void _anim_atn_side(self, double f31, bint is_left) noexcept nogil:
        """setBlendAtnMoveAnime side branch (3343). Port of UnderAnimState._set_atn_side_anime."""
        cdef double f1, f28
        cdef int m0, m1
        if f31 < _ATN_1C:
            f1 = fdivs(f31, _ATN_1C)
            if is_left:
                m0 = C_ATNLS; m1 = C_ATNWLS
            else:
                m0 = C_ATNRS; m1 = C_ATNWRS
            self._anim_set_move(f1, _ATN_24, _ATN_28, m0, m1, 4)
            self._m3598 = 1.0
        elif f31 < _ATN_20:
            f28 = fdivs(fsubs(f31, _ATN_1C), fsubs(_ATN_20, _ATN_1C))
            if is_left:
                m0 = C_ATNWLS; m1 = C_ATNDLS
            else:
                m0 = C_ATNWRS; m1 = C_ATNDRS
            self._anim_set_move(f28, _ATN_28, _ATN_2C, m0, m1, 4)
            self._m3598 = fsubs(1.0, fmuls(f28, self._m3598))
        else:
            m0 = C_ATNDLS if is_left else C_ATNDRS
            self._anim_set_move(1.0, _ATN_2C, _ATN_2C, m0, m0, 4)
            self._m3598 = 0.0

    cdef void _anim_atn_back(self, double dvar7) noexcept nogil:
        """setBlendAtnBackMoveAnime (3217). Port of UnderAnimState._set_atn_back_anime."""
        cdef double f1
        if dvar7 < _ATNB_1C:
            f1 = fdivs(dvar7, _ATNB_1C)
            self._anim_set_move(f1, _H_38, _ATNB_24, C_WAITS, C_ATNWB, 4)
            self._m3598 = 1.0
        elif dvar7 < _ATNB_20:
            f1 = fdivs(fsubs(dvar7, _ATNB_1C), fsubs(_ATNB_20, _ATNB_1C))
            self._anim_set_move(f1, _ATNB_24, _ATNB_28, C_ATNWB, C_ATNDB, 4)
            self._m3598 = fsubs(1.0, f1)
        else:
            self._anim_set_move(1.0, _ATNB_28, _ATNB_28, C_ATNDB, C_ATNDB, 4)
            self._m3598 = 0.0

    cdef double _foot_speedf_c(self, double nspeed, double msd, int m0, int m1,
                               double f0, double f1, double ratio, double m3598, double morf) noexcept nogil:
        """posMoveFromFootPos: pose the foot (m0@f0, m1@f1, oldframe-morf `morf`), take the 1-frame
        delayed toe delta + compose speedF, then shift the toe stream. Port of foot_speedf._foot_speedf."""
        cdef double cur[12]
        cdef int i
        cdef double speedF, f312
        if self._defer_draw:
            # Compose first (it reads only t1/t2), stash the pose for the end-of-frame base.
            _foot_compose_c(self._t1, self._t2, nspeed, msd, m3598, self._prev_f312, self._m35B4,
                            &speedF, &f312)
            self._pd_m0 = m0; self._pd_m1 = m1
            self._pd_f0 = f0; self._pd_f1 = f1; self._pd_ratio = ratio
            self._pd_morf = morf; self._pd_f312 = f312; self._pd_msd = msd
            self._has_pd = True
            return speedF
        self._pose_toe_core(self._code2idx[m0], self._code2idx[m1 if m1 >= 0 else m0],
                            f0, f1, ratio, morf, cur)
        _foot_compose_c(self._t1, self._t2, nspeed, msd, m3598, self._prev_f312, self._m35B4,
                        &speedF, &f312)
        self._m35B4 = msd
        for i in range(12):
            self._t2[i] = self._t1[i]
            self._t1[i] = cur[i]
        self._prev_f312 = f312
        return speedF

    cdef void _finish_draw_c(self, double px, double py, double pz, long long facing,
                             long long lean) noexcept nogil:
        """Deferred-draw completion: pose the stashed frame at the CURRENT (post-posMove) base and
        shift the toe stream. No-op when nothing was stashed (a frozen / non-posing frame). Twin of
        FootSpeedF.finish_draw."""
        cdef double cur[12]
        cdef int i
        if not self._has_pd:
            return
        self._has_pd = False
        self._set_pos_c(px, py, pz, facing, lean)
        self._pose_toe_core(self._code2idx[self._pd_m0],
                            self._code2idx[self._pd_m1 if self._pd_m1 >= 0 else self._pd_m0],
                            self._pd_f0, self._pd_f1, self._pd_ratio, self._pd_morf, cur)
        self._m35B4 = self._pd_msd
        for i in range(12):
            self._t2[i] = self._t1[i]
            self._t1[i] = cur[i]
        self._prev_f312 = self._pd_f312

    def set_defer_draw(self, bint defer):
        """Draw at frame END from the post-posMove base (`FootSpeedF.defer_draw`). Carried by
        `seed_from_foot`; a coupled caller calls `_finish_draw_c` every frame."""
        self._defer_draw = defer

    def w_step(self, double nspeed, double msd, double anim_nspeed, bint has_anim):
        """One walk (MOVE / MOVE_TURN tail) frame. Port of FootSpeedF.step. `has_anim` splits the
        anim-blend speed from the position speed (procMoveTurn_init(1))."""
        return self._w_step_c(nspeed, msd, anim_nspeed, has_anim)

    cdef double _w_step_c(self, double nspeed, double msd, double anim_nspeed, bint has_anim) noexcept nogil:
        nspeed = f32(nspeed)
        msd = f32(msd)
        cdef double an = f32(anim_nspeed) if has_anim else nspeed
        cdef double morf
        cdef double na = nspeed if nspeed >= 0.0 else -nspeed
        cdef double cur[12]
        cdef int i, idle
        if not self._started:
            if nspeed <= 0.0:
                self._idle_frame = fadds(self._idle_frame, 1.0)
                idle = self._code2idx[self._idle_code]
                self._pose_toe_core(idle, idle, self._idle_frame, self._idle_frame, 0.0, -1.0, cur)
                self._m35B4 = msd
                for i in range(12):
                    self._t2[i] = self._t1[i]
                    self._t1[i] = cur[i]
                self._prev_f312 = 0.0
                return 0.0
            self._started = True
            morf = 2.4
        elif na <= 0.001:
            self._stopped = True
            self._m35B4 = msd
            return 0.0
        elif self._has_pending:
            morf = self._pending_morf
            self._has_pending = False
        else:
            morf = -1.0
        _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                   &self._fc0_frame, &self._fc0_rate)
        _fc_update(self._fc1_attr, self._fc1_start, self._fc1_end, self._fc1_loop,
                   &self._fc1_frame, &self._fc1_rate)
        self._anim_blend_move(an, 1.0)
        return self._foot_speedf_c(nspeed, msd, self._move0, self._move1,
                                   self._fc0_frame, self._fc1_frame, self._a_ratio, self._m3598, morf)

    def w_step_atn(self, double nspeed, double msd, int direction, double f31,
                   double morf, bint has_morf):
        """One ATN_MOVE frame. Port of FootSpeedF.step_atn."""
        return self._w_step_atn_c(nspeed, msd, direction, f31, morf, has_morf)

    cdef double _w_step_atn_c(self, double nspeed, double msd, int direction, double f31,
                              double morf, bint has_morf) noexcept nogil:
        nspeed = f32(nspeed)
        msd = f32(msd)
        self._started = True
        cdef double m = morf if has_morf else -1.0
        _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                   &self._fc0_frame, &self._fc0_rate)
        _fc_update(self._fc1_attr, self._fc1_start, self._fc1_end, self._fc1_loop,
                   &self._fc1_frame, &self._fc1_rate)
        if direction == D_FORWARD:
            self._anim_blend_move(nspeed, 1.0)
        elif direction == D_BACKWARD:
            self._anim_atn_back(f32(f31))
        else:
            self._anim_atn_side(f32(f31), direction == D_LEFT)
        return self._foot_speedf_c(nspeed, msd, self._move0, self._move1,
                                   self._fc0_frame, self._fc1_frame, self._a_ratio, self._m3598, m)

    def w_step_single(self, double nspeed, double msd):
        """One single-anim proc frame (ROLL / WAIT_TURN / SLIP). Port of FootSpeedF.step_single_anim.
        Sets _started (getOldFrameFlg analog) like w_step_atn/w_enter_single do -- so a MOVE backslide
        after the proc-9 tier does not take w_step's cold nspeed<=0 rest path and return 0. Golden-inert
        (every real single-anim proc enters via w_enter_single, which already sets it)."""
        return self._w_step_single_c(nspeed, msd)

    cdef double _w_step_single_c(self, double nspeed, double msd) noexcept nogil:
        nspeed = f32(nspeed)
        msd = f32(msd)
        self._started = True
        cdef double morf = self._pending_morf if self._has_pending else -1.0
        self._has_pending = False
        if self._single_entered:
            self._single_entered = False                 # entry frame: pose at start, no ctrl advance
        else:
            _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                       &self._fc0_frame, &self._fc0_rate)
        return self._foot_speedf_c(nspeed, msd, self._move0, self._move0,
                                   self._fc0_frame, self._fc0_frame, 0.0, self._m3598, morf)

    def w_enter_single(self, int code, double morf, double start, double end,
                       double rate, bint has_morf):
        """setSingleMoveAnime entry (12794). Port of FootSpeedF.enter_single + UnderAnimState.set_single."""
        self._w_enter_single_c(code, morf, start, end, rate, has_morf)

    cdef void _w_enter_single_c(self, int code, double morf, double start, double end,
                                double rate, bint has_morf) noexcept nogil:
        self._move0 = code; self._move1 = -1; self._m34C3 = 0; self._a_ratio = 0.0
        cdef double frame = fsubs(end, 0.001) if rate < 0.0 else start
        self._fc0_attr = _MATTR[code]
        self._fc0_start = start; self._fc0_end = end; self._fc0_rate = rate; self._fc0_frame = frame
        self._fc0_loop = start if rate >= 0.0 else end
        self._started = True
        self._single_entered = True
        if has_morf:
            self._pending_morf = morf; self._has_pending = True
        else:
            self._has_pending = False

    def w_enter_wait_idle(self, double ratio, int r27_code, double morf, double msd):
        """WAIT idle-proc turn-step re-pose after a WAIT_TURN pivot. Port of FootSpeedF.enter_wait_idle."""
        return self._w_enter_wait_idle_c(ratio, r27_code, morf, msd)

    cdef double _w_enter_wait_idle_c(self, double ratio, int r27_code, double morf, double msd) noexcept nogil:
        self._started = True
        self._anim_set_move(ratio, _H_38, _ATN_28, C_WAITS, r27_code, 2)
        self._m3598 = 0.0
        self._foot_speedf_c(0.0, f32(msd), self._move0, self._move1,
                            self._fc0_frame, self._fc1_frame, self._a_ratio, self._m3598, morf)
        self._pending_morf = morf; self._has_pending = True
        return 0.0

    def w_enter_subjectivity(self, double msd, double morf):
        """procSubjectivity_init on-axis (5948) -- the C-up-cancel FREEZE. See
        `_w_pose_idle_blend_c`. Port of FootSpeedF.enter_subjectivity."""
        self._started = True
        return self._w_pose_idle_blend_c(msd, morf)

    cdef double _w_pose_idle_blend_c(self, double msd, double morf) noexcept nogil:
        """setBlendMoveAnime's ModeFlg_00000001 IDLE arm, plain sub-branch (3114): advance both
        ctrls (actor execute), then setMoveAnime(0, H_38, H_40, WAITS, WALK(S), 2) -- m34C3=2,
        ratio 0, m3598=0, phase preserved -- and pose at nspeed 0 to warm the toe stream.
        `morf` < 0 = no oldframe-morf (procWait's steady setBlendMoveAnime(-1.0f), 6144).
        Port of FootSpeedF.pose_idle_blend; callers own `_started`."""
        _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                   &self._fc0_frame, &self._fc0_rate)
        _fc_update(self._fc1_attr, self._fc1_start, self._fc1_end, self._fc1_loop,
                   &self._fc1_frame, &self._fc1_rate)
        self._anim_set_move(0.0, _H_38, _H_40, C_WAITS, C_WALKS if self._sword else C_WALK, 2)
        self._m3598 = 0.0
        self._foot_speedf_c(0.0, f32(msd), self._move0, self._move1,
                            self._fc0_frame, self._fc1_frame, self._a_ratio, self._m3598, morf)
        return 0.0

    def w_enter_wait_rest_hp(self):
        """Port of FootSpeedF.enter_wait_rest_hp -- see `_w_enter_wait_rest_hp_c`."""
        self._w_enter_wait_rest_hp_c()

    cdef void _w_enter_wait_rest_hp_c(self) noexcept nogil:
        """procWait_init's LOW-LIFE arm (6072): setSingleMoveAnime(ANM_WAITATOB, field_0x68,
        field_0x6C, field_0x10, field_0x70) -- a SINGLE (m34C3 -> 0) at rate 0.6 from frame 0 with
        the frame ctrl's end forced to 12, plus commonProcInit's m3598 = 0 (5805). Both ctrls take
        their actor-execute update first; MOVE0's is overwritten by the single, MOVE1's is its last
        (setSingleMoveAnime clears its heap index). Port of FootSpeedF.enter_wait_rest_hp."""
        _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                   &self._fc0_frame, &self._fc0_rate)
        _fc_update(self._fc1_attr, self._fc1_start, self._fc1_end, self._fc1_loop,
                   &self._fc1_frame, &self._fc1_rate)
        self._w_enter_single_c(C_WAITATOB, _H_70, _H_6C, _H_10, _H_68, True)
        self._m3598 = 0.0

    def w_step_subjectivity(self, double msd):
        """One SUBJECTIVITY / post-B WAIT hold frame: the WAITS/WALK ctrls advance (no re-pose),
        the foot poses at the frozen ratio (pure WAITS); position frozen. Port of
        FootSpeedF.step_subjectivity."""
        _fc_update(self._fc0_attr, self._fc0_start, self._fc0_end, self._fc0_loop,
                   &self._fc0_frame, &self._fc0_rate)
        _fc_update(self._fc1_attr, self._fc1_start, self._fc1_end, self._fc1_loop,
                   &self._fc1_frame, &self._fc1_rate)
        self._foot_speedf_c(0.0, f32(msd), self._move0, self._move1,
                            self._fc0_frame, self._fc1_frame, self._a_ratio, self._m3598, -1.0)
        return 0.0

    cdef void _w_set_pending_c(self, double v) noexcept nogil:
        self._pending_morf = v; self._has_pending = True

    def w_set_pending(self, v):
        """land.py sets FootSpeedF._pending_morf directly on some proc transitions; route into C."""
        if v is None:
            self._has_pending = False
        else:
            self._pending_morf = v; self._has_pending = True

    def w_get_pending(self):
        return self._pending_morf if self._has_pending else None

    def w_get_idle_frame(self):
        return self._idle_frame

    def seed_from_foot(self, foot, code2idx):
        """Seeding bridge: copy a PYTHON `foot_speedf.FootSpeedF` (`foot_native=False`,
        the from-f0 FreeRun path) state INTO this fused C engine so `w_step`/`w_step_atn`/
        `w_step_single` reproduce it bit-for-bit. The Python foot stream lives in the
        UnderAnimState (`foot.st`) + FootFK old-pose dicts (`foot.ff.old_*`, joint-keyed) + the
        posMoveFromFootPos toe stream (`foot.t1/t2/prev_f312/m35B4`); this method lands all of it
        in the C engine's own storage (12 foot-chain slots). Call on a fresh `clone_state()` engine
        (shares the immutable AnimData). `code2idx` = foot.ff._anim_idx in ANIM_ORDER."""
        from .anim_state import ANIM_CODE
        from .foot_fk import CHAIN_JOINTS, BODY_CO_EXTRA
        cdef int i, jnt
        if not self._fused_ready:
            self.init_anim(code2idx)
        st = foot.st
        ff = foot.ff
        self._sword = bool(foot.sword)      # carry the getAnmData WALKS/DASHS swap (see set_sword)
        self._defer_draw = bool(foot.defer_draw)     # and the end-of-frame draw base
        self._has_pd = False
        self._move0 = ANIM_CODE[st.move0]
        self._move1 = ANIM_CODE[st.move1] if st.move1 is not None else -1
        self._m34C3 = int(st.m34C3)
        self._a_ratio = float(st.ratio)
        self._m3598 = float(st.m3598)
        self._fc0_attr = int(st.fc0.attribute); self._fc0_start = float(st.fc0.start)
        self._fc0_end = float(st.fc0.end); self._fc0_loop = float(st.fc0.loop)
        self._fc0_rate = float(st.fc0.rate); self._fc0_frame = float(st.fc0.frame)
        self._fc1_attr = int(st.fc1.attribute); self._fc1_start = float(st.fc1.start)
        self._fc1_end = float(st.fc1.end); self._fc1_loop = float(st.fc1.loop)
        self._fc1_rate = float(st.fc1.rate); self._fc1_frame = float(st.fc1.frame)
        m = ff.morf
        self._m_counter = float(m.counter); self._m_f8 = float(m.f8); self._m_rate = float(m.rate)
        self._m_f10 = float(m.f10); self._m_f14 = float(m.f14)
        for i in range(12):
            jnt = CHAIN_JOINTS[i]
            if jnt in ff.old_quat:
                q = ff.old_quat[jnt]; t = ff.old_trans[jnt]; s = ff.old_scale[jnt]
                self._oldq[i][0] = q[0]; self._oldq[i][1] = q[1]
                self._oldq[i][2] = q[2]; self._oldq[i][3] = q[3]
                self._oldt[i][0] = t[0]; self._oldt[i][1] = t[1]; self._oldt[i][2] = t[2]
                self._olds[i][0] = s[0]; self._olds[i][1] = s[1]; self._olds[i][2] = s[2]
                self._has_old[i] = True
            else:
                self._has_old[i] = False
        # body_co extras (exec-pass centre): copy joints 2,3,4,14,15 -> body_co slots 0..4 from
        # the Python FootFK old-pose dicts, and arm `_body_co` so `_pose_toe_core` poses them each
        # frame. `ff.body_co` is False on the plain walk path -> the store stays inert.
        self._body_co = bool(getattr(ff, 'body_co', False))
        if self._body_co:
            for i in range(5):
                jnt = BODY_CO_EXTRA[i]
                if jnt in ff.old_quat:
                    q = ff.old_quat[jnt]; t = ff.old_trans[jnt]; s = ff.old_scale[jnt]
                    self._oldq_bc[i][0] = q[0]; self._oldq_bc[i][1] = q[1]
                    self._oldq_bc[i][2] = q[2]; self._oldq_bc[i][3] = q[3]
                    self._oldt_bc[i][0] = t[0]; self._oldt_bc[i][1] = t[1]; self._oldt_bc[i][2] = t[2]
                    self._olds_bc[i][0] = s[0]; self._olds_bc[i][1] = s[1]; self._olds_bc[i][2] = s[2]
                    self._has_old_bc[i] = True
                else:
                    self._has_old_bc[i] = False
        for i in range(12):
            self._t1[i] = float(foot.t1[i]); self._t2[i] = float(foot.t2[i])
        self._prev_f312 = float(foot.prev_f312); self._m35B4 = float(foot.m35B4)
        self._started = bool(foot.started); self._stopped = bool(foot.stopped)
        self._single_entered = bool(foot._single_entered)
        self._idle_frame = float(foot.idle_frame); self._idle_code = ANIM_CODE[foot.idle_anim]
        pm = foot._pending_morf
        if pm is None:
            self._has_pending = False
        else:
            self._pending_morf = float(pm); self._has_pending = True


# ---- posMoveFromFootPos composition (plant select + absXZ + smoothing + speedF) ---------------
cdef double _sqrtf_c(double x) noexcept nogil:
    """std::sqrtf: frsqrte seed + 3 Newton refines in f64, then f32(x*guess). Bit-exact core of
    foot_speedf._sqrtf (a math-accurate seed matches: 3 Newton steps wash out the crude frsqrte seed)."""
    x = f32(x)
    cdef double g
    if x > 0.0:
        g = 1.0 / _c_sqrt(x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        return f32(x * g)
    return f32(x)

cdef void _foot_compose_c(double* t1, double* t2, double nspeed, double msd, double m3598,
                          double prev_f312, double m35B4, double* out_speedF, double* out_f312) noexcept nogil:
    """posMoveFromFootPos toe->speedF core (d_a_player_main.cpp:2372+). t1/t2 = the flat 12-double
    toe arrays for the last two DRAWN frames. Writes speedF + f312. Bit-exact port of the tail of
    foot_speedf._foot_speedf (plant select on t1, 1-frame-delayed toe delta, recursive smoothing,
    speedF = nspeed*(1-m3598) +/- f31_2*m3598 with the |.|<0.05 -> 0 snap)."""
    cdef int plant = 0 if f32((t1[1] + t1[7]) * 0.5) < f32((t1[4] + t1[10]) * 0.5) else 1
    cdef int o = plant * 3
    cdef double dx = f32(t1[o + 0] - t2[o + 0])
    cdef double dz = f32(t1[o + 2] - t2[o + 2])
    cdef double f312 = _sqrtf_c(fmadds(dz, dz, fmuls(dx, dx)))
    cdef double dm = f32(m35B4 - msd)
    if dm < 0.0:
        dm = -dm
    if m3598 < 1.0 and dm < 0.2:
        f312 = fadds(fmuls(f312, f32(0.3)), fmuls(f32(0.7), prev_f312))
    cdef double spz = f32(nspeed * f32(1.0 - m3598))
    if nspeed >= 0.0:
        spz = f32(spz + f32(f312 * m3598))
    else:
        spz = f32(spz - f32(f312 * m3598))
    cdef double asp = spz if spz >= 0.0 else -spz
    out_speedF[0] = 0.0 if asp < 0.05 else spz
    out_f312[0] = f312

def foot_compose(t1, t2, double nspeed, double msd, double m3598, double prev_f312, double m35B4):
    """posMoveFromFootPos toe->speedF (d_a_player_main.cpp:2372+). t1/t2 are the flat 12-tuples from
    pose_toe for the last two DRAWN frames. Returns (speedF, f312)."""
    cdef double ct1[12]
    cdef double ct2[12]
    cdef int i
    for i in range(12):
        ct1[i] = t1[i]; ct2[i] = t2[i]
    cdef double speedF, f312
    _foot_compose_c(ct1, ct2, nspeed, msd, m3598, prev_f312, m35B4, &speedF, &f312)
    return (speedF, f312)


# ==== LAND manualCamera (cam_bezier) ============================================================
# Bit-exact port of the per-frame camera math (dCamMath::rationalBezierRatio + the manualCamera
# azimuth recompute + the substick PADClamp/normalize). Runs every frame; see cam_bezier.py.
cdef double _STICK_NRM = 0.0, _DEG2S16 = 0.0, _S162DEG = 0.0

def init_cam(stick_nrm, deg2s16, s162deg):
    """Receive the exact f32/double camera constants from cam_bezier (STICK_NRM is a specific DOL f32)."""
    global _STICK_NRM, _DEG2S16, _S162DEG
    _STICK_NRM = stick_nrm; _DEG2S16 = deg2s16; _S162DEG = s162deg

cdef inline long long _s16c(long long x) noexcept nogil:
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x

cdef void _clamp_stick_c(int x, int y, int min_, int max_, int xy, int* ox, int* oy) noexcept nogil:
    """PADClamp ClampStick (Padclamp.c): per-axis dead-zone (subtract min_) + octagonal clamp (points
    outside the octagon scaled onto its edge, each axis s8-truncated). x,y are s8 (raw byte - 128).
    Params: main stick min=15/max=72/xy=40; sub (C-stick) min=15/max=59/xy=31."""
    cdef int sx = 1 if x >= 0 else -1
    cdef int sy = 1 if y >= 0 else -1
    if x < 0: x = -x
    if y < 0: y = -y
    x = 0 if x <= min_ else x - min_
    y = 0 if y <= min_ else y - min_
    if x == 0 and y == 0:
        ox[0] = 0; oy[0] = 0; return
    cdef int d
    if xy * y <= xy * x:
        d = xy * x + (max_ - xy) * y
    else:
        d = xy * y + (max_ - xy) * x
    if xy * max_ < d:
        x = (xy * max_ * x) // d
        y = (xy * max_ * y) // d
    ox[0] = sx * x; oy[0] = sy * y

def cstick_normalize(csx, csy):
    """Raw C-stick bytes -> (mStickCPosX, mStickCPosY). Bit-exact port of cam_bezier.cstick_normalize."""
    cdef int px, py
    _clamp_stick_c(<int>csx - 128, <int>csy - 128, 15, 59, 31, &px, &py)
    cdef double posx = f32(px / 42.0)
    cdef double posy = f32(py / 42.0)
    cdef double val = f32(_c_sqrt(f32(posx * posx) + f32(posy * posy)))
    if val > 1.0:
        posx = f32(posx / val)
        posy = f32(posy / val)
    return (posx, posy)

cdef double _rbr_c(double p1, double p2) noexcept nogil:
    """dCamMath::rationalBezierRatio (double math, single-rounded result). Core of rationalBezierRatio."""
    cdef double sign = 1.0
    if p1 < 0.0:
        sign = -1.0; p1 = -p1
    cdef double dVar4 = (2.0 * p1 * p2 - 2.0 * p1) - 2.0 * p2
    cdef double dVar3 = -dVar4 - 1.0
    cdef double dVar5 = dVar4 * dVar4 - 4.0 * dVar3 * p1
    cdef double sq = _c_sqrt(dVar5) if dVar5 > 0.0 else 0.0
    cdef double num = -dVar4 - sq
    cdef double denom0 = 2.0 * dVar3
    if denom0 <= 1e-7 and denom0 >= -1e-7:
        return 0.0
    cdef double t = num / denom0
    cdef double tt = t * t
    cdef double om = 1.0 - t
    cdef double bez_denom = tt + (om * om + p2 * (2.0 * om * t))
    if bez_denom <= 1.00000001168610e-7:
        return 0.0
    return f32(sign * (tt / bez_denom))

def cam_step_target(cam_target_s16, stick_x, scale):
    """One manualCamera azimuth update -> new cam_target (s16). Bit-exact port of step_cam_target."""
    cdef double sx = stick_x, sc = scale, ratio
    if sx >= 0.75:
        ratio = 1.0
    elif sx <= -0.75:
        ratio = -1.0
    else:
        ratio = _rbr_c(f32(_STICK_NRM * sx), 2.0)
    cdef double cur_deg = f32(_S162DEG * <double>_s16c(<long long>cam_target_s16))
    cdef double inc_deg = f32(ratio * sc)
    cdef double total = f32(cur_deg + inc_deg)
    cdef long long new = <long long>(f32(_DEG2S16 * total))       # fctiwz: trunc toward zero
    return new & 0xFFFF


# ==== LAND physics core (LandState port) ========================================================
# Bit-exact port of the tww_sim.land.LandState per-frame step (dispatch + stick decode + the two-angle
# chase + checkNextMode + the turn/roll/slip procs + camera + position integration). Owns the physics
# state in C and drives the shared PoseEngine for speedF; LandState delegates step() here when the fused
# engine is present, syncing output fields back for tests/planners. The pure-Python LandState body stays
# as the bit-identical fallback (proven by the perf_land fingerprint with the .pyd hidden).
# link_state / daPyProc + mDirection enums (mirror land.py).
DEF LS_SUBJECTIVITY=1
DEF LS_WAIT=4
DEF LS_FREE_WAIT=5
DEF LS_MOVE=6
DEF LS_ATN_MOVE=7
DEF LS_ATN_ACTOR_WAIT=8
DEF LS_ATN_ACTOR_MOVE=9
DEF LS_WAIT_TURN=23
DEF LS_MOVE_TURN=24
DEF LS_SLIP=25
DEF LS_FRONT_ROLL=30
DEF LS_CUT_A=0x41
DEF LS_CUT_F=0x42
DEF LD_FORWARD=0
DEF LD_BACKWARD=1
DEF LD_LEFT=2
DEF LD_RIGHT=3
DEF LD_NONE=4

# math.degrees factor: x * (180.0 / pi) in double, exactly as CPython math_degrees.
DEF _DEG_PER_RAD = 57.29577951308232

# C-up-cancel (subjectivity freeze) input gates -- mirror land.py CUP_POSY / CUP_MAIN_MAX / C-DOWN.
# AttentionLock / atn_actor: NONE/LOCK/RELEASE + the front-of-player cone
# (attention.py FRONT_CONE_HALF) + setShapeAngleToAtnActor's cLib_addCalcAngleS knobs (2629).
DEF _ATN_NONE=0
DEF _ATN_LOCK=1
DEF _ATN_RELEASE=2
DEF _ATN_FRONT_CONE_HALF=0x4000
DEF _ATN_SHAPE_SCALE=2
DEF _ATN_SHAPE_MAX=0x2000
DEF _ATN_SHAPE_MIN=0x800
DEF _CUP_POSY = 0.5
DEF _CUP_MAIN_MAX = 0.5
DEF _CDOWN_POSY = -0.74
DEF _SUBJ_CAM_FLOOR = 9
DEF _CDOWN_RUN = 3

# HIO tuning constants copied from LandState (one canonical source) via land_init_consts.
cdef double _L_MAX_NSPEED, _L_F14, _L_F1C, _L_F20, _L_F24
cdef long long _L_F0, _L_F4, _L_F6
cdef double _L_ATN_MAX, _L_ATN_SPD, _L_ATN_ACC, _L_ATN_DEC, _L_ATN_SCL
cdef long long _L_ATN_TURN_MAX, _L_ATN_TURN_MIN, _L_ATN_TURN_SCALE
cdef double _L_ATNB_MAX, _L_ATNB_SPD, _L_ATNB_ACC, _L_ATNB_DEC, _L_ATNB_SCL
cdef double _L_ATNB_COS_FWD, _L_ATNB_COS_BACK
cdef double _L_ROLL_SPD, _L_ROLL_ADD, _L_ROLL_MIN, _L_ROLL_END, _L_ROLL_RATE
cdef double _L_ROLL_ENTRY_MORF, _L_MOVE_REENTRY_MORF, _L_ROLL_EARLY, _L_ATTACK_MSD_MIN
cdef long long _L_TURN_MAX, _L_TURN_MIN, _L_TURN_SCALE
cdef double _L_WAIT_TURN_ANIM_RATE
cdef double _L_SLIP_THRESH, _L_SLIP_ENTRY, _L_SLIP_DEC_SCALE, _L_SLIP_DEC_MAX, _L_SLIP_DEC_MIN
cdef double _L_SLIP_ANIM_RATE, _L_SLIP_MORF, _L_MT_SLIP_SEED
# the sword-thrust cut (hio.py CUT_*): the per-type fields are indexed [0]=CUT_F, [1]=CUT_A.
cdef double _L_CUT_RATE, _L_CUT_START, _L_CUT_END, _L_CUT_PASS, _L_CUT_LAUNCH_MUL
cdef double _L_CUT_DEC_SCALE, _L_CUT_DEC_MIN
cdef double _L_CUT_EARLY[2]
cdef double _L_CUT_LAUNCH_ADD[2]
cdef double _L_CUT_DEC_MAX[2]
cdef long long _L_CUT_TURN_SCALE, _L_CUT_TURN_MAX, _L_CUT_TURN_MIN
# the roll bonk window (hio.py ROLL_BONK_*): read only to REFUSE the unported crash proc.
cdef long long _L_ROLL_BONK_ANGLE
cdef double _L_ROLL_BONK_FMIN, _L_ROLL_BONK_FMAX, _L_ROLL_BONK_SPEED
cdef bint _LAND_CONSTS_READY = False


cdef inline int _cut_slot(int cut_type) noexcept nogil:
    """[0] for CUT_F, [1] for CUT_A -- the C form of hio.py's per-cut-type dicts."""
    return 1 if cut_type == LS_CUT_A else 0


def land_init_consts(c):
    """Copy the LandState HIO/tuning constants into C module globals (idempotent). `c` is a dict built
    from the LandState class attributes so the values stay single-sourced in land.py."""
    global _L_MAX_NSPEED, _L_F14, _L_F1C, _L_F20, _L_F24, _L_F0, _L_F4, _L_F6
    global _L_ATN_MAX, _L_ATN_SPD, _L_ATN_ACC, _L_ATN_DEC, _L_ATN_SCL
    global _L_ATN_TURN_MAX, _L_ATN_TURN_MIN, _L_ATN_TURN_SCALE
    global _L_ATNB_MAX, _L_ATNB_SPD, _L_ATNB_ACC, _L_ATNB_DEC, _L_ATNB_SCL
    global _L_ATNB_COS_FWD, _L_ATNB_COS_BACK
    global _L_ROLL_SPD, _L_ROLL_ADD, _L_ROLL_MIN, _L_ROLL_END, _L_ROLL_RATE
    global _L_ROLL_ENTRY_MORF, _L_MOVE_REENTRY_MORF, _L_ROLL_EARLY, _L_ATTACK_MSD_MIN
    global _L_TURN_MAX, _L_TURN_MIN, _L_TURN_SCALE, _L_WAIT_TURN_ANIM_RATE
    global _L_SLIP_THRESH, _L_SLIP_ENTRY, _L_SLIP_DEC_SCALE, _L_SLIP_DEC_MAX, _L_SLIP_DEC_MIN
    global _L_SLIP_ANIM_RATE, _L_SLIP_MORF, _L_MT_SLIP_SEED, _LAND_CONSTS_READY
    global _L_CUT_RATE, _L_CUT_START, _L_CUT_END, _L_CUT_PASS, _L_CUT_LAUNCH_MUL
    global _L_CUT_DEC_SCALE, _L_CUT_DEC_MIN
    global _L_CUT_TURN_SCALE, _L_CUT_TURN_MAX, _L_CUT_TURN_MIN
    global _L_ROLL_BONK_ANGLE, _L_ROLL_BONK_FMIN, _L_ROLL_BONK_FMAX, _L_ROLL_BONK_SPEED
    _L_MAX_NSPEED = c['MAX_NSPEED']; _L_F14 = c['F14']; _L_F1C = c['F1C']; _L_F20 = c['F20']
    _L_F24 = c['F24']; _L_F0 = c['F0']; _L_F4 = c['F4']; _L_F6 = c['F6']
    _L_ATN_MAX = c['ATN_MAX']; _L_ATN_SPD = c['ATN_SPD']; _L_ATN_ACC = c['ATN_ACC']
    _L_ATN_DEC = c['ATN_DEC']; _L_ATN_SCL = c['ATN_SCL']
    _L_ATN_TURN_MAX = c['ATN_TURN_MAX']; _L_ATN_TURN_MIN = c['ATN_TURN_MIN']
    _L_ATN_TURN_SCALE = c['ATN_TURN_SCALE']
    _L_ATNB_MAX = c['ATNB_MAX']; _L_ATNB_SPD = c['ATNB_SPD']; _L_ATNB_ACC = c['ATNB_ACC']
    _L_ATNB_DEC = c['ATNB_DEC']; _L_ATNB_SCL = c['ATNB_SCL']
    _L_ATNB_COS_FWD = c['ATNB_COS_FWD']; _L_ATNB_COS_BACK = c['ATNB_COS_BACK']
    _L_ROLL_SPD = c['ROLL_SPD']; _L_ROLL_ADD = c['ROLL_ADD']; _L_ROLL_MIN = c['ROLL_MIN']
    _L_ROLL_END = c['ROLL_END']; _L_ROLL_RATE = c['ROLL_RATE']
    _L_ROLL_ENTRY_MORF = c['ROLL_ENTRY_MORF']; _L_MOVE_REENTRY_MORF = c['MOVE_REENTRY_MORF']
    _L_ROLL_EARLY = c['ROLL_EARLY']; _L_ATTACK_MSD_MIN = c['ATTACK_MSD_MIN']
    _L_TURN_MAX = c['TURN_MAX']; _L_TURN_MIN = c['TURN_MIN']; _L_TURN_SCALE = c['TURN_SCALE']
    _L_WAIT_TURN_ANIM_RATE = c['WAIT_TURN_ANIM_RATE']
    _L_SLIP_THRESH = c['SLIP_THRESH']; _L_SLIP_ENTRY = c['SLIP_ENTRY']
    _L_SLIP_DEC_SCALE = c['SLIP_DEC_SCALE']; _L_SLIP_DEC_MAX = c['SLIP_DEC_MAX']
    _L_SLIP_DEC_MIN = c['SLIP_DEC_MIN']; _L_SLIP_ANIM_RATE = c['SLIP_ANIM_RATE']
    _L_SLIP_MORF = c['SLIP_MORF']; _L_MT_SLIP_SEED = c['MT_SLIP_SEED']
    # the cut: scalars, then the two per-type dicts flattened onto [CUT_F, CUT_A] slots.
    _L_CUT_RATE = c['CUT_RATE']; _L_CUT_START = c['CUT_START']; _L_CUT_END = c['CUT_END']
    _L_CUT_PASS = c['CUT_PASS']; _L_CUT_LAUNCH_MUL = c['CUT_LAUNCH_MUL']
    _L_CUT_DEC_SCALE = c['CUT_DEC_SCALE']; _L_CUT_DEC_MIN = c['CUT_DEC_MIN']
    _L_CUT_TURN_SCALE = c['CUT_TURN_SCALE']; _L_CUT_TURN_MAX = c['CUT_TURN_MAX']
    _L_CUT_TURN_MIN = c['CUT_TURN_MIN']
    _L_CUT_EARLY[0] = c['CUT_EARLY'][LS_CUT_F]; _L_CUT_EARLY[1] = c['CUT_EARLY'][LS_CUT_A]
    _L_CUT_LAUNCH_ADD[0] = c['CUT_LAUNCH_ADD'][LS_CUT_F]
    _L_CUT_LAUNCH_ADD[1] = c['CUT_LAUNCH_ADD'][LS_CUT_A]
    _L_CUT_DEC_MAX[0] = c['CUT_DEC_MAX'][LS_CUT_F]; _L_CUT_DEC_MAX[1] = c['CUT_DEC_MAX'][LS_CUT_A]
    _L_ROLL_BONK_ANGLE = c['ROLL_BONK_ANGLE']; _L_ROLL_BONK_FMIN = c['ROLL_BONK_FMIN']
    _L_ROLL_BONK_FMAX = c['ROLL_BONK_FMAX']; _L_ROLL_BONK_SPEED = c['ROLL_BONK_SPEED']
    _LAND_CONSTS_READY = True


cdef double _clib_addcalc(double value, double target, double scale,
                          double max_step, double min_step) noexcept nogil:
    """mathlib.cLib_addCalc (f32 chase). Bit-exact port."""
    if value == target:
        return value
    cdef double step = f32(scale * f32(target - value))
    cdef double nv, ms
    if step >= min_step or step <= -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        return f32(value + step)
    if step > 0.0:
        if step < min_step:
            nv = f32(value + min_step)
            return target if nv > target else nv
    else:
        ms = -min_step
        if step > ms:
            nv = f32(value + ms)
            return target if nv < target else nv
    return value


cdef long long _clib_addcalc_angles(long long value, long long target, long long scale,
                                    long long max_step, long long min_step) noexcept nogil:
    """land.cLib_addCalcAngleS (s16 integer chase). Bit-exact port; C int division truncates toward
    zero (cdivision) == Python int(diff / scale)."""
    value &= 0xFFFF
    target &= 0xFFFF
    if value == target:
        return value
    cdef long long diff = _s16c(target - value)
    cdef long long step = diff / scale
    cdef long long nv
    if step > min_step or step < -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        return (value + step) & 0xFFFF
    if diff >= 0:
        nv = (value + min_step) & 0xFFFF
        return target if _s16c(target - nv) <= 0 else nv
    else:
        nv = (value - min_step) & 0xFFFF
        return target if _s16c(target - nv) >= 0 else nv


cdef long long _cam_step_target_c(long long cam_target, double stick_x, double scale) noexcept nogil:
    """cam_bezier.step_cam_target core (one manualCamera azimuth update)."""
    cdef double ratio
    if stick_x >= 0.75:
        ratio = 1.0
    elif stick_x <= -0.75:
        ratio = -1.0
    else:
        ratio = _rbr_c(f32(_STICK_NRM * stick_x), 2.0)
    cdef double cur_deg = f32(_S162DEG * <double>_s16c(cam_target))
    cdef double inc_deg = f32(ratio * scale)
    cdef double total = f32(cur_deg + inc_deg)
    cdef long long new = <long long>(f32(_DEG2S16 * total))
    return new & 0xFFFF


cdef double _cstick_posx_c(int csx, int csy) noexcept nogil:
    """cam_bezier.cstick_normalize -> mStickCPosX only (the camera yaw command needs just X)."""
    cdef int px, py
    _clamp_stick_c(csx - 128, csy - 128, 15, 59, 31, &px, &py)
    cdef double posx = f32(px / 42.0)
    cdef double posy = f32(py / 42.0)
    cdef double val = f32(_c_sqrt(f32(posx * posx) + f32(posy * posy)))
    if val > 1.0:
        posx = f32(posx / val)
    return posx


cdef double _cstick_posy_c(int csx, int csy) noexcept nogil:
    """cam_bezier.cstick_normalize -> mStickCPosY only (the C-up-cancel subjectivity gesture)."""
    cdef int px, py
    _clamp_stick_c(csx - 128, csy - 128, 15, 59, 31, &px, &py)
    cdef double posx = f32(px / 42.0)
    cdef double posy = f32(py / 42.0)
    cdef double val = f32(_c_sqrt(f32(posx * posx) + f32(posy * posy)))
    if val > 1.0:
        posy = f32(posy / val)
    return posy


# Tetra's look-at head + Link's neck, resident in C -- the two models that generate the proc-9
# re-aim eye, and most of a coupled step's cost. Kept in its own file because
# it is a distinct subsystem, `include`d rather than imported because `LandCore` runs it INSIDE
# the coupled step and so needs its C state in this translation unit.
include "_zl1c.pxi"
# dBgS_Acch::CrrPos (both actors' BG wall pass) -- same reason: the coupled step braces Link
# and Tetra INSIDE the frame, so the collision core has to be nogil C in this translation unit.
include "_acchc.pxi"


cdef class CutAnimData:
    """The ANM_CUT root-motion tracks: joint 0's three TRANSLATE keyframe tracks for cutf and cuta.

    That joint-0 translate IS the thrust's lunge (`m3700`; posMove reads getAnmTransform(0) and MOVE1
    is NULL for a setSingleMoveAnime cut, so there is no blend) -- the 23.22 u the roll-stab stacks on
    top of the carried speedF. Only joint 0 and only translate: nothing else in the cut BCK moves
    position, and the cut poses no foot chain (`land/procs/cut.py`).

    Built once from `core.anim.j3d_eval.load_anim(_generated/anim/link_anim_cuts.json)`, then IMMUTABLE
    -- so a `LandCore.clone()` shares it by reference and a parallel fan-out reads it per thread.
    Slots follow `_cut_slot`: [0] = CUT_F, [1] = CUT_A."""
    cdef double* _t[2]
    cdef int _cnt[2][3]
    cdef int _off[2][3]
    cdef int _tt[2][3]

    def __cinit__(self, cutf, cuta):
        cdef int s, ax, n
        for s in range(2):
            self._t[s] = NULL
        for s in range(2):
            anm = cutf if s == 0 else cuta
            td = anm['trans_data']
            n = len(td)
            self._t[s] = <double*>malloc(n * sizeof(double))
            if self._t[s] == NULL:
                raise MemoryError()
            for ax in range(n):
                self._t[s][ax] = td[ax]
            trk = anm['joints'][0]['t']
            for ax in range(3):
                self._cnt[s][ax] = int(trk[ax][0])
                self._off[s][ax] = int(trk[ax][1])
                self._tt[s][ax] = int(trk[ax][2])

    def __dealloc__(self):
        cdef int s
        for s in range(2):
            free(self._t[s])

    def m3700_at(self, int cut_type, double frame):
        """`land.procs.cut._cut_m3700_at` -- the leaf the 0-ULP gate diffs against the Python eval."""
        cdef double out[3]
        _cut_m3700_c(self, _cut_slot(cut_type), frame, out)
        return (out[0], out[1], out[2])


cdef void _cut_m3700_c(CutAnimData d, int slot, double frame, double* out) noexcept nogil:
    """m3700 = the CUT anim's joint-0 root mTranslate at `frame` (J3DAnmTransformKey::calcTransform's
    translate arm for one joint). Twin of `_CutMixin._cut_m3700_at`."""
    cdef int ax, cnt
    for ax in range(3):
        cnt = d._cnt[slot][ax]
        if cnt == 0:
            out[ax] = 0.0
        elif cnt == 1:
            out[ax] = f32(d._t[slot][d._off[slot][ax]])
        else:
            out[ax] = f32(_keyframe_interp_c(frame, cnt, d._tt[slot][ax], d._t[slot],
                                             d._off[slot][ax], 0))


cdef class LandCore:
    """C-resident LandState physics engine. Holds a reference to the shared PoseEngine (for speedF) and
    owns all per-frame physics/stick/camera state. `setup` seeds it; `step` advances one frame and
    returns speedF; the caller (land.LandState) reads the public fields to sync + build the state tag.

    COUPLED-ACTOR SURFACE, RESIDENT BUT NOT DISPATCHED. The cut arm (`_cut_init`/`_proc_cut`,
    CutAnimData), the BG wall pass for both actors (`_acchc.pxi`, `seed_walls`, `_link_wall_pass`,
    `_tetra_wall_pass`), the look pair (`_zl1c.pxi`, `seed_look`) and the attention update
    (`_atn_update`) are all here and complete, but `step` calls NONE of them: the frame that drove
    them was a route-search step that has been removed. So a native-only run does not cut and has no
    wall pass. The pure-Python path in `land/` models all of it and is what the seam-clip solver
    actually runs (every `harness/rollstab` entry point builds `LandState(native=False)`). Giving
    this surface a general public driver is a behaviour change wanting live re-validation, not a
    refactor -- do not wire it silently."""
    cdef PoseEngine _pe
    cdef public double pos_x, pos_z
    cdef public long long facing, travel, csangle
    cdef public long long m34E6, m34dc, m34ea, m34de, target, turn_target
    cdef public long long turn_shape_scale, turn_shape_max, turn_shape_min
    cdef public int state, direction
    cdef public double nspeed, speedF, msd, max_nspeed, roll_frame
    cdef public bint _roll_entered, _l_prev
    cdef public bint _init_frame            # last step DISPATCHED a proc *_init (zero-lean base)
    cdef public bint _subj_arm, _subj_ended
    cdef int _abtn_prev, _subj_frames, _cdown_run
    cdef double _anim_nspeed
    cdef bint _has_anim_nspeed
    cdef int _inbuf[2][6]
    cdef long long _cam_yaw, _cam_target
    cdef double _cam_scale, _cam_pending_posx
    # --- Coupled-actor state: CC push pair, actor lock, look pair, cut. A caller seeds these; the
    cdef public double pos_y                # Link world Y (constant in the push window; base rounding)
    cdef public double m351C                # setMoveSlantAngle lean state (s16 stored as double)
    cdef public double _draw_lean_c         # shape_angle.z at draw (s16(m351C)>>1)
    cdef public int _atn_state              # AttentionLock.state: 0 NONE / 1 LOCK / 2 RELEASE
    cdef int _atn_fade, _atn_fade_frames    # RELEASE reticle-fade timer
    cdef bint _atn_l_prev                    # AttentionLock's own prev-frame L (rising edge)
    cdef public bint _atn_list_present      # GetLockonList(0) != NULL
    cdef public double _tetra_x, _tetra_z   # tracked Tetra feet XZ (f32 point)
    cdef double _atn_eye_x, _atn_eye_z      # proc-9 re-aim target (Tetra eyePos XZ; injected)
    cdef bint _has_eye
    cdef public double _pend_link_x, _pend_link_z  # Link CC recoil for THIS frame (posMove consume)
    cdef public double _pend_tetra_x, _pend_tetra_z # Tetra CC push for THIS frame (matched pair)
    cdef int _cbuf[6]                       # delay-1 pending controller input
    cdef bint _has_cbuf
    cdef public bint _actor_locked           # mpAttnActorLockOn != NULL; a caller arms it (see step)
    cdef public bint low_life               # checkRestHPAnime's life half (seeded; wait-stop-pose.md)
    # --- the look pair, run INSIDE the frame (session 128): her Zl1Look + Link's NeckLook ---
    cdef Zl1LookCore _zl1
    cdef NeckLookCore _neck
    cdef bint _has_look                     # both wired -> the step generates its own proc-9 eye
    cdef public double _tetra_y             # her world Y (setMtx/setAttention; constant here)
    # --- the sword-thrust cut (CUT_F/CUT_A): the roll's b_trig arm and the root-translate lunge ---
    cdef public double cut_frame            # ANM_CUT MOVE0 frame ctrl (starts at CUT_START)
    cdef long long cut_target               # mProcVar2.m34D4 (the latched diagonal aim)
    cdef bint _has_cut_target
    cdef double _cut_m3700[3]               # previous frame's joint-0 root translate
    cdef double _cut_add_x, _cut_add_z      # THIS frame's rotated root-translate delta
    cdef public bint sword_drawn            # gates the roll->cut hand-off (seeded)
    cdef public bint _b_trig                # swordTrigger(): B mItemTrigger RISING EDGE this frame
    cdef CutAnimData _cutanm                # joint-0 translate tracks (immutable, shared on clone)
    cdef bint _has_cutanm
    # --- dBgS_Acch::CrrPos, both actors (session 150): the BG wall pass INSIDE the frame ---
    cdef WallMesh _lwalls                   # Link's mAcch mesh (NULL/None = no pass)
    cdef WallMesh _twalls                   # Tetra's mObjAcch mesh
    cdef bint _has_lwalls, _has_twalls
    cdef double _lwh[8]                     # Link's wall cylinder heights
    cdef int _lnh
    cdef double _lwr, _lgravity             # Link's wall radius + the CrrPos-time speed.y dip
    cdef double _twh[8]                     # Tetra's (her R 50 / half-H 30 cylinder)
    cdef int _tnh
    cdef double _twr
    cdef public bint wall_hit               # mAcch.ChkWallHit() -- LAST frame's CrrPos, Link
    cdef public bint line_hit               # LINE_CHECK_HIT (diagnostic; the Python twin's info key)
    cdef bint _wall_cir_hit[8]              # SetWallCirHit per cylinder
    cdef long long _wall_angle[8]           # SetWallAngleY per cylinder
    cdef public bint _roll_m3570            # the roll's grind latch (6838)
    # Sticky refusals: a case the C step CANNOT model. The nogil frame can only raise a flag; the
    # GIL-holding caller (`FreeRun._step_native` via `wall_check`) turns it into an exception, so an
    # unported branch REFUSES instead of silently running the wrong proc.
    cdef public bint bonk_unmodelled        # the roll bonk fired -> procFrontRollCrash, unported
    cdef public bint sidle_unmodelled       # the A-press was a SIDLE, not a roll -- unported

    @property
    def pe_phase(self):
        """The shared PoseEngine's anim-phase fingerprint (diagnostic; see PoseEngine.phase)."""
        return self._pe.phase

    @property
    def pe(self):
        """The bound PoseEngine (read-only). Lets a Python owner clone the fused engine for a
        bit-exact `LandCore.clone(pe.clone_state())` (the FreeRun native-step beam-search clone)."""
        return self._pe

    def setup(self, PoseEngine pe, double pos_x, double pos_z, long long facing,
              long long travel, long long csangle, int state, double nspeed,
              double speedF, double cam_scale):
        cdef int i, j
        self._pe = pe
        self.pos_x = pos_x
        self.pos_z = pos_z
        self.facing = facing & 0xFFFF
        self.travel = travel & 0xFFFF
        self.csangle = csangle & 0xFFFF
        self.state = state
        self.nspeed = f32(nspeed)
        self.speedF = f32(speedF)
        self.msd = 0.0
        self.max_nspeed = _L_MAX_NSPEED
        self.direction = LD_NONE
        self.m34E6 = facing & 0xFFFF
        self.m34dc = facing & 0xFFFF
        self.m34ea = facing & 0xFFFF
        self.m34de = facing & 0xFFFF
        self.target = 0
        self.turn_target = 0
        self.turn_shape_scale = 0
        self.turn_shape_max = 0
        self.turn_shape_min = 0
        self.roll_frame = 0.0
        self._roll_entered = False
        self._l_prev = False
        self._subj_arm = False
        self._subj_ended = False
        self._subj_frames = 0
        self._cdown_run = 0
        self._abtn_prev = 0
        self._anim_nspeed = 0.0
        self._has_anim_nspeed = False
        for i in range(2):
            self._inbuf[i][0] = 128; self._inbuf[i][1] = 128; self._inbuf[i][2] = 0
            self._inbuf[i][3] = 0; self._inbuf[i][4] = 128; self._inbuf[i][5] = 128
        self._cam_yaw = (self.csangle - 0x8000) & 0xFFFF
        self._cam_target = (self._cam_yaw - 1) & 0xFFFF
        self._cam_scale = cam_scale
        self._cam_pending_posx = 0.0
        # Coupled-actor state (inert unless a caller drives it):
        self.pos_y = 0.0
        self.m351C = 0.0
        self._draw_lean_c = 0.0
        self._atn_state = _ATN_NONE
        self._atn_fade = 0
        self._atn_fade_frames = 10
        self._atn_l_prev = False
        self._atn_list_present = False
        self._tetra_x = 0.0; self._tetra_z = 0.0
        self._atn_eye_x = 0.0; self._atn_eye_z = 0.0
        self._has_eye = False
        self._pend_link_x = 0.0; self._pend_link_z = 0.0
        self._pend_tetra_x = 0.0; self._pend_tetra_z = 0.0
        self._has_cbuf = False
        self._actor_locked = False
        self.low_life = False
        self._zl1 = None
        self._neck = None
        self._has_look = False
        self._tetra_y = 0.0
        # cut state (inert until a roll's b_trig arm dispatches one)
        self.cut_frame = 0.0
        self.cut_target = 0
        self._has_cut_target = False
        self._cut_m3700[0] = 0.0; self._cut_m3700[1] = 0.0; self._cut_m3700[2] = 0.0
        self._cut_add_x = 0.0; self._cut_add_z = 0.0
        self.sword_drawn = False
        self._b_trig = False
        self._cutanm = None
        self._has_cutanm = False
        # BG wall pass (inert until seed_walls)
        self._lwalls = None; self._twalls = None
        self._has_lwalls = False; self._has_twalls = False
        self._lnh = 0; self._tnh = 0
        self._lwr = 0.0; self._lgravity = 0.0; self._twr = 0.0
        self.wall_hit = False
        self.line_hit = False
        self._roll_m3570 = False
        self.bonk_unmodelled = False
        self.sidle_unmodelled = False
        for i in range(8):
            self._lwh[i] = 0.0; self._twh[i] = 0.0
            self._wall_cir_hit[i] = False; self._wall_angle[i] = 0
        for i in range(6):
            self._cbuf[i] = 128 if i == 0 or i == 1 or i == 4 or i == 5 else 0

    def clone(self, PoseEngine new_pe):
        """Clone over a caller-supplied PoseEngine (a state-copy of the source engine, via
        PoseEngine.clone_state). Copies all physics + camera state; bit-exact even MID-WALK now that
        the engine carries its own toe stream. See land.LandState.clone."""
        cdef LandCore c = LandCore.__new__(LandCore)
        cdef int i, j
        c._pe = new_pe
        c.pos_x = self.pos_x; c.pos_z = self.pos_z
        c.facing = self.facing; c.travel = self.travel; c.csangle = self.csangle
        c.m34E6 = self.m34E6; c.m34dc = self.m34dc; c.m34ea = self.m34ea
        c.m34de = self.m34de; c.target = self.target; c.turn_target = self.turn_target
        c.turn_shape_scale = self.turn_shape_scale; c.turn_shape_max = self.turn_shape_max
        c.turn_shape_min = self.turn_shape_min
        c.state = self.state; c.direction = self.direction
        c.nspeed = self.nspeed; c.speedF = self.speedF; c.msd = self.msd
        c.max_nspeed = self.max_nspeed; c.roll_frame = self.roll_frame
        c._roll_entered = self._roll_entered; c._l_prev = self._l_prev
        c._subj_arm = self._subj_arm; c._subj_ended = self._subj_ended
        c._abtn_prev = self._abtn_prev; c._subj_frames = self._subj_frames; c._cdown_run = self._cdown_run
        c._anim_nspeed = self._anim_nspeed; c._has_anim_nspeed = self._has_anim_nspeed
        for i in range(2):
            for j in range(6):
                c._inbuf[i][j] = self._inbuf[i][j]
        c._cam_yaw = self._cam_yaw; c._cam_target = self._cam_target
        c._cam_scale = self._cam_scale; c._cam_pending_posx = self._cam_pending_posx
        # coupled-actor state
        c.pos_y = self.pos_y; c.m351C = self.m351C; c._draw_lean_c = self._draw_lean_c
        c._atn_state = self._atn_state; c._atn_fade = self._atn_fade
        c._atn_fade_frames = self._atn_fade_frames; c._atn_l_prev = self._atn_l_prev
        c._atn_list_present = self._atn_list_present
        c._tetra_x = self._tetra_x; c._tetra_z = self._tetra_z
        c._atn_eye_x = self._atn_eye_x; c._atn_eye_z = self._atn_eye_z; c._has_eye = self._has_eye
        c._pend_link_x = self._pend_link_x; c._pend_link_z = self._pend_link_z
        c._pend_tetra_x = self._pend_tetra_x; c._pend_tetra_z = self._pend_tetra_z
        c._actor_locked = self._actor_locked; c._has_cbuf = self._has_cbuf
        c.low_life = self.low_life
        # the look pair: each clones its own state (the fan branches a node into an aim fan).
        c._zl1 = self._zl1.clone() if self._zl1 is not None else None
        c._neck = self._neck.clone() if self._neck is not None else None
        c._has_look = self._has_look
        c._tetra_y = self._tetra_y
        # cut state; the keyframe tracks are immutable dev data -> shared by reference
        c.cut_frame = self.cut_frame; c.cut_target = self.cut_target
        c._has_cut_target = self._has_cut_target
        c._cut_m3700[0] = self._cut_m3700[0]; c._cut_m3700[1] = self._cut_m3700[1]
        c._cut_m3700[2] = self._cut_m3700[2]
        c._cut_add_x = self._cut_add_x; c._cut_add_z = self._cut_add_z
        c.sword_drawn = self.sword_drawn; c._b_trig = self._b_trig
        c._cutanm = self._cutanm; c._has_cutanm = self._has_cutanm
        # BG wall pass: the meshes are immutable -> shared by reference (the AnimData contract)
        c._lwalls = self._lwalls; c._twalls = self._twalls
        c._has_lwalls = self._has_lwalls; c._has_twalls = self._has_twalls
        c._lnh = self._lnh; c._tnh = self._tnh
        c._lwr = self._lwr; c._lgravity = self._lgravity; c._twr = self._twr
        c.wall_hit = self.wall_hit
        c.line_hit = self.line_hit
        c._roll_m3570 = self._roll_m3570
        c.bonk_unmodelled = self.bonk_unmodelled
        c.sidle_unmodelled = self.sidle_unmodelled
        for j in range(8):
            c._lwh[j] = self._lwh[j]; c._twh[j] = self._twh[j]
            c._wall_cir_hit[j] = self._wall_cir_hit[j]; c._wall_angle[j] = self._wall_angle[j]
        for j in range(6):
            c._cbuf[j] = self._cbuf[j]
        return c

    # --- SUBJECTIVITY freeze (chained-freeze tech); mirrors LandState.enter_freeze/hold_freeze/resume_walk.
    def enter_freeze(self):
        """procSubjectivity_init: mNormalSpeed=0 (freeze) + the WAITS/WALK idle blend (phase preserved)."""
        self.nspeed = 0.0
        self.speedF = 0.0
        self.state = LS_SUBJECTIVITY
        self._pe.w_enter_subjectivity(self.msd, _L_MOVE_REENTRY_MORF)

    def hold_freeze(self):
        """One SUBJECTIVITY / post-B WAIT hold frame: position frozen, the WAITS anim advances."""
        self.speedF = 0.0
        self._pe.w_step_subjectivity(self.msd)

    def resume_walk(self):
        """procMove_init on WAIT->MOVE: setBlendMoveAnime preserves the carried WAITS phase (m34C3=2)."""
        self.state = LS_MOVE
        self.nspeed = 0.0
        self._pe.w_set_pending(_L_MOVE_REENTRY_MORF)

    # --- stick layer (setStickData, 10530) ---
    cdef void _set_stick_data(self, int sx, int sy) noexcept nogil:
        # Faithful PADClamp octagon clamp + JUTGamePad::CStick::update (STICK_MODE_1). Bit-exact twin
        # of mathlib.main_stick_decode: msd = min(hypot(clamped)/54, 1) (f64, on-axis == the old naive
        # value); angle = (s16)(10430.379f * atan2f(mPosX, -mPosY)) on the CLAMPED+normalized vector.
        cdef int cx, cy
        _clamp_stick_c(sx - 128, sy - 128, 15, 72, 40, &cx, &cy)
        cdef double mag = _c_hypot(<double>cx, <double>cy) / 54.0
        if mag > 1.0:
            mag = 1.0
        self.msd = mag
        cdef double px, py, value
        cdef long long ang
        if mag <= 0.05:
            self.target = self.travel
        else:
            px = f32(cx / 54.0)
            py = f32(cy / 54.0)
            value = f32(_c_sqrt(f32(f32(px * px) + f32(py * py))))
            if value > 1.0:
                px = f32(px / value)
                py = f32(py / value)
            if py == 0.0:
                ang = 0x4000 if px > 0.0 else 0xC000
            else:
                ang = (<long long>f32(f32(10430.379) * f32(_c_atan2(px, -py)))) & 0xFFFF
            self.m34dc = (ang + 0x8000) & 0xFFFF
            self.target = (self.m34dc + self.csangle) & 0xFFFF

    cdef inline int _get_dir(self, long long angle) noexcept nogil:
        cdef long long a = _s16c(angle)
        cdef long long aa = a if a >= 0 else -a
        if aa > 0x6000:
            return LD_BACKWARD
        if a >= 0x2000:
            return LD_LEFT
        if a <= -0x2000:
            return LD_RIGHT
        return LD_FORWARD

    # --- setNormalSpeedF (2301), walk path ---
    cdef void _set_normal_speed_f(self, double param_1, double param_2, double param_3, double param_4) noexcept nogil:
        cdef double dVar10 = f32(self.msd * f32(self.max_nspeed * self.msd))
        cdef double temp_f0, temp_f3, dVar6
        if dVar10 < self.nspeed:
            temp_f0 = f32(self.nspeed - dVar10)
            temp_f3 = param_3 if temp_f0 > param_3 else temp_f0
            if temp_f3 < param_4:
                temp_f3 = param_4
            param_1 = 0.0
            dVar6 = dVar10
        else:
            temp_f3 = param_3
            dVar6 = 0.0
        if not (_c_fabs(param_1) < 1.0e-5):
            self.nspeed = f32(self.nspeed + param_1)
            if self.nspeed > dVar10:
                self.nspeed = dVar10
        else:
            self.nspeed = _clib_addcalc(self.nspeed, dVar6, param_2, temp_f3, param_4)

    # --- setSpeedAndAngleNormal (2751), walk path ---
    cdef void _set_speed_and_angle_normal(self, long long param_1, bint attention_lock) noexcept nogil:
        cdef bint bVar2 = False
        cdef double dVar11, dVar9, dVar10, sp_ratio
        cdef long long sVar6, sVar7, old_facing, t1, t2
        dVar9 = 0.0
        if self.msd > 0.05:
            dVar11 = f32(self.msd * self.msd)
            if ((not attention_lock) and (_lldist(self.target, self.travel) > 0x7800)
                    and self.state != LS_MOVE_TURN):
                if self.state == LS_WAIT or self.state == LS_FREE_WAIT or self.state == LS_WAIT_TURN:
                    return
                if self.state == LS_MOVE:
                    sp_ratio = f32(self.speedF / self.max_nspeed)
                    if (sp_ratio > _L_SLIP_THRESH
                            and self._get_dir(_s16c(self.m34ea - self.m34dc)) == LD_BACKWARD):
                        return
                    if sp_ratio <= _L_SLIP_THRESH:
                        self.travel = _clib_addcalc_angles(self.travel, self.target,
                                                           _L_F6, param_1, _L_F4)
                        return
                    bVar2 = True
                else:
                    self.travel = _clib_addcalc_angles(self.travel, self.target,
                                                       _L_F6, param_1, _L_F4)
            else:
                sVar6 = <long long>(f32(<double>param_1 * dVar11))
                if sVar6 < 10:
                    sVar6 = 10
                sVar7 = <long long>(f32(<double>_L_F4 * dVar11))
                if sVar7 < 1:
                    sVar7 = 1
                self.travel = _clib_addcalc_angles(self.travel, self.target, _L_F6, sVar6, sVar7)
            if not bVar2:
                dVar9 = jma_cos(_s16c(self.target - self.travel))
                if self.nspeed > f32(0.5 * self.max_nspeed):
                    if dVar9 < 0.7:
                        dVar9 = f32(0.7)
                elif dVar9 < 0.0:
                    dVar9 = 0.0
                dVar10 = f32(0.5 - f32(0.5 * _c_fabs(f32(self.nspeed / self.max_nspeed))))
                if self.msd > dVar10:
                    dVar9 = f32(dVar9 * f32(_L_F14 * dVar11))
                else:
                    dVar9 = 0.0
        if (not attention_lock) and self.state != LS_MOVE_TURN and self.msd > 0.05:
            old_facing = self.facing
            self.facing = _clib_addcalc_angles(self.facing, self.target, _L_F6,
                                               (param_1 << 1) & 0xFFFF, (_L_F4 << 1) & 0xFFFF)
            t1 = _s16c(old_facing - self.travel)
            t2 = _s16c(self.facing - self.travel)
            if t1 * t2 <= 0:
                self.facing = self.travel
        self._set_normal_speed_f(dVar9, _L_F24, _L_F1C, _L_F20)

    # --- setSpeedAndAngleAtn (2851) ---
    cdef void _set_speed_and_angle_atn(self) noexcept nogil:
        if self.direction == LD_FORWARD:
            self._set_speed_and_angle_normal(_L_F0, True)
            return
        if self.direction == LD_BACKWARD:
            self._set_speed_and_angle_atn_back()
            return
        cdef double fVar2
        cdef long long old
        if self.msd > 0.05:
            if self._get_dir(self.target - self.travel) == LD_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = _clib_addcalc_angles(self.travel, self.target, _L_ATN_TURN_SCALE,
                                               _L_ATN_TURN_MAX, _L_ATN_TURN_MIN)
            fVar2 = f32(f32(_L_ATN_SPD * self.msd) * jma_cos(_s16c(self.travel - old)))
        else:
            fVar2 = 0.0
        self.facing = self.m34E6
        self._set_normal_speed_f(fVar2, _L_ATN_SCL, _L_ATN_ACC, _L_ATN_DEC)

    cdef void _set_speed_and_angle_atn_back(self) noexcept nogil:
        cdef double f1
        cdef long long old
        if self.msd > 0.05:
            if self._get_dir(self.target - self.travel) == LD_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = _clib_addcalc_angles(self.travel, self.target, _L_ATN_TURN_SCALE,
                                               _L_ATN_TURN_MAX, _L_ATN_TURN_MIN)
            f1 = f32(f32(_L_ATNB_SPD * self.msd) * jma_cos(_s16c(self.travel - old)))
        else:
            f1 = 0.0
        self.facing = self.m34E6
        self._set_normal_speed_f(f1, _L_ATNB_SCL, _L_ATNB_ACC, _L_ATNB_DEC)

    cdef void _update_atn_direction(self) noexcept nogil:
        cdef long long iVar6 = _s16c(self.travel - self.facing)
        cdef double f2 = jma_sin(iVar6)
        cdef double fVar4 = jma_cos(iVar6)
        cdef int uVar1 = self.direction
        # The FWD/BACK branch is gated on mpAttnActorLockOn == NULL: a live actor-lock keeps mDirection
        # on a SIDE (the strafe pose). `_actor_locked` defaults False, so an unlocked step is unaffected.
        if self.msd > 0.05:
            if (not self._actor_locked) and (fVar4 <= _L_ATNB_COS_BACK or fVar4 >= _L_ATNB_COS_FWD):
                self.direction = LD_BACKWARD if fVar4 <= _L_ATNB_COS_BACK else LD_FORWARD
            else:
                if uVar1 == LD_BACKWARD or uVar1 == LD_FORWARD:
                    self.direction = LD_RIGHT
                    self.max_nspeed = _L_ATN_MAX
                if f2 > 0.0:
                    self.direction = LD_LEFT
                elif f2 < 0.0:
                    self.direction = LD_RIGHT
        if self.direction == LD_BACKWARD:
            self.max_nspeed = _L_ATNB_MAX
        elif self.direction == LD_FORWARD:
            self.max_nspeed = _L_MAX_NSPEED
        elif self.direction != LD_RIGHT and self.direction != LD_LEFT:
            self.direction = LD_RIGHT

    cdef void _check_next_mode(self, bint l_held) noexcept nogil:
        cdef int cur = self.state
        cdef long long dist
        # `_actor_locked` (mpAttnActorLockOn != NULL) defaults False, so an unlocked step takes the
        # plain L-held arm; a caller that arms it gets the ATN_ACTOR routing, as land/procs/move.py does.
        if l_held or self._actor_locked:
            self.max_nspeed = _L_ATN_MAX
            if self._actor_locked:
                self.state = LS_ATN_ACTOR_WAIT if _c_fabs(self.nspeed) <= 0.001 else LS_ATN_ACTOR_MOVE
            else:
                self.state = LS_WAIT if _c_fabs(self.nspeed) <= 0.001 else LS_ATN_MOVE
            return
        self.max_nspeed = _L_MAX_NSPEED
        self.direction = LD_NONE
        dist = _lldist(self.target, self.travel)
        if _c_fabs(self.nspeed) <= 0.001:
            if dist > 0x7800 and self.msd > 0.05:
                self._proc_wait_turn_init()
            else:
                if not (self.state == LS_WAIT or self.state == LS_FREE_WAIT):
                    self.state = LS_WAIT
        elif cur == LS_MOVE_TURN and self.travel != self.facing:
            self.state = LS_MOVE_TURN
        elif dist > 0x7800 and self.msd > 0.05:
            if (f32(self.speedF / self.max_nspeed) > _L_SLIP_THRESH
                    and self._get_dir(_s16c(self.m34ea - self.m34dc)) == LD_BACKWARD):
                self._proc_slip_init()
            else:
                self._proc_move_turn_init(1)
        elif (self._get_dir(_s16c(self.target - self.travel)) == LD_BACKWARD and self.msd > 0.05):
            self._proc_move_turn_init(1)
        else:
            self.state = LS_MOVE

    # --- turn / roll / slip procs ---
    cdef void _proc_wait_turn_init(self) noexcept nogil:
        self.state = LS_WAIT_TURN
        self.turn_target = self.target
        self.travel = self.facing
        self._pe._w_enter_single_c(C_ROT, _L_MOVE_REENTRY_MORF, 0.0, _MMAX[C_ROT],
                                   _L_WAIT_TURN_ANIM_RATE, True)

    cdef void _proc_wait_turn(self, bint l_held) noexcept nogil:
        self.nspeed = _clib_addcalc(self.nspeed, 0.0, _L_F24, _L_F1C, _L_F20)
        self.facing = _clib_addcalc_angles(self.facing, self.turn_target,
                                           _L_TURN_SCALE, _L_TURN_MAX, _L_TURN_MIN)
        self.travel = self.facing
        if _s16c(self.turn_target - self.facing) == 0:
            self._check_next_mode(l_held)

    cdef void _proc_move_turn_init(self, int param_1) noexcept nogil:
        self.state = LS_MOVE_TURN
        self._pe._w_set_pending_c(_L_MOVE_REENTRY_MORF)
        if param_1 != 0:
            self.turn_shape_max = (_L_F0 * 4 + 0x4A56) & 0xFFFF
            self.turn_shape_min = (_L_F0 * 2) & 0xFFFF
            self.turn_shape_scale = 2
            self.travel = self.target
            self._anim_nspeed = self.nspeed
            self._has_anim_nspeed = True
            self.nspeed = f32(self.nspeed * 0.5)
        else:
            self.turn_shape_max = (_L_F0 * 2) & 0xFFFF
            self.turn_shape_min = _L_F0 & 0xFFFF
            self.turn_shape_scale = 3

    cdef void _proc_move_turn(self, bint l_held) noexcept nogil:
        self._set_speed_and_angle_normal(_L_F0, l_held)
        self.facing = _clib_addcalc_angles(self.facing, self.travel,
                                           self.turn_shape_scale, self.turn_shape_max, self.turn_shape_min)
        self._check_next_mode(l_held)
        if self.state == LS_MOVE:
            self._pe._w_set_pending_c(_L_MOVE_REENTRY_MORF)

    cdef void _proc_slip_init(self) noexcept nogil:
        self.state = LS_SLIP
        self.nspeed = f32(self.speedF * _L_SLIP_ENTRY)
        self._pe._w_enter_single_c(C_SLIP, _L_SLIP_MORF, 0.0, _MMAX[C_SLIP], _L_SLIP_ANIM_RATE, True)

    cdef void _proc_slip(self, bint l_held) noexcept nogil:
        self.nspeed = _clib_addcalc(self.nspeed, 0.0, _L_SLIP_DEC_SCALE,
                                    _L_SLIP_DEC_MAX, _L_SLIP_DEC_MIN)
        if _c_fabs(self.nspeed) <= 0.001:
            if self.msd > 0.05:
                self.travel = (self.facing + 0x8000) & 0xFFFF
                self.facing = (self.facing + 0x100) & 0xFFFF
                self.nspeed = f32(self.max_nspeed * _L_MT_SLIP_SEED)
                self._proc_move_turn_init(0)
            else:
                self._check_next_mode(l_held)

    cdef void _roll_init(self) noexcept nogil:
        cdef double v = f32(f32(self.speedF * _L_ROLL_SPD) + _L_ROLL_ADD)
        cdef double cap
        if v < _L_ROLL_MIN:
            v = f32(_L_ROLL_MIN)
        else:
            cap = f32(_L_ROLL_ADD + f32(_L_MAX_NSPEED * _L_ROLL_SPD))
            if v > cap:
                v = cap
        self.nspeed = v
        self.facing = self.target
        self.travel = self.facing
        # m3570 latch (6838): a roll STARTED already wall-hit facing the wall (within mRoll.field_0x4)
        # disables the mid-roll crash -- it GRINDS instead of bonking. Reads LAST frame's CrrPos, so it
        # is False-by-default (never wall-hit) on a core with no Link mesh wired -- the pre-port value.
        self._roll_m3570 = not (self._wall_cir_hit[0]
                                and _lldist((self.travel + 0x8000) & 0xFFFF, self._wall_angle[0])
                                <= _L_ROLL_BONK_ANGLE)
        self.state = LS_FRONT_ROLL
        self.roll_frame = 0.0
        self._roll_entered = True
        self._pe._w_enter_single_c(C_ROLLF, _L_ROLL_ENTRY_MORF, 0.0, _L_ROLL_END, _L_ROLL_RATE, True)

    cdef void _roll_exit(self, bint l_held) noexcept nogil:
        """The roll's checkNextMode transition, WITH the b_trig CUT arm (`procs/roll.py::_roll_exit`).

        A buffered sword button + the sword drawn routes to a cut -- the "roll stab": L held -> CUT_A
        (vertical slash), else CUT_F (forward thrust) -- carrying the roll's full speedF into the
        cut's first-frame lunge. The aim is `changeCutProc`'s sVar2: the stick target while pushed and
        unlocked, else shape_angle.y."""
        cdef long long aim
        if self._b_trig and self.sword_drawn:
            aim = self.target if (self.msd > 0.05 and not l_held) else self.facing
            self._cut_init(LS_CUT_A if l_held else LS_CUT_F, aim)
            return
        self._check_next_mode(l_held)
        if self.state == LS_MOVE:
            self._pe._w_set_pending_c(_L_MOVE_REENTRY_MORF)

    cdef void _proc_roll(self, bint l_held) noexcept nogil:
        if self._roll_entered:
            self._roll_entered = False
            return
        self.roll_frame = f32(self.roll_frame + _L_ROLL_RATE)
        if self.roll_frame >= _L_ROLL_END:
            if self.msd <= 0.05:
                self.nspeed = f32(self.nspeed - _L_ROLL_MIN)
            self._roll_exit(l_held)
        elif (self.roll_frame > _L_ROLL_EARLY
              and (self.msd > 0.05 or (self._b_trig and self.sword_drawn))):
            # getFrame()>field_0x10 -> checkNextMode(1) (6866); inert only when neutral AND no action --
            # a pushed stick (roll-EBS) or a B RISING EDGE (swordTrigger) fires it.
            self._roll_exit(l_held)
        elif (self.speedF >= _L_ROLL_BONK_SPEED and self._roll_m3570
              and self.wall_hit and self._wall_cir_hit[0]
              and _lldist((self.travel + 0x8000) & 0xFFFF, self._wall_angle[0]) <= _L_ROLL_BONK_ANGLE
              and _L_ROLL_BONK_FMIN <= self.roll_frame <= _L_ROLL_BONK_FMAX):
            # The roll bonk (6869) -> procFrontRollCrash_init, which this core does NOT model. A nogil
            # frame cannot raise, so flag it and let `wall_check` refuse: the alternative is running the
            # roll on through a frame the console spent airborne.
            self.bonk_unmodelled = True

    # --- the sword-thrust cut (CUT_F 0x42 / CUT_A 0x41), dispatched out of a roll --------------
    cdef void _cut_init(self, int cut_type, long long aim) noexcept nogil:
        """procCutF_init / procCutA_init (d_a_player_sword.inc:660/430) -- `_CutMixin._cut_init`.

        setSingleMoveAnime(ANM_CUT*, rate CUT_RATE, start CUT_START); m3700 = cXyz::Zero; m34C2 = 1.
        mNormalSpeed KEEPS the entry value (the roll's carried speedF) this frame, and current.angle.y
        (travel) is NOT touched -- the snap to shape_angle.y happens in `_proc_cut` frame 2+."""
        self.state = cut_type
        self.cut_frame = _L_CUT_START
        self._cut_m3700[0] = 0.0; self._cut_m3700[1] = 0.0; self._cut_m3700[2] = 0.0
        self.cut_target = aim & 0xFFFF
        self._has_cut_target = True
        # No foot-engine pose: the cut anim is not a foot-chain walk anim and m3598 stays 0, so
        # position = the joint-0 root lunge + mNormalSpeed. The toe stream freezes.

    cdef bint _cut_checkpass(self, double frame) noexcept nogil:
        """J3DFrameCtrl::checkPass, EMode_NONE arm -- `_CutMixin._checkpass_none`. True iff CUT_PASS is
        crossed by this update; `frame` is the already-advanced frame and next is recomputed here."""
        cdef double cur = frame
        cdef double nxt = f32(cur + _L_CUT_RATE)
        if nxt < _L_CUT_START:
            nxt = _L_CUT_START
        if nxt >= _L_CUT_END:
            nxt = f32(_L_CUT_END - 0.001)
        if cur <= nxt:
            return cur <= _L_CUT_PASS and _L_CUT_PASS < nxt
        return nxt <= _L_CUT_PASS and _L_CUT_PASS < cur

    cdef void _proc_cut(self, bint l_held) noexcept nogil:
        """One CUT_F/CUT_A frame (`_CutMixin._proc_cut`). Advance the MOVE0 ctrl (+CUT_RATE,
        EMode_NONE), then: getFrame()>field_0xC -> checkNextMode(1) exit to WAIT; the diagonal-aim
        shape snap; checkPass(CUT_PASS) -> launch mNormalSpeed off the pre-cut speedF; then the
        per-frame cLib_addCalc decel. The lunge itself is applied in the position block."""
        cdef int ct = self.state
        cdef int slot = _cut_slot(ct)
        cdef double fc = f32(self.cut_frame + _L_CUT_RATE)
        cdef double end_clamp = f32(_L_CUT_END - 0.001)
        if fc < _L_CUT_START:
            fc = _L_CUT_START
        if fc >= _L_CUT_END:
            fc = end_clamp
        self.cut_frame = fc
        if fc > _L_CUT_EARLY[slot]:
            self.state = LS_WAIT
            self.nspeed = 0.0
            self._pe._w_set_pending_c(_L_MOVE_REENTRY_MORF)
            return
        if self._has_cut_target and self.cut_target != self.facing:
            self.facing = _clib_addcalc_angles(self.facing, self.cut_target, _L_CUT_TURN_SCALE,
                                               _L_CUT_TURN_MAX, _L_CUT_TURN_MIN)
        self.travel = self.facing
        if self._cut_checkpass(fc):
            self.nspeed = f32(f32(_c_fabs(self.speedF) * _L_CUT_LAUNCH_MUL)
                              + _L_CUT_LAUNCH_ADD[slot])
        self.nspeed = _clib_addcalc(self.nspeed, 0.0, _L_CUT_DEC_SCALE, _L_CUT_DEC_MAX[slot],
                                    _L_CUT_DEC_MIN)

    cdef void _cam_step(self, int acsx, int acsy):
        self._cam_target = _cam_step_target_c(self._cam_target, self._cam_pending_posx, self._cam_scale)
        cdef long long diff = _s16c(self._cam_target - self._cam_yaw)
        self._cam_yaw = (self._cam_yaw + (diff / 2)) & 0xFFFF
        self._cam_pending_posx = _cstick_posx_c(acsx, acsy)

    # --- proc dispatch + per-frame step ---
    def step(self, int sx, int sy, int buttons=0, int triggerL=0, int csx=128, int csy=128):
        """Advance one frame; returns speedF (the position-integrating speed). The caller syncs the
        public physics fields + builds the (d, tag) tuple + `visited`."""
        cdef int asx = self._inbuf[0][0], asy = self._inbuf[0][1], abtn = self._inbuf[0][2]
        cdef int atrig = self._inbuf[0][3], acsx = self._inbuf[0][4], acsy = self._inbuf[0][5]
        self._inbuf[0][0] = self._inbuf[1][0]; self._inbuf[0][1] = self._inbuf[1][1]
        self._inbuf[0][2] = self._inbuf[1][2]; self._inbuf[0][3] = self._inbuf[1][3]
        self._inbuf[0][4] = self._inbuf[1][4]; self._inbuf[0][5] = self._inbuf[1][5]
        self._inbuf[1][0] = sx; self._inbuf[1][1] = sy; self._inbuf[1][2] = buttons
        self._inbuf[1][3] = triggerL; self._inbuf[1][4] = csx; self._inbuf[1][5] = csy
        self.csangle = (self._cam_yaw + 0x8000) & 0xFFFF
        self._set_stick_data(asx, asy)
        cdef bint l_held = ((abtn & 0x40) != 0) or (atrig >= 200)
        cdef bint a_pressed = (abtn & 0x100) != 0
        # mItemTrigger A/B rising edge (checkSubjectEnd needs the EDGE, not a held button -- a B held
        # from before procSubjectivity's body runs misses it and does NOT exit). See land.py step().
        cdef bint ab_edge = ((abtn & ~self._abtn_prev) & 0x300) != 0
        self._abtn_prev = abtn
        cdef bint moving = self.msd > 0.05
        # --- SUBJECTIVITY freeze (C-up cancel), input-driven -- mirrors land.py step() (see there for
        # the full model + decomp cites). C-up entry armed 1 frame (camera path); exits: A/B edge, L
        # held (no floor), C-DOWN 0x2000 (floored at lock+SUBJ_CAM_FLOOR). Freeze persists while C-up is
        # re-requested (re-enter cup-cam); the exit-to-WAIT is its own hold frame; re-walk needs C-up
        # released + a forward stick, phase carried (m34C3=2). Position frozen throughout.
        cdef double posy = _cstick_posy_c(acsx, acsy)
        cdef bint cup_now = (self.msd < _CUP_MAIN_MAX and posy > _CUP_POSY)
        cdef bint was_ended
        if self._subj_arm:
            self._subj_arm = False
            self.state = LS_SUBJECTIVITY
            self.nspeed = 0.0
            self.speedF = 0.0
            self._subj_ended = False
            self._subj_frames = 0
            self._cdown_run = 0
            self._pe.w_enter_subjectivity(self.msd, _L_MOVE_REENTRY_MORF)
            self.m34de = self.facing
            self.m34ea = self.m34dc
            self._cam_step(acsx, acsy)
            self._l_prev = l_held
            return 0.0
        if self.state == LS_SUBJECTIVITY:
            self._subj_frames += 1
            was_ended = self._subj_ended
            if cup_now:
                self._subj_ended = False
                self._cdown_run = 0
            else:
                if ab_edge or l_held:
                    self._subj_ended = True
                if posy < _CDOWN_POSY:
                    self._cdown_run += 1
                    if self._cdown_run >= _CDOWN_RUN and self._subj_frames >= _SUBJ_CAM_FLOOR:
                        self._subj_ended = True
                else:
                    self._cdown_run = 0
            if was_ended and (not cup_now) and self.msd > 0.05:
                self.state = LS_MOVE
                self.nspeed = 0.0
                self._pe.w_set_pending(_L_MOVE_REENTRY_MORF)
            else:
                self.speedF = 0.0
                self._pe.w_step_subjectivity(self.msd)
                self.m34de = self.facing
                self.m34ea = self.m34dc
                self._cam_step(acsx, acsy)
                self._l_prev = l_held
                return 0.0
        elif ((self.state == LS_MOVE or self.state == LS_WAIT or self.state == LS_FREE_WAIT
               or self.state == LS_ATN_MOVE) and cup_now):
            self._subj_arm = True

        if l_held and not self._l_prev:
            self.m34E6 = self.facing
        # The A-press is only ATTACK (the roll) above mBasic.field_0x1C -- setDoStatusBasic 2220; at or
        # below it the game sheathes instead (PUT_AWAY, 2218), which this model does not carry.
        if (a_pressed and self.msd > _L_ATTACK_MSD_MIN
                and (self.state == LS_MOVE or self.state == LS_ATN_MOVE)):
            self.facing = self.target
            self._roll_init()

        cdef int proc = self.state
        if proc == LS_WAIT or proc == LS_FREE_WAIT:
            if l_held:
                self.state = LS_ATN_MOVE
                self._set_speed_and_angle_atn()
            else:
                self._set_speed_and_angle_normal(_L_F0, False)
            self._check_next_mode(l_held)
        elif proc == LS_MOVE:
            self._set_speed_and_angle_normal(_L_F0, l_held)
            self._check_next_mode(l_held)
        elif proc == LS_ATN_MOVE:
            self._set_speed_and_angle_atn()
            self._check_next_mode(l_held)
        elif proc == LS_WAIT_TURN:
            self._proc_wait_turn(l_held)
        elif proc == LS_MOVE_TURN:
            self._proc_move_turn(l_held)
        elif proc == LS_SLIP:
            self._proc_slip(l_held)
        elif proc == LS_FRONT_ROLL:
            self._proc_roll(l_held)

        cdef int prev_dir = self.direction
        if self.state == LS_ATN_MOVE:
            self._update_atn_direction()
        if proc == LS_ATN_MOVE and self.state == LS_MOVE:
            self._pe.w_set_pending(_L_MOVE_REENTRY_MORF)

        self._pe.set_pos(self.pos_x, 0.0, self.pos_z, self.facing)

        cdef double f31, na, ratio
        cdef long long r3, r3a
        cdef int r27
        if self.state == LS_WAIT_TURN:
            self._pe.w_step_single(self.nspeed, self.msd)
            self.speedF = 0.0
        elif proc == LS_WAIT_TURN and self.state == LS_WAIT:
            r3 = _s16c(self.facing - self.m34de)
            r3a = r3 if r3 >= 0 else -r3
            r27 = C_ATNWLS if r3 > 0 else C_ATNWRS
            ratio = f32(f32(0.5) + f32(0.001 * <double>r3a))
            if ratio > 1.0:
                ratio = 1.0
            self._pe.w_enter_wait_idle(ratio, r27, _L_MOVE_REENTRY_MORF, self.msd)
            self.speedF = 0.0
        elif self.state == LS_FRONT_ROLL or self.state == LS_SLIP:
            self._pe.w_step_single(self.nspeed, self.msd)
            na = self.nspeed if self.nspeed >= 0.0 else -self.nspeed
            self.speedF = 0.0 if na < 0.05 else self.nspeed
        elif self.state == LS_ATN_MOVE:
            f31 = f32(_c_fabs(self.nspeed) / self.max_nspeed)
            if proc != LS_ATN_MOVE or self.direction != prev_dir:
                self.speedF = self._pe.w_step_atn(self.nspeed, self.msd, self.direction, f31,
                                                  _L_MOVE_REENTRY_MORF, True)
            else:
                self.speedF = self._pe.w_step_atn(self.nspeed, self.msd, self.direction, f31, 0.0, False)
        else:
            self.speedF = self._pe.w_step(self.nspeed, self.msd,
                                          self._anim_nspeed if self._has_anim_nspeed else 0.0,
                                          self._has_anim_nspeed)
            self._has_anim_nspeed = False

        cdef double d = self.speedF
        self.pos_x = f32(self.pos_x + f32(d * jma_sin(self.travel)))
        self.pos_z = f32(self.pos_z + f32(d * jma_cos(self.travel)))
        self.m34de = self.facing
        self.m34ea = self.m34dc
        self._cam_step(acsx, acsy)
        self._l_prev = l_held
        return d


    # ================= Coupled-actor surface: CC push, walls, look pair, cut ===================
    # The from-f0 FreeRun window: MOVE(6) <-> ATN_MOVE(7) <-> ATN_ACTOR_WAIT/MOVE(8/9) <-> FRONT_ROLL.
    # Adds the dAttention_c hold-mode lock machine + the actor-lock targeting procs 8/9 (re-aim +
    # DIR_BACKWARD negation) + the locked-actor checkNextMode/setBlendAtnMoveAnime gates + the posMove
    # CC-push consume, all resident in C. Physics port of land.state.LandState.step. speedF via the
    # seeded fused PoseEngine. NOTE: no public step dispatches this surface -- see the class docstring.
    @property
    def shape_z(self):
        """sim_shape_z: shape_angle.z = s16(m351C) >> 1 (the lean the from_f0 gate asserts)."""
        return _s16c(<long long>self.m351C) >> 1

    @property
    def attn_y(self):
        """Link's `attention_info.position` Y -- what the camera reads him at.

        `setAttentionPos` (d_a_player_main.cpp:10271, right after setCollision) builds it as
        ``f32(92.5 + baseTR[1][3])``, so the term is the pose engine's OWN base row and this
        reads it there rather than re-deriving it beside the engine. That row is set by
        `_set_pos_c` on whatever the frame last drew at, which is exactly the base the wired
        `FootFK` carries -- and it is the last camera argument a native run could not supply.

        On flat ground the row is Link's constant world Y (no m35C4 walk lift, no m35B8 ground
        decay). It is exported anyway: the camera should read the base from the engine that owns
        it, so a ground model landing later moves this without touching the camera."""
        return fadds(f32(92.5), self._pe._base[7])

    def co_center_exec(self, init_frame=None):
        """Link's exec-pass body-Co centre (cx, cz) for the frame this core LAST stepped -- the twin
        of `from_f0._computed_center`, and what a caller has to recompute the CC push pair after
        moving him.

        Same base/lean conventions as `head_top_exec` and as the centre a coupled caller builds
        internally: the base takes the DRAW lean (zero on a proc-``*_init`` frame) and the BODY_CHN
        twist the post-update one. It exists because a native run's Python `LandState` is a
        field-holder whose pose is the SEED's -- computing the centre off it would silently use an
        f0 pose (see `FreeRun.place_link`).

        ``init_frame`` -- None uses the flag this core recorded for the frame it stepped, which is
        the true one. Pass True/False to OVERRIDE it: `_computed_center` takes that flag as an
        argument and every run-level caller passes False, so the override is what lets the two
        engines be compared for equality rather than one of them being quietly more correct."""
        cdef long long body_lean_v = _s16c(<long long>self.m351C) >> 1
        cdef bint init_f = self._init_frame if init_frame is None else <bint>bool(init_frame)
        cdef long long base_lean_v = 0 if init_f else (<long long>self._draw_lean_c)
        cdef double out[2]
        self._pe._body_co_center(self.pos_x, self.pos_y, self.pos_z, self.facing,
                                 base_lean_v & 0xFFFF, -body_lean_v, out)
        return (out[0], out[1])

    def head_top_exec(self, neck=None):
        """Link's exec-pass ``mHeadTopPos`` (x, y, z) for the frame this core LAST stepped -- the
        twin of `from_f0._computed_head_top`, and the one value Tetra's look model needs from him.

        Same base/lean conventions as the body-Co centre computed in a coupled caller: the base takes
        the DRAW lean (zero on a proc-``*_init`` frame, `_init_frame`) and the BODY_CHN twist takes
        the post-update lean. ``neck`` = `NeckLook.local_38()` for the head jointBeforeCB twist, or
        None for untwisted.

        This closes the gap that kept a coupled rollout in Python: `_step_native` reproduces the wired
        step 0-ULP given csangle and the proc-9 re-aim eye, and the eye is her `Zl1Look` output, which
        reads exactly this Y (`dNpc_playerEyePos`) and otherwise only positions."""
        cdef long long body_lean_v = _s16c(<long long>self.m351C) >> 1
        cdef long long base_lean_v = 0 if self._init_frame else (<long long>self._draw_lean_c)
        cdef long long nlx = 0, nly = 0, nlz = 0
        if neck is not None:
            nlx = _s16c(<long long>int(neck[0]) & 0xFFFF)
            nly = _s16c(<long long>int(neck[1]) & 0xFFFF)
            nlz = _s16c(<long long>int(neck[2]) & 0xFFFF)
        cdef double out[3]
        self._pe._head_top(self.pos_x, self.pos_y, self.pos_z, self.facing,
                           base_lean_v & 0xFFFF, -body_lean_v, nlx, nly, nlz, out)
        return (out[0], out[1], out[2])

    def head_mtx_exec(self, neck=None):
        """The exec-pass WORLD head anm matrix (3x4) for the frame this core LAST stepped -- the twin
        of `from_f0._computed_head_mtx`, same conventions as `head_top_exec`. `NeckLook.update`
        measures the CACHED previous-frame value of this matrix, so the eye chain needs both."""
        cdef long long body_lean_v = _s16c(<long long>self.m351C) >> 1
        cdef long long base_lean_v = 0 if self._init_frame else (<long long>self._draw_lean_c)
        cdef long long nlx = 0, nly = 0, nlz = 0
        if neck is not None:
            nlx = _s16c(<long long>int(neck[0]) & 0xFFFF)
            nly = _s16c(<long long>int(neck[1]) & 0xFFFF)
            nlz = _s16c(<long long>int(neck[2]) & 0xFFFF)
        cdef double m[12]
        self._pe._head_mtx(self.pos_x, self.pos_y, self.pos_z, self.facing,
                           base_lean_v & 0xFFFF, -body_lean_v, nlx, nly, nlz, m)
        return ((m[0], m[1], m[2], m[3]), (m[4], m[5], m[6], m[7]), (m[8], m[9], m[10], m[11]))

    def seed_look(self, Zl1AnimData data, zl1, neck, head_mtx, double tetra_y):
        """Wire the look pair INTO the step (session 128): from here a coupled caller runs her
        `Zl1Look` and Link's `NeckLook` itself and generates its own proc-9 re-aim eye, instead of
        being handed one per frame.

        `zl1`/`neck` are the SEEDED Python models (`core.npc_zl1_look.Zl1Look`,
        `land.neck_look.NeckLook`) -- the one place the two representations meet, so a native run
        starts from the same fixture the wired one does. `head_mtx` is the f0 exec head matrix (what
        f1's setNeckAngle measures), `tetra_y` her world Y. The seed eye is armed as this frame's
        re-aim target, so the first step reads it exactly as the injected mode did."""
        self._zl1 = Zl1LookCore(data)
        self._zl1.seed_from(zl1)
        self._neck = NeckLookCore()
        self._neck.seed(neck, head_mtx)
        self._tetra_y = tetra_y
        self._has_look = True
        self._atn_eye_x = self._zl1._eye[0]
        self._atn_eye_z = self._zl1._eye[2]
        self._has_eye = True

    @property
    def has_look(self):
        """True when the look pair runs inside the step (`seed_look` was called)."""
        return bool(self._has_look)

    def zl1_snapshot(self):
        """Her whole hidden state (see `Zl1LookCore.snapshot`) -- what the 0-ULP gate diffs."""
        return self._zl1.snapshot()

    def neck_snapshot(self):
        """m3564 as (x, y, z)."""
        return self._neck.snapshot()

    @property
    def look_eye(self):
        """Her eyePos as the step last computed it -- the value THIS core's next frame re-aims at."""
        return self._zl1.eye

    @property
    def look_tattn(self):
        """Her `attention_info.position` (the camera's lock target) from the last step."""
        return self._zl1.tattn

    def look_check(self):
        """Raise whatever the Python look model would have (the nogil step sets a flag instead)."""
        self._zl1.check()

    @property
    def cut_target_py(self):
        """`LandState.cut_target` -- the latched thrust aim, or None before a cut has latched one.

        None rather than 0: the Python field defaults to None and a native run's `LandState` is a
        field-holder synced from here, so handing it a 0 would read as an aim of due north that no
        cut ever set."""
        return int(self.cut_target) if self._has_cut_target else None

    def seed_cut(self, CutAnimData data, bint sword_drawn):
        """Arm the roll->CUT hand-off (session 150): the ANM_CUT root tracks + `sword_drawn`.

        Without this a mid-roll B is IGNORED by the C step, which is the gap `clip_roll.fire` used to
        have to step in Python for -- so it is seeded, never defaulted: a core that was not handed the
        tracks refuses the cut (the coupled step flags it) instead of rolling on through it."""
        self._cutanm = data
        self._has_cutanm = True
        self.sword_drawn = sword_drawn

    def seed_walls(self, link_mesh, tetra_mesh, link_wall_h, double link_wall_r, double gravity,
                   tetra_wall_h, double tetra_wall_r):
        """Wire `dBgS_Acch::CrrPos` for either actor (session 150) -- the BG wall pass INSIDE the frame.

        ``link_mesh``/``tetra_mesh`` are `WallMesh` objects (None = that actor keeps no pass, which is
        the herd phase's setting -- see `seeds.make_freerun`); pass the SAME object to every core of a
        beam, it is immutable and shared. The cylinder geometry comes from the Python models
        (`land.walls.WALL_H/WALL_R/GRAVITY`, `core.npc_zl1.WALL_H/WALL_R`) rather than being restated
        here, so one canonical value per constant survives the port."""
        cdef int i
        self._lwalls = link_mesh
        self._twalls = tetra_mesh
        self._has_lwalls = link_mesh is not None
        self._has_twalls = tetra_mesh is not None
        self._lnh = len(link_wall_h)
        self._tnh = len(tetra_wall_h)
        if self._lnh > 8 or self._tnh > 8:
            raise ValueError("at most 8 wall cylinders per actor")
        for i in range(self._lnh):
            self._lwh[i] = link_wall_h[i]
        for i in range(self._tnh):
            self._twh[i] = tetra_wall_h[i]
        self._lwr = link_wall_r
        self._lgravity = gravity
        self._twr = tetra_wall_r

    @property
    def walls_link(self):
        return self._lwalls

    @property
    def walls_tetra(self):
        return self._twalls

    @property
    def wall_cir_hit(self):
        """SetWallCirHit per Link cylinder, from the LAST frame's CrrPos (what the procs read)."""
        return tuple(bool(self._wall_cir_hit[i]) for i in range(self._lnh if self._lnh else 3))

    @property
    def wall_angle(self):
        """SetWallAngleY per Link cylinder (the twin of `LandState.wall_angle`)."""
        return tuple(int(self._wall_angle[i]) for i in range(self._lnh if self._lnh else 3))

    def wall_check(self):
        """Raise whatever the nogil frame could only FLAG -- call once per step, under the GIL.

        The C step must never silently run a branch it does not model, and it cannot raise from
        `nogil`, so the coupled step sets a sticky flag and this converts it. Both cases are
        Link-wall consequences that only exist once his mesh is wired, which is why they arrived with
        it rather than before."""
        if self.bonk_unmodelled:
            raise RuntimeError(
                "the roll BONKED (mid-roll head-on wall hit inside the crash window): "
                "procFrontRollCrash is not ported to LandCore, so the native step cannot carry this "
                "frame. Step this roll on the Python path (LandState models the crash).")
        if self.sidle_unmodelled:
            raise RuntimeError(
                "the A press dispatched a SIDLE, not a roll (setDoStatus SIDLE preempts ATTACK at a "
                "head-on wall): the sidle proc is not modelled on either path, so the native step "
                "refuses rather than rolling. Same verdict as LandState.sidle_blocked.")

    cdef void _link_wall_pass(self, double old_x, double old_z) noexcept nogil:
        """Link's `mAcch.CrrPos` at the game's point in the frame (`land.walls.wall_pass`, grounded
        default): old = the frame-START position (old.pos.y is the SNAPPED ground height), new = the
        integrated position with the mid-frame gravity dip, speed.y = that same gravity. Writes back
        XZ + the per-cylinder wall state the procs read NEXT frame."""
        cdef double px = self.pos_x, pz = self.pos_z
        cdef double y_old = self.pos_y
        cdef double py = fadds(y_old, self._lgravity)
        self.wall_hit = _ac_crr_pos(old_x, y_old, old_z, &px, &py, &pz, self._lgravity,
                                    self._lwalls._vtx, self._lwalls._pla,
                                    self._lwalls._sp68, self._lwalls._sp6c,
                                    self._lwalls._cand, self._lwalls._n,
                                    self._lwh, self._lnh, self._lwr,
                                    self._wall_cir_hit, self._wall_angle, &self.line_hit)
        self.pos_x = px
        self.pos_z = pz

    cdef void _tetra_wall_pass(self, double old_x, double old_z) noexcept nogil:
        """Tetra's `mObjAcch.CrrPos` where `Zl1FollowState.step` runs it -- after posMove consumes the
        recoil, speed_y 0 on the flat floor (a gravity dip mis-ejects a corrected XZ by 1 ULP). Twin of
        the `FreeRun.step` walls_tetra block; her hit flags are not read by anything, so no cir out."""
        cdef double px = self._tetra_x, pz = self._tetra_z
        cdef double py = self._tetra_y
        _ac_crr_pos(old_x, self._tetra_y, old_z, &px, &py, &pz, 0.0,
                    self._twalls._vtx, self._twalls._pla,
                    self._twalls._sp68, self._twalls._sp6c,
                    self._twalls._cand, self._twalls._n,
                    self._twh, self._tnh, self._twr, NULL, NULL, NULL)
        self._tetra_x = f32(px)
        self._tetra_z = f32(pz)

    cdef bint _sidle_blocks_roll(self) noexcept nogil:
        """`land.walls.sidle_blocks_roll`: an A press at a head-on wall is setDoStatus SIDLE (2241),
        which preempts the ATTACK/roll in the doTrigger chain (4188). ChkWallHit (LAST frame's CrrPos),
        a 25+wallR line check along FACING at each cylinder height hitting a steep wall (|n.y| <= 0.05),
        and facing within 0x2000 of head-on."""
        if not self.wall_hit:
            return False
        cdef double sin_f = jma_sin(self.facing)
        cdef double cos_f = jma_cos(self.facing)
        cdef double reach = fadds(25.0, self._lwr)
        cdef int hi, ci, ti, hit_ti
        cdef double sx, sy, sz, cex, cey, cez, h
        cdef double dst[3]
        cdef double nx, ny, nz
        cdef long long wall_ang
        for hi in range(self._lnh - 1, -1, -1):       # the decomp scans i = 2..0
            h = self._lwh[hi]
            sx = self.pos_x; sy = fadds(self.pos_y, h); sz = self.pos_z
            cex = fadds(sx, fmuls(sin_f, reach)); cey = sy
            cez = fadds(sz, fmuls(cos_f, reach))
            hit_ti = -1
            for ci in range(self._lwalls._n):
                ti = self._lwalls._cand[ci]
                if _ac_cross_lin_tri(sx, sy, sz, cex, cey, cez,
                                     self._lwalls._vtx + ti * 9, self._lwalls._pla + ti * 4, dst):
                    cex = dst[0]; cey = dst[1]; cez = dst[2]
                    hit_ti = ti
            if hit_ti >= 0:
                nx = self._lwalls._pla[hit_ti * 4 + 0]
                ny = self._lwalls._pla[hit_ti * 4 + 1]
                nz = self._lwalls._pla[hit_ti * 4 + 2]
                if _c_fabs(ny) > 0.05:
                    return False
                wall_ang = _cm_atan2s_c(nx, nz)
                return _lldist(wall_ang, (self.facing + 0x8000) & 0xFFFF) <= 0x2000
        return False

    cdef inline bint _atn_locked(self) noexcept nogil:
        return self._atn_state == _ATN_LOCK or self._atn_state == _ATN_RELEASE

    cdef bint _atn_target_present(self) noexcept nogil:
        """chaseAttention front-of-player cone gate (attention.py _atn_target_present)."""
        cdef long long bearing = _cm_atan2s_c(f32(self._tetra_x - self.pos_x),
                                              f32(self._tetra_z - self.pos_z))
        cdef long long d = _s16c((bearing - self.facing) & 0xFFFF)
        if d < 0:
            d = -d
        return d <= _ATN_FRONT_CONE_HALF

    cdef void _atn_update(self, bint l_held, bint target_present, bint target_exists) noexcept nogil:
        """dAttention_c hold-mode Run (attention.py AttentionLock.update).

        `target_present` = chaseAttention() (cone-gated, used by NONE/LOCK only); `target_exists` =
        LockonTarget(0) != NULL, which is what RELEASE keys on -- see the Python docstring."""
        cdef bint rising = l_held and not self._atn_l_prev
        cdef int prev_state = self._atn_state
        if self._atn_state == _ATN_NONE:
            if rising and target_present:
                self._atn_state = _ATN_LOCK
        elif self._atn_state == _ATN_LOCK:
            if not target_present:
                self._atn_state = _ATN_NONE
            elif not l_held:
                self._atn_state = _ATN_RELEASE
                self._atn_fade = self._atn_fade_frames
        elif self._atn_state == _ATN_RELEASE:
            if rising:
                self._atn_state = _ATN_LOCK if target_present else _ATN_NONE
            else:
                if self._atn_fade > 0:
                    self._atn_fade -= 1
                if (not target_exists) or self._atn_fade <= 0:
                    self._atn_state = _ATN_NONE
        self._atn_l_prev = l_held
        if self._atn_state == _ATN_LOCK or self._atn_state == _ATN_RELEASE:
            self._atn_list_present = True
        elif prev_state != _ATN_NONE:
            self._atn_list_present = False
        else:
            self._atn_list_present = target_present

    cdef void _set_shape_angle_to_atn_actor(self) noexcept nogil:
        """setShapeAngleToAtnActor (2625): re-aim shape_angle.y at the locked actor's eyePos
        (injected _atn_eye; feet fallback). No-op while unlocked (the body2 frame past the drop)."""
        if not self._atn_locked():
            return
        cdef double ax, az
        if self._has_eye:
            ax = self._atn_eye_x; az = self._atn_eye_z
        else:
            ax = self._tetra_x; az = self._tetra_z
        cdef long long ta = _cm_atan2s_c(f32(ax - self.pos_x), f32(az - self.pos_z))
        self.facing = _clib_addcalc_angles(self.facing, ta & 0xFFFF,
                                           _ATN_SHAPE_SCALE, _ATN_SHAPE_MAX, _ATN_SHAPE_MIN)

    cdef void _set_speed_and_angle_atn_actor(self) noexcept nogil:
        """setSpeedAndAngleAtnActor (2909): the actor-lock chase (procs 8/9). Same mAtnMove family as
        the ATN path with the DIR_BACKWARD negation flip, but re-aims facing at the actor (no mDirection
        forward/backward split -- procs 8/9 always run this)."""
        cdef double f1
        cdef long long old
        if self.msd > 0.05:
            if self._get_dir(self.target - self.travel) == LD_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = _clib_addcalc_angles(self.travel, self.target, _L_ATN_TURN_SCALE,
                                               _L_ATN_TURN_MAX, _L_ATN_TURN_MIN)
            f1 = f32(f32(_L_ATN_SPD * self.msd) * jma_cos(_s16c(self.travel - old)))
        else:
            f1 = 0.0
        self._set_shape_angle_to_atn_actor()
        self._set_normal_speed_f(f1, _L_ATN_SCL, _L_ATN_ACC, _L_ATN_DEC)


cdef inline long long _lldist(long long a, long long b) noexcept nogil:
    """cLib_distanceAngleS: |signed s16 difference|."""
    cdef long long d = _s16c(a - b)
    return d if d >= 0 else -d

