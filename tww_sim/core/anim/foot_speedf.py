"""foot_speedf.py - offline posMoveFromFootPos: turn (mNormalSpeed, mStickDistance) into the walk
position speed `speedF`, bit-faithfully.

This is the last link of the land-walk position chain. It composes the three ported subsystems:
  UnderAnimState (anim_state.py)  -- which anims fill MOVE0/MOVE1, their frame-ctrl frames, the
                                     blend ratio, and m3598 (the WALK<->DASH speedF blend), all a
                                     bit-exact function of the already-bit-exact mNormalSpeed.
  FootFK (foot_fk.py)             -- the stateful foot forward-kinematics with the oldframe-morf,
                                     giving the model-local foot toe both feet.
  posMoveFromFootPos math (here)  -- plant select, the 1-frame-delayed toe delta f31_2, the
                                     recursive smoothing, and speedF = nspeed*(1-m3598) +/- f31_2*m3598.

Faithful to d_a_player_main.cpp:2353. Reproduces live speedF bit-exact (float ~1e-5) across the
flat on-axis walk INCLUDING the standing->walk entry: while nspeed==0 the game keeps drawing the
standing idle (FREEB advancing at rate 1.0), and the first moving frame's f31_2 is exactly the
idle-drift delta absXZ(FK(FREEB@f+2) - FK(FREEB@f+1)). We reproduce that by advancing the idle
during the input-latency frames. The fully-stopped frame (nspeed hits 0) has speedF=0 (the MOVE
proc is exiting, posMoveFromFootPos no longer drives position).

SCOPE: the normal flat, on-axis, free walk from a FREEB standing idle (the land_flatwalk anchor).
One walk burst. Attention/heavy/slope/ice, and re-entering idle after a stop, are future tiers.

Requires the gitignored _generated/anim keyframe data (Link.arc/LkAnm.arc, dev-supplied); if it is
absent `FootSpeedF()` raises and tww_sim.land falls back to its calibrated speedF stand-in. Use
`FootSpeedF.available()` to probe without raising.
"""
import math
import os

from .. import fp
from . import fk
from .anim_state import (UnderAnimState, ANIM_META, ANIM_CODE, ANIM_ORDER,
                         NATIVE_META_MAX, NATIVE_META_ATTR, NATIVE_HIO, H_38, H_40,
                         H_3C, H_10, H_68, H_6C, H_70)

# Optional native composition (anim/_anmc.foot_compose); bit-exact with _py_foot_compose below.
try:
    from . import _anmc as _N
except ImportError:
    _N = None

# f32 literals from the posMoveFromFootPos recursive-smoothing (d_a_player_main.cpp:2400).
_F0_3 = fp.f32(0.3)
_F0_7 = fp.f32(0.7)
IDLE_ANIM = 'freeb'
# posMoveFromFootPos rest offset used only when oldFrameFlg==false (Link never posed the walk yet).
# Not reached from a standing anchor (flag already true); kept for provenance.
REST_TOE = ((-14.05, 0.0, 5.02), (14.05, 0.0, 5.02))   # [right, left]


def _f32(x):
    return fp.f32(float(x))


def _sqrtf(x):
    """std::sqrtf (MSL math.h): frsqrte seed + 3 Newton refines in DOUBLE, then f32(x*guess).
    The crude frsqrte seed (~5 bits) is fully washed out by 3 Newton steps (the comment claims 32
    sig bits, > f32's 24), so a math-accurate double seed gives the byte-identical f32 result."""
    x = fp.f32(x)
    if x > 0.0:
        g = 1.0 / math.sqrt(x)                        # frsqrte seed (low bits irrelevant after Newton)
        g = 0.5 * g * (3.0 - g * g * x)               # all 3 refines in f64
        g = 0.5 * g * (3.0 - g * g * x)
        g = 0.5 * g * (3.0 - g * g * x)
        return fp.f32(x * g)                          # y = (float)(x * guess)
    return fp.f32(x)


def _absxz(dx, dz):
    """cXyz::absXZ() for the toe delta (dx,0,dz): sqrtf(abs2XZ) where abs2XZ is the paired-single
    PSVECSquareMag == fmadds(dz,dz, fmuls(dx,dx)) (f32, one fused round of dz*dz onto the f32 dx*dx),
    NOT the double-precision math.hypot. See tww c_xyz.h / dolphin/mtx/vec.c PSVECSquareMag."""
    sq = fp.fmadds(dz, dz, fp.fmuls(dx, dx))
    return _sqrtf(sq)


def _plant_of(feet):
    """m34BC on flat ground: index (0=right jnt39, 1=left jnt34) of the lower toe/heel midpoint Y.
    `feet` is the flat 12-tuple [Rtoe, Ltoe, Rheel, Lheel] x (x,y,z) from step_feet/pose_toe."""
    m0 = _f32((feet[1] + feet[7]) * 0.5)     # right: toe.y (idx 1) + heel.y (idx 7)
    m1 = _f32((feet[4] + feet[10]) * 0.5)    # left:  toe.y (idx 4) + heel.y (idx 10)
    return 0 if m0 < m1 else 1


