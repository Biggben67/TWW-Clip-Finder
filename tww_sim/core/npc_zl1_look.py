"""FP-faithful model of Tetra's (NPC ``Zl1``) look-at head: **eyePos** + **attention_info.position**.

The two per-frame Tetra outputs the coupled courtyard replay/planner consumes that the follow model
(:mod:`npc_zl1`) does not produce:

1. ``attention_info.position`` (**tattn**, the camera's lock target) -- ``setAttention``
   (d_a_npc_zl1.cpp:1277): ``(pos.x, f32(pos.y + 140.0), pos.z)`` at her POST-move position.
2. ``eyePos`` (the proc-9 ``setShapeAngleToAtnActor`` re-aim target) -- her ANIMATED head-joint
   world position + the ``(20, -16, 0)`` eye offset (``_nodeCB_Head``, :167-182), where the head
   pose = the playing BCK (wait03/look, via ``mDoExt_McaMorf``) composed with the
   ``dNpc_JntCtrl_c`` look-at chase (``lookAtTarget_2``, d_npc.cpp:828-915) applied through the
   two node callbacks (backbone = chest joint 2: ``XrotM(bb_y) ZrotM(-bb_x)``; head joint 6:
   ``YrotM(-head_y/2) ZrotM(-head_x/2)`` -- the half-angle twist, the other half goes to the
   pupils) at the model base ``transS(pos) * ZXYrotM(current.angle)`` (``setMtx``, :521-575).

Scope = the **stt-3 courtyard regime** (she is plowed, ``optn_1`` runs every frame, dist < 230):
the look-target state machine is ``field_0x84D == 1`` (target = ``dNpc_playerEyePos(-20)`` =
Link's head-top Y over his feet XZ) with the random look-around timer (``field_0x7B8``, seeded
``rnd(90, 180)`` at ``setStt(3)``) that switches to ``look.bck`` + ``field_0x84D = 0``. The
timer/anim state is deterministic given the live-captured seed EXCEPT the ``cLib_getRndValue``
re-seed after a full look cycle completes -- the model flags that horizon (``rng_horizon``) the
same way the FreeRun follow guard flags dist > 230. Event/talk/demo branches are out of scope
(asserted unreachable).

Execute-frame order modeled (``_execute``, :2784-2846): ``optn_1`` (timers -> ``field_0x84D``,
possible ``setAnm``) -> ``lookBack`` (JntCtrl chase; src = her PRE-move pos with her PREVIOUS
eyePos.y) -> [CC move consumed] -> ``play_animation`` (McaMorf frame/morf advance + wrap detect)
-> ``setMtx`` (FK at the POST-move pos) -> ``setAttention`` (eyePos + tattn writes).

Decomp-grounded (GZLJ01; US line numbers, logic identical): ``d_a_npc_zl1.cpp`` (``optn_1``,
``lookBack``, ``setAnm_NUM``/``setAnm_anm``, ``_nodeCB_Head``/``_nodeCB_BackBone``, ``setMtx``,
``setAttention``, ``play_animation``, HIO ``a_prm_tbl``), ``d_npc.cpp`` (``dNpc_JntCtrl_c``:
``lookAtTarget_2``, ``turn_fromHead2Backbone``/``turn_fromBackbone2Head``, ``chkLim``,
``setParam``, ``follow_current``; ``dNpc_playerEyePos``), ``m_Do_ext.cpp`` (``mDoExt_McaMorf``
ctor/``setAnm``/``setMorf``/``play``/``calc``), ``J3DAnimation.cpp`` (``J3DFrameCtrl::update``),
``m_Do_mtx.cpp`` (rot conventions), ``c_lib.cpp`` (``cLib_addCalcAngleL``, ``cLib_calcTimer``,
``cLib_chaseF``). Skeleton/anim data = ``_generated/anim/zl1_{skeleton,anims}.json``
(``harness/anim/extract_zl1.py``; gitignored, dev-supplied). Pure stdlib + ``core.fp`` /
``core.mathlib`` / ``core.anim``. No Dolphin dependency.
"""
import os, json

from .fp import f32 as _f, fadds, fsubs, fmuls
from . import fp
from . import mathlib as S
from .anim import fk
from .anim import j3d_eval
from .anim import quat as Q
from .npc_zl1 import _s16, cLib_chaseF

