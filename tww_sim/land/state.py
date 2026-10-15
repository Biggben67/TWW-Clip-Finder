#!/usr/bin/env python3
"""state.py - the LandState class: one Link on flat, wall-free ground, stepped frame by frame.

Pure-offline transcription of the on-ground locomotion procs, validated bit-exact vs the live game
for `mNormalSpeed` (potential_speed) and the state machine on a flat, wall-free floor. LandState
carries the HIO constant block + the per-frame `step` dispatcher + position integration; the proc
bodies live in procs/* as mixins it multi-inherits (`_MoveMixin` first, the MRO base). Constants +
leaf helpers are in constants.py. See land.py (shim) for the preserved public import surface.

Decomp = spec (`tww/src/d/actor/d_a_player_main.cpp`):
  procMove (6221) -> setSpeedAndAngleNormal (2751) -> setNormalSpeedF (2301); stick via
  setStickData (10530). HIO walk constants: d_a_player_HIO_data.inc:8 (see LandState.HIO).

WHAT IS BIT-EXACT vs WHAT IS CALIBRATED (read this before trusting a number)
--------------------------------------------------------------------------
* `mNormalSpeed` (nspeed / potential_speed): BIT-EXACT. The +3.5/frame accel to the cap
  17 and the cLib_addCalc decel 17->14.5->12->9.5->7->4.5->2->0.2->0 fall straight out of
  setSpeedAndAngleNormal + setNormalSpeedF with the shipped HIO constants (0 fitting).
* state machine (FREE_WAIT 5 -> MOVE 6 -> WAIT 4) and the two angles: reproduced.
* `speedF` (true_speed) and hence POSITION: BIT-EXACT (float, ~1e-5) when the anim engine is
  available. On land the real speedF is foot-plant/animation driven -- posMoveFromFootPos (2353)
  reads the walk anim's foot-joint matrices -- so it needs the ported J3D animation runtime
  (core.anim: the BCK keyframe eval + reduced foot-chain FK + two-anim blend + oldframe-morf,
  all FMA-faithful). core.anim.foot_speedf.FootSpeedF is that chain; LandState drives it each
  frame and it reproduces speedF to ~1e-5 across accel/cruise/decel INCLUDING the standing->walk
  entry and the stop. Its keyframe DATA (Link.arc/LkAnm.arc) is copyrighted and gitignored under
  _generated/anim/, so it is dev-supplied: when absent, speedF FALLS BACK to a calibrated cLib
  chase toward mNormalSpeed (SPEEDF_CHASE below), matching the END position within +-3 and locked
  at steady state. => nspeed/state/angles are ULP-exact always; position is ~1e-5 with the anim
  data present, a +-3 model without it.

INPUT LATENCY: the game acts on the stick delivered 2 frames earlier (INPUT_DELAY). This one
constant reproduces BOTH observed edges: forward accel starts on the 3rd up-frame and the
release decel starts on the 3rd neutral-frame (live land_walk_gt.csv).
"""
from __future__ import annotations
import math
from ..core import mathlib as S
from ..core.mathlib import f32, cLib_addCalc, cM_scos_s16, s16_signed, main_stick_decode
from ..core.camera import CameraManual, LAND_SCALE
from .constants import *  # noqa: F401,F403  (proc enums, DIR_*, gates -- also re-exported by land.py)
from .constants import _STATE_TAG, _cM_ssin_s16
from .walls import wall_pass, sidle_blocks_roll, GRAVITY as walls_GRAVITY
from .floors import gnd_spz as _gnd_spz_fn, gnd_frame_end as _gnd_frame_end_fn
from .attention import AttentionLock, FRONT_CONE_HALF
from .hio import _LandHIO
from .procs.move import _MoveMixin
from .procs.atn import _AtnMixin
from .procs.atn_actor import _AtnActorMixin
from .procs.roll import _RollMixin
from .procs.crash import _CrashMixin
from .procs.cut import _CutMixin
from .procs.turn import _TurnMixin
from .procs.ballistic import _BallisticMixin
from .procs.freeze import _FreezeMixin


