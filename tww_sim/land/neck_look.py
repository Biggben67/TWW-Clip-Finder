#!/usr/bin/env python3
"""NeckLook: Link's head-look twist ``m3564`` (``setNeckAngle``, d_a_player_main.cpp:8938-9169).

``jointBeforeCB``
twists Link's HEAD joint (CL_JNT_HEAD_JNT_e, 15) by ``local_38 = (m3564.y, m3564.z, m3564.x)``
(:269-270), and ``m3564`` chases a look target each execute frame in ``setNeckAngle`` (:11571 --
AFTER ``setMoveSlantAngle``, BEFORE ``mpCLModel->calc()``, so it reads the PREVIOUS frame's head
anm matrix and twists THIS frame's pose / ``mHeadTopPos``). Unmodeled it cost <=0.96 u of head-top
Y on the untarget-tier frames -> Tetra's elevation chase shifted -> a <=16-BAM facing echo on
Link's re-aim frames in the self-contained replay.

The per-frame law (the courtyard-reachable branches; everything s16-wrapping):

1. **Gate** (:9086): the chase runs toward a target only when the DISPATCH proc's mode flags
   (``mModeFlg``, set from the proc table at ``commonProcInit`` :5806) carry ``ModeFlg_00000080 |
   ModeFlg_08000000`` AND a look pos ``sp18`` was selected. MOVE/WAIT/ATN*/CUT* carry 0x80;
   FRONT_ROLL / MOVE_TURN / WAIT_TURN / SLIP do NOT -- which is exactly why ``m3564`` chases 0
   through every roll (live probe) even while the actor-lock is held mid-roll.
2. **Target selection** (:9014-9046): ``sp18 = eyePos`` of the locked actor (``mpAttnActorLockOn``)
   or, unlocked, of the attention's stocked lock-on-list head (``GetLockonList(0)`` via
   ``checkAttentionPosAngle``) -- both gated on the SAME +-0x6000 cone of ``m34DE`` (:9014/:8927,
   ``cLib_distanceAngleS(cLib_targetAngleY(current.pos, eyePos), m34DE)``). The list is why the
   chase continues on the post-drop backslide frames: in state NONE ``stockAttention`` restocks it
   every attention Run, EXCEPT on the RELEASE->NONE transition Run itself, where ``freeAttention``
   has just cleared it (``AttentionLock.list_present`` models that timing -- the probe's f21
   chase-to-0 hole).
3. **Measure** (:9070-9083): off the PREV frame's head matrix M, ``spC4 = M*(11.25,0,0)`` (head
   centre), ``spAC = M*(11.25,18.75,0) - spC4`` (eye direction); ``r24_4 = atan2s(-spAC.y,
   absXZ(spAC)) - m3564.x`` (the anim's own pitch, twist removed), ``r25_3 = atan2s(spAC.x,
   spAC.z) - m34DE - m3564.y``.
4. **Target angles** (:9087-9102): ``spB8 = sp18 - spC4``; ``r27 = atan2s(-spB8.y, absXZ(spB8))``
   clamped [-10000, 8000]; ``r23_3 = atan2s(spB8.x, spB8.z) - m34DE`` (or ``m3564.y`` when
   ``absXZ(spB8) < 30``) clamped +-``YAW_CLAMP`` (HIO ``mShip.m.field_0x0`` = 14336).
5. **Half-angle chase targets** (:9103-9114, the ModeFlg_00000080 non-DASHKAZE branch):
   ``r4 = (r27 >> 1) - r24_4``, ``r23 = (r23_3 >> 1) - r25_3``. Gate failed -> ``r4 = r23 = 0``
   (the :9138 ``m34C3 == 1`` branch reads ``m34E2 >> 1`` -- 0 the whole courtyard window, probed).
6. **Chase** (:9157-9168): ``cLib_addCalcAngleS(&m3564.{x,y}, target, 3, 0x1000, 0x100)``; then the
   yaw overflow clamp (:9159-9165, keeps ``r25_3 + m3564.y`` inside +-YAW_CLAMP); ``m3564.z``
   chases 0 (never driven in this regime).

Live ground truth: ``fixtures/courtyard_m3564.json`` (single-stepped slot-2 probe, f0..f44 --
``_notes/tetrapush-m3564_probe.py``); the f0->f5 decay 1262->842->562->306->50->0 pins the
(3, 0x1000, 0x100) chase knobs bit-for-bit. Pure model, no Dolphin dependency; inert unless
stepped by a driver (the from-f0 replay / FreeRun wires it -- the land goldens never construct it).
"""
from __future__ import annotations

