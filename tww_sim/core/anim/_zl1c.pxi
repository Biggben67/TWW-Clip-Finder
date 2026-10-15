# ==== The look pair, resident in C: Tetra's Zl1Look + Link's NeckLook (session 128) =============
#
# `include`d into _anmc.pyx (one translation unit -- these run INSIDE the coupled step, so
# they must reach LandCore/PoseEngine's C state without the GIL).
#
# WHY: the coupled frame went to C and left these two in Python, because between them
# they are what produces the proc-9 re-aim eye. Measured in s128 they are 91% of the step -- her
# 77.5%, the neck 13.4%, the C core itself 9.1% -- so this is the whole remaining win.
#
# Bit-exact ports of `core/npc_zl1_look.py` (Zl1JntCtrl / Zl1Morf / Zl1Look) and `land/neck_look.py`
# (NeckLook). Every tuning value is passed IN from those modules at arm time (`init_zl1_consts` /
# `init_neck_consts`) rather than re-declared here -- one canonical value per constant, and a change
# to the Python model cannot silently leave a stale copy behind in C.

# ---- her eye chain: CHAIN = (0, 1, 2, 5, 6), the model root -> stomach -> chest -> neck -> head --
DEF Z_NCH = 5
DEF Z_BB = 2                     # chain slot of BBONE_JNT (joint 2, "chest") -- nodeCB_BackBone
DEF Z_HD = 4                     # chain slot of HEAD_JNT  (joint 6, "head")  -- nodeCB_Head
DEF Z_NANM = 2                   # the two regime anims: slot 0 = wait03, slot 1 = look

cdef int _Z_CHAIN[Z_NCH]
cdef long long _Z_MAXA[2][2]     # chkLim mMaxAngles[i][j]: i 0 head / 1 backbone, j 0 x / 1 y
cdef long long _Z_MINA[2][2]
cdef long long _Z_TURN_POS, _Z_TURN_NEG          # mMaxTurnStep by the sign of field_0x7BC
cdef long long _Z_CHASE_SCALE, _Z_CHASE_MIN      # cLib_addCalcAngleL(.., 4, turn_step, 4)
cdef double _Z_EYE_OFF[3]                        # a_eye_pos_off (_nodeCB_Head)
cdef double _Z_ATTN_Y_OFF                        # field_1C: attention_info.position.y = pos.y + this
cdef double _Z_PLAYER_EYE_Y                      # dNpc_playerEyePos(-20)
cdef double _Z_ANM_MORF, _Z_ANM_SPEED
cdef int _Z_NUM_WAIT03, _Z_NUM_LOOK              # the game's anim NUMBERS (field_0x849)
cdef int _Z_RND_FLOOR                            # the rnd(0x5A, 0xB4) floor held at the RNG horizon
cdef bint _Z_CONSTS_READY = False


def init_zl1_consts(chain, maxa, mina, turn_pos, turn_neg, chase, eye_off, attn_y_off,
                    player_eye_y, anm_morf, anm_speed, num_wait03, num_look, rnd_floor):
    """Arm the Zl1 look constants FROM `core.npc_zl1_look` (idempotent; called once when the first
    native look chain is built). Nothing here is a literal: `maxa`/`mina` are Zl1JntCtrl._MAX/_MIN,
    `chase` is the (scale, min_step) of the cLib_addCalcAngleL chase, and so on."""
    global _Z_CONSTS_READY, _Z_TURN_POS, _Z_TURN_NEG, _Z_CHASE_SCALE, _Z_CHASE_MIN
    global _Z_ATTN_Y_OFF, _Z_PLAYER_EYE_Y, _Z_ANM_MORF, _Z_ANM_SPEED
    global _Z_NUM_WAIT03, _Z_NUM_LOOK, _Z_RND_FLOOR
    cdef int i, j
    for i in range(Z_NCH):
        _Z_CHAIN[i] = chain[i]
    for i in range(2):
        for j in range(2):
            _Z_MAXA[i][j] = maxa[i][j]
            _Z_MINA[i][j] = mina[i][j]
    _Z_TURN_POS = turn_pos; _Z_TURN_NEG = turn_neg
    _Z_CHASE_SCALE = chase[0]; _Z_CHASE_MIN = chase[1]
    for i in range(3):
        _Z_EYE_OFF[i] = eye_off[i]
    _Z_ATTN_Y_OFF = attn_y_off
    _Z_PLAYER_EYE_Y = player_eye_y
    _Z_ANM_MORF = anm_morf; _Z_ANM_SPEED = anm_speed
    _Z_NUM_WAIT03 = num_wait03; _Z_NUM_LOOK = num_look
    _Z_RND_FLOOR = rnd_floor
    _Z_CONSTS_READY = True


# ---- the neck: setNeckAngle's gate is a PROC-TABLE property (mModeFlg), so it is a lookup ------
DEF N_PROCTAB = 128
cdef bint _N_FLG80[N_PROCTAB]
cdef bint _N_FLG8M[N_PROCTAB]
cdef long long _N_CONE_HALF, _N_YAW_CLAMP, _N_PITCH_MAX, _N_PITCH_MIN
cdef long long _N_CH_SCALE, _N_CH_MAX, _N_CH_MIN
cdef double _N_EYE_OFF[3]
cdef double _N_HEAD_CTR[3]
cdef bint _N_CONSTS_READY = False


