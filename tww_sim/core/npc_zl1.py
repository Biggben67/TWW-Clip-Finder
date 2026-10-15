"""FP-faithful *partial* model of Tetra (NPC ``Zl1``) for seam-clip planning.

Models only the two Tetra behaviors a seam-clip planner must predict at the flooded-Hyrule
Tetra corner -- the **type-5** ``field_0x84F == 5`` *following* variant (savestate slot 3,
the same one [[tetra-push-model]] / ``actor-push.md`` uses). This is deliberately NOT a full
``daNpc_Zl1_c`` AI port: the event/demo/cutscene branches, message flow, eye/joint control,
and water FX are out of scope. Two things are in scope:

1. **FOLLOW** (:class:`Zl1FollowState`) -- she chases Link when he wanders too far. The idle
   <-> move state machine ``optn_action1`` -> ``optn_1``/``optn_2`` (``d_a_npc_zl1.cpp``):
   engages when the **3D** distance to Link exceeds **230 u** (``field_34 + 100``), turns to
   face him, accelerates (``chaseF`` at 1 u/f) toward a distance-scaled target speed
   (``0.04 * sqrt(dist^2 - 130^2)``, capped **10 u/f**), and decelerates to a full stop once
   he is back within **130 u** (``field_34``). Movement is ``posMoveF`` (``speedF`` along
   ``current.angle.y``) + her consumed CC recoil, then ``CrrPos``. This is the per-frame
   **Tetra counterpart state** the CC-push seam-clip pipeline needs.

2. **LOCK-ON / TALK / SPEAK region** (:func:`zl1_attention_active`) -- the player attention
   system (``dAttention_c``) makes her a valid **L-target / talk / speak** target inside her
   ``attention_info`` profile. Tetra's ``distances[TALK] = distances[SPEAK] = 0xAB`` selects
   ``dist_table[0xAB]`` (``d_att_dist.cpp``): horizontal **XZ < 300 u**, **|dy| < 300**, and
   Link's facing within **+-90 deg** (``0x4000``) of the direction toward her (front-cone bits
   ``0x0004``). A planner must AVOID this region on any frame where an A- or L-press is live,
   or Link talks to / locks onto Tetra instead of doing the intended action.

Decomp-grounded (GZLJ01, US ``/* addr */`` comments; the param literals are un-versioned so
they are the JP values too -- see [[jp-vs-us-decomp-addresses]]):
``daNpc_Zl1_c`` (``optn_1``/``optn_2``, ``chk_areaIN``, ``createInit``, ``init_ZL1_5``),
``dAttention_c::calcWeight`` + ``check_distace`` + ``check_flontofplayer`` (``d_attention.cpp``)
+ ``dist_table`` (``d_att_dist.cpp``), ``fopAcM_posMoveF``/``calcSpeed``/``posMove``,
``cLib_addCalcAngleS``/``cLib_chaseF``/``cLib_targetAngleY``/``cM_atan2s``. Pure stdlib +
``core.fp`` / ``core.mathlib`` / ``core.collision`` (``fsqrt``). No Dolphin dependency.

Constants live in ``knowledge/reference/constants.md`` (Zl1 follow + attention); the mechanic
page is ``knowledge/mechanics/tetra-follow.md``.
"""
from .fp import f32 as _f, fadds, fsubs, fmuls, fmadds
from .collision import fsqrt, acch_crr_pos
from . import mathlib as S

# Tetra's BG wall-check cylinder: a single dBgS_AcchCir SetWall(halfH=30, R=50) (d_a_npc_zl1.cpp:3022);
# her mObjAcch (dBgS_ObjAcch : dBgS_Acch, no CrrPos override) runs the Phase-W acch_crr_pos. KB: tetra-follow.md.
WALL_R = 50.0
WALL_H = (30.0,)