class LandState(_LandHIO, _MoveMixin, _AtnMixin, _AtnActorMixin, _RollMixin, _CrashMixin, _CutMixin,
                _TurnMixin, _BallisticMixin, _FreezeMixin):
    """One Link on flat, wall-free ground, stepped frame by frame. The land analogue of
    SwimState. Carries the two-angle model first-class (travel = current.angle.y velocity
    direction; facing = shape_angle.y visual body direction) even though the on-axis walk
    keeps them fused -- the brakeslide/EBS tiers exercise the split.

    Seed from a live frame-0 snapshot (pos_z, angles, csangle) exactly like run_tests seeds
    SwimState. Step with raw sticks; csangle is a per-frame input (default 0 = free-cam ref).
    """
    # HIO constant block (m_HIO->m{Move,AtnMove,Roll,Cut,Turn,Slip,...}) lives in hio.py as the
    # _LandHIO base (split out to keep this module under the size cap); read as self.<NAME> via MRO.

    def __init__(self, pos_z=764.079, pos_x=0.0, facing=0, travel=0, csangle=0,
                 state=FREE_WAIT, nspeed=0.0, speedF=0.0, idle_frame=DEFAULT_IDLE_FRAME,
                 use_anim=True, cam_scale=LAND_SCALE, pos_y=0.0, native=True, foot_native=True,
                 sword_drawn=False, idle_anim=None, walls=None, model_draw=False,
                 floors=None, gnd_seed=None, input_delay=INPUT_DELAY, low_life=False):
        self.pos_x = float(pos_x)
        self.pos_z = float(pos_z)
        # Phase W: `walls` = WALL tris in game traversal order -> the per-frame CrrPos wall
        # pass (land/walls.py). None => byte-identical wall-free. See mechanics/wall-response.md.
        self._walls = walls
        # Phase G: `floors` = GroundCross candidate tris (land/floors.py, the per-frame ground
        # pass); None => byte-identical flat. `gnd_seed` = anchor-RAM GroundState seed kwargs.
        self._gnd = None
        if floors is not None:
            from .floors import GroundState
            seed = dict(gnd_seed or {})
            self._gnd_waist_seed = seed.pop('waist', None)
            self._gnd = GroundState(floors, **seed)
            if not use_anim:
                raise ValueError("floors= requires the anim foot engine (use_anim=True)")
            native = False                 # the C twin has no ground response
            foot_native = False            # m35B8 / waist tracking need the Python foot path
        self.wall_hit = False                    # mAcch.ChkWallHit() (aggregate, 1-frame late)
        self.wall_cir_hit = (False, False, False)  # mAcchCir[i].ChkWallHit()
        self.wall_angle = (0, 0, 0)              # mAcchCir[i].GetWallAngleY() (s16)
        self.line_hit = False                    # LINE_CHECK_HIT
        # Planner-rejection signal (sidle-suppressed roll); a bonk = FRONT_ROLL_CRASH in visited.
        self.sidle_blocked = False
        # Planner-rejection signal: an A-press at or below ATTACK_MSD_MIN, which the game answers
        # with PUT_AWAY (sheathe) and not the roll -- the unmodeled dispatch, session 88.
        self.attack_blocked = False
        # Vertical state for the ballistic hops. pos_y accumulates in f32; ground_y = the jump-entry
        # height. Seed pos_y from live for a bit-exact airtime (the vertical rounding is magnitude-dependent).
        self.pos_y = f32(pos_y)
        self.speed_y = 0.0             # speed.y (integrated by gravity while airborne)
        self.gravity = 0.0             # per-proc gravity (set at hop entry)
        self.ground_y = f32(pos_y)     # m3688.y flat landing height (reset at hop entry)
        self.ground_hit = True         # mAcch GROUND_HIT (grounded at rest); re-derived each air frame
        self.air_anim = 0.0            # ROLLB frame ctrl during BACK_JUMP (gates the land) / land recovery
        self.facing = int(facing) & 0xFFFF     # shape_angle.y (s16)
        self.travel = int(travel) & 0xFFFF     # current.angle.y (s16)
        self.csangle = int(csangle) & 0xFFFF   # dCam_getControledAngleY (s16); set each frame from _cam
        # LAND camera (predict.CameraManual = dCamera_c::manualCamera, bit-exact); centered C-stick
        # -> frozen. cam_scale = styleParam[24] deg/frame (MM83 land=8.0). See camera.md.
        self._cam = CameraManual(csangle=self.csangle, scale=cam_scale)
        self.target = 0                        # m34E8 (s16), set each frame by setStickData
        self.m34dc = int(facing) & 0xFFFF      # stick want-angle pre-csangle (m34E8 = m34dc + csangle)
        self.m34ea = int(facing) & 0xFFFF      # PREVIOUS frame's m34dc (slip stick-flip detector, 11289)
        self.m34de = int(facing) & 0xFFFF      # PREVIOUS frame's shape_angle.y (11287; WAIT idle-anim turn-step)
        self.m351C = 0                         # MOVE turn-lean state (setMoveSlantAngle, 9499);
        #                                        shape_angle.z = m351C >> 1 tilts the setWorldMatrix base
        self._draw_lean = 0                    # shape_angle.z used at THIS frame's draw (pre-update
        #                                        m351C>>1): the body Co centre (body_cyl) reads it
        self.state = int(state)                # link_state / mCurProc
        self.nspeed = f32(nspeed)              # mNormalSpeed (potential_speed) -- bit-exact
        self.speedF = f32(speedF)              # position-integrating speed
        self.msd = 0.0                         # mStickDistance
        self.max_nspeed = f32(self.MAX_NSPEED) # mMaxNormalSpeed (switches 17/15/12 under ATN)
        self.direction = DIR_NONE              # mDirection (ATN physics branch selector)
        self.m34E6 = int(facing) & 0xFFFF      # facing lock captured on attention-lock engage
        self._l_prev = False                   # attention-lock (L) held last frame (rising edge)
        # Actor-lock (Z-target) machine (attention.py); `_atn_actor_pos` = the locked actor's world XZ.
        # None => inert (`_atn` stays NONE), so every single-actor path is byte-identical.
        self._atn = AttentionLock()
        self._atn_actor_pos = None
        # chaseAttention override: None = compute the real front-cone gate; True/False forces it (only
        # for a bare non-coupled replay whose Link position is wrong -- see _atn_target_present).
        self._atn_force_present = None
        self._subj_arm = False                 # C-up gesture seen -> enter SUBJECTIVITY next frame
        self._subj_ended = False               # B/A/L/C-DOWN ended the freeze (checkSubjectEnd) -> stick re-walks
        self._subj_frames = 0                  # body frames since the freeze locked (C-DOWN camera floor)
        self._cdown_run = 0                    # consecutive acted C-down frames (0x2000 subject-exit arming)
        self._abtn_prev = 0                    # acted buttons last frame (for the A/B mItemTrigger edge)
        self.visited = set()                   # every proc state this run passed through (path assertions)
        self.roll_frame = 0.0                  # ANM_ROLLF frame ctrl during FRONT_ROLL (times the exit)
        self._roll_entered = False             # entry frame: don't advance the anim ctrl yet
        # Sword-thrust cut (CUT_F / CUT_A) state -- the "roll stab". sword_drawn gates the roll->cut
        # trigger (a cut only fires out of a roll if the sword is out; a bare roll routes to MOVE).
        self.sword_drawn = bool(sword_drawn)   # gates the roll->cut trigger; see land-movement.md (roll stab)
        # checkRestHPAnime's SEEDED life half (life isn't simulated); False = healthy, the arm every
        # anchor and golden takes. See knowledge/model/wait-stop-pose.md (the low-life arm).
        self.low_life = bool(low_life)
        if self.low_life:
            # The native animation engine does not carry ANM_WAITB yet. Critical-health runs use
            # the Python foot state so WAITATOB -> WAITB and its delayed toe stream remain exact.
            native = False
            foot_native = False
        # Mid-walk sword pull-out (opt-in; FootSpeedF.draw_sword). OFF by default => byte-identical;
        # requires the pure-Python foot path (native _anmc has no DASHS), forced below.
        self._model_draw = bool(model_draw)
        self._draw_cd = None                   # countdown to the anim-set flip once the draw starts (None = idle)
        if self._model_draw:
            native = False
            foot_native = False
        self._b_held = False                   # swordButton() (B mItemButton, HELD) this frame
        self._b_trig = False                   # swordTrigger() (B mItemTrigger, RISING EDGE) this frame -- the
        #                                        actual roll->cut trigger (a HELD B never re-fires the edge)
        self.cut_frame = 0.0                   # mFrameCtrlUnder[MOVE0] frame during a cut (times the lunge/exit)
        self._cut_entered = False              # cut entry frame: no ctrl advance, nspeed carried, m3700_prev=0
        self._cut_m3700 = (0.0, 0.0, 0.0)      # previous frame's m3700 (anim joint-0 translate); reset 0 at init
        self._cut_add = (0.0, 0.0)             # this frame's rotated root-translate delta, added after the shared bottom
        # daPy_lk_c CC push (mStts.m_cc_move): consumed in posMove after posMoveFromFootPos, before
        # the m34C2 cut lunge + CrrPos (2558). None => byte-identical; set each frame via set_cc_move.
        self._cc_move = None
        self._cut_anim_cache = None            # loaded cutf/cuta anim dict (j3d_eval), lazy
        self.cut_target = None                 # mProcVar2.m34D4: the latched thrust aim (shape snaps here
        #                                        on the 1st cut proc frame). None -> straight (== roll facing).
        self.turn_target = 0                   # mProcVar2.m34D4 (WaitTurn facing-pivot target)
        self.turn_shape_scale = 0              # MoveTurn shape-sweep cLib params (m34D0/m34D4/m34D6)
        self.turn_shape_max = 0
        self.turn_shape_min = 0
        self._anim_nspeed = None               # 1-frame anim/integrate speed split (procMoveTurn_init halving)
        # Controller-input buffer (idx 0 = oldest = acted this frame): (sx,sy,btn,trigL,csx,csy). `input_delay`
        # = raw->physics latency (default 2 = walk goldens; a DTM replay is one stage in -> 1; see README).
        self._input_delay = int(input_delay)
        self._inbuf = [(128, 128, 0, 0, 128, 128)] * self._input_delay
        # Anim-driven speedF: the ported posMoveFromFootPos chain (bit-exact position). None when
        # disabled or the keyframe data is absent -> fall back to the SPEEDF_CHASE stand-in.
        self._foot = None
        if use_anim:
            try:
                from ..core.anim.foot_speedf import FootSpeedF
                kw = {} if idle_anim is None else {"idle_anim": idle_anim}
                self._foot = FootSpeedF(idle_frame=float(idle_frame), pos_x=self.pos_x,
                                        pos_z=self.pos_z, pos_y=self.pos_y, facing=self.facing,
                                        native=foot_native, sword=self.sword_drawn, **kw)
            except (FileNotFoundError, OSError, ImportError):
                self._foot = None
        if self._gnd is not None:
            if self._foot is None:
                raise ValueError("floors= requires the anim keyframe data (FootSpeedF)")
            self._foot.ff.track_waist = True
            if self._gnd_waist_seed is not None:
                self._foot.ff.last_waist = tuple(f32(v) for v in self._gnd_waist_seed)
        # Native land physics: fused C engine present -> the whole per-frame step is one LandCore call;
        # absent (or native=False, REQUIRED for the ballistic hops the C twin lacks) -> bit-identical Python.
        # A walls mesh forces the Python path too (the C twin has no wall response).
        self._core = self._build_core() if (native and walls is None) else None

    def _build_core(self):
        """Build the native LandCore over the fused PoseEngine, seeded from this LandState's current
        (rest) fields. Returns None when the fused engine is absent -> the Python step path is used."""
        foot = self._foot
        if foot is None or getattr(foot, "_core", None) is None:
            return None
        from ..core.anim import _anmc as _N
        _N.land_init_consts(_LAND_CONSTS)
        core = _N.LandCore()
        core.setup(foot._core, self.pos_x, self.pos_z, self.facing, self.travel,
                   self.csangle, self.state, self.nspeed, self.speedF, float(self._cam.scale))
        return core

    def clone(self, share_foot=False):
        """A deep copy that keeps stepping bit-exactly, mid-walk included.

        ``share_foot`` -- share the anim engine by reference rather than state-copying it. It is
        two thirds of this clone (9.5 us of 14.4), and it is dead weight for exactly one caller:
        a `from_f0.FreeRun` on the C engine keeps its `LandState` as a FIELD-HOLDER synced from
        `LandCore`, never calls `step` on it, and so leaves `_foot` at the f0 seed pose forever.
        Refused when `_core` is set, because there the foot IS the engine the core poses through
        and sharing it would alias two runs onto one pose."""
        if share_foot and self._core is not None:
            raise ValueError("share_foot is for a state that never steps its own anim engine; this "
                             "one drives a LandCore through _foot._core")
        s = LandState.__new__(LandState)
        s.__dict__.update(self.__dict__)
        s._inbuf = list(self._inbuf)
        s._cam = self._cam.clone()          # s16-integer camera: clone so A* nodes never alias one
        # Mutated every step, so sharing couples branches to each other AND to the parent; the
        # attention one silently changes the roll exit routing (proc 9 vs 6). See AttentionLock.clone.
        s._atn = self._atn.clone()
        s.visited = set(self.visited)
        if self._gnd is not None:
            s._gnd = self._gnd.clone()      # ground bookkeeping (m35B8 chase, probe hysteresis)
        # State-copy the stateful anim engine so the clone continues BIT-EXACTLY even MID-WALK (the
        # old path rebuilt fresh at rest, valid only pre-walk). FootSpeedF.clone carries the toe stream.
        if self._foot is not None:
            s._foot = self._foot if share_foot else self._foot.clone()
        # The native LandCore aliases the SAME PoseEngine as the clone's _foot; copy its physics +
        # camera state over that state-copied engine (was rebuilt fresh -> mid-walk anim was lost).
        if self._core is not None and s._foot is not None and getattr(s._foot, "_core", None) is not None:
            s._core = self._core.clone(s._foot._core)
        else:
            s._core = None
        return s

    # setMoveSlantAngle HIO constants (daPy_HIO_move_c1, d_a_player_HIO_data.inc)
    SLANT_THRESH = f32(0.95)       # field_0x4C: |speedF|/max above this -> lean chases
    SLANT_GAIN = f32(1.6)          # field_0x50: lean target per turn-delta tread
    SLANT_DECAY = f32(0.35)        # field_0x54: off-MOVE / slow decay factor
    SLANT_SCALE, SLANT_MAX, SLANT_MIN = 4, 200, 100   # field_0xC / 0x8 / 0xA (addCalcAngleS)

    def _set_move_slant_angle(self):
        """daPy_lk_c::setMoveSlantAngle (d_a_player_main.cpp:9499): the MOVE turn-lean state m351C.
        Runs at frame end AFTER setWorldMatrix (11561), so the lean it computes tilts the NEXT
        frame's base. target = 1.6 * (s16)(m34DE - shape_angle.y) * ((|speedF|/17 - 0.95)/0.05)
        while in MOVE above the speed threshold; else m351C decays by 35% (s16-truncated, snap to
        0 when the decrement truncates away). m34DE here is still the frame-START value (11287)."""
        fvar1 = f32(abs(f32(self.speedF / self.max_nspeed)))
        if self.state == MOVE and fvar1 > self.SLANT_THRESH:
            ratio = f32(f32(fvar1 - self.SLANT_THRESH) / f32(1.0 - self.SLANT_THRESH))
            tgt = int(f32(f32(self.SLANT_GAIN * s16_signed(self.m34de - self.facing)) * ratio))
            self.m351C = cLib_addCalcAngleS(self.m351C, tgt & 0xFFFF,
                                            self.SLANT_SCALE, self.SLANT_MAX, self.SLANT_MIN)
        else:
            sv = int(f32(s16_signed(self.m351C) * self.SLANT_DECAY))
            self.m351C = 0 if sv == 0 else (self.m351C - sv) & 0xFFFF

    def _sync_from_core(self):
        """Copy the LandCore's post-step public fields back onto this LandState (for tests/planners
        reading pos/state/etc.) and record the visited proc.

        **Sync every field a caller can SEE, not the ones the step happens to need.** A missing one is
        not inert: it reads as a measurement that never moved, and the physics gates cannot find it
        because nothing inside the sim reads the mirror. ``m351C`` was absent until session 148 and
        cost four sessions of terminals solved at the wrong body lean --
        `knowledge/strategy/the-lean-is-the-rolls-own-dispatch.md`."""
        c = self._core
        self.pos_x = c.pos_x
        self.pos_z = c.pos_z
        self.facing = c.facing
        self.travel = c.travel
        self.csangle = c.csangle
        self.state = c.state
        self.nspeed = c.nspeed
        self.speedF = c.speedF
        self.msd = c.msd
        self.max_nspeed = c.max_nspeed
        self.direction = c.direction
        self.m351C = int(c.m351C)
        self._draw_lean = int(c._draw_lean_c)
        self.visited.add(self.state)

    @property
    def anim_fc0(self):
        """The walk-anim frame-ctrl phase (`J3DFrameCtrl` frame of MOVE slot 0). At the 17u speed cap
        this advances a fixed +2.3/frame and the freeze coast is a pure function of it — the observable
        the fewest-frame freeze planner (`plan_land.reach_freeze(min_frames=True)`) uses to predict a
        start crawl's full-speed freeze. Reads whichever backend is active (native core / Python foot)."""
        if self._core is not None:
            return self._core.pe_phase[0]
        if self._foot is not None:
            return self._foot.st.fc0.frame
        return 0.0

    # --- stick layer (setStickData, 10530) -------------------------------------------------
    def _set_stick_data(self, sx, sy):
        """mStickDistance + m34E8 world target from a raw stick. The stick is run through PADClamp's
        octagonal clamp + JUTGamePad::CStick::update (main_stick_decode) exactly as the console does:
        mStickDistance = mMainStickValue (capped at 1), m34DC = mMainStickAngle + 0x8000, m34E8 =
        m34DC + csangle. The octagon clamp is a no-op on-axis / inside the octagon and shifts the
        near-full OFF-AXIS angle by a few s16 -- the decode fix that removes the sim-vs-live drift."""
        ang, self.msd = main_stick_decode(sx, sy)
        if ang is None:
            self.target = self.travel           # neutral: no want -> hold (irrelevant, gated)
        else:
            self.m34dc = (ang + 0x8000) & 0xFFFF
            self.target = (self.m34dc + self.csangle) & 0xFFFF

    def set_cc_move(self, mv):
        """Queue the CC push (Tetra ``m_cc_move``) for the NEXT :meth:`step`, consumed in ``posMove``
        (see the consumption site). ``mv`` = (dx, dy, dz) f32 world push accumulated from the PRIOR
        frame's Co overlap (``dCcS::SetPosCorrect`` -> ``cc_push.co_move_pair``), or None to clear.
        The push lands after the foot/roll speedF move and before the cut lunge + the CrrPos wall
        pass. Requires the Python path (walls= or native=False); raises otherwise (see step)."""
        self._cc_move = None if mv is None else (f32(mv[0]), f32(mv[1]), f32(mv[2]))

    # --- proc dispatch + per-frame step ----------------------------------------------------
    def step(self, sx, sy, buttons=0, triggerL=0, csx=128, csy=128):
        """Advance one frame with a raw main stick (sx, sy) + optional L-target (buttons 0x40 or
        analog triggerL) + raw C-stick (csx, csy) steering the camera. Returns (d_pos, tag).
        csangle is driven per-frame from the shared camera; a centered C-stick (csx=128, the
        free-cam default) holds it frozen at the seed, matching straight superswims."""
        if self._core is not None:               # native LandCore: one C call/frame, then sync
            if self._cc_move is not None:
                raise RuntimeError("cc_move (Tetra push) requires the Python path; the native "
                                   "LandCore has no CC pass. Construct with walls= (native off) or "
                                   "native=False.")
            d = self._core.step(int(sx), int(sy), int(buttons), int(triggerL), int(csx), int(csy))
            self._sync_from_core()
            return d, _STATE_TAG.get(self.state, "?")
        # 2-frame controller latency: act on the input (stick, L AND C-stick) delivered INPUT_DELAY
        # frames ago -- the whole controller poll is delivered together.
        self._inbuf.append((int(sx), int(sy), int(buttons), int(triggerL), int(csx), int(csy)))
        asx, asy, abtn, atrig, acsx, acsy = self._inbuf.pop(0)
        # Frame-START proc: "a proc *_init ran" == post-step state != this. Captured before the A-roll
        # trigger (which would mask a roll entry); the deferred draw needs it (model/draw-base.md).
        entry_state = self.state
        # setStickData reads the camera value as of the START of the frame (the camera integrator
        # advances LATER in the frame): m34E8 = m34DC(stick) + csangle[f-1]. Mirror swim_predict.
        self.csangle = self._cam.csangle
        self._set_stick_data(asx, asy)
        l_held = bool(abtn & 0x40) or atrig >= 200      # checkAttentionLock proxy (digital/analog L)
        a_pressed = bool(abtn & 0x100)                   # doTrigger: A = the "do"/roll button
        self._b_held = bool(abtn & 0x200)                # swordButton (B mItemButton, HELD)
        # mItemTrigger RISING EDGE (on the delivered/delayed input): a HELD B misses it -> no exit. See KB.
        # ab_edge = combined A|B (freeze checkSubjectEnd 5698); _b_trig = B-only (roll->cut swordTrigger 4203).
        ab_edge = ((abtn & ~self._abtn_prev) & 0x300) != 0
        self._b_trig = ((abtn & ~self._abtn_prev) & 0x200) != 0
        self._abtn_prev = abtn

        # Attention lock-on machine (dAttention_c::Run; inert with no target). It reads L one frame AHEAD
        # of physics: input_delay=2 -> the delay-1 L `_inbuf[0]` (s6); input_delay=1 -> physics IS delay-1.
        if self._input_delay >= 2 and self._inbuf:
            _atn_btn, _atn_trig = self._inbuf[0][2], self._inbuf[0][3]
            l_atn = bool(_atn_btn & 0x40) or _atn_trig >= 200
        else:
            l_atn = l_held
        # chaseAttention target-present gate (front-of-player cone, _atn_target_present): an actor is
        # chaseable only inside it; RELEASE keys on the weaker _atn_target_exists (no cone) instead.
        self._atn.update(l_atn, self._atn_target_present(), self._atn_target_exists())

        # --- mid-walk sword pull-out (opt-in): B rising edge -> DRAW_DELAY frames later the anim set
        # flips base->sword BEFORE the proc dispatch (this frame's foot pose). See FootSpeedF.draw_sword.
        if self._model_draw and self._foot is not None:
            if self._draw_cd is None:
                if self._b_trig and not self.sword_drawn and self.state in (MOVE, WAIT, FREE_WAIT):
                    self._draw_cd = self.DRAW_DELAY
            else:
                self._draw_cd -= 1
                if self._draw_cd <= 0:
                    self._foot.draw_sword()
                    self.sword_drawn = True
                    self._draw_cd = None

        moving = self.msd > 0.05
        # --- SUBJECTIVITY freeze (C-up cancel), fully input-driven (no enter_freeze/hold/resume API).
        # Full state machine + decomp cites: knowledge/mechanics/land-movement.md (subjectivity freeze).
        posy = self._cstick_posy(acsx, acsy)
        cup_now = (self.msd < CUP_MAIN_MAX and posy > CUP_POSY)   # C-up still requested this frame
        if self._subj_arm:                       # armed last frame by the C-up gesture -> init the freeze
            if self._gnd is not None:
                from .floors import SlopeNotModeled
                raise SlopeNotModeled("SUBJECTIVITY freeze is not wired into floors mode "
                                      "(its hold frames bypass the ground pass)")
            self._subj_arm = False
            self.state = SUBJECTIVITY
            self.nspeed = 0.0
            self.speedF = 0.0
            self._subj_ended = False
            self._subj_frames = 0
            self._cdown_run = 0
            if self._foot is not None:
                self._foot.enter_subjectivity(self.msd, low_life=self._check_rest_hp_anime())
                if self._gnd is not None:
                    _gnd_frame_end_fn(self)
                if self._foot.defer_draw:
                    self._foot.set_pos(
                        self.pos_x, self.pos_z, facing=self.facing, py=self.pos_y, lean=0
                    )
                    self._foot.finish_draw()
            self.m34de = self.facing
            self.m34ea = self.m34dc
            self._cam.step(acsx, acsy)
            self.visited.add(SUBJECTIVITY)
            self._l_prev = l_held
            return 0.0, "SUBJ"
        if self.state == SUBJECTIVITY:
            self._subj_frames += 1
            subjectivity_m35b4 = self._foot.m35B4 if self._foot is not None else None
            if cup_now:
                # C-up still held -> camera re-requests subjectivity; prior exit void, stay frozen (re-enter cup-cam).
                self._subj_ended = False
                self._cdown_run = 0
            else:
                if ab_edge or l_held:            # A/B mItemTrigger edge | L held (mItemButton) -- no floor
                    self._subj_ended = True
                if posy < CDOWN_POSY:            # C-DOWN -> camera 0x2000, but only past the SUBJ_VIEW_IN floor
                    self._cdown_run += 1
                    if self._cdown_run >= CDOWN_RUN and self._subj_frames >= SUBJ_CAM_FLOOR:
                        self._subj_ended = True
                else:
                    self._cdown_run = 0
            # checkSubjectEnd calls changeWaitProc immediately. This frame remains a frozen hold,
            # but mCurProc is observably WAIT; the following frame reaches MOVE through procWait's
            # checkNextMode/procMove_init path. Jumping directly SUBJECTIVITY -> MOVE changes the
            # first carried-phase foot displacement.
            if self._subj_ended and not cup_now:
                self.state = WAIT
                # changeWaitProc -> procWait_init runs on the subjectivity-exit frame. Besides
                # publishing WAIT it resets mDirection and re-enters the WAITS/WALK idle blend.
                # Both are observable on the next frame: a held L row must take ATN's side branch,
                # and the carried toe pose supplies the first small re-walk displacement.
                self.direction = DIR_NONE
            self.speedF = 0.0
            if self._foot is not None:
                if self.state == WAIT:
                    if self._check_rest_hp_anime():
                        self._foot.enter_wait_rest_hp()
                        self._foot.step_single_anim(0.0, self.msd)
                    else:
                        self._foot.enter_wait(self.msd, self.MOVE_REENTRY_MORF)
                else:
                    self._foot.step_subjectivity(self.msd)
                # procSubjectivity returns from its body, but actor execute still runs the
                # shared setWorldMatrix/footBgCheck draw tail. Skipping it froze m359C and
                # shifted the first re-walk displacement by more than one world unit.
                if self._gnd is not None:
                    _gnd_frame_end_fn(self)
                if self._foot.defer_draw:
                    self._foot.set_pos(
                        self.pos_x, self.pos_z, facing=self.facing,
                        py=self.pos_y, lean=0,
                    )
                    self._foot.finish_draw()
                if self.state == WAIT:
                    # checkSubjectEnd leaves field_0x35B4 untouched on the cancel frame even
                    # when the delivered A row also holds full forward. The toe stream advances,
                    # but this stick-history field is first written on the following MOVE frame.
                    self._foot.m35B4 = subjectivity_m35b4
            self.m34de = self.facing
            self.m34ea = self.m34dc
            self._cam.step(acsx, acsy)
            self.visited.add(self.state)
            self._l_prev = l_held
            return 0.0, "WAIT" if self.state == WAIT else "SUBJ"
        elif self.state in (MOVE, WAIT, FREE_WAIT, ATN_MOVE) and cup_now:
            self._subj_arm = True                # C-up from a grounded MOVE/WAIT -> freeze NEXT frame
        # Attention-lock engage: capture the facing lock (m34E6 = shape_angle.y, 2067) on the rising
        # edge; it stays frozen because the ATN path writes shape_angle.y = m34E6 every frame.
        if l_held and not self._l_prev:
            self.m34E6 = self.facing
        # doTrigger (A) dispatch (checkNextActionFromButton 4309): L held -> JUMP (sidehop L/R, backflip
        # back; no forward); L off + moving -> ATTACK roll. Input mapping: land-movement.md (a gotcha).
        grounded = self.state in (WAIT, FREE_WAIT, MOVE, ATN_MOVE)
        if a_pressed and grounded:
            if l_held:
                jdir = self._get_dir_from_angle(s16_signed(self.target - self.facing))
                if jdir in (DIR_LEFT, DIR_RIGHT):
                    self._side_step_init(jdir)
                elif jdir == DIR_BACKWARD:
                    self._back_jump_init()
            elif moving and self.state in ROLL_FROM:
                # A against a wall offers SIDLE, not the roll (setDoStatus 2241 preempts
                # ATTACK, 4188); the guard forbids the roll, the sidle stays unmodeled.
                if self._walls is not None and sidle_blocks_roll(self):
                    self.sidle_blocked = True    # sticky: planners reject this input stream
                elif self.msd <= self.ATTACK_MSD_MIN:
                    # Too shallow to be ATTACK: the press is PUT_AWAY and sheathes (unmodeled), so
                    # flag it like the sidle and do NOT roll. mechanics/roll-attack-threshold.md.
                    self.attack_blocked = True   # sticky: planners reject this input stream
                else:
                    self.facing = self.target
                    self._roll_init()

        # dispatch the active proc body. WAIT/FREE_WAIT/MOVE/ATN_MOVE run their speed/angle update then
        # checkNextMode (the arbiter: starts locomotion from idle, routes reversals to the turn procs).
        proc = self.state                        # dispatch-time proc (mCurProc; may transition below)
        if proc in (WAIT, FREE_WAIT):
            if self._atn.locked:                 # locked actor from a standstill -> procAtnActorWait
                self.state = ATN_ACTOR_WAIT
                self._set_speed_and_angle_atn_actor()
            elif l_held:                         # attention lock, no actor -> procAtnMove path
                self.state = ATN_MOVE
                self._set_speed_and_angle_atn()
            else:
                self._set_speed_and_angle_normal(self.F0, attention_lock=False)
            self._check_next_mode(l_held)
        elif proc == MOVE:
            self._set_speed_and_angle_normal(self.F0, attention_lock=l_held)
            self._check_next_mode(l_held)
        elif proc == ATN_MOVE:
            # procAtnMove can execute for one frame after target is released.
            # setSpeedAndAngleNormal's internal checkAttentionLock branches on
            # the live lock state, not merely on the proc that began the frame.
            self._set_speed_and_angle_atn(attention_lock=l_held)
            self._check_next_mode(l_held)
        elif proc in (ATN_ACTOR_MOVE, ATN_ACTOR_WAIT):
            self._set_speed_and_angle_atn_actor()   # procAtnActorMove/Wait: actor-lock speed/angle
            self._check_next_mode(l_held)
        elif proc == WAIT_TURN:
            self._proc_wait_turn(l_held)         # checkNextMode when the pivot completes
        elif proc == MOVE_TURN:
            self._proc_move_turn(l_held)         # checkNextMode after the facing sweep
        elif proc == SLIP:
            self._proc_slip(l_held)              # checkNextMode / hand to MoveTurn when the skid dies
        elif proc == FRONT_ROLL:
            self._proc_roll(l_held)              # checkNextMode on its exit frame (-> CUT if B buffered)
        elif proc == FRONT_ROLL_CRASH:
            self._proc_crash(l_held)             # roll bonk: airborne bounce, lands, plays out ROLLFMIS
        elif proc in (CUT_F, CUT_A):
            self._proc_cut(l_held)               # sword-thrust lunge; exits to WAIT when the anim passes field_0xC
        elif proc in (SIDE_STEP, BACK_JUMP):
            self._proc_ballistic(l_held)         # lands on the (1-frame-late) ground hit
        elif proc in (SIDE_STEP_LAND, BACK_JUMP_LAND):
            self._proc_ballistic_land(l_held)    # recovery anim -> WAIT

        # setBlendAtnMoveAnime's direction update for a (possibly just-entered) ATN frame. Capture the
        # pre-update mDirection (uVar1, 3291): the anim re-triggers the oldframe-morf when it changes.
        prev_dir = self.direction
        if self.state in (ATN_MOVE, ATN_ACTOR_MOVE, ATN_ACTOR_WAIT):
            self._update_atn_direction()         # setBlendAtnMoveAnime mDirection (proc 7/8/9 share it)
        # ATN[_ACTOR] / WAIT -> MOVE: procMove_init re-triggers the oldframe-morf (6215), so the walk
        # re-warms from the pose it left. `started` gates WAIT (see the WAIT branch below).
        if (self.state == MOVE and self._foot is not None
                and (proc in (ATN_MOVE, ATN_ACTOR_MOVE, ATN_ACTOR_WAIT)
                     or (proc in (WAIT, FREE_WAIT) and self._foot.started))):
            self._foot._pending_morf = self.MOVE_REENTRY_MORF

        # Before posing, set Link's CURRENT (pre-integration) world pos + shape_angle.y: the foot FK runs
        # from worldBase(pos) to carry world-magnitude quantization. See knowledge/model/sim.md.
        if self._foot is not None:
            self._foot.set_pos(self.pos_x, self.pos_z, facing=self.facing, py=self.pos_y)
        # Phase G: this frame's speedF slope angle r3 = prev CrrPos poly at THIS travel
        # (:2408-2413; 0 on the micro-incline tier -- see land/floors.py).
        if self._gnd is not None:
            if self._foot.skip_cruise_pose:
                raise RuntimeError("floors mode is incompatible with skip_cruise_pose "
                                   "(deferred poses would replay without the per-frame m35B8)")
            if self._gnd.m34e2 != 0:
                from .floors import SlopeNotModeled
                raise SlopeNotModeled("nonzero m34E2 (%d): the anim-rate cos / ATN f31 slope "
                                      "terms are not wired" % self._gnd.m34e2)
            self._foot.gnd_r3 = self._gnd.speedf_r3(self.travel)
        # speedF -> position. ROLL/SLIP = momentum; WAIT_TURN frozen; MOVE + MOVE_TURN tail + ATN_MOVE use
        # the anim engine (only the SLIP tail keeps the fallback); single-anim procs pose to warm the stream.
        if self.state in (SIDE_STEP, BACK_JUMP):
            if self._gnd is not None:
                from .floors import SlopeNotModeled
                raise SlopeNotModeled("ballistic hops still snap to the flat ground_y -- "
                                      "not wired into floors mode")
            # Airborne ballistic: horizontal momentum (shared bottom advances pos.x/z); vertical integrates
            # speed.y by gravity, then CrrPos snaps to the floor + flags GROUND_HIT. See land-movement.md.
            self.speedF = 0.0 if abs(self.nspeed) < 0.05 else self.nspeed
            self.speed_y = f32(self.speed_y + self.gravity)
            if self.speed_y < self.MAX_FALL:
                self.speed_y = f32(self.MAX_FALL)
            self.pos_y = f32(self.pos_y + self.speed_y)
            if self.pos_y <= self.ground_y:
                self.pos_y = f32(self.ground_y)
                self.ground_hit = True
            else:
                self.ground_hit = False
        elif self.state in (SIDE_STEP_LAND, BACK_JUMP_LAND):
            self.speedF = 0.0                     # land recovery: mNormalSpeed 0, position frozen
        elif self.state == WAIT_TURN:
            if self._foot is not None:
                self._foot.step_single_anim(self.nspeed, self.msd)   # pose ANM_ROT, warm the toe stream
            self.speedF = 0.0
        elif proc == WAIT_TURN and self.state == WAIT and self._foot is not None:
            # Pivot done -> WAIT: procWait_init's idle-proc setBlendMoveAnime, facing != m34DE turn-step
            # arm (WAITS/ANM_ATNW{L,R}S, ratio clamp(0.5+0.001|dfacing|,0,1)) -- see land-movement.md.
            r3 = s16_signed(self.facing - self.m34de)
            r27 = 'atnwls' if r3 > 0 else 'atnwrs'
            ratio = min(f32(f32(0.5) + f32(0.001 * abs(r3))), 1.0)
            self._foot.enter_wait_idle(ratio, r27, self.MOVE_REENTRY_MORF, self.msd)
            self.speedF = 0.0
        elif self.state in (FRONT_ROLL, SLIP):
            if self._foot is not None:
                self._foot.step_single_anim(self.nspeed, self.msd)   # warm the toe stream
            # m3598==0 here so speedF == mNormalSpeed, but posMoveFromFootPos still snaps |speedF|<0.05
            # to 0 (d_a_player_main.cpp:2418) -- the slip decel tail. See land-sim.md (slip-skid tail).
            self.speedF = _gnd_spz_fn(self, self.nspeed)
        elif proc in (ATN_ACTOR_MOVE, ATN_ACTOR_WAIT) or self.state in (ATN_ACTOR_MOVE, ATN_ACTOR_WAIT):
            # speedF momentum (entered from a roll, m3598==0). Keyed on the DISPATCH proc so the proc-9
            # BODY flip isn't overwritten when checkNextMode already routed self.state to MOVE (cf. CUT).
            if self._foot is not None:
                if self.state == MOVE:
                    # Routed to MOVE this frame: checkNextMode TRUE skips the ATN pose (6307);
                    # procMove_init's walk pose (the _pending_morf above) fires NOW (see README s15).
                    self._foot.step(self.nspeed, self.msd)
                else:
                    # procAtnActorMove/Wait pose = the ATN_MOVE setBlendAtnMoveAnime dispatcher
                    # (6299/6308); entry morf fires on the proc's first dispatch frame (init).
                    f31 = f32(abs(self.nspeed) / self.max_nspeed)
                    entered = proc not in (ATN_ACTOR_MOVE, ATN_ACTOR_WAIT)
                    atn_morf = (self.MOVE_REENTRY_MORF if (entered or self.direction != prev_dir)
                                else None)
                    self._foot.step_atn(self.nspeed, self.msd, self.direction, f31, atn_morf)
            self.speedF = _gnd_spz_fn(self, self.nspeed)
        elif self.state == FRONT_ROLL_CRASH:
            # Roll-bonk bounce: reversed momentum + gravity arc; the ground snap runs AFTER
            # the wall pass below (game order). Pose stream caveat: procs/crash.py.
            self.speedF = _gnd_spz_fn(self, self.nspeed)
            crash_y0 = self.pos_y
            self.speed_y = f32(self.speed_y + self.gravity)
            if self.speed_y < self.MAX_FALL:
                self.speed_y = f32(self.MAX_FALL)
            self.pos_y = f32(self.pos_y + self.speed_y)
        elif self.state in (CUT_F, CUT_A):
            # Sword-thrust lunge: speedF (==nspeed, m3598==0) + posMove m34C2==1 root-translate delta
            # (rotated by shape); entry frame m3700_prev==0 -> full root translate stacks (~49.22). See KB.
            self.speedF = _gnd_spz_fn(self, self.nspeed)
            m3700 = self._cut_m3700_at(self.state, self.cut_frame)
            sp5c = (f32(m3700[0] - self._cut_m3700[0]), f32(m3700[1] - self._cut_m3700[1]),
                    f32(m3700[2] - self._cut_m3700[2]))
            self._cut_m3700 = m3700
            s = _cM_ssin_s16(self.facing); c = S.cM_scos_s16(self.facing)   # rotate by shape_angle.y
            self._cut_add = (f32(f32(sp5c[2] * s) + f32(sp5c[0] * c)),
                             f32(f32(sp5c[2] * c) - f32(sp5c[0] * s)))
        elif proc in (CUT_F, CUT_A):
            # The cut EXITED to WAIT this frame (checkNextMode(1) set mNormalSpeed=0) -> position freezes.
            self.speedF = 0.0
        elif self.state == WAIT and self._foot is not None and self._foot.started:
            # THE WALK -> WAIT STOP: procWait_init (6068) / procWait (6093) keep POSING while Link is
            # stopped, and the re-walk's f31_2 measures that. knowledge/model/wait-stop-pose.md.
            rest_hp = self._check_rest_hp_anime()   # `started`: a never-walked stream poses in step()
            if proc != WAIT:                          # procWait_init
                if rest_hp:
                    self._foot.enter_wait_rest_hp()   # low life -> the ANM_WAITATOB single
                    self._foot.step_single_anim(0.0, self.msd)
                else:
                    self._foot.enter_wait(self.msd, self.MOVE_REENTRY_MORF,
                                          low_life=rest_hp)
            elif self._foot.st.m34C3 == 0:            # procWait mid-single (6119): re-pose only if
                if self._foot.st.fc0.rate < 0.01 or not rest_hp:   # the rate died or life recovered
                    self._foot.enter_wait(self.msd, self.MOVE_REENTRY_MORF,
                                          low_life=rest_hp)
                else:
                    self._foot.step_single_anim(0.0, self.msd)
            else:                                     # procWait, in the blend (6144)
                self._foot.step_wait(self.msd, low_life=rest_hp)
            self.speedF = 0.0
        elif self.state == ATN_MOVE and self._foot is not None:
            # ATN_MOVE: setBlendAtnMoveAnime poses the strafe/back anim. f31 = |nspeed*cos(m34E2)|/max
            # (cos=1 on flat); the pose warms the toe stream so an EBS-release MOVE rejoins bit-exact.
            f31 = f32(abs(self.nspeed) / self.max_nspeed)
            atn_morf = (self.MOVE_REENTRY_MORF if (proc != ATN_MOVE or self.direction != prev_dir)
                        else None)
            self.speedF = self._foot.step_atn(self.nspeed, self.msd, self.direction, f31, atn_morf)
        elif self._foot is not None:
            # walk anim engine (bit-exact for a clean MOVE; the MOVE_TURN tail rejoins it too). On the
            # procMoveTurn_init(1) frame the anim is posed at the pre-halving speed (_anim_nspeed).
            self.speedF = self._foot.step(self.nspeed, self.msd, anim_nspeed=self._anim_nspeed)
            self._anim_nspeed = None
        else:
            sc, mx, mn = SPEEDF_CHASE
            self.speedF = cLib_addCalc(self.speedF, self.nspeed, sc, mx, mn)
            if self.nspeed == 0.0 and abs(self.speedF) < 0.5:
                self.speedF = 0.0                # snap to a clean standstill at the WAIT edge
        # world motion is speedF along travel: speed.z = speedF*cos, x = speedF*sin. pos.{x,z} are f32
        # fields (cXyz) re-rounded each frame -> accumulate in f32, not an f64 sum. See knowledge/model/sim.md.
        d = self.speedF
        px0, pz0 = self.pos_x, self.pos_z
        self.pos_x = f32(self.pos_x + f32(d * _cM_ssin_s16(self.travel)))
        self.pos_z = f32(self.pos_z + f32(d * S.cM_scos_s16(self.travel)))
        # CC push (posMove 2558: current.pos += *GetCCMoveP()): after the speedF move above, before
        # the m34C2 cut lunge below + CrrPos. Cleared each frame (2609). See mechanics/actor-push.md.
        if self._cc_move is not None:
            self.pos_x = f32(self.pos_x + self._cc_move[0])
            self.pos_z = f32(self.pos_z + self._cc_move[2])
            self._cc_move = None
        # Sword-cut root-translate lunge (posMove m34C2==1) on top of the foot term, zeroed except on a
        # CUT frame; the returned displacement is then the TRUE single-frame move (foot + lunge, ~49.22).
        if self.state in (CUT_F, CUT_A):
            self.pos_x = f32(self.pos_x + self._cut_add[0])
            self.pos_z = f32(self.pos_z + self._cut_add[1])
        # Phase G grounded gravity dip (posMoveFromFootPos :2464-2479); CrrPos snaps it back
        # below. The ballistic/crash branches above already integrate their own y.
        if self._gnd is not None and self.state != FRONT_ROLL_CRASH:
            gnd_y0 = self.pos_y
            self._gnd.y_old = gnd_y0       # old.pos.y (start-of-frame; setStepsOffset :9548)
            self.speed_y = f32(self.speed_y + walls_GRAVITY)
            if self.speed_y < self.MAX_FALL:
                self.speed_y = f32(self.MAX_FALL)
            self.pos_y = f32(self.pos_y + self.speed_y)
        # mAcch.CrrPos wall pass: after integration, before the deferred draw (the game's
        # order; scope + caveats in mechanics/wall-response.md).
        if self._walls is not None and self.state not in (SIDE_STEP, BACK_JUMP,
                                                          SIDE_STEP_LAND, BACK_JUMP_LAND):
            if self.state == FRONT_ROLL_CRASH:
                wall_pass(self, px0, pz0, y_old=crash_y0, y_mid=self.pos_y,
                          sy=self.speed_y, snap=False)
            elif self._gnd is not None:
                # floors mode: pos_y already carries the dip -- pass the real y pair.
                wall_pass(self, px0, pz0, y_old=gnd_y0, y_mid=self.pos_y,
                          sy=self.speed_y, snap=False)
            else:
                wall_pass(self, px0, pz0)
        if self._gnd is not None:
            # dBgS_Acch GroundCheck (d_bg_s_acch.cpp:122): probe at pos.y+60, snap to the max
            # plane-cross iff above the dipped y; then m34E2 (execute :11498, post-CrrPos).
            self.pos_y, _sy = self._gnd.crrpos_ground(self.pos_x, self.pos_y, self.pos_z)
            if _sy is not None:
                self.speed_y = _sy
            self.ground_hit = self._gnd.ground_hit
            self._gnd.update_m34e2(self.facing)
        elif self.state == FRONT_ROLL_CRASH:
            # GroundCheck after the wall pass: snap iff ground_h > the dipped y (strict).
            if self.ground_y > self.pos_y:
                self.pos_y = f32(self.ground_y)
                self.speed_y = 0.0
                self.ground_hit = True
            else:
                self.ground_hit = False
        # Deferred foot draw at post-integration pos with LAST frame's lean (setWorldMatrix runs before
        # setMoveSlantAngle, 11551); expose that draw-time lean (body_cyl reads it) + evolve m351C always.
        self._draw_lean = s16_signed(self.m351C) >> 1
        if self._gnd is not None:
            _gnd_frame_end_fn(self)
        if self._foot is not None and self._foot.defer_draw:
            # A proc *_init frame draws UPRIGHT: commonProcInit zeroes shape_angle.z (:5841) before
            # setWorldMatrix, setMoveSlantAngle restores it after. See knowledge/model/draw-base.md.
            self._foot.set_pos(self.pos_x, self.pos_z, facing=self.facing, py=self.pos_y,
                               lean=0 if self.state != entry_state else self._draw_lean)
            self._foot.finish_draw()
            self._set_move_slant_angle()
            d = math.hypot(self.pos_x - px0, self.pos_z - pz0)
        else:
            self._set_move_slant_angle()
        self._cut_add = (0.0, 0.0)
        self.m34de = self.facing                 # m34DE = shape_angle.y (end-of-frame, 11287): last facing
        self.m34ea = self.m34dc                  # m34EA = m34DC (end-of-frame, 11289): last stick want
        # advance the shared camera for NEXT frame (its own 1-frame internal lag stacks on the
        # controller delay above); csangle[f] read at the top of the next step.
        self._cam.step(acsx, acsy)
        self.visited.add(self.state)
        self._l_prev = l_held
        return d, _STATE_TAG.get(self.state, "?")