def init_neck_consts(flg80, flg8m, cone_half, chase, pitch_max, pitch_min, yaw_clamp,
                     eye_offset, head_center_offset):
    """Arm the NeckLook constants FROM `land.neck_look` (idempotent). `flg80`/`flg8m` are the proc
    sets carrying ModeFlg_00000080 / ModeFlg_08000000 -- copied into a table so the nogil path can
    test them; a proc code past the table is simply not in either set, exactly like the frozensets."""
    global _N_CONSTS_READY, _N_CONE_HALF, _N_YAW_CLAMP, _N_PITCH_MAX, _N_PITCH_MIN
    global _N_CH_SCALE, _N_CH_MAX, _N_CH_MIN
    cdef int i
    for i in range(N_PROCTAB):
        _N_FLG80[i] = False
        _N_FLG8M[i] = False
    for p in flg80:
        if 0 <= int(p) < N_PROCTAB:
            _N_FLG80[<int>p] = True
    for p in flg8m:
        if 0 <= int(p) < N_PROCTAB:
            _N_FLG8M[<int>p] = True
    _N_CONE_HALF = cone_half
    _N_CH_SCALE = chase[0]; _N_CH_MAX = chase[1]; _N_CH_MIN = chase[2]
    _N_PITCH_MAX = pitch_max; _N_PITCH_MIN = pitch_min
    _N_YAW_CLAMP = yaw_clamp
    for i in range(3):
        _N_EYE_OFF[i] = eye_offset[i]
        _N_HEAD_CTR[i] = head_center_offset[i]
    _N_CONSTS_READY = True


# ---- small shared kernels -----------------------------------------------------------------------
cdef inline double _fsqrt_c(double a) noexcept nogil:
    """`core.collision.fsqrt` = f32(sqrt(f32(a))) -- a CORRECTLY-ROUNDED sqrt, NOT the MSL
    frsqrte+Newton `_sqrtf_c`. Both models reach here through `collision.fsqrt`, so using the other
    one would be a silent 1-ULP bug in the elevation chase."""
    return f32(_c_sqrt(f32(a)))


cdef inline double _abs_xz_c(double x, double z) noexcept nogil:
    """cXyz::absXZ -- the fmadds contraction both models use (npc_zl1_look.cLib_targetAngleX /
    neck_look._abs_xz)."""
    return _fsqrt_c(fmadds(z, z, fmuls(x, x)))


cdef long long _clib_addcalc_anglel(long long value, long long target, long long scale,
                                    long long max_step, long long min_step) noexcept nogil:
    """cLib_addCalcAngleL (c_lib.cpp:205) -- the s32 angle chase, NO s16 wrap anywhere. Port of
    npc_zl1_look.cLib_addCalcAngleL; the division truncates toward zero in both."""
    cdef long long diff = target - value
    cdef long long step
    if value == target:
        return value
    step = diff / scale                      # cdivision=True -> C truncation, == int(diff/scale)
    if step > min_step or step < -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        value += step
    elif diff >= 0:
        value += min_step
        if target - value <= 0:
            value = target
    else:
        value -= min_step
        if target - value >= 0:
            value = target
    return value


cdef inline double _clib_chasef(double value, double target, double step) noexcept nogil:
    """cLib_chaseF (c_lib.cpp:276): step toward target, snapping on overshoot."""
    if step == 0.0:
        return value
    cdef double s = f32(-step) if value > target else f32(step)
    cdef double nv = fadds(value, s)
    if fmuls(s, fsubs(nv, target)) >= 0.0:
        return target
    return nv


cdef inline long long _half_toward_zero(long long v) noexcept nogil:
    """C `/2` on a signed s16 (truncates toward zero) -- the head CB's half-angle split."""
    return v / 2 if v >= 0 else -((-v) / 2)


cdef inline void _rot_x_c(long long a, double* m) noexcept nogil:
    """mDoMtx_XrotS as a 3x4 (npc_zl1_look._rot_x)."""
    cdef double c = jma_cos(a), s = jma_sin(a)
    m[0] = 1.0; m[1] = 0.0;      m[2] = 0.0; m[3] = 0.0
    m[4] = 0.0; m[5] = c;        m[6] = f32(-s); m[7] = 0.0
    m[8] = 0.0; m[9] = s;        m[10] = c;  m[11] = 0.0


cdef inline void _rot_y_c(long long a, double* m) noexcept nogil:
    cdef double c = jma_cos(a), s = jma_sin(a)
    m[0] = c;        m[1] = 0.0; m[2] = s;   m[3] = 0.0
    m[4] = 0.0;      m[5] = 1.0; m[6] = 0.0; m[7] = 0.0
    m[8] = f32(-s);  m[9] = 0.0; m[10] = c;  m[11] = 0.0


cdef inline void _rot_z_c(long long a, double* m) noexcept nogil:
    cdef double c = jma_cos(a), s = jma_sin(a)
    m[0] = c;   m[1] = f32(-s); m[2] = 0.0;  m[3] = 0.0
    m[4] = s;   m[5] = c;       m[6] = 0.0;  m[7] = 0.0
    m[8] = 0.0; m[9] = 0.0;     m[10] = 1.0; m[11] = 0.0


cdef void _tr_matrix_c(long long rx, long long ry, long long rz,
                       double tx, double ty, double tz, double* m) noexcept nogil:
    """J3DGetTranslateRotateMtx -> 3x4 (fk.tr_matrix). Element ops fused per the MWCC codegen; this
    is NOT psmtx_quat(euler_to_quat(rot)) and the two differ in the low bits, so her non-morf pose
    path must use exactly this."""
    cdef double sx = jma_sin(rx), cx = jma_cos(rx)
    cdef double sy = jma_sin(ry), cy = jma_cos(ry)
    cdef double sz = jma_sin(rz), cz = jma_cos(rz)
    cdef double cxsz = fmuls(cx, sz)
    cdef double sxcz = fmuls(sx, cz)
    cdef double sxsz = fmuls(sx, sz)
    cdef double cxcz = fmuls(cx, cz)
    m[8] = f32(-sy)
    m[0] = fmuls(cz, cy)
    m[4] = fmuls(sz, cy)
    m[9] = fmuls(cy, sx)
    m[10] = fmuls(cy, cx)
    m[1] = fmsubs(sxcz, sy, cxsz)
    m[6] = fmsubs(cxsz, sy, sxcz)
    m[2] = fmadds(cxcz, sy, sxsz)
    m[5] = fmadds(sxsz, sy, cxcz)
    m[3] = f32(tx); m[7] = f32(ty); m[11] = f32(tz)