# --- Zl1 HIO follow params (daNpc_Zl1_HIO_c::daNpc_Zl1_HIO_c a_prm_tbl, d_a_npc_zl1.cpp:85) ---
FOLLOW_KEEP_DIST = 130.0        # field_34: the distance she holds (target speed 0 at/below it)
FOLLOW_ENGAGE_DIST = 230.0      # field_34 + 100: idle->move (optn_1 requires 3D dist > this)
FOLLOW_SPEED_GAIN = 0.04        # field_38: target speedF = GAIN * sqrt(dist^2 - KEEP^2)
FOLLOW_SPEED_MAX = 10.0         # field_3C: cLib_maxLimit cap on target speedF
FOLLOW_ACCEL = 1.0              # field_44: cLib_chaseF step (speedF units per frame)
FOLLOW_TURN_SCALE = 4           # cLib_addCalcAngleS scale (diff >> divide)
FOLLOW_TURN_MAX = 0x800         # cLib_addCalcAngleS maxStep (s16/frame)
FOLLOW_TURN_MIN = 0x80          # cLib_addCalcAngleS minStep (s16/frame)
ENGAGE_FACE_GATE = 0x1800       # optn_1: only start moving once facing within this of Link
GRAVITY = -4.5                  # init_ZL1_5: current gravity (applied in calcSpeed)

# optn_action1 field_0x84B action states (setStt): 3 = idle (optn_1), 4 = move/follow (optn_2).
STT_IDLE = 3
STT_MOVE = 4

# --- Attention profile: attention_info + dist_table[0xAB] (d_a_npc_zl1.cpp:396-404, d_att_dist.cpp) ---
ATTN_HEIGHT = 140.0             # field_1C: attention_info.position.y = pos.y + this
ATTN_XZ_MAX = 300.0            # dist_table[0xAB].mDistXZMax (mDistXZAngleAdjust = 0 -> constant)
ATTN_DY_MAX = 300.0            # dist_table[0xAB].mDeltaYMax  (reject if dy >= this)
ATTN_DY_MIN = -300.0           # dist_table[0xAB].mDeltaYMin  (reject if dy <= this)
ATTN_FRONT_HALF_ANGLE = 0x4000  # front-cone bits 0x0004 -> reject if |Link facing error| > 90 deg


def _s16(x):
    """Sign-extend an integer into the signed s16 range (wrap like the game's s16 arithmetic)."""
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _abs2_3d(dx, dy, dz):
    """cXyz::abs2() == PSVECSquareMag (dolphin/mtx/vec.c:130): paired-single (z^2 + x^2) + y^2,
    each square a rounded ps_mul, the z^2+x^2 a fused ps_madd. Bit-exact vs the console."""
    x2 = fmuls(dx, dx)
    y2 = fmuls(dy, dy)
    return fadds(fmadds(dz, dz, x2), y2)


def _abs2_xz(dx, dz):
    """cXyz::abs2XZ() -- the y=0 case of abs2: fmadds(dz, dz, dx*dx) (matches cc_push/PSVECMag)."""
    return fmadds(dz, dz, fmuls(dx, dx))


def cLib_addCalcAngleS(value, target, scale, max_step, min_step):
    """``cLib_addCalcAngleS`` (c_lib.cpp:160): s16 damped angle chase. Integer/s16 math (NOT the
    f32 ``cLib_addCalc``): ``step = (s16)(target - value) / scale``; if ``|step| > min_step`` clamp
    to ``+-max_step`` and add; else snap by ``+-min_step`` without overshooting ``target``. Returns
    the new (signed s16) value. ``value``/``target`` are s16."""
    value = _s16(value)
    target = _s16(target)
    diff = _s16(target - value)
    if value == target:
        return value
    # C integer division truncates toward zero; _s16(diff) is already the wrapped short.
    step = int(diff / scale) if diff >= 0 else -int((-diff) / scale)
    if step > min_step or step < -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        return _s16(value + step)
    # |step| <= min_step: creep by min_step toward target, snapping if we reach/pass it.
    if diff >= 0:
        nv = _s16(value + min_step)
        return target if _s16(target - nv) <= 0 else nv
    nv = _s16(value - min_step)
    return target if _s16(target - nv) >= 0 else nv


