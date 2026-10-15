"""anim_state.py - port of Link's under-body movement anim STATE MACHINE, driven by mNormalSpeed.

Reproduces, offline and bit-faithfully, the per-frame animation blend state that the game computes
in daPy_lk_c::setBlendMoveAnime -> setMoveAnime -> J3DFrameCtrl::update (d_a_player_main.cpp:2966,
12723; J3DAnimation.cpp:143). Output per game frame: which anims occupy MOVE0/MOVE1, the two
frame-controller frame values + rates, the blend ratio (getRatio(1)), and m3598 (the WALK<->DASH
speedF blend). Feed the frame/ratio into the FK (fk.foot_toe_blend) to get the model-local toe,
then posMoveFromFootPos -> f31_2 -> speedF. This is the offline replacement for reading the live
frame controllers, so the land route planner can predict transient walk position with no Dolphin.

SCOPE: the normal flat, on-axis, free (non-attention/heavy/grab/slope/ice) walk. The regime
selection picks r28=WAITS, r27=WALK, r26=DASH; the observed arc is FREEB(entry)->WAITS->WALK->DASH
and back. Other movement modes (attention strafe, heavy boots, slopes, ice slip) take other branches
of setBlendMoveAnime and are out of scope here.

Everything hand-verified bit-exact vs a live flat-walk arc (see tests): the rate formula
f27r = f28 + f27*((f25*f3/f26) - f28), rate1 = f27r*f26/f3, phase preservation frame = (old/oldMax)*newMax,
and the m3598 closed forms all match the live capture to the value.

HIO tuning constants (daPy_HIO_move_c0::m, d_a_player_HIO_data.inc) used here:
  field_0x18 (mMaxNormalSpeed src) = 17.0 ; field_0x2C = 0.5 (WAITS<->WALK thresh);
  field_0x30 = 1.0 (WALK<->DASH thresh); field_0x38 = 1.1 ; field_0x40 (f29) = 0.8 ;
  field_0x48 = 2.3 (DASH cruise rate) ; field_0x60 (f28 free) = 1.0.
Anim frame maxima are plain metadata (not copyrighted keyframe data).
"""
from .. import fp

# --- J3DFrameCtrl attribute modes (J3DAnimation.h) -----------------------------------------------
EMode_NONE, EMode_RESET, EMode_LOOP, EMode_REVERSE, EMode_LOOP_REVERSE = 0, 1, 2, 3, 4

# mDirection enum (daPy_lk_c::direction_e); the ATN anim machine branches on it.
DIR_FORWARD, DIR_BACKWARD, DIR_LEFT, DIR_RIGHT, DIR_NONE = 0, 1, 2, 3, 4

# anim metadata (frameMax, attribute) -- from parse_bck; small integers, not copyrighted data.
ANIM_META = {
    'freeb': (244, EMode_NONE),
    'waits': (60, EMode_LOOP),
    'walk':  (32, EMode_LOOP),
    'walks': (32, EMode_LOOP),   # ANM_WALKS: the sword-drawn walk (getAnmData sword table maps
    #                              ANM_WALK -> WALKS); LEG pose differs from 'walk', same meta.
    'dash':  (32, EMode_LOOP),
    'dashs': (32, EMode_LOOP),   # ANM_DASHS: the sword-drawn dash (getAnmData sword table); LEG pose
    #                              differs from 'dash', same frameMax/attribute. See anim-engine.md.
    'rollf': (19, EMode_NONE),   # ANM_ROLLF (forward roll); single-anim during FRONT_ROLL
    'rot':   (9,  EMode_LOOP),   # ANM_ROT   (pivot in place); single-anim during WAIT_TURN
    'slip':  (7,  EMode_NONE),   # ANM_SLIP  (reversal skid);  single-anim during SLIP
    'atnwls': (18, EMode_LOOP),  # ANM_ATNWLS (turn-in-place walk-step L); WAIT idle-proc re-pose
    'atnwrs': (18, EMode_LOOP),  # ANM_ATNWRS (turn-in-place walk-step R); WAIT idle-proc re-pose
    'atnls': (30, EMode_LOOP),   # ANM_ATNLS  (attention strafe, standing L); setBlendAtnMoveAnime side
    'atnrs': (30, EMode_LOOP),   # ANM_ATNRS  (attention strafe, standing R)
    'atndls': (18, EMode_LOOP),  # ANM_ATNDLS (attention strafe, dash L)
    'atndrs': (18, EMode_LOOP),  # ANM_ATNDRS (attention strafe, dash R)
    'atnwb': (20, EMode_LOOP),   # ANM_ATNWB  (attention back walk); setBlendAtnBackMoveAnime
    'atndb': (20, EMode_LOOP),   # ANM_ATNDB  (attention back dash)
    'waitatob': (13, EMode_NONE),  # ANM_WAITATOB (wait A->B, the low-life idle transition); the
    #                                WAIT proc plays it as a SINGLE, and with an explicit frame-ctrl
    #                                end of H_10 (12) -- not this frameMax. wait-stop-pose.md.
    'waitb': (19, EMode_LOOP),     # ANM_WAITB: steady critical-health idle after WAITATOB
}