# ==== her keyframe bank ==========================================================================
cdef class Zl1AnimData:
    """IMMUTABLE Zl1 eye-chain keyframe data -- the 2 regime anims x the 5 CHAIN joints, in the same
    flat layout `AnimData` uses for Link. Built once and shared by every `Zl1LookCore` (and so by
    every clone in a fan), exactly as AnimData is shared across PoseEngines."""
    cdef int _meta[Z_NANM][Z_NCH][3][3][3]     # [anim][chain slot][s/r/t][axis][cnt, off, tt]
    cdef double* _sdata[Z_NANM]
    cdef double* _rdata[Z_NANM]
    cdef double* _tdata[Z_NANM]
    cdef int _dec[Z_NANM]
    cdef double _fmax[Z_NANM]

    def __cinit__(self):
        cdef int i
        for i in range(Z_NANM):
            self._sdata[i] = NULL; self._rdata[i] = NULL; self._tdata[i] = NULL

    def __dealloc__(self):
        cdef int i
        for i in range(Z_NANM):
            if self._sdata[i] != NULL: free(self._sdata[i])
            if self._rdata[i] != NULL: free(self._rdata[i])
            if self._tdata[i] != NULL: free(self._tdata[i])

    def add_anim(self, int idx, anm, chain):
        """Register a parsed BCK (a j3d_eval anm dict) at slot `idx` (0 = wait03, 1 = look).

        ASSERTS the scale tracks are static 1.0 on every chain joint. `Zl1Morf.pose_locals` ignores
        scale entirely -- neither the tr_matrix path nor the quat path multiplies it in -- and that
        is only correct because the data says so. Checking it here makes the omission explicit
        instead of an undocumented assumption in a C loop."""
        cdef list sd = anm['scale_data'], rd = anm['rot_data'], td = anm['trans_data']
        cdef int ns = len(sd), nr = len(rd), nt = len(td), i, slot, track, axis
        self._sdata[idx] = <double*>malloc(ns * sizeof(double))
        self._rdata[idx] = <double*>malloc(nr * sizeof(double))
        self._tdata[idx] = <double*>malloc(nt * sizeof(double))
        for i in range(ns): self._sdata[idx][i] = sd[i]
        for i in range(nr): self._rdata[idx][i] = <double>(<long long>rd[i])
        for i in range(nt): self._tdata[idx][i] = td[i]
        self._dec[idx] = anm['dec_shift']
        self._fmax[idx] = float(anm['frame_max'])
        cdef list joints = anm['joints']
        cdef list keys = ['s', 'r', 't']
        for slot in range(Z_NCH):
            j = joints[chain[slot]]
            for track in range(3):
                trk = j[keys[track]]
                for axis in range(3):
                    m = trk[axis]
                    self._meta[idx][slot][track][axis][0] = m[0]
                    self._meta[idx][slot][track][axis][1] = m[1]
                    self._meta[idx][slot][track][axis][2] = m[2]
            for axis in range(3):
                cnt, off, _tt = j['s'][axis]
                if cnt == 0:
                    continue
                if cnt != 1 or float(sd[off]) != 1.0:
                    raise ValueError(
                        "Zl1 anim %d joint %d scale axis %d is not static 1.0 (cnt=%d) -- the eye "
                        "chain's pose path drops scale, which is only valid while this holds"
                        % (idx, chain[slot], axis, cnt))


_ZL1_DATA_CACHE = []


def zl1_anim_data(anms, chain, name_wait03, name_look):
    """Build (and cache) the shared `Zl1AnimData` from `core.npc_zl1_look.load()`'s anim dict.
    Cached like `fk.load`: the parsed data is read-only truth, so one bank serves every run."""
    if _ZL1_DATA_CACHE:
        return _ZL1_DATA_CACHE[0]
    cdef Zl1AnimData d = Zl1AnimData()
    d.add_anim(0, anms[name_wait03], chain)
    d.add_anim(1, anms[name_look], chain)
    _ZL1_DATA_CACHE.append(d)
    return d