# --- Zl1 skeleton: the eye chain world_root -> stomach -> chest -> neck -> head ----------------
CHAIN = (0, 1, 2, 5, 6)
BBONE_JNT = 2                    # "chest" (m_bbone_jnt_num) -- nodeCB_BackBone
HEAD_JNT = 6                     # "head"  (m_hed_jnt_num)   -- nodeCB_Head
EYE_OFF = (20.0, -16.0, 0.0)     # a_eye_pos_off (_nodeCB_Head :169)

# --- HIO params (daNpc_Zl1_HIO_c a_prm_tbl, d_a_npc_zl1.cpp:85-118) ----------------------------
ATTN_Y_OFF = 140.0               # field_1C: attention_info.position.y = pos.y + this
MAX_HEAD_X, MAX_HEAD_Y = 0x18E2, 0x2328
MIN_HEAD_X, MIN_HEAD_Y = _s16(0xE71E), _s16(0xDCD8)
MAX_BB_X, MAX_BB_Y = 0x0BB8, 0x03E8
MIN_BB_X, MIN_BB_Y = _s16(0xF8E4), _s16(0xFC18)
TURN_STEP_POS = 0x0180           # field_5C: mMaxTurnStep when field_0x7BC >= 0 (the courtyard case)
TURN_STEP_NEG = 0x1000           # mMaxTurnStep (HIO): selected when field_0x7BC < 0
LOOK_TURN_VEL = 0x0800           # field_18: lookAtTarget_2 r27 (body-turn step; blocked by r28 here)
PLAYER_EYE_Y_OFF = -20.0         # dNpc_playerEyePos(-20.0f) (lookBack :1223)
JNT_CHASE = (4, 4)               # lookAtTarget_2's cLib_addCalcAngleL (scale, min_step); max = turn_step
RND_FLOOR = 0x5A                 # the rnd(0x5A, 0xB4) floor held at the RNG horizon (see _optn_1)

# --- anim numbers (bckResID table) + prm rows used in this regime (setAnm/setAnm_NUM) ----------
ANM_WAIT03 = 8                   # setStt(3) -> setAnm tbl[3] = {bck 8, morf 8.0, speed 1.0, LOOP}
ANM_LOOK = 0x0C                  # look-around: setAnm_NUM(0xc) = {bck 12, morf 8.0, speed 1.0, LOOP}
ANM_NAME = {ANM_WAIT03: 'wait03', ANM_LOOK: 'look'}
ANM_MORF = 8.0
ANM_SPEED = 1.0
EMODE_LOOP = 2

_LOAD_CACHE = None


def load():
    """(anms, skeleton) for Zl1, cached (read-only shared data, like ``anim.fk.load``)."""
    global _LOAD_CACHE
    if _LOAD_CACHE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        rb = here
        while rb != os.path.dirname(rb) and not os.path.exists(os.path.join(rb, 'pyproject.toml')):
            rb = os.path.dirname(rb)
        gen = os.path.join(rb, '_generated', 'anim')
        with open(os.path.join(gen, 'zl1_anims.json')) as f:
            anms = json.load(f)
        with open(os.path.join(gen, 'zl1_skeleton.json')) as f:
            sk = json.load(f)
        _LOAD_CACHE = (anms, sk)
    return _LOAD_CACHE


def _rot_x(a):
    """mDoMtx_XrotS (m_Do_mtx.cpp:88): 3x4, JMAS table sin/cos."""
    c, s = fk.jma_cos(a), fk.jma_sin(a)
    return [[1.0, 0.0, 0.0, 0.0], [0.0, c, _f(-s), 0.0], [0.0, s, c, 0.0]]


def _rot_y(a):
    c, s = fk.jma_cos(a), fk.jma_sin(a)
    return [[c, 0.0, s, 0.0], [0.0, 1.0, 0.0, 0.0], [_f(-s), 0.0, c, 0.0]]