# HIO daPy_HIO_move_c0::m constants (flat free-walk subset), f32 members in the game -- keep them f32:
# fp.fmuls/fadds don't quantize operands, so an f64 literal (1.1) leaks 1 ULP to the rate (resolved-bugs).
H_MAXSPEED = fp.f32(17.0)     # mMaxNormalSpeed
H_2C = fp.f32(0.5)            # WAITS<->WALK regime threshold (field_0x2C)
H_30 = fp.f32(1.0)           # WALK<->DASH regime threshold (field_0x30)
H_38 = fp.f32(1.1)           # field_0x38 (regime-1 f28)
H_3C = fp.f32(0.4)           # field_0x3C (critical-health WAITB rate)
H_40 = fp.f32(0.8)           # field_0x40 (f29)
H_48 = fp.f32(2.3)           # field_0x48 (DASH cruise rate / regime-2 f25)
H_60 = fp.f32(1.0)           # field_0x60 (free-walk f28)
# procWait_init's low-life arm, setSingleMoveAnime(ANM_WAITATOB, ...) -- see wait-stop-pose.md.
H_0E = 6                     # field_0xE  (life threshold, quarter-hearts)
H_10 = fp.f32(12.0)          # field_0x10 (WAITATOB frame-ctrl end)
H_68 = fp.f32(0.6)           # field_0x68 (WAITATOB rate)
H_6C = fp.f32(0.0)           # field_0x6C (WAITATOB start frame)
H_70 = fp.f32(6.0)           # field_0x70 (WAITATOB oldframe-morf)

# daPy_HIO_atnMove_c1 (side strafe) + daPy_HIO_atnMoveB_c1 (back), d_a_player_HIO_data.inc:14/18. f29 = 1.0
# (not heavy); the abs2XZ()>=49 -> 1.9x rate branch is inert on flat ground (observed rates are field_0x2C/0x28).
ATN_1C = fp.f32(0.01)        # mAtnMove.field_0x1C  (side WAIT<->WALK f31 threshold)
ATN_20 = fp.f32(0.9)         # mAtnMove.field_0x20  (side WALK<->DASH f31 threshold)
ATN_24 = fp.f32(1.25)        # mAtnMove.field_0x24  (setMoveAnime rate arg)
ATN_28 = fp.f32(1.0)         # mAtnMove.field_0x28  (setMoveAnime rate arg; * f29)
ATN_2C = fp.f32(1.8)         # mAtnMove.field_0x2C  (side DASH single rate; * f29)
ATNB_1C = fp.f32(0.75)       # mAtnMoveB.field_0x1C (back WAIT<->WALK f31 threshold)
ATNB_20 = fp.f32(1.0)        # mAtnMoveB.field_0x20 (back WALK<->DASH f31 threshold)
ATNB_24 = fp.f32(0.8)        # mAtnMoveB.field_0x24 (setMoveAnime rate arg)
ATNB_28 = fp.f32(0.95)       # mAtnMoveB.field_0x28 (back DASH single rate)


# Canonical anim-CODE order for the native fused engine (_anmc): fixed small codes mapped to the JSON
# data-index via foot_fk._anim_idx. Keep in sync with the DEF codes in _anmc.pyx.
# The sword-drawn pair ('walks'/'dashs') is APPENDED, so every existing code keeps its value (the
# .pyx DEF C_* constants are positional). Keep in sync with _anmc's DEF N_ANIM.
ANIM_ORDER = ['waits', 'walk', 'dash', 'rollf', 'rot', 'slip', 'atnwls', 'atnwrs',
              'atnls', 'atnrs', 'atndls', 'atndrs', 'atnwb', 'atndb', 'freeb',
              'walks', 'dashs', 'waitatob']