# Single-sourced HIO/tuning constants handed to the native LandCore (_anmc.land_init_consts). Keeps
# state.py the one canonical home for the walk/atn/roll/turn/slip constants; the C twin never restates them.
_LAND_CONSTS = {n: getattr(LandState, n) for n in (
    'MAX_NSPEED', 'F14', 'F1C', 'F20', 'F24', 'F0', 'F4', 'F6',
    'ATN_MAX', 'ATN_SPD', 'ATN_ACC', 'ATN_DEC', 'ATN_SCL',
    'ATN_TURN_MAX', 'ATN_TURN_MIN', 'ATN_TURN_SCALE',
    'ATNB_MAX', 'ATNB_SPD', 'ATNB_ACC', 'ATNB_DEC', 'ATNB_SCL', 'ATNB_COS_FWD', 'ATNB_COS_BACK',
    'ROLL_SPD', 'ROLL_ADD', 'ROLL_MIN', 'ROLL_END', 'ROLL_RATE', 'ROLL_ENTRY_MORF',
    'MOVE_REENTRY_MORF', 'ROLL_EARLY', 'ATTACK_MSD_MIN',
    'TURN_MAX', 'TURN_MIN', 'TURN_SCALE', 'WAIT_TURN_ANIM_RATE',
    'SLIP_THRESH', 'SLIP_ENTRY', 'SLIP_DEC_SCALE', 'SLIP_DEC_MAX', 'SLIP_DEC_MIN',
    'SLIP_ANIM_RATE', 'SLIP_MORF', 'MT_SLIP_SEED',
    # the sword-thrust cut (the roll-stab): the per-type CUT_EARLY/CUT_LAUNCH_ADD/CUT_DEC_MAX stay
    # dicts keyed by CUT_F/CUT_A and land_init_consts flattens them onto its two C slots.
    'CUT_RATE', 'CUT_START', 'CUT_END', 'CUT_PASS', 'CUT_LAUNCH_MUL', 'CUT_DEC_SCALE',
    'CUT_DEC_MIN', 'CUT_EARLY', 'CUT_LAUNCH_ADD', 'CUT_DEC_MAX',
    'CUT_TURN_SCALE', 'CUT_TURN_MAX', 'CUT_TURN_MIN',
    # the roll bonk window -- the C step reads it only to REFUSE the unported crash proc.
    'ROLL_BONK_ANGLE', 'ROLL_BONK_FMIN', 'ROLL_BONK_FMAX', 'ROLL_BONK_SPEED')}


def run_walk(sticks, csangle=0, **seed):
    """Step a list of raw (sx, sy) sticks from a seed state. Returns per-frame rows.
    `seed` forwards to LandState (pos_z, facing, travel, state, nspeed, speedF)."""
    s = LandState(csangle=csangle, **seed)
    rows = [{"f": 0, "state": s.state, "nspeed": s.nspeed, "speedF": s.speedF,
             "pos_z": s.pos_z, "msd": s.msd}]
    for i, (sx, sy) in enumerate(sticks, 1):
        d, tag = s.step(sx, sy)
        rows.append({"f": i, "state": s.state, "nspeed": s.nspeed, "speedF": s.speedF,
                     "pos_z": s.pos_z, "msd": s.msd, "tag": tag})
    return rows