# ==== her per-frame state ========================================================================
cdef class Zl1LookCore:
    """`Zl1Look` + its `Zl1JntCtrl` and `Zl1Morf`, resident in C. One `_step_c` call is her whole
    execute frame: optn_1 -> lookBack -> play_animation -> setMtx -> setAttention."""
    cdef Zl1AnimData data
    cdef int* _meta_p
    cdef double** _sdata_p
    cdef double** _rdata_p
    cdef double** _tdata_p
    cdef int* _dec_p
    cdef double* _fmax_p
    # --- Zl1JntCtrl: mAngles[i][j] chase state (s32 -- cLib_addCalcAngleL never wraps) ---
    cdef long long _ang[2][2]
    cdef long long _f2c, _f2e, _f30, _f32
    cdef bint _trn, _head_lock, _bbone_lock
    cdef long long _turn_step
    # --- Zl1Morf: the J3DFrameCtrl + the morf blend against the per-joint stored old pose ---
    cdef int _anm                     # data slot: 0 wait03 / 1 look
    cdef int _attr, _mstate
    cdef double _start, _end, _loop, _rate, _frame
    cdef double _cur_morf, _prev_morf, _morf_step
    cdef double _oldq[Z_NCH][4]
    cdef double _oldt[Z_NCH][3]
    # --- Zl1Look ---
    cdef int _cur_anm                 # field_0x849: the game's anim NUMBER (8 wait03 / 12 look)
    cdef int _f84d, _f7b8, _f7ba, _f7bc, _f7c3
    cdef double _m_frame
    cdef long long _f83c, _f83e
    cdef double _eye[3]
    cdef double _tattn[3]
    cdef double _head_org[3]
    cdef long long _counter
    cdef bint _rng_horizon
    cdef long long _angle_y
    cdef int _err                     # 0 ok / 1 = f84d left the modeled stt-3 regime (see step())

    def __cinit__(self, Zl1AnimData data):
        self.data = data
        self._meta_p = &data._meta[0][0][0][0][0]
        self._sdata_p = &data._sdata[0]
        self._rdata_p = &data._rdata[0]
        self._tdata_p = &data._tdata[0]
        self._dec_p = &data._dec[0]
        self._fmax_p = &data._fmax[0]
        self._err = 0

    def clone(self):
        """A branch copy: shares the immutable bank, copies every mutable field (the roll fan clones
        a node into a whole aim fan, so this owes bit-identity -- gated)."""
        cdef Zl1LookCore c = Zl1LookCore(self.data)
        cdef int i, j
        for i in range(2):
            for j in range(2):
                c._ang[i][j] = self._ang[i][j]
        c._f2c = self._f2c; c._f2e = self._f2e; c._f30 = self._f30; c._f32 = self._f32
        c._trn = self._trn; c._head_lock = self._head_lock; c._bbone_lock = self._bbone_lock
        c._turn_step = self._turn_step
        c._anm = self._anm; c._attr = self._attr; c._mstate = self._mstate
        c._start = self._start; c._end = self._end; c._loop = self._loop
        c._rate = self._rate; c._frame = self._frame
        c._cur_morf = self._cur_morf; c._prev_morf = self._prev_morf; c._morf_step = self._morf_step
        for i in range(Z_NCH):
            for j in range(4):
                c._oldq[i][j] = self._oldq[i][j]
            for j in range(3):
                c._oldt[i][j] = self._oldt[i][j]
        c._cur_anm = self._cur_anm; c._f84d = self._f84d; c._f7b8 = self._f7b8
        c._f7ba = self._f7ba; c._f7bc = self._f7bc; c._f7c3 = self._f7c3
        c._m_frame = self._m_frame; c._f83c = self._f83c; c._f83e = self._f83e
        for i in range(3):
            c._eye[i] = self._eye[i]
            c._tattn[i] = self._tattn[i]
            c._head_org[i] = self._head_org[i]
        c._counter = self._counter; c._rng_horizon = self._rng_horizon
        c._angle_y = self._angle_y; c._err = self._err
        return c

    def seed_from(self, zl1):
        """Seed from a Python `Zl1Look` (itself seeded from the live probe row) -- the ONE place the
        two representations meet, so the native run starts from the fixture the wired one does."""
        cdef int i, j, jnt
        m = zl1.morf
        for i in range(2):
            for j in range(2):
                self._ang[i][j] = int(zl1.jnt.angles[i][j])
        self._f2c = int(zl1.jnt.f2c); self._f2e = int(zl1.jnt.f2e)
        self._f30 = int(zl1.jnt.f30); self._f32 = int(zl1.jnt.f32)
        self._trn = bool(zl1.jnt.trn)
        self._head_lock = bool(zl1.jnt.head_lock); self._bbone_lock = bool(zl1.jnt.bbone_lock)
        self._turn_step = int(zl1.jnt.turn_step)
        self._cur_anm = int(zl1.cur_anm)
        self._anm = 1 if self._cur_anm == _Z_NUM_LOOK else 0
        self._attr = int(m.attr); self._mstate = int(m.state)
        self._start = float(m.start); self._end = float(m.end); self._loop = float(m.loop)
        self._rate = float(m.rate); self._frame = float(m.frame)
        self._cur_morf = float(m.cur_morf); self._prev_morf = float(m.prev_morf)
        self._morf_step = float(m.morf_step)
        for i in range(Z_NCH):
            jnt = _Z_CHAIN[i]
            q = m.old_quat[jnt]; t = m.old_trans[jnt]
            for j in range(4):
                self._oldq[i][j] = q[j]
            for j in range(3):
                self._oldt[i][j] = t[j]
        self._f84d = int(zl1.f84d); self._f7b8 = int(zl1.f7b8); self._f7ba = int(zl1.f7ba)
        self._f7bc = int(zl1.f7bc); self._f7c3 = int(zl1.f7c3)
        self._m_frame = float(zl1.m_frame)
        self._f83c = int(zl1.f83c); self._f83e = int(zl1.f83e)
        for i in range(3):
            self._eye[i] = float(zl1.eye[i])
            self._tattn[i] = 0.0
            self._head_org[i] = float(zl1.head_org[i])
        self._counter = int(zl1.counter)
        self._rng_horizon = bool(zl1.rng_horizon)
        self._angle_y = _s16c(int(zl1.angle_y) & 0xFFFF)
        self._err = 0

    def snapshot(self):
        """Her whole hidden state, in the shape the gate compares against the Python model. The
        old-pose store is in here on purpose: it is rewritten every frame and only reaches the eye
        through the NEXT morf blend, so a wrong store is silent for one frame and then diverges."""
        cdef int i, j
        return dict(
            eye=(self._eye[0], self._eye[1], self._eye[2]),
            angles=((self._ang[0][0], self._ang[0][1]), (self._ang[1][0], self._ang[1][1])),
            targets=(self._f2c, self._f2e, self._f30, self._f32),
            trn=bool(self._trn), turn_step=int(self._turn_step),
            cur_anm=int(self._cur_anm), f84d=int(self._f84d), f7b8=int(self._f7b8),
            f7ba=int(self._f7ba), f7bc=int(self._f7bc), f7c3=int(self._f7c3),
            m_frame=self._m_frame, f83c=int(self._f83c), f83e=int(self._f83e),
            counter=int(self._counter), rng_horizon=bool(self._rng_horizon),
            angle_y=int(self._angle_y),
            head_org=(self._head_org[0], self._head_org[1], self._head_org[2]),
            frame=self._frame, cur_morf=self._cur_morf, prev_morf=self._prev_morf,
            morf_step=self._morf_step, end=int(self._end), loop=int(self._loop),
            rate=self._rate, attr=int(self._attr),
            old_quat=tuple(tuple(self._oldq[i][j] for j in range(4)) for i in range(Z_NCH)),
            old_trans=tuple(tuple(self._oldt[i][j] for j in range(3)) for i in range(Z_NCH)),
        )

    @property
    def eye(self):
        return (self._eye[0], self._eye[1], self._eye[2])

    @property
    def tattn(self):
        return (self._tattn[0], self._tattn[1], self._tattn[2])

    @property
    def rng_horizon(self):
        """True once a `cLib_getRndValue` re-seed was needed -- past this the offline model is
        holding the rnd floor and is no longer tracking the console (same horizon the Python model
        flags)."""
        return bool(self._rng_horizon)

    def check(self):
        """Raise whatever the Python model would have raised. `_step_c` is `noexcept nogil`, so an
        out-of-regime look mode sets a flag instead; the Python-side driver calls this."""
        if self._err == 1:
            raise AssertionError("Zl1 look mode %d out of the modeled stt-3 regime" % self._f84d)

    # ---- setAnm_NUM -> setAnm_anm (no-op while already playing; field_0x849 check) --------------
    cdef void _set_anm_c(self, int num) noexcept nogil:
        if self._cur_anm == num:
            return
        self._anm = 1 if num == _Z_NUM_LOOK else 0
        self._start = 0.0
        self._end = self._fmax_p[self._anm]           # J3DFrameCtrl::init(getFrameMax())
        self._attr = 2                                # EMode_LOOP (both regime anims)
        self._rate = f32(_Z_ANM_SPEED)
        self._frame = 0.0
        self._loop = 0.0
        # setMorf: prev_morf >= 0 after the first anm -> cur = 0, step = 1/morf; prev = cur
        if self._prev_morf < 0.0 or _Z_ANM_MORF <= 0.0:
            self._cur_morf = 1.0
        else:
            self._cur_morf = 0.0
            self._morf_step = fdivs(1.0, f32(_Z_ANM_MORF))
        self._prev_morf = self._cur_morf
        self._cur_anm = num
        self._f7c3 = 0
        self._m_frame = 0.0

    # ---- optn_1 (stt-3, in plow range, no talk): the look timer machine -------------------------
    cdef void _optn_1_c(self) noexcept nogil:
        if self._cur_anm == _Z_NUM_LOOK:
            # `field_0x7C3 && cLib_calcTimer(&field_0x7BA) == 0` -- the timer only DECREMENTS when
            # the anim-wrapped flag is set (short-circuit), then tests the NEW value.
            if self._f7c3 != 0:
                if self._f7ba != 0:
                    self._f7ba -= 1
                if self._f7ba == 0:
                    # the game re-seeds 7B8 from the GLOBAL RNG stream -- unmodelable offline, so
                    # flag the horizon and hold the rnd floor (same as the Python model).
                    self._set_anm_c(_Z_NUM_WAIT03)
                    self._f7b8 = _Z_RND_FLOOR
                    self._rng_horizon = True
            self._f84d = 0
            return
        if self._f7b8 != 0:
            self._f7b8 -= 1
        if self._f7b8 == 0:
            self._set_anm_c(_Z_NUM_LOOK)
            self._f7ba = <int>(self._counter & 1) + 1
            self._f84d = 0
            return
        self._f84d = 1

    # ---- chkLim / the head<->backbone splits (dNpc_JntCtrl_c) -----------------------------------
    cdef inline long long _chk_lim_c(self, long long angle, int i, int j) noexcept nogil:
        cdef long long a = _s16c(angle & 0xFFFF)
        if a > _Z_MAXA[i][j]:
            a = _Z_MAXA[i][j]
        if a < _Z_MINA[i][j]:
            a = _Z_MINA[i][j]
        return a

    cdef void _turn_h2b_c(self, long long delta, long long* out) noexcept nogil:
        """turn_fromHead2Backbone (d_npc.cpp:800) -> (head_y, bbone_y) targets."""
        cdef long long head = 0, bbone = 0
        if not self._head_lock:
            head = self._chk_lim_c(_s16c((delta - self._f32) & 0xFFFF), 0, 1)
        if not self._bbone_lock:
            bbone = self._chk_lim_c(_s16c((delta - head) & 0xFFFF), 1, 1)
        out[0] = head; out[1] = bbone

    cdef void _turn_b2h_c(self, long long delta, long long* out) noexcept nogil:
        """turn_fromBackbone2Head (d_npc.cpp:783). The guard reads the OLD backbone target."""
        cdef long long head = 0, bbone = 0
        if not self._bbone_lock:
            bbone = self._chk_lim_c(delta, 1, 1)
            if self._f32 and bbone < 0:
                bbone = 0
        if not self._head_lock:
            head = self._chk_lim_c(_s16c((delta - bbone) & 0xFFFF), 0, 1)
        out[0] = head; out[1] = bbone

    cdef void _look_at_target_2_c(self, bint has_target, double tx, double ty, double tz,
                                  double sx, double sy, double sz) noexcept nogil:
        """lookAtTarget_2 (d_npc.cpp:827-915) for the stt-3 regime. `has_target` False = the
        default-yaw arm (target_y = current.angle.y, target_x = 0).

        The mbTrn body-turn branch is NOT reachable here and so is not ported: optn_1 sets
        field_0x7D8, which is `no_body_turn` at the call site, and the Python model asserts if it is
        ever entered. Only the else arm (the `trn` recompute) runs."""
        cdef long long target_y, target_x, delta_y, tsum
        cdef long long ht[2]
        cdef double dx, dy, dz
        if has_target:
            target_y = _s16c(_cm_atan2s_c(fsubs(tx, sx), fsubs(tz, sz)) & 0xFFFF)
            dx = fsubs(tx, sx); dy = fsubs(ty, sy); dz = fsubs(tz, sz)
            target_x = _s16c(_cm_atan2s_c(dy, _abs_xz_c(dx, dz)) & 0xFFFF)
        else:
            target_y = _s16c(self._angle_y & 0xFFFF)
            target_x = 0

        delta_y = _s16c((target_y - self._angle_y) & 0xFFFF)
        if self._f32 >= 0:
            if delta_y >= self._f32 or self._f32 == 0:
                self._turn_h2b_c(delta_y, ht)
            else:
                self._turn_b2h_c(delta_y, ht)
        else:
            if delta_y <= self._f32 or self._f32 == 0:
                self._turn_h2b_c(delta_y, ht)
            else:
                self._turn_b2h_c(delta_y, ht)
        self._f2e = ht[0]
        self._f32 = ht[1]
        self._ang[0][1] = _clib_addcalc_anglel(self._ang[0][1], ht[0], _Z_CHASE_SCALE,
                                               self._turn_step, _Z_CHASE_MIN)
        self._ang[1][1] = _clib_addcalc_anglel(self._ang[1][1], ht[1], _Z_CHASE_SCALE,
                                               self._turn_step, _Z_CHASE_MIN)
        tsum = ht[0] + ht[1]
        self._trn = (delta_y > tsum) if delta_y >= 0 else (delta_y < tsum)

        # X (elevation) split: head clamp first, remainder to the backbone
        cdef long long head_x = self._chk_lim_c(target_x, 0, 0)
        cdef long long bb_x = self._chk_lim_c(_s16c((target_x - head_x) & 0xFFFF), 1, 0)
        self._f2c = head_x
        self._f30 = bb_x
        self._ang[0][0] = _clib_addcalc_anglel(self._ang[0][0], head_x, _Z_CHASE_SCALE,
                                               self._turn_step, _Z_CHASE_MIN)
        self._ang[1][0] = _clib_addcalc_anglel(self._ang[1][0], bb_x, _Z_CHASE_SCALE,
                                               self._turn_step, _Z_CHASE_MIN)

    # ---- McaMorf::play + J3DFrameCtrl::update (LOOP) -------------------------------------------
    cdef void _play_c(self) noexcept nogil:
        if self._cur_morf < 1.0:
            self._prev_morf = self._cur_morf
            self._cur_morf = _clib_chasef(self._cur_morf, 1.0, self._morf_step)
        self._mstate = 0
        self._frame = fadds(self._frame, self._rate)
        while self._frame < self._start:
            self._mstate |= 2
            if f32(self._loop - self._start) <= 0.0:
                break
            self._frame = fadds(self._frame, f32(self._loop - self._start))
        while self._frame >= self._end:
            self._mstate |= 2
            if f32(self._end - self._loop) <= 0.0:
                break
            self._frame = fsubs(self._frame, f32(self._end - self._loop))

    cdef void _calc_transform_c(self, double frame, int slot,
                                long long* rot, double* trans) noexcept nogil:
        """j3d_eval.calc_transform for one chain joint of the CURRENT anim. Scale is not read: it is
        static 1.0 on every chain joint (asserted in `Zl1AnimData.add_anim`) and her pose path drops
        it, unlike Link's."""
        cdef int anim = self._anm
        cdef int* m = self._meta_p
        cdef int axis, cnt, off, tt, dec = self._dec_p[anim]
        cdef double v
        cdef double* rd = self._rdata_p[anim]
        cdef double* td = self._tdata_p[anim]
        for axis in range(3):
            cnt = m[((((anim * Z_NCH + slot) * 3 + 1) * 3 + axis) * 3) + 0]
            off = m[((((anim * Z_NCH + slot) * 3 + 1) * 3 + axis) * 3) + 1]
            tt = m[((((anim * Z_NCH + slot) * 3 + 1) * 3 + axis) * 3) + 2]
            if cnt == 0:
                rot[axis] = 0
            elif cnt == 1:
                rot[axis] = _as_s32c((<long long>rd[off]) << dec)
            else:
                v = _keyframe_interp_c(frame, cnt, tt, rd, off, 1)
                rot[axis] = _as_s32c((<long long>v) << dec)
            cnt = m[((((anim * Z_NCH + slot) * 3 + 2) * 3 + axis) * 3) + 0]
            off = m[((((anim * Z_NCH + slot) * 3 + 2) * 3 + axis) * 3) + 1]
            tt = m[((((anim * Z_NCH + slot) * 3 + 2) * 3 + axis) * 3) + 2]
            if cnt == 0:
                trans[axis] = 0.0
            elif cnt == 1:
                trans[axis] = f32(td[off])
            else:
                trans[axis] = _keyframe_interp_c(frame, cnt, tt, td, off, 0)

    cdef void _pose_locals_c(self, double* locals_) noexcept nogil:
        """`Zl1Morf.pose_locals`: the CHAIN joints' local 3x4 at the current frame, updating the
        old-pose store. Non-morf = J3DGetTranslateRotateMtx off the anim TRS; morf = JMAQuatLerp
        (store, new) + mDoMtx_quat + a NON-fused translate lerp. `locals_` is Z_NCH * 12 doubles."""
        cdef int i, k
        cdef long long rot[3]
        cdef double trans[3]
        cdef double qn[4]
        cdef double q[4]
        cdef double oq[4]
        cdef double t[3]
        cdef double f31 = 0.0, f30 = 0.0
        cdef bint morf_on = self._cur_morf < 1.0
        if morf_on:
            f31 = fdivs(fsubs(self._cur_morf, self._prev_morf), fsubs(1.0, self._prev_morf))
            f30 = fsubs(1.0, f31)
        for i in range(Z_NCH):
            self._calc_transform_c(self._frame, i, rot, trans)
            if not morf_on:
                _euler_to_quat_c(rot[0], rot[1], rot[2], q)
                for k in range(4):
                    self._oldq[i][k] = q[k]
                for k in range(3):
                    self._oldt[i][k] = trans[k]
                _tr_matrix_c(rot[0], rot[1], rot[2], trans[0], trans[1], trans[2],
                             &locals_[i * 12])
            else:
                _euler_to_quat_c(rot[0], rot[1], rot[2], qn)
                for k in range(4):
                    oq[k] = self._oldq[i][k]
                _quat_lerp_c(oq, qn, f31, q)
                # translate lerp is NON-fused (m_Do_ext.cpp:1394-1396): old*f30 + new*f31
                for k in range(3):
                    t[k] = fadds(fmuls(self._oldt[i][k], f30), fmuls(trans[k], f31))
                for k in range(4):
                    self._oldq[i][k] = q[k]
                for k in range(3):
                    self._oldt[i][k] = t[k]
                _psmtx_quat_c(q, &locals_[i * 12])
                locals_[i * 12 + 3] = f32(t[0])
                locals_[i * 12 + 7] = f32(t[1])
                locals_[i * 12 + 11] = f32(t[2])

    cdef void _pose_eye_c(self, double px, double py, double pz) noexcept nogil:
        """setMtx: base = transS(pos) * ZXYrotM(0, angle_y, 0); chain FK with the backbone CB
        (XrotM(bb_y) ZrotM(-bb_x)) and the head CB (YrotM(-f83C) ZrotM(-f83E)); eye = M * EYE_OFF.
        Writes `_head_org` (the head joint's world origin, before the twist) and `_eye`."""
        cdef double locals_[Z_NCH * 12]
        self._pose_locals_c(locals_)
        cdef long long fc = self._angle_y & 0xFFFF
        cdef double c = jma_cos(fc), s = jma_sin(fc)
        cdef double bufA[12]
        cdef double bufB[12]
        cdef double rm[12]
        cdef double* cur = bufA
        cdef double* nxt = bufB
        cdef double* swp
        cdef int i
        # fk.world_base at lean 0: no ZrotS concat (that arm is Link's shape_angle.z, not hers).
        cur[0] = c;        cur[1] = 0.0; cur[2] = s;   cur[3] = f32(px)
        cur[4] = 0.0;      cur[5] = 1.0; cur[6] = 0.0; cur[7] = f32(py)
        cur[8] = f32(-s);  cur[9] = 0.0; cur[10] = c;  cur[11] = f32(pz)
        for i in range(Z_BB + 1):                      # chain slots 0, 1, 2 (joints 0, 1, chest)
            _concat_c(cur, &locals_[i * 12], nxt)
            swp = cur; cur = nxt; nxt = swp
        # nodeCB_BackBone (:196): XrotM(getBackbone_y()); ZrotM(-getBackbone_x())
        _rot_x_c(self._ang[1][1], rm)
        _concat_c(cur, rm, nxt); swp = cur; cur = nxt; nxt = swp
        _rot_z_c(-self._ang[1][0], rm)
        _concat_c(cur, rm, nxt); swp = cur; cur = nxt; nxt = swp
        for i in range(Z_BB + 1, Z_NCH):               # chain slots 3, 4 (neck, head)
            _concat_c(cur, &locals_[i * 12], nxt)
            swp = cur; cur = nxt; nxt = swp
        # nodeCB_Head (:167): the head world origin, then the -half-angle twist, then the eye offset
        self._head_org[0] = cur[3]; self._head_org[1] = cur[7]; self._head_org[2] = cur[11]
        _rot_y_c(-self._f83c, rm)
        _concat_c(cur, rm, nxt); swp = cur; cur = nxt; nxt = swp
        _rot_z_c(-self._f83e, rm)
        _concat_c(cur, rm, nxt); swp = cur; cur = nxt; nxt = swp
        _mv_c(cur, _Z_EYE_OFF[0], _Z_EYE_OFF[1], _Z_EYE_OFF[2], self._eye)

    cdef void _step_c(self, double pre_x, double pre_z,
                      double post_x, double post_y, double post_z,
                      double link_x, double link_z, double link_head_top_y) noexcept nogil:
        """One Zl1 execute frame (`Zl1Look.step`). `pre_*` = her position BEFORE this frame's CC
        plow (lookBack runs before posMoveF), `post_*` = after (what setMtx/setAttention use)."""
        cdef double src_y = self._eye[1]           # lookBack src carries her PREVIOUS eyePos.y
        cdef double ty
        cdef long long hy, hx
        self._counter += 1
        self._optn_1_c()
        if self._f84d == 1:
            ty = fadds(f32(link_head_top_y), f32(_Z_PLAYER_EYE_Y))
            self._look_at_target_2_c(True, link_x, ty, link_z, pre_x, src_y, pre_z)
        elif self._f84d == 0:
            self._look_at_target_2_c(False, 0.0, 0.0, 0.0, pre_x, src_y, pre_z)
        else:
            self._err = 1
            return
        hy = self._ang[0][1]; hx = self._ang[0][0]
        self._f83c = _half_toward_zero(hy)
        self._f83e = _half_toward_zero(hx)
        # play_animation: morf/frame advance + the wrap-detect anim-completed flag
        self._play_c()
        self._f7c3 = 1 if self._frame < self._m_frame else 0
        self._m_frame = self._frame
        self._pose_eye_c(post_x, post_y, post_z)
        self._tattn[0] = post_x
        self._tattn[1] = fadds(f32(post_y), f32(_Z_ATTN_Y_OFF))
        self._tattn[2] = post_z