ANIM_CODE = {name: i for i, name in enumerate(ANIM_ORDER)}
NATIVE_META_MAX = [float(ANIM_META[n][0]) for n in ANIM_ORDER]
NATIVE_META_ATTR = [int(ANIM_META[n][1]) for n in ANIM_ORDER]
# HIO constants (already f32-quantized above) handed to the native engine, keyed by field.
NATIVE_HIO = dict(maxspeed=H_MAXSPEED, h2c=H_2C, h30=H_30, h38=H_38, h40=H_40, h48=H_48, h60=H_60,
                  atn1c=ATN_1C, atn20=ATN_20, atn24=ATN_24, atn28=ATN_28, atn2c=ATN_2C,
                  atnb1c=ATNB_1C, atnb20=ATNB_20, atnb24=ATNB_24, atnb28=ATNB_28,
                  h10=H_10, h68=H_68, h6c=H_6C, h70=H_70)


class FrameCtrl:
    """J3DFrameCtrl: frame + rate + [start,end) + loop mode. update() = J3DAnimation.cpp:143."""
    __slots__ = ('attribute', 'start', 'end', 'loop', 'rate', 'frame')

    def __init__(self):
        self.attribute = EMode_LOOP
        self.start = 0.0
        self.end = 1.0
        self.loop = 0.0
        self.rate = 0.0
        self.frame = 0.0

    def clone(self):
        """Memberwise copy (mid-walk clone support). See land.LandState.clone."""
        c = FrameCtrl()
        c.attribute = self.attribute; c.start = self.start; c.end = self.end
        c.loop = self.loop; c.rate = self.rate; c.frame = self.frame
        return c

    def set(self, attribute, start, end, rate, frame):
        """daPy_lk_c::setFrameCtrl (12938): loop = start if rate>=0 else end.

        Every float member is **f32**, because `J3DFrameCtrl`'s are (`mFrame`/`mRate`/`mStart`/
        `mEnd`/`mLoopFrame`), and `update()`'s `mFrame += mRate` is a single-precision add. Rounding
        here rather than trusting callers is not defensive style, it is the fix for a real console
        divergence (session 90): `enter_roll` passed the literal `1.1`, a Python DOUBLE fractionally
        below `f32(1.1)`, and at roll frame 2.2 -> 3.3 the true f32 sum is an exact tie -- so the
        double's head start broke the tie DOWN to 3.299999952316284 where the hardware rounds
        half-to-even UP to 3.3000001907348633. One ULP of anim frame, 3 ULP of root translate, and a
        Co centre that moved Tetra by a ULP and lost a seam clip. `LandState.roll_frame` accumulates
        the same anim frame from an f32 `ROLL_RATE` and got it right, which is how the two disagreed
        at all. See `knowledge/mechanics/link-co-centre.md`."""
        self.attribute = attribute
        self.end = fp.f32(end)
        self.rate = fp.f32(rate)
        self.start = fp.f32(start)
        self.frame = fp.f32(frame)
        self.loop = self.start if self.rate >= 0.0 else self.end

    def update(self):
        """J3DFrameCtrl::update: mFrame += mRate then wrap/clamp per attribute (f32 throughout)."""
        self.frame = fp.fadds(self.frame, self.rate)
        a = self.attribute
        if a == EMode_NONE:
            if self.frame < self.start:
                self.frame = self.start; self.rate = 0.0
            if self.frame >= self.end:
                self.frame = fp.fsubs(self.end, 0.001); self.rate = 0.0
        elif a == EMode_RESET:
            if self.frame < self.start:
                self.frame = self.start; self.rate = 0.0
            if self.frame >= self.end:
                self.frame = self.start; self.rate = 0.0
        elif a == EMode_LOOP:
            while self.frame < self.start:
                if self.loop - self.start <= 0.0:
                    break
                self.frame = fp.fadds(self.frame, fp.fsubs(self.loop, self.start))
            while self.frame >= self.end:
                if self.end - self.loop <= 0.0:
                    break
                self.frame = fp.fsubs(self.frame, fp.fsubs(self.end, self.loop))
        elif a == EMode_REVERSE:
            if self.frame >= self.end:
                self.frame = fp.fsubs(self.end, 0.001); self.rate = -self.rate
            if self.frame < self.start:
                self.frame = self.start; self.rate = 0.0
        elif a == EMode_LOOP_REVERSE:
            if self.frame >= self.end:
                self.frame = fp.fsubs(self.end, 0.001); self.rate = -self.rate
            if self.frame < self.start:
                self.frame = self.start; self.rate = -self.rate