def _rot_z(a):
    c, s = fk.jma_cos(a), fk.jma_sin(a)
    return [[c, _f(-s), 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]


def cLib_addCalcAngleL(value, target, scale, max_step, min_step):
    """c_lib.cpp:205 -- the s32 angle chase (NO s16 wrap; plain integer math). Returns new value."""
    value = int(value); target = int(target)
    diff = target - value
    if value != target:
        step = int(diff / scale) if diff >= 0 else -int((-diff) / scale)
        if step > min_step or step < -min_step:
            if step > max_step:
                step = max_step
            if step < -max_step:
                step = -max_step
            value += step
        else:
            if diff >= 0:
                value += min_step
                if target - value <= 0:
                    value = target
            else:
                value -= min_step
                if target - value >= 0:
                    value = target
    return value


def cLib_targetAngleY(src, dst):
    """c_lib.cpp:343: cM_atan2s(dx, dz)."""
    return S.cM_atan2s(fsubs(dst[0], src[0]), fsubs(dst[2], src[2]))


def cLib_targetAngleX(src, dst):
    """c_lib.cpp:348: cM_atan2s(dy, absXZ) -- elevation from src to dst."""
    from .collision import fsqrt
    dx = fsubs(dst[0], src[0]); dy = fsubs(dst[1], src[1]); dz = fsubs(dst[2], src[2])
    dist = fsqrt(fp.fmadds(dz, dz, fmuls(dx, dx)))
    return S.cM_atan2s(dy, dist)


class Zl1JntCtrl:
    """``dNpc_JntCtrl_c`` (d_npc.h:36): the head/backbone look-at chase. ``angles[i][j]`` =
    ``mAngles`` with i: 0 head / 1 backbone, j: 0 x (elevation) / 1 y (yaw); ``f2c/f2e/f30/f32`` =
    the per-frame clamped targets (header 0x2C..0x32). Clamps/steps are fixed per-frame by
    ``setParam`` from the Zl1 HIO table (``_execute`` :2792)."""

    __slots__ = ('angles', 'trn', 'head_lock', 'bbone_lock', 'f2c', 'f2e', 'f30', 'f32',
                 'turn_step')

    def __init__(self):
        self.angles = [[0, 0], [0, 0]]
        self.trn = False
        self.head_lock = False
        self.bbone_lock = False
        self.f2c = self.f2e = self.f30 = self.f32 = 0
        self.turn_step = TURN_STEP_POS

    def clone(self):
        """A deep copy for planner/beam-search branching (the ``angles`` list-of-lists is copied;
        the rest are immutable scalars)."""
        c = Zl1JntCtrl()
        c.angles = [list(a) for a in self.angles]
        c.trn, c.head_lock, c.bbone_lock = self.trn, self.head_lock, self.bbone_lock
        c.f2c, c.f2e, c.f30, c.f32 = self.f2c, self.f2e, self.f30, self.f32
        c.turn_step = self.turn_step
        return c

    # mMax/MinAngles[i][j] -- i 0 head / 1 backbone, j 0 x / 1 y (setParam order, d_npc.cpp:128)
    _MAX = ((MAX_HEAD_X, MAX_HEAD_Y), (MAX_BB_X, MAX_BB_Y))
    _MIN = ((MIN_HEAD_X, MIN_HEAD_Y), (MIN_BB_X, MIN_BB_Y))

    def _chk_lim(self, angle, i, j):
        """chkLim (d_npc.cpp:776): clamp s16 into [mMin[i][j], mMax[i][j]]."""
        a = _s16(angle)
        if a > self._MAX[i][j]:
            a = self._MAX[i][j]
        if a < self._MIN[i][j]:
            a = self._MIN[i][j]
        return a

    def _turn_head2backbone(self, delta):
        """turn_fromHead2Backbone (d_npc.cpp:800) -> (head_y, bbone_y) targets."""
        head = 0
        if not self.head_lock:
            head = self._chk_lim(_s16(delta - self.f32), 0, 1)
        bbone = 0
        if not self.bbone_lock:
            bbone = self._chk_lim(_s16(delta - head), 1, 1)
        return head, bbone

    def _turn_backbone2head(self, delta):
        """turn_fromBackbone2Head (d_npc.cpp:783). The guard reads the OLD backbone target
        (field_0x32) -- the bool param_4 is unused in the shipped code."""
        bbone = 0
        if not self.bbone_lock:
            bbone = self._chk_lim(delta, 1, 1)
            if self.f32 and bbone < 0:
                bbone = 0
        head = 0
        if not self.head_lock:
            head = self._chk_lim(_s16(delta - bbone), 0, 1)
        return head, bbone

    @staticmethod
    def _follow_current(angle, diff):
        """follow_current (d_npc.cpp:815): subtract the body-turn delta, zero-crossing snap."""
        old = angle
        angle = _s16(angle - diff)
        carry = 0
        if (old > 0 > angle) or (old < 0 < angle):
            carry = -angle
            angle = 0
        return angle, carry

    def look_at_target_2(self, angle_y, target, src, default_y, turn_vel, no_body_turn):
        """lookAtTarget_2 (d_npc.cpp:827-915). ``angle_y`` = current.angle.y (r26, s16);
        ``target`` = cXyz or None (r29); ``src`` = cXyz (r24). Returns the (possibly body-turned)
        new angle_y. Mutates the chased ``angles`` + targets."""
        if target is not None:
            target_y = _s16(cLib_targetAngleY(src, target))
            target_x = _s16(cLib_targetAngleX(src, target))
        else:
            target_y = _s16(default_y)
            target_x = 0

        delta_y = _s16(target_y - angle_y)
        # head/backbone Y split, keyed on the OLD backbone target sign (field_0x32)
        if self.f32 >= 0:
            if delta_y >= self.f32 or self.f32 == 0:
                head_t, bbone_t = self._turn_head2backbone(delta_y)
            else:
                head_t, bbone_t = self._turn_backbone2head(delta_y)
        else:
            if delta_y <= self.f32 or self.f32 == 0:
                head_t, bbone_t = self._turn_head2backbone(delta_y)
            else:
                head_t, bbone_t = self._turn_backbone2head(delta_y)
        self.f2e = head_t
        self.f32 = bbone_t
        self.angles[0][1] = cLib_addCalcAngleL(self.angles[0][1], head_t,
                                               JNT_CHASE[0], self.turn_step, JNT_CHASE[1])
        self.angles[1][1] = cLib_addCalcAngleL(self.angles[1][1], bbone_t,
                                               JNT_CHASE[0], self.turn_step, JNT_CHASE[1])

        if self.trn and not no_body_turn:
            # the mbTrn body-turn branch (cLib_addCalcAngleS on current.angle.y + follow_current)
            # is blocked in the stt-3 regime (optn_1 sets field_0x7D8 = true -> r28 true)
            raise AssertionError("Zl1 body-turn branch reached -- out of the modeled stt-3 regime")
        else:
            tsum = head_t + bbone_t
            self.trn = (delta_y > tsum) if delta_y >= 0 else (delta_y < tsum)

        # X (elevation) split: head clamp first, remainder to the backbone
        head_x = self._chk_lim(target_x, 0, 0)
        rem = _s16(target_x - head_x)
        bb_x = self._chk_lim(rem, 1, 0)
        self.f2c = head_x
        self.f30 = bb_x
        self.angles[0][0] = cLib_addCalcAngleL(self.angles[0][0], head_x,
                                               JNT_CHASE[0], self.turn_step, JNT_CHASE[1])
        self.angles[1][0] = cLib_addCalcAngleL(self.angles[1][0], bb_x,
                                               JNT_CHASE[0], self.turn_step, JNT_CHASE[1])
        return angle_y


class Zl1Morf:
    """``mDoExt_McaMorf`` for the Zl1 eye chain: the J3DFrameCtrl (LOOP) + the morf blend against
    the per-joint stored old pose (mpTransformInfo/mpQuat). Poses ONLY the CHAIN joints (all
    scale tracks in wait03/look/wait are static 1.0 -- asserted at load -- so the Maya scale and
    SSC branches are no-ops)."""

    __slots__ = ('anms', 'sk', 'anm', 'attr', 'start', 'end', 'loop', 'rate', 'frame', 'state',
                 'cur_morf', 'prev_morf', 'morf_step', 'old_quat', 'old_trans')

    def __init__(self, anms, sk):
        self.anms = anms
        self.sk = sk
        self.anm = None
        self.attr = EMODE_LOOP
        self.start = 0
        self.end = 0
        self.loop = 0
        self.rate = _f(1.0)
        self.frame = _f(0.0)
        self.state = 0
        # setMorf: first-ever setAnm has mPrevMorf < 0 -> cur = 1 (no morf)
        self.cur_morf = _f(1.0)
        self.prev_morf = _f(1.0)
        self.morf_step = _f(0.0)
        # ctor: store = the BIND pose (skeleton TRS) + its quat (m_Do_ext.cpp:1319-1327)
        self.old_quat = {}
        self.old_trans = {}
        for j in sk['joints']:
            if j['index'] in CHAIN:
                r = j['rotation']
                self.old_quat[j['index']] = Q.euler_to_quat(r[0], r[1], r[2])
                self.old_trans[j['index']] = tuple(_f(v) for v in j['translate'])

    def clone(self):
        """A copy that SHARES the immutable anim data (``anms``, ``sk``, the current ``anm`` row)
        and copies the mutable ctrl state -- for planner/beam-search branching without re-loading
        or deep-copying the FK tables (deepcopy of those is what makes a whole-object copy slow)."""
        c = Zl1Morf.__new__(Zl1Morf)
        c.anms, c.sk, c.anm = self.anms, self.sk, self.anm
        for s in ('attr', 'start', 'end', 'loop', 'rate', 'frame', 'state',
                  'cur_morf', 'prev_morf', 'morf_step'):
            setattr(c, s, getattr(self, s))
        c.old_quat = dict(self.old_quat)
        c.old_trans = dict(self.old_trans)
        return c

    def set_anm(self, name, morf=ANM_MORF, speed=ANM_SPEED):
        """McaMorf::setAnm via dNpc_setAnmFNDirect (start 0, end -1 -> frameMax, loop mode from
        the prm row -- LOOP for both regime anims)."""
        self.anm = self.anms[name]
        self.start = 0
        self.end = int(self.anm['frame_max'])       # J3DFrameCtrl::init(getFrameMax()); s16
        self.attr = EMODE_LOOP
        self.rate = _f(speed)
        self.frame = _f(0.0)
        self.loop = 0                                # setLoopFrame(getFrame())
        # setMorf(morf): prev_morf >= 0 after the first anm -> cur = 0, step = 1/morf; prev = cur
        if self.prev_morf < 0.0 or morf <= 0.0:
            self.cur_morf = _f(1.0)
        else:
            self.cur_morf = _f(0.0)
            self.morf_step = fp.fdivs(1.0, _f(morf))
        self.prev_morf = self.cur_morf

    def play(self):
        """McaMorf::play (morf chase) + J3DFrameCtrl::update (LOOP branch)."""
        if self.cur_morf < 1.0:
            self.prev_morf = self.cur_morf
            self.cur_morf = cLib_chaseF(self.cur_morf, 1.0, self.morf_step)
        self.state = 0
        self.frame = fadds(self.frame, self.rate)
        while self.frame < self.start:
            self.state |= 2
            if _f(self.loop - self.start) <= 0.0:
                break
            self.frame = fadds(self.frame, _f(self.loop - self.start))
        while self.frame >= self.end:
            self.state |= 2
            if _f(self.end - self.loop) <= 0.0:
                break
            self.frame = fsubs(self.frame, _f(self.end - self.loop))

    def pose_locals(self):
        """The CHAIN joints' local 3x4 matrices at the current frame (McaMorf::calc per joint),
        updating the old-pose store. Non-morf: J3DGetTranslateRotateMtx from the anim TRS
        (scale==1). Morf: JMAQuatLerp(store, new) + mDoMtx_quat + lerped translate."""
        local = {}
        morf_on = self.cur_morf < 1.0
        if morf_on:
            f31 = fp.fdivs(fsubs(self.cur_morf, self.prev_morf), fsubs(1.0, self.prev_morf))
            f30 = fsubs(1.0, f31)
        for jnt in CHAIN:
            info = j3d_eval.calc_transform(self.anm, jnt, self.frame)
            rot = info['rotation']; trans = info['translate']
            if not morf_on:
                q = Q.euler_to_quat(rot[0], rot[1], rot[2])
                self.old_quat[jnt] = q
                self.old_trans[jnt] = (trans[0], trans[1], trans[2])
                local[jnt] = fk.tr_matrix((rot[0], rot[1], rot[2]), (trans[0], trans[1], trans[2]))
            else:
                qn = Q.euler_to_quat(rot[0], rot[1], rot[2])
                q = Q.quat_lerp(self.old_quat[jnt], qn, f31)
                ot = self.old_trans[jnt]
                # translate lerp is NON-fused (m_Do_ext.cpp:1394-1396): old*f30 + new*f31
                t = tuple(fadds(fmuls(ot[k], f30), fmuls(trans[k], f31)) for k in range(3))
                self.old_quat[jnt] = q
                self.old_trans[jnt] = t
                m = Q.psmtx_quat(q)                  # mDoMtx_quat == PSMTXQuat
                m[0][3] = _f(t[0]); m[1][3] = _f(t[1]); m[2][3] = _f(t[2])
                local[jnt] = m
        return local


class Zl1Look:
    """The per-frame driver: ``optn_1`` timers -> ``lookBack`` -> McaMorf advance -> ``setMtx``
    FK -> (eyePos, tattn). Seed the hidden state from a live capture (``seed()``), then call
    :meth:`step` once per game frame AFTER Tetra's position update (the plow)."""

    def __init__(self, anms=None, sk=None):
        if anms is None or sk is None:
            anms, sk = load()
        self.jnt = Zl1JntCtrl()
        self.morf = Zl1Morf(anms, sk)
        self.cur_anm = ANM_WAIT03
        self.f84d = 1                # look-mode selector (1 = chase player eye)
        self.f7b8 = 0                # look-around countdown (rnd(0x5A, 0xB4) at setStt(3))
        self.f7ba = 0                # look-anim extra-wrap countdown
        self.f7bc = 0                # turn-step selector (>= 0 -> 0x180)
        self.f7c3 = 0                # anim wrapped flag (play_animation)
        self.m_frame = _f(0.0)       # mFrame (0x78C): last frame ctrl value, wrap detect
        self.f83c = 0                # head_y/2 (the head CB counter-twist)
        self.f83e = 0                # head_x/2
        self.eye = (0.0, 0.0, 0.0)   # eyePos (fopAc+0x260) -- lookBack reads its OWN prev .y
        self.head_org = (0.0, 0.0, 0.0)   # field_0x770 (head joint world origin), provenance
        self.counter = 0             # g_Counter.mCounter0 (parity for the look-anim 7BA seed)
        self.rng_horizon = False     # True once a cLib_getRndValue re-seed was needed (unmodelable)
        self.angle_y = 0             # her current.angle.y (stt-3: constant; the setMtx base yaw)

    def clone(self):
        """A deep copy for planner/beam-search branching: the mutable jnt/morf state is cloned
        (the morf SHARES the FK tables -- see `Zl1Morf.clone`); scalars/tuples are immutable."""
        c = Zl1Look.__new__(Zl1Look)
        c.__dict__.update(self.__dict__)
        c.jnt = self.jnt.clone()
        c.morf = self.morf.clone()
        return c

    @classmethod
    def seed_from_row(cls, row, counter=0):
        """Build + seed a :class:`Zl1Look` from a live-probe fixture row (the
        ``fixtures/courtyard_zl1look.json`` f0 shape: ``jnt``/``morf``/``f849``/... keys as read
        by ``_notes/tetrapush-zl1look_probe.py``)."""
        lk = cls()
        lk.seed(angles=[list(a) for a in row['jnt']['angles']],
                targets=(row['jnt']['f2c'], row['jnt']['f2e'],
                         row['jnt']['f30'], row['jnt']['f32']),
                cur_anm=row['f849'], frame=row['morf']['frame'],
                cur_morf=row['morf']['cur'], prev_morf=row['morf']['prev'],
                morf_step=row['morf']['step'],
                f84d=row['f84d'], f7b8=row['f7b8'], f7ba=row['f7ba'], f7bc=row['f7bc'],
                f7c3=row['f7c3'], m_frame=row['mframe'], f83c=row['f83c'], f83e=row['f83e'],
                eye=row['eye'], counter=counter, trn=bool(row['jnt']['trn']),
                angle_y=row['travel'])
        return lk

    def seed(self, *, angles, targets, cur_anm, frame, cur_morf, prev_morf, morf_step,
             f84d, f7b8, f7ba, f7bc, f7c3, m_frame, f83c, f83e, eye, counter, trn=False,
             angle_y=0, old_quat=None, old_trans=None):
        """Load the live-captured hidden state (the f0 pause-boundary values). ``angles`` /
        ``targets`` = the m_jnt block ([[hx,hy],[bx,by]], (f2c,f2e,f30,f32)); ``frame``/morfs =
        the McaMorf ctrl; ``old_quat/old_trans`` only needed when a morf is ACTIVE at the seed
        (cur_morf < 1)."""
        self.jnt.angles = [list(a) for a in angles]
        self.jnt.f2c, self.jnt.f2e, self.jnt.f30, self.jnt.f32 = targets
        self.jnt.trn = trn
        self.jnt.turn_step = TURN_STEP_NEG if f7bc < 0 else TURN_STEP_POS
        self.cur_anm = cur_anm
        self.morf.anm = self.morf.anms[ANM_NAME[cur_anm]]
        self.morf.end = int(self.morf.anm['frame_max'])
        self.morf.loop = 0
        self.morf.rate = _f(ANM_SPEED)
        self.morf.frame = _f(frame)
        self.morf.cur_morf = _f(cur_morf)
        self.morf.prev_morf = _f(prev_morf)
        self.morf.morf_step = _f(morf_step)
        if cur_morf < 1.0:
            if old_quat is None:
                raise ValueError("morf active at the seed (cur_morf < 1) needs the old-pose store")
            self.morf.old_quat = dict(old_quat)
            self.morf.old_trans = dict(old_trans)
        self.f84d = f84d
        self.f7b8 = f7b8; self.f7ba = f7ba; self.f7bc = f7bc
        self.f7c3 = f7c3
        self.m_frame = _f(m_frame)
        self.f83c = f83c; self.f83e = f83e
        self.eye = tuple(eye)
        self.counter = counter
        self.angle_y = _s16(angle_y)

    # --- optn_1 (stt-3, in plow range, no talk): the look timer machine (:2497-2530) -----------
    def _optn_1(self):
        if self.cur_anm == ANM_LOOK:
            # `field_0x7C3 && cLib_calcTimer(&field_0x7BA) == 0` -- the timer only DECREMENTS
            # when the anim-wrapped flag is set (short-circuit), then tests the NEW value.
            if self.f7c3 != 0:
                if self.f7ba != 0:
                    self.f7ba -= 1
                if self.f7ba == 0:
                    # the game re-seeds 7B8 = rnd(0x5A, 0xB4) from the GLOBAL RNG stream --
                    # unmodelable offline; flag the horizon and hold the rnd floor (class doc).
                    self._set_anm(ANM_WAIT03)
                    self.f7b8 = RND_FLOOR
                    self.rng_horizon = True
            self.f84d = 0
            return
        if self.f7b8 != 0:
            self.f7b8 -= 1
        if self.f7b8 == 0:
            self._set_anm(ANM_LOOK)
            self.f7ba = (self.counter & 1) + 1
            self.f84d = 0
            return
        self.f84d = 1

    def _set_anm(self, num):
        """setAnm_NUM -> setAnm_anm: no-op if already playing (field_0x849 check)."""
        if self.cur_anm == num:
            return
        self.morf.set_anm(ANM_NAME[num])
        self.cur_anm = num
        self.f7c3 = 0
        self.m_frame = _f(0.0)

    def step(self, *, pos_pre, pos_post, link_pos, link_head_top_y, angle_y=None):
        """One Zl1 execute frame. ``pos_pre`` = her position BEFORE this frame's CC plow (the
        end-of-last-frame pos; ``lookBack`` runs before ``posMoveF``), ``pos_post`` = after (what
        ``setMtx``/``setAttention`` use). ``link_pos`` = Link's post-execute frame-k position,
        ``link_head_top_y`` = his exec-pass ``mHeadTopPos.y`` (``FootFK.head_top``). Returns
        ``(eye, tattn)`` -- eye is what Link's proc-9 re-aim reads NEXT frame; tattn is what the
        camera Run reads at the END of this frame."""
        if angle_y is None:
            angle_y = self.angle_y
        else:
            angle_y = _s16(angle_y)
        self.counter += 1
        # 1. the action (optn_1) sets field_0x84D + may switch the anim
        self._optn_1()
        # 2. lookBack: src = pre-move pos with the PREVIOUS eyePos.y (:1204-1206)
        src = (pos_pre[0], self.eye[1], pos_pre[2])
        if self.f84d == 1:
            ty = fadds(_f(link_head_top_y), _f(PLAYER_EYE_Y_OFF))
            target = (link_pos[0], ty, link_pos[2])
        elif self.f84d == 0:
            target = None
        else:  # pragma: no cover
            raise AssertionError("Zl1 look mode %d out of the modeled stt-3 regime" % self.f84d)
        self.jnt.look_at_target_2(angle_y, target, src, angle_y, LOOK_TURN_VEL, True)
        # C '/2' on s16 truncates toward zero
        hy, hx = self.jnt.angles[0][1], self.jnt.angles[0][0]
        self.f83c = int(hy / 2) if hy >= 0 else -int(-hy / 2)
        self.f83e = int(hx / 2) if hx >= 0 else -int(-hx / 2)
        # 3. play_animation: morf/frame advance + the wrap-detect anim-completed flag
        self.morf.play()
        self.f7c3 = 0
        if self.morf.frame < self.m_frame:
            self.f7c3 = 1
        self.m_frame = self.morf.frame
        # 4. setMtx: FK at the post-move pos; node CBs; eye offset
        eye = self._pose_eye(pos_post, angle_y)
        self.eye = eye
        # 5. setAttention: tattn from the post-move pos
        tattn = (pos_post[0], fadds(_f(pos_post[1]), _f(ATTN_Y_OFF)), pos_post[2])
        return eye, tattn

    def _pose_eye(self, pos, angle_y):
        """setMtx: base = transS(pos) * ZXYrotM(0, angle_y, 0); chain FK with the backbone CB
        (XrotM(bb_y) ZrotM(-bb_x)) and the head CB (YrotM(-f83C) ZrotM(-f83E)); eye =
        M_head' * EYE_OFF (PSMTXMultVec)."""
        locals_ = self.morf.pose_locals()
        base, _ = fk.world_base(_f(pos[0]), _f(pos[1]), _f(pos[2]), int(angle_y) & 0xFFFF)
        m = base
        for jnt in (0, 1, BBONE_JNT):
            m = fk.mtx_concat(m, locals_[jnt])
        # nodeCB_BackBone (:196): XrotM(getBackbone_y()); ZrotM(-getBackbone_x())
        m = fk.mtx_concat(m, _rot_x(self.jnt.angles[1][1]))
        m = fk.mtx_concat(m, _rot_z(-self.jnt.angles[1][0]))
        m = fk.mtx_concat(m, locals_[5])
        m = fk.mtx_concat(m, locals_[HEAD_JNT])
        # nodeCB_Head (:167): head world origin, then the -half-angle twist, then the eye offset
        self.head_org = (m[0][3], m[1][3], m[2][3])
        m = fk.mtx_concat(m, _rot_y(-self.f83c))
        m = fk.mtx_concat(m, _rot_z(-self.f83e))
        return tuple(fk.mtx_mult_vec(m, EYE_OFF))


def link_eye_target(link_pos, head_top):
    """``dNpc_playerEyePos(-20)`` (d_npc.cpp:609): the trans-matrix MultVec of (0,-20,0) at
    mHeadTopPos, then x/z overwritten with current.pos -- i.e. (pos.x, headTop.y - 20, pos.z)
    with the exact PSMTXMultVec y arithmetic."""
    t = [[1.0, 0.0, 0.0, _f(head_top[0])],
         [0.0, 1.0, 0.0, _f(head_top[1])],
         [0.0, 0.0, 1.0, _f(head_top[2])]]
    out = fk.mtx_mult_vec(t, (0.0, PLAYER_EYE_Y_OFF, 0.0))
    return (_f(link_pos[0]), out[1], _f(link_pos[2]))