from ..core import mathlib as S
from ..core import fp
from ..core.fp import fsubs, fmuls
from .constants import cLib_addCalcAngleS

# The head-joint local offsets setNeckAngle measures with (d_a_player_main_data.inc:20-21).
EYE_OFFSET = (11.25, 18.75, 0.0)         # l_eye_offset
HEAD_CENTER_OFFSET = (11.25, 0.0, 0.0)   # l_head_center_offset

# Look-pos selection cone (:9014/:8927) -- +-0x6000 of m34DE, NOT the 0x4000 chaseAttention cone.
LOOK_CONE_HALF = 0x6000

# Chase knobs (:9157) + clamps (:9093-9102). YAW_CLAMP = HIO mShip.m.field_0x0
# (d_a_player_HIO_data.inc:297); PITCH clamp hard-coded at :9093-9097.
CHASE = (3, 0x1000, 0x100)
PITCH_MAX, PITCH_MIN = 8000, -10000
YAW_CLAMP = 14336

# Procs whose table row (d_a_player_main_data.inc:223-302) carries ModeFlg_00000080 -- the
# neck-look gate + the half-angle/yaw-clamp variant. Extend from the table if a new proc lands.
_FLG80_PROCS = frozenset((
    0x02,                    # CALL
    0x04,                    # WAIT
    0x06, 0x07, 0x08, 0x09,  # MOVE, ATN_MOVE, ATN_ACTOR_WAIT, ATN_ACTOR_MOVE
    0x0A, 0x0B,              # SIDESTEP, SIDESTEP_LAND
    0x41, 0x42, 0x43, 0x44, 0x45, 0x46,  # CUT_A/F/R/L/EA/EB
    0x4B,                    # WEAPON_NORMAL_SWING
))
# Rows with ModeFlg_08000000 instead (gate passes, but :9103 half-angle + :9159 clamp do NOT).
_FLG8M_PROCS = frozenset((0x0C, 0x10, 0x11, 0x49))


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def _abs_xz(x, z):
    """cXyz::absXZ = sqrtf(x*x + z*z), the fmadds contraction the compiler emits (the same op
    order `cLib_targetAngleX` is 0-ULP-gated with in core.npc_zl1_look)."""
    from ..core.collision import fsqrt
    return fsqrt(fp.fmadds(z, z, fmuls(x, x)))


def _dist_angle(a, b):
    """cLib_distanceAngleS: |s16(a - b)| as a plain int (abs(-0x8000) == 0x8000)."""
    return abs(_s16(a - b))