def cLib_chaseF(value, target, step):
    """``cLib_chaseF`` (c_lib.cpp:276): move f32 ``value`` toward ``target`` by ``step``, snapping
    to ``target`` on overshoot. Returns the new value (all f32)."""
    value = _f(value)
    target = _f(target)
    if step == 0.0:
        return value
    s = _f(-step) if value > target else _f(step)
    nv = fadds(value, s)
    if fmuls(s, fsubs(nv, target)) >= 0.0:
        return target
    return nv


def target_angle_y(from_xyz, to_xyz):
    """``cLib_targetAngleY`` (c_lib.cpp): ``cM_atan2s(to.x - from.x, to.z - from.z)`` -> u16 angle."""
    return S.cM_atan2s(fsubs(_f(to_xyz[0]), _f(from_xyz[0])),
                       fsubs(_f(to_xyz[2]), _f(from_xyz[2])))


def attn_yaw_bam(dx, dz):
    """The attention system's bearing: ``cSGlobe(delta).U()`` as ``SelectAttention`` computes it
    (``d_attention.cpp:472-474``). NOT the raw table ``cM_atan2s``: ``cSPolar::Val``
    (``c_angle.cpp``, US 80254214) stores ``Radian_to_SAngle(cM_atan2f(x, z))``, and ``cM_atan2f``
    is ``9.58738E-5f * cM_atan2s(f1, f2)`` (``c_math.cpp:162-165``) while ``Radian_to_SAngle`` is
    ``(s16)(rad * 10430.378f)`` (``c_angle.h:68``, float->int truncation toward zero). The f32
    round trip shifts ~18% of bearings by +-1 BAM vs the raw table value, which moves the front-cone
    boundary by 1 BAM at those bearings. (``cSGlobe::Formal`` only remaps the yaw for near-vertical
    deltas -- elevation beyond +-90 deg -- unreachable inside the XZ<=300/|dy|<300 region.)"""
    v = _s16(S.cM_atan2s(_f(dx), _f(dz)))
    rad = fmuls(_f(9.58738e-5), float(v))       # cM_atan2f: s16 -> f32 radians
    return _s16(int(fmuls(rad, _f(10430.378))))  # Radian_to_SAngle: f32 -> s16, trunc toward zero