def _py_foot_compose(t1, t2, nspeed, msd, m3598, prev_f312, m35B4, gnd_r3=0):
    """Pure-Python posMoveFromFootPos toe->speedF (fallback for _anmc.foot_compose). t1/t2 are the
    flat 12-tuples of the last two DRAWN frames. Returns (speedF, f312). `gnd_r3` = the ground
    slope angle (getGroundAngle at the previous CrrPos poly, Phase G floors mode): the scale
    ``sp7C.z *= cM_scos(r3); if (r3 < 0) *= 0.85`` (d_a_player_main.cpp:2414-2417) applies between
    the blend and the 0.05 snap; 0 skips it (== fmuls by 1.0, byte-identical flat)."""
    plant = _plant_of(t1)
    o = plant * 3
    dx = _f32(t1[o + 0] - t2[o + 0])
    dz = _f32(t1[o + 2] - t2[o + 2])
    f312 = _absxz(dx, dz)
    if m3598 < 1.0 and abs(_f32(m35B4 - msd)) < 0.2:
        f312 = fp.fadds(fp.fmuls(f312, _F0_3), fp.fmuls(_F0_7, prev_f312))
    spz = _f32(nspeed * _f32(1.0 - m3598))
    spz = _f32(spz + _f32(f312 * m3598)) if nspeed >= 0.0 else _f32(spz - _f32(f312 * m3598))
    if gnd_r3:
        from ..mathlib import cM_scos_s16
        spz = fp.fmuls(spz, cM_scos_s16(gnd_r3))
        if gnd_r3 < 0:
            spz = fp.fmuls(spz, _f32(0.85))
    speedF = 0.0 if abs(spz) < 0.05 else spz
    return speedF, f312