class NeckLook:
    """The per-frame ``m3564`` state. Feed :meth:`update` the frame's post-step primitives; read
    ``x/y/z`` (s16) and pass :meth:`local_38` to the head-pose FK (``FootFK.head_top(neck=...)``).
    """

    __slots__ = ('x', 'y', 'z')

    def __init__(self, x=0, y=0, z=0):
        self.x = _s16(int(x))
        self.y = _s16(int(y))
        self.z = _s16(int(z))

    def clone(self):
        """A deep copy (all state is three s16 scalars) -- for planner/beam-search node branching."""
        return NeckLook(self.x, self.y, self.z)

    def local_38(self):
        """The jointBeforeCB HEAD twist tuple ``(m3564.y, m3564.z, m3564.x)`` (:270)."""
        return (self.y, self.z, self.x)

    def select_look_pos(self, pos, eye, m34de, locked, list_present):
        """The courtyard-reachable ``sp18`` selection (:9014-9046): the locked actor's eyePos, or
        the stocked lock-on list head's, both through the +-0x6000 cone of ``m34DE``. ``eye`` is
        the candidate actor's ``eyePos`` (Tetra's, end-of-previous-frame); returns it or None. The
        deeper :9017 rungs (att look target, the detect probe, the ``m34C3 == 10`` velocity pos)
        have no courtyard occupants and are not modeled."""
        if eye is None or not (locked or list_present):
            return None
        bearing = S.cM_atan2s(fsubs(fp.f32(eye[0]), fp.f32(pos[0])),
                              fsubs(fp.f32(eye[2]), fp.f32(pos[2])))
        if _dist_angle(bearing, m34de) <= LOOK_CONE_HALF:
            return eye
        return None

    def update(self, head_mtx, m34de, proc, look_pos):
        """One ``setNeckAngle`` m3564 pass. ``head_mtx`` = the PREVIOUS frame's exec head anm
        matrix (3x4 world, twist included -- the sim's cached ``FootFK.head_mtx`` output);
        ``m34de`` = this frame's post-update ``m34DE`` (== shape_angle.y, written at :11287 before
        :11571); ``proc`` = the pause-boundary dispatch proc (its table row is ``mModeFlg``);
        ``look_pos`` = the selected ``sp18`` (see :meth:`select_look_pos`) or None."""
        from ..core.anim import fk

        flg80 = proc in _FLG80_PROCS
        gate = (flg80 or proc in _FLG8M_PROCS) and look_pos is not None

        # :9070-9083 -- the previous pose's own head angles, current twist removed. Computed
        # UNCONDITIONALLY in the decomp (the :9159 clamp consumes r25_3 even when the gate fails).
        spC4 = fk.mtx_mult_vec(head_mtx, HEAD_CENTER_OFFSET)
        sp88 = fk.mtx_mult_vec(head_mtx, EYE_OFFSET)
        spAC = (fsubs(sp88[0], spC4[0]), fsubs(sp88[1], spC4[1]), fsubs(sp88[2], spC4[2]))
        r24_4 = _s16(S.cM_atan2s(fp.f32(-spAC[1]), _abs_xz(spAC[0], spAC[2])) - self.x)
        r25_3 = _s16(S.cM_atan2s(spAC[0], spAC[2]) - m34de - self.y)

        if gate:
            # :9087-9102 -- the target's angles off the head centre, clamped.
            spB8 = (fsubs(fp.f32(look_pos[0]), spC4[0]),
                    fsubs(fp.f32(look_pos[1]), spC4[1]),
                    fsubs(fp.f32(look_pos[2]), spC4[2]))
            r27 = _s16(S.cM_atan2s(fp.f32(-spB8[1]), _abs_xz(spB8[0], spB8[2])))
            r23_3 = _s16(S.cM_atan2s(spB8[0], spB8[2]) - m34de)
            if float(_abs_xz(spB8[0], spB8[2])) < 30.0:
                r23_3 = self.y
            if r27 > PITCH_MAX:
                r27 = PITCH_MAX
            elif r27 < PITCH_MIN:
                r27 = PITCH_MIN
            if r23_3 > YAW_CLAMP:
                r23_3 = YAW_CLAMP
            elif r23_3 < -YAW_CLAMP:
                r23_3 = -YAW_CLAMP
            if flg80:
                # :9103-9110 half-angle (upper anim is never DASHKAZE in the land regime).
                r4 = _s16((r27 >> 1) - r24_4)
                r23 = _s16((r23_3 >> 1) - r25_3)
            else:
                r4 = _s16(r27 - r24_4)
                r23 = _s16(r23_3 - r25_3)
        else:
            # Gate failed: every reachable else-branch lands r4 = r23 = 0 (the :9138 m34C3==1 arm
            # reads m34E2 >> 1 -- 0 across the whole courtyard window, live-probed).
            r4 = 0
            r23 = 0

        self.x = _s16(cLib_addCalcAngleS(self.x & 0xFFFF, r4 & 0xFFFF, *CHASE))
        self.y = _s16(cLib_addCalcAngleS(self.y & 0xFFFF, r23 & 0xFFFF, *CHASE))
        if flg80:
            # :9159-9165 -- keep the SUMMED yaw (anim + twist) inside the clamp (gated on
            # ModeFlg_00000080 alone, NOT on a selected look pos).
            t = _s16(r25_3 + self.y)
            if t > YAW_CLAMP:
                self.y = _s16(YAW_CLAMP - r25_3)
            elif t < -YAW_CLAMP:
                self.y = _s16(-(YAW_CLAMP + r25_3))
        self.z = _s16(cLib_addCalcAngleS(self.z & 0xFFFF, 0, *CHASE))
        return self