class Zl1FollowState:
    """Per-frame follow state of a type-5 (following) Tetra. Mirrors the fields the follow path
    touches: world position (f32 x/y/z), ``current.angle.y`` (s16 facing), ``speedF`` (f32), and
    the ``field_0x84B`` action state (``STT_IDLE``/``STT_MOVE``). Seed it from a live capture
    (position/angle/speedF/state), then :meth:`step` it with Link's position each frame.

    Ground handling: on flat ground (the Tetra corner floor is flat -- Phase G) ``CrrPos`` snaps
    Y back every frame, so gravity nets to zero; pass ``ground_y`` to clamp Y (the flat-floor
    case). Walls (``CrrPos`` XZ correction / the ``move_jmp`` gap jump) are out of scope for this
    open-area follow model and are a follow-up (they reuse ``core.collision``); ``step`` asserts
    it is not asked to model a wall response.
    """

    __slots__ = ("x", "y", "z", "angle_y", "speedF", "stt")

    def __init__(self, x, y, z, angle_y, speedF=0.0, stt=STT_IDLE):
        self.x = _f(x)
        self.y = _f(y)
        self.z = _f(z)
        self.angle_y = _s16(angle_y)
        self.speedF = _f(speedF)
        self.stt = int(stt)

    def copy(self):
        return Zl1FollowState(self.x, self.y, self.z, self.angle_y, self.speedF, self.stt)

    @property
    def pos(self):
        return (self.x, self.y, self.z)

    def _dist2_to(self, link_pos):
        """3D squared distance to Link -- ``fopAcM_searchActorDistance2`` = ``delta.abs2()``."""
        dx = fsubs(_f(link_pos[0]), self.x)
        dy = fsubs(_f(link_pos[1]), self.y)
        dz = fsubs(_f(link_pos[2]), self.z)
        return _abs2_3d(dx, dy, dz)

    def _run_action(self, link_pos):
        """One dispatch of ``optn_action1`` for the type-5 gameplay states (idle/move), setting
        ``speedF`` and turning ``angle.y`` for THIS frame. Returns nothing; mutates self. The
        ``field_0x84B`` switch reads the state ONCE, so a ``setStt`` here only takes effect next
        frame (the game's 1-frame action-state latency)."""
        dist2 = self._dist2_to(link_pos)
        ang_to_link = target_angle_y(self.pos, link_pos)

        if self.stt == STT_IDLE:
            # optn_1: far enough -> turn toward Link; once roughly facing, switch to move.
            engage2 = _f(FOLLOW_ENGAGE_DIST * FOLLOW_ENGAGE_DIST)  # (field_34+100)^2, f32
            if dist2 >= engage2:
                self.angle_y = cLib_addCalcAngleS(self.angle_y, ang_to_link,
                                                  FOLLOW_TURN_SCALE, FOLLOW_TURN_MAX, FOLLOW_TURN_MIN)
                if abs(_s16(ang_to_link - self.angle_y)) < ENGAGE_FACE_GATE:
                    self.stt = STT_MOVE      # setStt(4): next frame runs optn_2 (speedF still 0 now)
            # idle: speedF stays 0 (setStt(3) zeroed it); no position move beyond gravity.
            return

        if self.stt == STT_MOVE:
            # optn_2: chase Link. target speed from sqrt(dist^2 - keep^2), capped; accel via chaseF.
            keep2 = _f(FOLLOW_KEEP_DIST * FOLLOW_KEEP_DIST)
            temp = fsubs(dist2, keep2)
            v_target = _f(0.0)
            if temp > 0.0:
                v_target = fmuls(_f(FOLLOW_SPEED_GAIN), fsqrt(temp))
                if v_target > FOLLOW_SPEED_MAX:
                    v_target = _f(FOLLOW_SPEED_MAX)          # cLib_maxLimit(temp2, field_3C)
            self.angle_y = cLib_addCalcAngleS(self.angle_y, ang_to_link,
                                              FOLLOW_TURN_SCALE, FOLLOW_TURN_MAX, FOLLOW_TURN_MIN)
            self.speedF = cLib_chaseF(self.speedF, v_target, FOLLOW_ACCEL)
            if int(v_target) == 0 and int(self.speedF) == 0:
                self.stt = STT_IDLE          # setStt(3): back to idle; case 3 zeroes speedF
                self.speedF = _f(0.0)
            return

        raise ValueError("Zl1FollowState models only the type-5 idle/move follow states "
                         "(stt 3/4); got stt=%r" % (self.stt,))

    def step(self, link_pos, cc_move=(0.0, 0.0, 0.0), ground_y=None, walls=None):
        """Advance one game frame given Link's world position ``link_pos`` (x, y, z).

        Order matches ``daNpc_Zl1_c::_execute`` (type-5 gameplay path): run the action function
        (sets ``speedF`` + turns ``angle.y``), then ``posMoveF(this, GetCCMoveP())`` == ``calcSpeed``
        (XZ from ``speedF`` along ``angle.y``; Y += gravity) + ``posMove`` (pos += speed, then +=
        the consumed CC recoil ``cc_move``), then ``mObjAcch.CrrPos`` (the wall pass + ground clamp).

        ``cc_move`` = Tetra's ``m_cc_move`` recoil consumed this frame (0 when not overlapping
        Link; wired up by the CC-push integration). ``ground_y`` = flat floor height to clamp Y to
        (None leaves Y integrating under gravity). ``walls`` = the room's ordered wall tris
        (``land.walls.load_ordered_mesh``) to run her per-frame ``CrrPos`` wall correction with her
        R=50 / half-H=30 cylinder; None skips it (open-area follow, no wall in reach)."""
        self._run_action(link_pos)

        old = (self.x, self.y, self.z)                     # pm_old_pos (frame-start, ground-snapped)
        # calcSpeed: xSpeed = speedF * cM_ssin(angle.y); zSpeed = speedF * cM_scos(angle.y).
        # cM_ssin/cM_scos take the s16 angle directly (JMASSin/JMASCos table lookup).
        x_speed = fmuls(self.speedF, S.cM_ssin_s16(self.angle_y))
        z_speed = fmuls(self.speedF, S.cM_scos_s16(self.angle_y))
        # posMove: pos += speed, then += CC recoil (componentwise f32 adds).
        nx = fadds(fadds(old[0], x_speed), _f(cc_move[0]))
        nz = fadds(fadds(old[2], z_speed), _f(cc_move[2]))
        # Y: on the flat corner floor/water she floats with speed.y == 0 (live), so the CrrPos slice
        # sees speed_y = 0 (a -4.5 dip mis-ejects a wall-corrected XZ by 1 ULP); free-fall accrues it.
        if ground_y is not None:
            sy = _f(0.0)
            ny = old[1]
        else:
            sy = _f(GRAVITY)
            ny = fadds(fadds(old[1], sy), _f(cc_move[1]))

        if walls is not None:
            # mObjAcch.CrrPos wall pass (same dBgS_Acch::CrrPos core as Phase W), her cylinder.
            (nx, ny, nz), _info = acch_crr_pos(old, (nx, ny, nz), walls,
                                               speed_y=sy, wall_h=WALL_H, wall_r=WALL_R)
        self.x, self.z = nx, nz
        self.y = _f(ground_y) if ground_y is not None else ny
        return self