class FootSpeedF:
    """Stateful offline posMoveFromFootPos driver. step(nspeed, msd) -> speedF for this frame.

    Seed idle_frame with the live FREEB frame-controller value at the anchor (mFrameCtrlUnder[0]
    frame); it fixes the entry idle-drift phase. Default 70.0 = the land_flatwalk anchor.
    """

    @staticmethod
    def available():
        """True iff the generated anim + skeleton data is present (so the engine can run)."""
        try:
            fk.load()
            return True
        except (FileNotFoundError, OSError):
            return False

    def __init__(self, idle_frame=70.0, idle_anim=IDLE_ANIM, pos_x=0.0,
                 pos_z=764.0791015625, pos_y=0.0, facing=0, native=True, sword=False):
        self.anm, self.sk = fk.load()                 # raises if the data is absent
        self.idle_anim = idle_anim
        self.sword = bool(sword)                       # sword equipped -> DASH poses as DASHS (leg pose)
        self._core = None                             # fused native engine (set up below if available)
        self._idle_frame_py = float(idle_frame)       # backing store for the idle_frame property
        self.idle_end = float(ANIM_META[idle_anim][0])
        self.st = UnderAnimState(move0_anim=idle_anim, move0_frame=self.idle_frame, m34C3=0,
                                 sword=self.sword)
        from .foot_fk import FootFK
        self.ff = FootFK(self.anm, self.sk)
        # Link's world pose for the frame being posed (the foot FK runs from worldBase(pos)). LandState
        # updates it via set_pos BEFORE each step; seeded here at the anchor rest pose.
        self.pos_x = float(pos_x)
        self.pos_z = float(pos_z)
        # Link's world Y: the m37B4 base-cancellation rounding depends on |Y| (fk.world_base
        # docstring) -- a y=-6534 floor shifts pose coords by ULPs vs the old py=0.
        self.pos_y = float(pos_y)
        # shape_angle.z: the MOVE turn lean (m351C >> 1, setMoveSlantAngle) baked into the model
        # base by setWorldMatrix's ZXYrotM. 0 at rest and on any straight walk.
        self.lean = 0
        self.facing = int(facing) & 0xFFFF
        self.ff.set_pos(self.pos_x, self.pos_z, py=self.pos_y, facing=self.facing)
        self.started = False
        self.stopped = False
        self._rest_blend = False                       # seed_rest_blend() from-rest mode (WAIT(4) blend)
        self._rest_single = False                      # seeded low-life WAITATOB single (m34C3 == 0)
        self._rest_idle = 'waits'                      # MOVE0 idle anim for a seeded mode-2 WAIT
        self._rest_noops = 0                           # leading alignment no-op steps (DTM gate padding)
        # Deferred-draw mode: pose at frame END / post-integration pos like the game (see
        # finish_draw docstring). Off by default: legacy pre-integration draw, byte-identical.
        self.defer_draw = False
        self._pending_draw = None
        # Opt-in fast path (default OFF): cruise (m3598==0) poses defer into _skipped and replay on
        # the first consumer -- bit-exact for EVERY stream. See finish_draw/_drain_skipped.
        self.skip_cruise_pose = False
        self._skipped = []
        # Phase G: per-frame slope angle r3 (speedF scale) + footBgCheck's m35B8 foot lift
        # (baked into every _apply_base); 0 / 0.0 = the byte-identical flat fast path.
        # m35c4 = the setStepsOffset walk lift (draw base y = pos.y + m35C4, :9561);
        # floors mode sets it per frame, 0.0 = byte-identical flat.
        self.m35c4 = 0.0
        self.gnd_r3 = 0
        self.m35b8 = 0.0
        # Seed the FootFK old pose + delayed toe stream (t1=draw_{N-1}, t2=draw_{N-2}) with the
        # idle rest pose. Pre-walk seeds only feed m3598==0 frames (speedF==0), so they're immaterial.
        self.ff.seed(idle_anim, self.idle_frame)
        draw0 = self.ff.step_feet(idle_anim, idle_anim, self.idle_frame, self.idle_frame, 0.0, -1.0)
        self.t1 = draw0
        self.t2 = draw0
        self.prev_f312 = 0.0
        self.m35B4 = 0.0                               # previous frame's mStickDistance
        self._single_entered = False                   # single-anim entry frame: hold the ctrl at start
        self._pending_py = None                        # morf to apply on the next step (Python fallback store)
        # Fused native path (one C call/frame): the Python seeding above already left the engine's
        # old-pose correct + produced draw0; w_init captures the toe stream. Python st/ff = fallback.
        # sword=True keeps the Python foot STATE (the C engine poses the pair via PoseEngine.set_sword
        # but has no subjectivity proc, which this path's sword callers need). anim-engine.md.
        use_native = native and not self.sword
        if use_native and _N is not None and getattr(self.ff, '_engine', None) is not None:
            _N.init_anim_consts(NATIVE_META_MAX, NATIVE_META_ATTR, NATIVE_HIO)   # idempotent
            code2idx = [self.ff._anim_idx[name] for name in ANIM_ORDER]
            self._core = self.ff._engine
            self._core.init_anim(code2idx)
            self._core.w_init(ANIM_CODE[idle_anim], self._idle_frame_py, draw0)
        elif not use_native:
            # Force the pure-Python st/ff path (drop only the C-resident STATE; native math accel stays)
            # -- the SUBJECTIVITY freeze lives on the Python UnderAnimState. draw0/seed above left t1/t2 exact.
            self.ff._engine = None

    def clone(self):
        """State-copy clone (mid-walk-safe). Shares the immutable parsed anim/skeleton; deep-copies
        the stateful anim engine (the fused C PoseEngine via FootFK.clone, or the Python
        UnderAnimState) + the delayed toe stream, so a clone taken mid-walk continues bit-exactly
        (0 divergence at every frame). Replaces the old rebuild-at-rest clone, which reset the toe
        stream to the idle pose and so was only valid to clone before the first walk step."""
        c = FootSpeedF.__new__(FootSpeedF)
        c.anm = self.anm; c.sk = self.sk
        c.idle_anim = self.idle_anim
        c.sword = self.sword
        c.idle_end = self.idle_end
        c.pos_x = self.pos_x; c.pos_z = self.pos_z; c.pos_y = self.pos_y; c.facing = self.facing
        c.lean = self.lean
        c.started = self.started; c.stopped = self.stopped
        c._single_entered = self._single_entered
        c._idle_frame_py = self._idle_frame_py
        c._pending_py = self._pending_py
        c._rest_blend = self._rest_blend
        c._rest_single = self._rest_single
        c._rest_idle = self._rest_idle
        c._rest_noops = self._rest_noops
        c.defer_draw = self.defer_draw
        c._pending_draw = self._pending_draw
        c.skip_cruise_pose = self.skip_cruise_pose
        c._skipped = list(self._skipped)
        c.gnd_r3 = self.gnd_r3
        c.m35b8 = self.m35b8
        c.m35c4 = self.m35c4
        c.st = self.st.clone()
        c.ff = self.ff.clone()
        c._core = c.ff._engine                 # fused engine lives on the cloned FootFK (None in Py mode)
        c.t1 = self.t1; c.t2 = self.t2         # flat toe tuples (immutable) -> share the reference
        c.prev_f312 = self.prev_f312
        c.m35B4 = self.m35B4
        return c

    @property
    def idle_frame(self):
        """The (drifting) standing-idle frame. Fused mode tracks it in C; clone reads it here so a
        clone taken mid input-latency drift re-seeds at the right phase (matches the Python path)."""
        return self._core.w_get_idle_frame() if self._core is not None else self._idle_frame_py

    @idle_frame.setter
    def idle_frame(self, v):
        # Only the Python fallback mutates this (fused w_step owns the C copy).
        self._idle_frame_py = float(v)

    @property
    def _pending_morf(self):
        return self._core.w_get_pending() if self._core is not None else self._pending_py

    @_pending_morf.setter
    def _pending_morf(self, v):
        if self._core is not None:
            self._core.w_set_pending(v)
        else:
            self._pending_py = v

    def set_pos(self, px, pz, facing=0, py=None, lean=None):
        """LandState calls this each frame BEFORE stepping, with the CURRENT (pre-integration) world
        pos + shape_angle.y. The foot FK poses from worldBase(pos), so the toe carries the game's
        world-magnitude quantization for THIS frame's draw (stored into the toe stream). `py` =
        Link's world Y; `lean` = shape_angle.z (the m351C>>1 MOVE turn lean, setWorldMatrix's
        ZXYrotM z term). Omitting either keeps the previous value."""
        self.pos_x = fp.f32(px)
        self.pos_z = fp.f32(pz)
        if py is not None:
            self.pos_y = fp.f32(py)
        if lean is not None:
            self.lean = int(lean) & 0xFFFF
        self.facing = int(facing) & 0xFFFF
        if self._core is not None:
            self._core.set_pos(self.pos_x, self.pos_y, self.pos_z, self.facing)

    def _apply_base(self):
        py = fp.fadds(_f32(self.pos_y), self.m35c4) if self.m35c4 else self.pos_y
        self.ff.set_pos(self.pos_x, self.pos_z, py=py, facing=self.facing, lean=self.lean,
                        m35b8=self.m35b8)

    def seed_rest_blend(self, d_frame, w_frame, d_rate, w_rate, m359C, m35B4=0.0, noops=0,
                        t1=None, t2=None, idle_anim='waits'):
        """Seed the anchor-REST WAIT(4) under-body state so the sim is bit-exact FROM REST -- no
        mid-run live calibration. A healthy anchor uses the setMoveAnime(ANM_WAITS, ANM_WALK,
        r29=2) blend; a settled critical-health anchor uses ANM_WAITB instead. In both, MOVE0
        advances at captured `d_rate`, MOVE1=WALK(S)
        advancing at `w_rate`, both live every rest frame, with posMoveFromFootPos running (so the
        toe stream + the m359C 0.3/0.7 recursion are ACTIVE at rest). Args are the live rest values
        (mint captures them into the anchor's seed json): d_frame/w_frame/d_rate/w_rate = the two
        J3DFrameCtrl phases+rates (player +0x2F64/+0x2F78/+0x2F60/+0x2F74), m359C/m35B4 = the
        smoothing state (+0x34C4/+0x34DC). `noops` = leading step() calls to IGNORE entirely: a
        savestate-anchored DTM's first frames exist only for row alignment (the game has not run
        yet), verified live = 2 for the run_dtm pipeline (see harness/rollstab/calibrate.py).

        `t1`/`t2` (flat 12-tuples [rtoe, ltoe, rheel, lheel] xyz) = the anchor's STORED delayed
        foot poses, read from RAM (mFootData[i].field_0x018/0x00C; JP player +0x3CF8/+0x3CEC and
        +0x3E10/+0x3E04): t2 directly at rest, t1 after ONE paused frame-advance. Pass them for a
        TRANSLATED (minted) anchor -- the stored poses carry the ORIGINAL position's f32 rounding
        noise, which re-posing at the shifted position cannot reproduce (this was the ~1e-4
        translated-anchor z residual of session 9). When omitted, both are re-posed at the current
        anchor pos (exact for anchors resting where they were captured).
        Python foot path only (the fused native engine carries no WAIT-blend rest state)."""
        if self._core is not None:
            raise NotImplementedError("seed_rest_blend needs the pure-Python foot path (native=False)")
        if idle_anim not in ('waits', 'waitb'):
            raise ValueError("rest idle must be 'waits' or 'waitb'")
        st = self.st
        w_anim = st._walk
        st.move0 = idle_anim
        st.move1 = w_anim
        st.m34C3 = 2
        st.ratio = 0.0
        st.m3598 = 0.0
        st.fc0.set(ANIM_META[idle_anim][1], 0.0, float(ANIM_META[idle_anim][0]), float(d_rate),
                   float(d_frame))
        st.fc1.set(ANIM_META[w_anim][1], 0.0, float(ANIM_META[w_anim][0]), float(w_rate),
                   float(w_frame))
        # Rest toe stream: the last two drawn rest poses; the step_feet calls also leave the
        # ff internal old pose (morf source). Explicit t1/t2 captures then override the compose inputs.
        f0p = _f32(d_frame - d_rate)
        if f0p < 0.0:
            f0p = _f32(f0p + float(ANIM_META[idle_anim][0]))
        f1p = _f32(w_frame - w_rate)
        if f1p < 0.0:
            f1p = _f32(f1p + float(ANIM_META[w_anim][0]))
        self._apply_base()
        self.t2 = self.ff.step_feet(idle_anim, w_anim, f0p, f1p, st.ratio, -1.0)
        self.t1 = self.ff.step_feet(idle_anim, w_anim, float(d_frame), float(w_frame), st.ratio, -1.0)
        if t1 is not None:
            self.t1 = tuple(_f32(v) for v in t1)
        if t2 is not None:
            self.t2 = tuple(_f32(v) for v in t2)
        self.prev_f312 = float(m359C)
        self.m35B4 = _f32(m35B4)
        self._rest_blend = True
        self._rest_single = False
        self._rest_idle = idle_anim
        self._rest_noops = int(noops)
        self.defer_draw = True     # from-rest exactness requires the game's end-of-frame draw pos

    def seed_rest_single(self, d_frame, d_rate, m359C, m35B4=0.0, noops=0,
                         t1=None, t2=None):
        """Seed an in-progress critical-health ``ANM_WAITATOB`` WAIT pose.

        Unlike the ordinary WAIT blend, this is a single animation (``m34C3 == 0``) whose frame
        controller runs from 0 through the HIO end frame 12 at rate 0.6.  A following walk resets
        its WALK/DASH controller phase to zero, which changes the first few foot-driven ``speedF``
        values even though ``mNormalSpeed`` acceleration itself is health-independent.

        ``d_frame``/``d_rate`` and the delayed toe stream are captured from the live player just as
        they are for :meth:`seed_rest_blend`.  The next simulated WAIT frame advances the existing
        single; it is not treated as a fresh ``procWait_init`` entry.
        """
        if self._core is not None:
            raise NotImplementedError("seed_rest_single needs the pure-Python foot path (native=False)")
        st = self.st
        st.move0 = 'waitatob'
        st.move1 = None
        st.m34C3 = 0
        st.ratio = 0.0
        st.m3598 = 0.0
        st.fc0.set(ANIM_META['waitatob'][1], 0.0, float(H_10), float(d_rate), float(d_frame))

        previous = max(0.0, _f32(d_frame - d_rate))
        self._apply_base()
        self.t2 = self.ff.step_feet('waitatob', 'waitatob', previous, previous, 0.0, -1.0)
        self.t1 = self.ff.step_feet('waitatob', 'waitatob', float(d_frame), float(d_frame), 0.0, -1.0)
        if t1 is not None:
            self.t1 = tuple(_f32(v) for v in t1)
        if t2 is not None:
            self.t2 = tuple(_f32(v) for v in t2)
        self.prev_f312 = float(m359C)
        self.m35B4 = _f32(m35B4)
        self.started = False
        self._single_entered = False
        self._pending_morf = None
        self._rest_blend = False
        self._rest_single = True
        self._rest_idle = 'waitb'
        self._rest_noops = int(noops)
        self.defer_draw = True

    def enter_single(self, anim, morf, start=0.0, end=None, rate=1.0):
        """setSingleMoveAnime(anim, rate, start, end, morf) (12794): the under-body switches to a single
        anim (m34C3=0), so posMoveFromFootPos keeps posing the foot + updating the toe stream while m3598
        stays frozen (=> speedF stays the proc's own value: roll/slip momentum, WaitTurn frozen at 0).
        Because m34C3==0, the following walk blend re-inits its frame ctrl to 0 on the proc->MOVE exit.
        Shared by procFrontRoll_init (ANM_ROLLF), procWaitTurn_init (ANM_ROT), procSlip_init (ANM_SLIP);
        call step_single_anim() each proc frame. `end` defaults to the anim's frameMax."""
        if end is None:
            end = float(ANIM_META[anim][0])
        if self._core is not None:
            self.started = True
            self._core.w_enter_single(ANIM_CODE[anim], float(morf) if morf is not None else 0.0,
                                      float(start), float(end), float(rate), morf is not None)
            return
        self.st.set_single(anim, start, end, rate)
        self.started = True
        self._single_entered = True                # entry frame: don't advance the ctrl (matches land)
        self._pending_morf = float(morf) if morf is not None else None

    def enter_roll(self, morf=2.0, start=0.0, end=19.0, rate=1.1):
        """procFrontRoll_init: setSingleMoveAnime(ANM_ROLLF). morf = the roll-entry oldframe-morf
        (mRoll.field_0x14); it decays out long before the exit."""
        self.enter_single('rollf', morf, start, end, rate)

    def step_single_anim(self, nspeed, msd):
        """One single-anim proc frame: advance the anim frame ctrl, pose the foot, run the
        posMoveFromFootPos toe-stream bookkeeping (f31_2, m359C, stored toe). Returns speedF (which the
        caller discards for the momentum/frozen procs). Its real job is warming the toe stream so the
        post-proc walk tail is bit-exact.

        Sets `started` (the getOldFrameFlg() analog, posMoveFromFootPos d_a_player_main.cpp:2354) like
        step_atn/enter_wait_idle/enter_single do: posing a roll/proc-9/slip frame leaves oldFrameFlg
        true, so a FOLLOWING MOVE (esp. a NEGATIVE-nspeed backslide) must NOT take the cold rest path
        in step() and return 0. Golden-inert: every real roll/slip/WAIT_TURN enters via enter_single
        (which already sets started) BEFORE this runs, so this only bites a state SEEDED directly into a
        single-anim proc (the couple_replay / from-state-2 convention that skips the proc init)."""
        if self._core is not None:
            return self._core.w_step_single(_f32(nspeed), _f32(msd))
        self.started = True
        nspeed = _f32(nspeed)
        msd = _f32(msd)
        morf = self._pending_morf if self._pending_morf is not None else -1.0
        self._pending_morf = None
        if self._single_entered:                   # entry frame: pose at the start frame (no ctrl advance)
            self._single_entered = False
            state = dict(move0=self.st.move0, move1=self.st.move0, f0=self.st.fc0.frame,
                         f1=self.st.fc0.frame, ratio=0.0, m3598=self.st.m3598, morf=False)
        else:
            state = self.st.step_single()
        return self._foot_speedf(nspeed, msd, state, morf)

    # back-compat alias: the roll uses the shared single-anim stepper.
    step_roll = step_single_anim

    def enter_wait_idle(self, ratio, r27_anim, morf, msd):
        """One WAIT idle-proc frame right after a WAIT_TURN pivot (procWait_init/procWait ->
        setBlendMoveAnime idle branch, ModeFlg_00000001, shape_angle.y != m34DE). Poses the
        WAITS/ANM_ATNW{L,R}S turn-step blend (m3598=0) and updates the toe stream so the following
        walk-off entry (its f31_2 = |ATNW pose - the last ROT pose|) is bit-exact. mNormalSpeed is 0
        (WAIT) so speedF/position is 0 this frame; the pose only warms t1. Sets `_pending_morf` so
        the next frame's walk step re-triggers the oldframe-morf (procMove_init on WAIT->MOVE, 6215)."""
        self.started = True
        m = float(morf)
        if self._core is not None:
            return self._core.w_enter_wait_idle(float(ratio), ANIM_CODE[r27_anim], m, _f32(msd))
        self.st.set_wait_idle(ratio, r27_anim, m)
        state = dict(move0=self.st.move0, move1=self.st.move1, f0=self.st.fc0.frame,
                     f1=self.st.fc1.frame, ratio=self.st.ratio, m3598=self.st.m3598, morf=True)
        self._foot_speedf(0.0, _f32(msd), state, m)   # poses ATNW@0, shifts it into the toe stream
        self._pending_morf = m
        return 0.0

    def pose_idle_blend(self, msd, morf=None, low_life=False):
        """setBlendMoveAnime's ModeFlg_00000001 IDLE arm (d_a_player_main.cpp:3114).

        The one law behind every standing re-pose: the J3DFrameCtrls advance one frame (actor
        execute), then setBlendMoveAnime -- reached at mNormalSpeed == 0, so f30 == 0 puts it in
        regime 1 -- takes the idle arm and calls
        setMoveAnime(f27=0, f28=H_38, f25=H_40, ANM_WAITS, ANM_WALK, r29=2, param_1):
        Healthy MOVE0=WAITS (rate 1.1). With `low_life`, checkRestHPAnime selects WAITB (rate 0.4).
        MOVE1 is WALK, m34C3=2, ratio 0, and
        **m3598 = 0** (the idle arm's defining difference from the regime-1 blend, which would set
        m3598 = 1 and let the idle toe drift drive speedF). Phase f31 is PRESERVED from the walk
        (old m34C3 == 1), so the eventual re-walk resumes on the carried WAITS phase.

        mNormalSpeed is 0, so speedF and position are frozen; the pose's real job is to keep the toe
        stream advancing at the idle drift -- which is what the NEXT walk frame's f31_2 measures.

        `morf` = the setBlendMoveAnime argument: mBasic.field_0xC on a proc *_init (procWait_init
        6068, procSubjectivity_init 5948, procMove_init 6215), None/-1 on a steady body frame
        (procWait 6144 passes -1.0f). Callers own `started`. Python-path only; the native twin is
        `_anmc.PoseEngine._w_pose_idle_blend_c`.

        The sub-branches this does NOT take: the turn-step arm (shape_angle.y != m34DE and no
        attention lock -> WAITS/ATNW{L,R}S, `enter_wait_idle`) and the confused WAITQ single."""
        if self._core is not None:
            raise NotImplementedError("the idle-blend re-pose needs the pure-Python foot path (native=False)")
        msd = _f32(msd)
        m = float(morf) if morf is not None else -1.0
        idle_anim = 'waitb' if low_life else 'waits'
        idle_rate = H_3C if low_life else H_38
        self.st.fc0.update()                        # actor execute advances the walk ctrl this frame
        self.st.fc1.update()
        self.st._set_move_anime(0.0, idle_rate, H_40, idle_anim, self.st._walk, 2, m)
        self.st.m3598 = 0.0
        state = dict(move0=idle_anim, move1=self.st._walk, f0=self.st.fc0.frame,
                     f1=self.st.fc1.frame, ratio=self.st.ratio, m3598=0.0, morf=(m >= 0.0))
        self._foot_speedf(0.0, msd, state, m)
        return 0.0

    def enter_subjectivity(self, msd, morf=2.4, low_life=False):
        """procSubjectivity_init on-axis (d_a_player_main.cpp:5948) -- the C-up-cancel FREEZE.
        setBlendMoveAnime(mBasic.field_0xC) -> the idle arm; see `pose_idle_blend`. Its HOLD frames
        are `step_subjectivity` (procSubjectivity does NOT re-pose), unlike WAIT's."""
        self.started = True
        return self.pose_idle_blend(msd, morf, low_life=low_life)

    def enter_wait(self, msd, morf=2.4, low_life=False):
        """procWait_init (d_a_player_main.cpp:6068): commonProcInit(WAIT), mNormalSpeed = 0, then
        setBlendMoveAnime(mBasic.field_0xC) -- the same idle arm as the subjectivity freeze. The
        proc that routed here (procMove 6229 / procAtnMove 6242 / ...) SKIPS its own
        setBlendMoveAnime when checkNextMode returns true, so this is the frame's only pose."""
        self.started = True
        return self.pose_idle_blend(msd, morf, low_life=low_life)

    def enter_wait_rest_hp(self):
        """procWait_init's LOW-LIFE arm (d_a_player_main.cpp:6072):
        `setSingleMoveAnime(ANM_WAITATOB, field_0x68, field_0x6C, field_0x10, field_0x70)`.

        Reached instead of setBlendMoveAnime when `checkRestHPAnime()` holds and the player is not
        guarding, and it is a completely different shape from the WAITS/WALK idle blend: a SINGLE
        anim (m34C3 -> 0), the wait A->B transition, at rate 0.6 from frame 0, with the frame ctrl's
        end forced to 12 (H_10) rather than the clip's own 13. Because m34C3 lands at 0, the WALK
        blend that follows re-inits its phase to 0 (`setMoveAnime` f31 = 0 when m34C3 == 0) instead
        of carrying the WAITS phase -- so this arm changes the RE-WALK too, not just the stop.

        commonProcInit (5805) zeroes m3598 on the way in; setSingleMoveAnime itself does not touch
        it, so it is set here (the caller's proc init is what did it).

        The frame controllers advance ONCE first (the actor-execute update for this frame, before
        the proc re-poses). MOVE0's is then overwritten by the single, so only MOVE1's advance
        survives -- and it is the LAST one it gets, because setSingleMoveAnime clears MOVE1's heap
        index (12798) and the model calc stops advancing a slot it no longer draws. Live: MOVE1's
        frame steps 12.4498 -> 13.0777 on the stop frame and then holds it through the whole single.

        Call once on the WAIT init frame, then `step_single_anim` per WAIT frame (that frame
        included -- `enter_single` holds the ctrl at the start frame for the entry pose)."""
        if self._core is not None:
            self.started = True
            self._core.w_enter_wait_rest_hp()
            return
        self.st.fc0.update()
        self.st.fc1.update()
        self.enter_single('waitatob', H_70, H_6C, H_10, H_68)
        self.st.m3598 = 0.0

    def step_wait(self, msd, low_life=False):
        """One procWait body frame (d_a_player_main.cpp:6093). Unlike procSubjectivity, procWait
        RE-POSES every frame -- `setBlendMoveAnime(-1.0f)` at 6144 (the m34C3 != 0, no-restHP arm)
        -- so the WAITS/WALK pair is re-derived and MOVE1's frame is re-slaved to MOVE0's phase
        instead of advancing on its own rate. The f31 = frame/60 -> frame = f31*60 round-trip is not
        an f32 identity, so the re-pose is not a no-op even when nothing else changes."""
        self.started = True
        return self.pose_idle_blend(msd, None, low_life=low_life)

    def step_subjectivity(self, msd):
        """One SUBJECTIVITY (or the post-B WAIT) HOLD frame. procSubjectivity only setBodyAngleToCamera,
        so the WAITS/WALK ctrls just advance (no re-pose/remap) and the foot poses at the frozen ratio
        (0 -> pure WAITS). mNormalSpeed=0 -> speedF 0 (position frozen); the pose keeps warming the toe
        stream so the carried phase stays bit-exact when MOVE resumes. Python-path only."""
        if self._core is not None:
            raise NotImplementedError("subjectivity freeze needs the pure-Python foot path (native=False)")
        msd = _f32(msd)
        self.st.fc0.update()
        self.st.fc1.update()
        state = dict(move0=self.st.move0, move1=self.st.move1, f0=self.st.fc0.frame,
                     f1=self.st.fc1.frame, ratio=self.st.ratio, m3598=self.st.m3598, morf=False)
        self._foot_speedf(0.0, msd, state, -1.0)
        return 0.0

    def step_atn(self, nspeed, msd, direction, f31, morf=None):
        """One ATN_MOVE frame (procAtnMove -> setBlendAtnMoveAnime, d_a_player_main.cpp:6249). Advances
        the frame ctrls, poses the ATN strafe/back anim (warming the toe stream for any following MOVE),
        and returns speedF via the same posMoveFromFootPos composition as the walk step. `direction` =
        mDirection (post setBlendAtnMoveAnime update, from LandState); `f31` = |nspeed*cos(gndAngle)|/max.
        `morf` = mBasic.field_0xC (2.4) on ATN entry or a direction change, else None (-1 = no morf)."""
        if self._core is not None:
            self.started = True
            return self._core.w_step_atn(_f32(nspeed), _f32(msd), int(direction), _f32(f31),
                                         float(morf) if morf is not None else 0.0, morf is not None)
        nspeed = _f32(nspeed)
        msd = _f32(msd)
        self.started = True
        m = float(morf) if morf is not None else -1.0
        state = self.st.step_atn(nspeed, direction, _f32(f31), m)
        return self._foot_speedf(nspeed, msd, state, m)

    def _shift(self, cur, f312, msd):
        self.m35B4 = _f32(msd)
        self.t2 = self.t1
        self.t1 = cur
        self.prev_f312 = f312

    def step(self, nspeed, msd, anim_nspeed=None):
        """Advance one frame. `nspeed` = mNormalSpeed (bit-exact from LandState), `msd` =
        mStickDistance (the acted-on/latency-delayed stick magnitude). Returns speedF.

        `anim_nspeed` splits the anim-blend speed from the position-integrating speed for the
        one frame where the game poses the walk anim at a DIFFERENT mNormalSpeed than it later
        integrates position with. This happens at procMoveTurn_init(1): setBlendMoveAnime runs
        (posing at the full pre-turn speed) BEFORE `mNormalSpeed *= 0.5` (6616 vs 6623), and
        posMoveFromFootPos integrates with the halved speed. Default None => same value for both."""
        if self._core is not None:
            return self._core.w_step(_f32(nspeed), _f32(msd),
                                     0.0 if anim_nspeed is None else _f32(anim_nspeed),
                                     anim_nspeed is not None)
        nspeed = _f32(nspeed)
        msd = _f32(msd)
        an = nspeed if anim_nspeed is None else _f32(anim_nspeed)

        if not self.started:
            if nspeed <= 0.0:
                if self._rest_blend or self._rest_single:
                    # A rest frame IS a procWait body frame (same idle re-pose as `step_wait`);
                    # alignment no-ops touch NOTHING, and `started` must stay False for the morf.
                    if self._rest_noops > 0:
                        self._rest_noops -= 1
                        return 0.0
                    if self._rest_single:
                        return self.step_single_anim(0.0, msd)
                    return self.pose_idle_blend(msd, low_life=(self._rest_idle == 'waitb'))
                # input-latency / standing frame: keep drawing the idle so its drift is carried
                # into the toe stream; the game's m3598 here is 0 so speedF is 0 regardless.
                self.idle_frame = fp.fadds(self.idle_frame, 1.0)
                self._apply_base()
                cur = self.ff.step_feet(self.idle_anim, self.idle_anim,
                                        self.idle_frame, self.idle_frame, 0.0, -1.0)
                self._shift(cur, 0.0, msd)
                return 0.0
            self.started = True
            morf = 2.4                                # oldframe-morf triggers at walk-proc entry
        elif abs(nspeed) <= 0.001:
            # MOVE exit (speed bled to ~0 -> WAIT): speedF = 0. Gate on |nspeed| not sign -- the EBS runs
            # MOVE at a large NEGATIVE mNormalSpeed and must still integrate the composition below.
            if self._skipped:
                self._drain_skipped()  # the stop writes m35B4 (consumed by the re-walk): sync first
            self.stopped = True
            self.m35B4 = msd
            return 0.0
        elif self._pending_morf is not None:
            morf = self._pending_morf                 # roll->walk re-entry: re-trigger oldframe-morf
            self._pending_morf = None
        else:
            morf = -1.0

        state = self.st.step(an)
        return self._foot_speedf(nspeed, msd, state, morf)

    def _foot_speedf(self, nspeed, msd, state, morf):
        """The shared posMoveFromFootPos math (d_a_player_main.cpp:2372+): pose the foot, take the
        1-frame-delayed plant toe delta f31_2 with the recursive smoothing, and compose
        speedF = nspeed*(1-m3598) +/- f31_2*m3598. The plant/delta/smoothing/compose tail runs in C
        (_anmc.foot_compose) when available, else the bit-identical _py_foot_compose. t1 = the toe
        DRAWN last frame (1-frame delay), t2 = the frame before (both flat 12-tuples).

        defer_draw: the compose consumes only t1/t2, so speedF is exact BEFORE the draw; the game
        actually draws at frame END (post-integration pos), so the draw is stashed for
        finish_draw() after the caller moves."""
        if self._skipped and state['m3598'] != 0.0:
            self._drain_skipped()      # this compose consumes the toe stream: replay the deferred poses
        if self.gnd_r3:
            # Phase G slope scale (floors mode, nonzero cell): Python compose carries the exact
            # cM_scos(r3)/x0.85 terms. r3 == 0 stays on the (bit-identical) fast path below.
            speedF, f312 = _py_foot_compose(self.t1, self.t2, nspeed, msd, state['m3598'],
                                            self.prev_f312, self.m35B4, self.gnd_r3)
        else:
            compose = _N.foot_compose if _N is not None else _py_foot_compose
            speedF, f312 = compose(self.t1, self.t2, nspeed, msd, state['m3598'],
                                   self.prev_f312, self.m35B4)
        if self.defer_draw:
            self._pending_draw = (state, morf, f312, msd)
            return speedF
        self._apply_base()
        cur = self.ff.step_feet(state['move0'], state['move1'], state['f0'], state['f1'],
                                state['ratio'], i_morf=morf)
        self._shift(cur, f312, msd)
        return speedF

    def finish_draw(self):
        """Deferred-draw completion: pose this frame's foot at the CURRENT (post-integration) base
        -- the caller re-set_pos's with the moved position first -- and shift the toe stream. Call
        once per frame after integration when defer_draw is on; a frame with no stashed draw (WAIT
        rest / stopped / no foot step) is a no-op."""
        if self._pending_draw is None:
            return
        state, morf, f312, msd = self._pending_draw
        self._pending_draw = None
        if self.skip_cruise_pose and state['m3598'] == 0.0:
            # Cruise frame (speedF==nspeed exactly): DEFER the pose with its draw base; the first
            # consumer drains in order, so every stream stays bit-exact. See _drain_skipped.
            self._skipped.append((state, morf, msd,
                                  (self.pos_x, self.pos_z, self.pos_y, self.facing, self.lean,
                                   self.m35c4)))
            return
        if self._skipped:
            self._drain_skipped()
        self._apply_base()
        cur = self.ff.step_feet(state['move0'], state['move1'], state['f0'], state['f1'],
                                state['ratio'], i_morf=morf)
        self._shift(cur, f312, msd)

    def _drain_skipped(self):
        """Replay the deferred cruise poses in order (each at its own stashed draw base), rebuilding
        the exact toe stream t1/t2 + the m359C recursion a consumer is about to read. Each frame's
        f312 is recomputed here with the progressively-correct t1/t2/prev_f312/m35B4 (the value
        stashed at skip time was computed against a stale stream and is discarded); its speedF term
        was nspeed exactly (m3598==0), so nothing else about the frame needs re-running."""
        compose = _N.foot_compose if _N is not None else _py_foot_compose
        base0 = (self.pos_x, self.pos_z, self.pos_y, self.facing, self.lean, self.m35c4)
        for state, morf, msd, base in self._skipped:
            (self.pos_x, self.pos_z, self.pos_y, self.facing, self.lean,
             self.m35c4) = base
            self._apply_base()
            _, f312 = compose(self.t1, self.t2, 0.0, msd, state['m3598'],
                              self.prev_f312, self.m35B4)
            cur = self.ff.step_feet(state['move0'], state['move1'], state['f0'], state['f1'],
                                    state['ratio'], i_morf=morf)
            self._shift(cur, f312, msd)
        self._skipped = []
        self.pos_x, self.pos_z, self.pos_y, self.facing, self.lean, self.m35c4 = base0

    def draw_sword(self):
        """Mid-walk sword pull-out: flip the foot anim set base -> sword (WALK/DASH -> WALKS/DASHS) at
        the draw-completion frame. When mEquipItem flips to daPyItem_SWORD_e, getAnmData re-selects the
        sword table (decomp d_a_player_main.cpp:12951), setMoveAnime re-fetches it EVERY frame (12734),
        and procMove's steady setBlendMoveAnime(-1.0f) passes i_morf < 0 (6229) -> NO oldframe-morf. So
        the swap is an INSTANTANEOUS, phase-preserved pose jump: setMoveAnime preserves f31 =
        frame/frameMax (12732) and WALK/WALKS + DASH/DASHS share frameMax (32), so the frame value is
        literally unchanged; only the leg keyframes change (WALK==WALKS legs, so DASH->DASHS is the one
        that moves the toe -- session 31). Idempotent. Python foot path only (the native _anmc has no
        DASHS in its anim array), so a FootSpeedF that may draw mid-walk must be built native=False."""
        if self._core is not None:
            raise NotImplementedError("mid-walk draw needs the pure-Python foot path (native=False)")
        self.sword = True
        self.st._walk = 'walks'
        self.st._dash = 'dashs'