# ==== Link's neck: m3564 =========================================================================
cdef class NeckLookCore:
    """`NeckLook` (setNeckAngle's m3564 chase) plus the cached previous-frame exec head MATRIX it
    measures. The matrix lives here because it is the neck's own input and nothing else reads it."""
    cdef long long _x, _y, _z
    cdef double _head_mtx[12]

    def clone(self):
        cdef NeckLookCore c = NeckLookCore.__new__(NeckLookCore)
        cdef int i
        c._x = self._x; c._y = self._y; c._z = self._z
        for i in range(12):
            c._head_mtx[i] = self._head_mtx[i]
        return c

    def seed(self, neck, head_mtx):
        """Seed from a Python `NeckLook` + the f0 exec head matrix (what f1's setNeckAngle measures)."""
        cdef int i
        self._x = _s16c(int(neck.x) & 0xFFFF)
        self._y = _s16c(int(neck.y) & 0xFFFF)
        self._z = _s16c(int(neck.z) & 0xFFFF)
        for i in range(3):
            row = head_mtx[i]
            self._head_mtx[i*4+0] = row[0]; self._head_mtx[i*4+1] = row[1]
            self._head_mtx[i*4+2] = row[2]; self._head_mtx[i*4+3] = row[3]

    def snapshot(self):
        return (int(self._x), int(self._y), int(self._z))

    @property
    def head_mtx(self):
        return ((self._head_mtx[0], self._head_mtx[1], self._head_mtx[2], self._head_mtx[3]),
                (self._head_mtx[4], self._head_mtx[5], self._head_mtx[6], self._head_mtx[7]),
                (self._head_mtx[8], self._head_mtx[9], self._head_mtx[10], self._head_mtx[11]))

    cdef bint _select_look_pos_c(self, double px, double pz, double ex, double ez,
                                 long long m34de, bint have_eye, bint locked,
                                 bint list_present) noexcept nogil:
        """The reachable `sp18` selection (:9014-9046): the locked actor's eyePos, or the
        stocked lock-on list head's, both through the +-0x6000 cone of m34DE."""
        if not have_eye or not (locked or list_present):
            return False
        cdef long long bearing = _cm_atan2s_c(fsubs(f32(ex), f32(px)), fsubs(f32(ez), f32(pz)))
        cdef long long d = _s16c((bearing - m34de) & 0xFFFF)   # cLib_distanceAngleS
        if d < 0:
            d = -d
        return d <= _N_CONE_HALF

    cdef void _update_c(self, long long m34de, int proc, bint has_look,
                        double lx, double ly, double lz) noexcept nogil:
        """One setNeckAngle m3564 pass off the CACHED previous-frame head matrix (`NeckLook.update`)."""
        cdef bint flg80 = (0 <= proc < N_PROCTAB) and _N_FLG80[proc]
        cdef bint flg8m = (0 <= proc < N_PROCTAB) and _N_FLG8M[proc]
        cdef bint gate = (flg80 or flg8m) and has_look
        cdef double spC4[3]
        cdef double sp88[3]
        cdef double spAC[3]
        cdef double spB8[3]
        cdef long long r24_4, r25_3, r27, r23_3, r4, r23, t
        cdef int i
        # :9070-9083 -- the previous pose's own head angles, current twist removed. Computed
        # UNCONDITIONALLY in the decomp (the :9159 clamp consumes r25_3 even when the gate fails).
        _mv_c(self._head_mtx, _N_HEAD_CTR[0], _N_HEAD_CTR[1], _N_HEAD_CTR[2], spC4)
        _mv_c(self._head_mtx, _N_EYE_OFF[0], _N_EYE_OFF[1], _N_EYE_OFF[2], sp88)
        for i in range(3):
            spAC[i] = fsubs(sp88[i], spC4[i])
        r24_4 = _s16c((_cm_atan2s_c(f32(-spAC[1]), _abs_xz_c(spAC[0], spAC[2])) - self._x) & 0xFFFF)
        r25_3 = _s16c((_cm_atan2s_c(spAC[0], spAC[2]) - m34de - self._y) & 0xFFFF)

        if gate:
            spB8[0] = fsubs(f32(lx), spC4[0])
            spB8[1] = fsubs(f32(ly), spC4[1])
            spB8[2] = fsubs(f32(lz), spC4[2])
            r27 = _s16c(_cm_atan2s_c(f32(-spB8[1]), _abs_xz_c(spB8[0], spB8[2])) & 0xFFFF)
            r23_3 = _s16c((_cm_atan2s_c(spB8[0], spB8[2]) - m34de) & 0xFFFF)
            if _abs_xz_c(spB8[0], spB8[2]) < 30.0:
                r23_3 = self._y
            if r27 > _N_PITCH_MAX:
                r27 = _N_PITCH_MAX
            elif r27 < _N_PITCH_MIN:
                r27 = _N_PITCH_MIN
            if r23_3 > _N_YAW_CLAMP:
                r23_3 = _N_YAW_CLAMP
            elif r23_3 < -_N_YAW_CLAMP:
                r23_3 = -_N_YAW_CLAMP
            if flg80:
                # :9103-9110 half-angle (the upper anim is never DASHKAZE in the land regime).
                r4 = _s16c(((r27 >> 1) - r24_4) & 0xFFFF)
                r23 = _s16c(((r23_3 >> 1) - r25_3) & 0xFFFF)
            else:
                r4 = _s16c((r27 - r24_4) & 0xFFFF)
                r23 = _s16c((r23_3 - r25_3) & 0xFFFF)
        else:
            # Gate failed: every reachable else-branch lands r4 = r23 = 0.
            r4 = 0
            r23 = 0

        self._x = _s16c(_clib_addcalc_angles(self._x & 0xFFFF, r4 & 0xFFFF,
                                             _N_CH_SCALE, _N_CH_MAX, _N_CH_MIN))
        self._y = _s16c(_clib_addcalc_angles(self._y & 0xFFFF, r23 & 0xFFFF,
                                             _N_CH_SCALE, _N_CH_MAX, _N_CH_MIN))
        if flg80:
            # :9159-9165 -- keep the SUMMED yaw (anim + twist) inside the clamp (gated on
            # ModeFlg_00000080 alone, NOT on a selected look pos).
            t = _s16c((r25_3 + self._y) & 0xFFFF)
            if t > _N_YAW_CLAMP:
                self._y = _s16c((_N_YAW_CLAMP - r25_3) & 0xFFFF)
            elif t < -_N_YAW_CLAMP:
                self._y = _s16c((-(_N_YAW_CLAMP + r25_3)) & 0xFFFF)
        self._z = _s16c(_clib_addcalc_angles(self._z & 0xFFFF, 0,
                                             _N_CH_SCALE, _N_CH_MAX, _N_CH_MIN))