def zl1_attention_active(link_pos, link_facing, tetra_pos, link_attn_y=None):
    """Is Tetra a valid **L-target / talk / speak** target for Link right now? -- the planner
    AVOID predicate. Reproduces the eligibility gate the player attention system applies for a
    ``LOCKON_TALK``/``ACTION_SPEAK`` actor with ``distances[TALK]=distances[SPEAK]=0xAB``
    (``dAttention_c::calcWeight`` -> ``check_flontofplayer`` + ``check_distace``,
    ``dist_table[0xAB]``). True = Tetra CAN be locked onto / talked to (a live A/L press would
    engage her). This is necessary-not-sufficient (the real lock/talk also needs her to be the
    best-weighted target and the button pressed), so as a keep-out region it is conservative.

    ``link_pos``/``tetra_pos`` = (x, y, z) f32 world positions (feet); ``link_facing`` = Link's
    ``shape_angle.y`` (s16). Y gate uses the attention points: Tetra's is ``pos.y + 140``; Link's
    is ``link_attn_y`` if given, else his feet ``link_pos[1]`` (a ~unit slack that never matters at
    the corner, where |dy| << 300)."""
    dx = fsubs(_f(tetra_pos[0]), _f(link_pos[0]))
    dz = fsubs(_f(tetra_pos[2]), _f(link_pos[2]))
    # check_distace Y gate: dy = actor.attn.y - player.attn.y in (MIN, MAX) exclusive.
    tetra_attn_y = fadds(_f(tetra_pos[1]), _f(ATTN_HEIGHT))
    player_attn_y = _f(link_pos[1]) if link_attn_y is None else _f(link_attn_y)
    dy = fsubs(tetra_attn_y, player_attn_y)
    if dy <= ATTN_DY_MIN or dy >= ATTN_DY_MAX:
        return False
    # check_distace XZ gate: absXZ(delta) <= mDistXZMax (+ angle adjust, which is 0 here).
    if fsqrt(_abs2_xz(dx, dz)) > ATTN_XZ_MAX:
        return False
    # check_flontofplayer (mask 0x0004): reject unless Link's facing error to Tetra <= 90 deg.
    # angle1 = (dir Link->Tetra) - Link.shape_angle.y, the bearing via cSGlobe.U()'s atan2f
    # round trip (attn_yaw_bam), which is +-1 BAM off the raw table at ~18% of bearings.
    dir_to_tetra = attn_yaw_bam(dx, dz)
    face_err = abs(_s16(dir_to_tetra - _s16(link_facing)))
    if face_err > ATTN_FRONT_HALF_ANGLE:
        return False
    return True