class UnderAnimState:
    """The under-body (foot chain) two-anim blend state. step(nspeed) advances one game frame and
    returns the per-frame render state. Start it at the anchor with the live MOVE0 anim + frame."""

    def __init__(self, move0_anim='waits', move0_frame=0.0, move1_anim=None, m34C3=1, sword=False):
        self.fc0 = FrameCtrl()
        self.fc1 = FrameCtrl()
        self.move0 = move0_anim
        self.move1 = move1_anim
        self.m34C3 = m34C3          # current blend-anim state id (0 = single, else the r29)
        self.ratio = 0.0            # getRatio(1) = walk-slot weight
        self.m3598 = 0.0
        # Sword: getAnmData maps ANM_DASH -> DASHS and ANM_WALK -> WALKS (waits unchanged);
        # different leg pose -> different toe. See knowledge/model/anim-engine.md.
        self._dash = 'dashs' if sword else 'dash'
        self._walk = 'walks' if sword else 'walk'
        self.fc0.frame = fp.f32(move0_frame)          # f32 members, as in set() -- see FrameCtrl.set
        self.fc0.end = fp.f32(ANIM_META[move0_anim][0])
        self.fc0.attribute = ANIM_META[move0_anim][1]

    def clone(self):
        """Memberwise copy incl. the two frame ctrls (mid-walk clone support; pure-Python fallback
        path -- fused mode carries this in the C PoseEngine). See land.LandState.clone."""
        c = UnderAnimState.__new__(UnderAnimState)
        c.fc0 = self.fc0.clone()
        c.fc1 = self.fc1.clone()
        c.move0 = self.move0; c.move1 = self.move1
        c.m34C3 = self.m34C3; c.ratio = self.ratio; c.m3598 = self.m3598
        c._dash = self._dash
        c._walk = self._walk
        return c

    def _set_move_anime(self, f27, f28, f25, r27, r28, r29, i_morf):
        """daPy_lk_c::setMoveAnime (12723): r27->MOVE0, r28->MOVE1, ratio f27->MOVE1 (1-f27->MOVE0).
        Preserves anim phase across a swap and computes the two frame-ctrl rates. Returns (i_morf>=0)
        so the caller can trigger oldframe-morf. f31 (phase) uses the CURRENT MOVE0 anim's frame."""
        if self.m34C3 in (0, 9, 10):
            f31 = 0.0
        else:
            f31 = fp.fdivs(self.fc0.frame, float(ANIM_META[self.move0][0]))
        self.ratio = f27
        f3 = float(ANIM_META[r27][0])          # new MOVE0 frameMax
        f26 = float(ANIM_META[r28][0])         # new MOVE1 frameMax
        f30 = fp.fdivs(1.0, f3)
        # f27 = f28 + f27*((f25*f3/f26) - f28)   -- the new MOVE0 rate
        f27r = fp.fadds(f28, fp.fmuls(f27, fp.fsubs(fp.fdivs(fp.fmuls(f25, f3), f26), f28)))
        attr0 = ANIM_META[r27][1]
        attr1 = ANIM_META[r28][1]
        self.fc0.set(attr0, 0, f3, f27r, fp.fmuls(f31, f3))
        self.fc1.set(attr1, 0, f26, fp.fmuls(f30, fp.fmuls(f27r, f26)), fp.fmuls(f31, f26))
        self.move0, self.move1, self.m34C3 = r27, r28, r29
        return i_morf >= 0.0

    def _set_blend_move_anime(self, nspeed, m34E2_cos=1.0, i_morf=-1.0):
        """daPy_lk_c::setBlendMoveAnime (2966), flat free-walk path. Returns whether morf triggered."""
        f30 = fp.fdivs(abs(fp.fmuls(nspeed, m34E2_cos)), H_MAXSPEED)
        morf = False
        if f30 < H_2C:                                   # regime 1: WAITS <-> WALK (sword: WALKS)
            f25_2 = fp.fdivs(f30, H_2C)
            self.m3598 = fp.fsubs(1.0, fp.fmuls(fp.fsubs(1.0, H_60), f25_2))
            morf = self._set_move_anime(f25_2, H_38, H_40, 'waits', self._walk, 1, i_morf)
        elif f30 < H_30:                                 # regime 2: WALK <-> DASH (sword: WALKS/DASHS)
            f1 = fp.fdivs(fp.fsubs(f30, H_2C), fp.fsubs(H_30, H_2C))
            morf = self._set_move_anime(f1, H_40, H_48, self._walk, self._dash, 1, i_morf)
            self.m3598 = fp.fmuls(H_60, fp.fsubs(1.0, f1))
        else:                                            # regime 3: DASH cruise (sword: DASHS)
            morf = self._set_move_anime(1.0, H_48, H_48, self._dash, self._dash, 1, i_morf)
            self.m3598 = 0.0
        return morf

    def set_single(self, anim, start, end, rate, m34C3=0):
        """daPy_lk_c::setSingleMoveAnime (12794), under-body part: MOVE0 = `anim` at ratio 1, MOVE1 =
        NULL at ratio 0, m34C3 = 0. Used by procFrontRoll_init (ANM_ROLLF) and other single-anim procs.
        Does NOT touch m3598 (it keeps its pre-proc value -- so during a roll the foot term stays off
        exactly as it was, and speedF = mNormalSpeed momentum). frame ctrl: frame = end-0.001 if the
        rate is negative else start (12815). The caller triggers the FootFK oldframe-morf separately."""
        self.move0 = anim
        self.move1 = None
        self.m34C3 = m34C3
        self.ratio = 0.0
        frame = fp.fsubs(float(end), 0.001) if rate < 0.0 else float(start)
        self.fc0.set(ANIM_META[anim][1], float(start), float(end), float(rate), frame)

    def set_wait_idle(self, ratio, r27_anim, i_morf):
        """daPy_lk_c::setBlendMoveAnime idle branch (2966), the ModeFlg_00000001 + regime-1 +
        shape_angle.y != m34DE arm (line 3132): the WAIT idle proc, having just pivoted, poses the
        turn-in-place walk-step. MOVE0 = ANM_WAITS, MOVE1 = ANM_ATNWLS/ATNWRS at `ratio`
        (= clamp(0.5 + 0.001*|shape_angle.y - m34DE|, 0, 1)), r29 = 2, m3598 = 0. The frame-ctrl
        arguments are in_f27 = mMove.field_0x38 (1.1), f29 = mAtnMove.field_0x28 (1.0). Called with
        m34C3 == 0 (single-anim ROT preceded it), so the phase resets to frame 0. Returns whether
        the oldframe-morf triggered. Both frame-ctrl args are game f32 fields -> keep them f32
        (H_38/ATN_28): fp.fadds/fmuls don't quantize operands, so an f64 1.1 leaks 1 ULP into f27r,
        which becomes the next walk frame's phase f31 -> toe -> speedF (the waitturn f9 spike)."""
        morf = self._set_move_anime(ratio, H_38, ATN_28, 'waits', r27_anim, 2, i_morf)
        self.m3598 = 0.0
        return morf

    def _set_atn_side_anime(self, f31, is_left, i_morf):
        """setBlendAtnMoveAnime side branch (d_a_player_main.cpp:3343). f31 = |mNormalSpeed*cos(gndAngle)|
        / mMaxNormalSpeed. Blends ATN{L,R}S -> ATNW{L,R}S -> ATND{L,R}S with speed; sets m3598. ATN_MOVE
        is not ModeFlg_00000001, so the low-speed arm takes iVar6=4 / m3598=1 (idle would be 2 / 0)."""
        if f31 < ATN_1C:
            f1 = fp.fdivs(f31, ATN_1C)
            m0, m1 = ('atnls', 'atnwls') if is_left else ('atnrs', 'atnwrs')
            morf = self._set_move_anime(f1, ATN_24, ATN_28, m0, m1, 4, i_morf)
            self.m3598 = 1.0
        elif f31 < ATN_20:
            f28 = fp.fdivs(fp.fsubs(f31, ATN_1C), fp.fsubs(ATN_20, ATN_1C))
            m0, m1 = ('atnwls', 'atndls') if is_left else ('atnwrs', 'atndrs')
            morf = self._set_move_anime(f28, ATN_28, ATN_2C, m0, m1, 4, i_morf)
            self.m3598 = fp.fsubs(1.0, fp.fmuls(f28, self.m3598))   # uses the prior-frame m3598
        else:
            anim = 'atndls' if is_left else 'atndrs'
            morf = self._set_move_anime(1.0, ATN_2C, ATN_2C, anim, anim, 4, i_morf)
            self.m3598 = 0.0
        return morf

    def _set_atn_back_anime(self, dvar7, i_morf):
        """setBlendAtnBackMoveAnime (d_a_player_main.cpp:3217). dvar7 = |mNormalSpeed*cos(m34E2)| /
        mMaxNormalSpeed (cos(m34E2)=1 on flat ground). Blends WAITS -> ATNWB -> ATNDB; sets m3598."""
        if dvar7 < ATNB_1C:
            f1 = fp.fdivs(dvar7, ATNB_1C)
            morf = self._set_move_anime(f1, H_38, ATNB_24, 'waits', 'atnwb', 4, i_morf)  # f28 = mMove.field_0x38
            self.m3598 = 1.0
        elif dvar7 < ATNB_20:
            f1 = fp.fdivs(fp.fsubs(dvar7, ATNB_1C), fp.fsubs(ATNB_20, ATNB_1C))
            morf = self._set_move_anime(f1, ATNB_24, ATNB_28, 'atnwb', 'atndb', 4, i_morf)
            self.m3598 = fp.fsubs(1.0, f1)                          # back: 1 - f1 (not 1 - f1*m3598)
        else:
            morf = self._set_move_anime(1.0, ATNB_28, ATNB_28, 'atndb', 'atndb', 4, i_morf)
            self.m3598 = 0.0
        return morf

    def step_atn(self, nspeed, direction, f31, i_morf=-1.0):
        """One ATN_MOVE frame: J3DFrameCtrl update, then setBlendAtnMoveAnime dispatch on mDirection
        (2966). DIR_FORWARD reuses the walk machine (mMaxNormalSpeed 17); DIR_BACKWARD the back-strafe
        blend; a side direction the L/R strafe blend. `f31` = |nspeed*cos(gndAngle)|/max (the caller
        supplies it, already bit-exact from LandState). Returns the render state like step()."""
        self.fc0.update()
        self.fc1.update()
        if direction == DIR_FORWARD:
            morf = self._set_blend_move_anime(nspeed, i_morf=i_morf)
        elif direction == DIR_BACKWARD:
            morf = self._set_atn_back_anime(f31, i_morf)
        else:
            morf = self._set_atn_side_anime(f31, direction == DIR_LEFT, i_morf)
        return dict(move0=self.move0, move1=self.move1, f0=self.fc0.frame, f1=self.fc1.frame,
                    ratio=self.ratio, m3598=self.m3598, morf=morf)

    def step_single(self):
        """Advance the single-anim frame ctrl one game frame (J3DFrameCtrl::update) and return the
        render state: MOVE0 only (ratio 0), m3598 frozen. The mirror of step() for a setSingleMoveAnime
        proc (no setBlendMoveAnime re-pose). posMoveFromFootPos still runs, so the foot toe stream keeps
        updating -- which is what seeds the low-speed tail of the *following* walk (post-roll)."""
        self.fc0.update()
        return dict(move0=self.move0, move1=self.move0, f0=self.fc0.frame, f1=self.fc0.frame,
                    ratio=0.0, m3598=self.m3598, morf=False)

    def step(self, nspeed, m34E2_cos=1.0, i_morf=-1.0):
        """Advance one game frame at the given (already bit-exact) mNormalSpeed. Returns the render
        state for THIS game frame: move0/move1 anim names, f0/f1 the frame-ctrl frames the model
        DRAWS with this frame, ratio, m3598, morf. Order matches the game: the frame controllers
        advance at frame start (J3DFrameCtrl::update), THEN setBlendMoveAnime re-poses at the new
        phase; the register value the game exposes (and draws with) is the post-setBlendMoveAnime
        value. posMoveFromFootPos consumes the PREVIOUS frame's drawn toe, so f31_2 at frame N pairs
        the toe from f0 here with the toe from the prior step()."""
        self.fc0.update()
        self.fc1.update()
        morf = self._set_blend_move_anime(nspeed, m34E2_cos, i_morf)
        return dict(move0=self.move0, move1=self.move1, f0=self.fc0.frame, f1=self.fc1.frame,
                    ratio=self.ratio, m3598=self.m3598, morf=morf)
