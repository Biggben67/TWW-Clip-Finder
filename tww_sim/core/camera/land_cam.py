"""land_cam.py - fp-faithful port of the LAND dCamera_c per-frame loop (JP GZLJ01).

Scope: the camera regime the courtyard Tetra push (and land movement generally) runs in --
**manualCamera** (mode 12, style MM03: the C-stick free/behind camera, active whenever the
C-stick has been used and the recenter hasn't fired) with 1-frame **followCamera** blips
(mode 0, style FN08) on each L rising edge, sequenced by ``nextMode``/``onModeChange``/
``onStyleChange`` and committed by the ``Run`` tail + ``bumpCheck``. csangle
(``dCam_getControledAngleY``) = ``Inv(mDirection.inc)`` -- the committed view-globe yaw.

KEY STRUCTURAL FACT (session 18): on land the yaw is NOT a follow spring chasing Link -- in
mode 12 the yaw target ``m3A8.inc`` moves ONLY with C-stick X (rationalBezierRatio-shaped,
styleParam[24] deg/frame), and the view globe chases it at fixed cushions. The big per-frame
csangle swings in the courtyard captures are the TAS's own C-stick inputs. Link's position
moves only the camera CENTER (a per-axis cushioned chase of attentionPos + (0, m398, 0)).

Ported from the JP Ghidra decompiles (TWW_JP_NEW3/main.dol):
  manualCamera @ 8017527c, followCamera @ 80166bd4 (init + approach paths), nextMode
  @ 80160ed8, Run @ 80160260 (tail), onModeChange @ 801615e4, onStyleChange @ 80161b78,
  limited_range_addition @ 80161f70, cSGlobe/cSPolar/cSAngle (c_angle.cpp + JP inlines).
NOTE the zeldaret decomp header's cSGlobe SETTER U/V bindings are wrong (its followCamera
text is unusable); the JP binary truth is U == yaw (+6), V == elevation (+4), both accessors.

No BG collision is modeled (open-floor regime): lineBGCheck == miss everywhere, water/floor
clamps parametrized by ``floor_y``. Validated 0-ULP against the live oracle
(_notes/tetrapush-camoracle.json) by tests/test_land_cam.py.
"""
from __future__ import annotations

import math
import struct

from ..fp import f32, fadds, fmuls, fmadds
from ..collision import frsqrte, sqrtf_c
from .cam_bezier import rationalBezierRatio
from .cam_angle import (SGlobe, DEG2S16, _s16, _trunc, sang_deg, sang_from_deg, sang_cos,
                        sang_mul, _vsub, _vadd, _vscale, xyz_abs)

STICK_SAT = 0.75                    # _8358 / _16275
STICK_NRM = struct.unpack(">f", bytes.fromhex("3faaaaa8"))[0]   # _16276
BEZ_W = 2.0                         # _9006

# style params (p = styleParam[0..29]) read from the LIVE JP binary at 0x803485ac + idx*0x84
# (MM03 = 57, FN02 = 84) -- the decomp source rows differ; see knowledge/mechanics/land-camera.md.
STYLE_FN02 = dict(
    name="FN02", engine="follow", flags=0x405,
    p=[1.0, 0.0, -100000.0, 0.7, 0.25, 10.0, -100000.0, -100000.0, -100000.0, -100000.0,
       480.0, 280.0, -100000.0, 0.66, 0.08, 10.0, -60.0, 60.0, 2.0, 0.05,
       0.2, -100000.0, -100000.0, 1.0, 0.18, 60.0, -100000.0, -100000.0, -100000.0, 0.05])
STYLE_MM03 = dict(
    name="MM03", engine="manual", flags=0x002,
    p=[0.0, 0.0, -100000.0, 0.7, 0.25, 0.0, 0.0, 30.0, 0.0, 1.0,
       320.0, 240.0, 700.0, 0.0, 20.0, 0.0, 0.0, 30.0, 0.0, 0.6,
       0.33, 0.66, -100000.0, 0.0, 8.0, 55.0, 50.0, 60.0, 0.0, 0.4])
for _st in (STYLE_FN02, STYLE_MM03):
    _st["p"] = [f32(_v) for _v in _st["p"]]     # the DOL stores f32 params (0.7 != f64 0.7)

# The courtyard camera type (live type index 7): mode -> style. Only the modes the land loop
# can reach are mapped; anything else raises (extend when a capture shows it).
TYPE_JUMP = {0: STYLE_FN02, 1: STYLE_FN02, 12: STYLE_MM03}

# dCamSetup_c defaults (matched ctor, d_cam_param.cpp:207)
SETUP = dict(m09C=0.3, m0A0=0.2, m098=60.0, DMCValue=0.1, DMCAngle=30.0,
             cstick_m00=0.2, cstick_m04=0.95)



def _lra(value_f32, lo, hi, target):
    """d_camera::limited_range_addition: target = f32(target + value); clamp to [lo, hi]
    (doubles); returns (in_range, new_target). in_range == 0 means it was clamped."""
    lo = float(lo)
    hi = float(hi)
    value = float(value_f32)
    if hi < lo:
        value = -value
        lo, hi = hi, lo
    t = f32(float(target) + value)
    if float(t) < lo:
        return 0, f32(lo)
    if hi < float(t):
        return 0, f32(hi)
    return 1, t


def stick_ratio(pos):
    """manualCamera's C-stick shaping: >= 0.75 -> 1.0, > -0.75 -> RBR(1.3333*pos, 2.0),
    else -1.0."""
    pos = f32(pos)
    if pos >= STICK_SAT:
        return 1.0
    if pos > -STICK_SAT:
        return rationalBezierRatio(f32(STICK_NRM * pos), BEZ_W)
    return -1.0


# ---------------------------------------------------------------- pad decode
def pad_from_raw(inp):
    """The camera ``pad`` dict from one RAW controller input (dict with ``stickX``/``stickY``/
    ``substickX``/``substickY``/``triggerL``, bytes 0..255) -- the decoded JUTGamePad state
    ``dCamera_c::updatePad`` stores (main/C stick floats + trigger + ``mMainStickAngle``).

    The camera reads the polled ``g_mDoCPd`` pad, the SAME pipeline stage as the attention's
    delay-1 L -- in a DTM replay feed it the delay-1 raw input the physics acts on, never the
    physics' delay-2 acted pad. Decode: PADClamp octagon (main 15/72/40 div 54, sub 15/59/31
    div 42) + JUTGamePad TStick::update (STICK_MODE_1: unit-circle clamp, value capped at 1),
    trigger ClampTrigger 30/180 div 150. Gated 0-ULP against the live oracle's post-updatePad
    stick lasts by tests/test_from_f0.py (trigger mid-values 31..179 never occur in the oracle
    window and are decode-unvalidated; ``main_angle`` is DMC-only and inert at status 0)."""
    from ..mathlib import clamp_stick, _clamped_angle_s16
    mx_i, my_i = clamp_stick(int(inp['stickX']) - 128, int(inp['stickY']) - 128, 72, 40, 15)
    mx = f32(mx_i / 54.0)
    my = f32(my_i / 54.0)
    mval = f32(math.sqrt(f32(f32(mx * mx) + f32(my * my))))
    if mval > 1.0:
        mx = f32(mx / mval)
        my = f32(my / mval)
        mval = f32(1.0)
    ang = _clamped_angle_s16(mx_i, my_i, 54.0)
    cx_i, cy_i = clamp_stick(int(inp.get('substickX', 128)) - 128,
                             int(inp.get('substickY', 128)) - 128, 59, 31, 15)
    cx = f32(cx_i / 42.0)
    cy = f32(cy_i / 42.0)
    cval = f32(math.sqrt(f32(f32(cx * cx) + f32(cy * cy))))
    if cval > 1.0:
        cx = f32(cx / cval)
        cy = f32(cy / cval)
        cval = f32(1.0)
    t = int(inp.get('triggerL', 0))
    t = 0 if t <= 30 else (min(t, 180) - 30)
    return dict(mx=float(mx), my=float(my), mval=float(mval),
                cx=float(cx), cy=float(cy), cval=float(cval),
                trigL=float(f32(t / 150.0)), main_angle=ang)


# ---------------------------------------------------------------- block seed
def _bf(b, o):
    return struct.unpack(">f", b[o:o + 4])[0]


def _bs(b, o):
    return struct.unpack(">h", b[o:o + 2])[0]


def _bi(b, o):
    return struct.unpack(">i", b[o:o + 4])[0]


def _bu(b, o):
    return struct.unpack(">I", b[o:o + 4])[0]


def _bv3(b, o):
    return tuple(struct.unpack(">3f", b[o:o + 12]))


def seed_from_block(cam, b):
    """Seed a LandCamera from a raw live ``dCamera_c`` block (>= 0x510 bytes from the camera
    base; the oracle fixture's ``seed_cam_raw``). Only the land-loop state is read: committed
    globe/center/eye/fovy/angleY, the view cache, the mode machinery, pad lasts, and the
    manual-work union (valid when the seed frame is mode 12)."""
    cam.dir = SGlobe(_bf(b, 0x08), _bs(b, 0x0C), _bs(b, 0x0E), formal=False)
    cam.center = _bv3(b, 0x10)
    cam.eye = _bv3(b, 0x1C)
    cam.fovy = _bf(b, 0x38)
    cam.angleY = struct.unpack(">H", b[0x6C:0x6E])[0]
    cam.vc_dir = SGlobe(_bf(b, 0x3C), _bs(b, 0x40), _bs(b, 0x42), formal=False)
    cam.vc_center = _bv3(b, 0x44)
    cam.vc_eye = _bv3(b, 0x50)
    cam.vc_fovy = _bf(b, 0x60)
    cam.cur_mode = _bi(b, 0x13C)
    cam.m144 = _bi(b, 0x144)
    cam.m100, cam.m101, cam.m102 = b[0x100], b[0x101], b[0x102]
    cam.m108 = _bu(b, 0x108)
    cam.m110 = b[0x110]
    cam.m11C = _bu(b, 0x11C)
    cam.flags = _bu(b, 0x50C)
    cam.m184 = _bi(b, 0x184)
    cam.mx, cam.my, cam.mval = _bf(b, 0x154), _bf(b, 0x158), _bf(b, 0x15C)
    cam.cx, cam.cy, cam.cval = _bf(b, 0x16C), _bf(b, 0x170), _bf(b, 0x174)
    cam.trigL = _bf(b, 0x190)
    cam.m19A, cam.m19B = b[0x19A], b[0x19B]
    cam.w_delta = _bv3(b, 0x37C)
    cam.w_target = _bv3(b, 0x388)
    cam.w_m394 = _bf(b, 0x394)
    cam.w_m398 = _bf(b, 0x398)
    cam.w_m3A0 = b[0x3A0]
    cam.w_m3A4 = _bf(b, 0x3A4)
    cam.w_glob = SGlobe(_bf(b, 0x3A8), _bs(b, 0x3AC), _bs(b, 0x3AE), formal=False)
    cam.w_m3B0 = _bf(b, 0x3B0)
    cam.w_m3B4 = _bf(b, 0x3B4)
    cam.cur_style = TYPE_JUMP[cam.cur_mode]
    return cam


# ---------------------------------------------------------------- the camera
class LandCamera:
    """The dCamera_c land loop. Drive with per-frame ``step(pad, link, attn)``.

    pad:  dict(mx, my, mval, cx, cy, cval, trigL, main_angle) -- the game's DECODED stick
          state for this frame (mStickMainPosX/.., mStickCPosX/..; main_angle = the s16
          mMainStickAngle for the DMC system).
    link: dict(pos, facing, attn_pos) -- current.pos, shape_angle.y, attention_info.position.
    attn: dict(truth, target_attn) -- dAttention LockonTruth() and (when truth) the locked
          actor's attention_info.position; target_attn None <=> no lockon target.
    status0/status1: the dComIfGp player status words (default 0 = plain land movement).
    """

    def clone(self):
        """A deep copy for planner/beam-search node branching: every field is a scalar or an
        immutable tuple except the three mutable ``SGlobe``s, which are ``.copy()``-ed. Additive;
        the camera has no shared immutable tables so this is cheap."""
        c = LandCamera.__new__(LandCamera)
        c.__dict__.update(self.__dict__)
        c.dir = self.dir.copy()
        c.vc_dir = self.vc_dir.copy()
        c.w_glob = self.w_glob.copy()
        return c

    def __init__(self, floor_y=0.16326504945755005):
        self.floor_y = f32(floor_y)
        # committed
        self.dir = SGlobe(300.0, 0, 0)
        self.center = (0.0, 0.0, 0.0)
        self.eye = (0.0, 0.0, 0.0)
        self.fovy = 60.0
        self.angleY = 0
        # view cache
        self.vc_dir = SGlobe(300.0, 0, 0)
        self.vc_center = (0.0, 0.0, 0.0)
        self.vc_eye = (0.0, 0.0, 0.0)
        self.vc_fovy = 60.0
        # mode machinery
        self.cur_mode = 12
        self.cur_style = STYLE_MM03
        self.m144 = 0
        self.m184 = 0
        self.m100 = self.m101 = self.m102 = 1
        self.m108 = 0
        self.m110 = 1
        self.m11C = 0
        self.m14C = 0.0
        self.flags = 0
        self.m148 = 0
        self.m068 = 9
        # DMC
        self.dmc_on = 0
        self.dmc_frozen = 0
        self.dmc_stick = 0
        # pad lasts
        self.mx = self.my = self.mval = 0.0
        self.cx = self.cy = self.cval = 0.0
        self.trigL = 0.0
        self.m19A = self.m19B = 0
        # manual work
        self.w_delta = (0.0, 0.0, 0.0)      # m37C..m384 (lock-blend delta vec)
        self.w_target = (0.0, 0.0, 0.0)     # m388..m390 (target center)
        self.w_m394 = 0.0                   # lock blend ramp
        self.w_m398 = 0.0                   # center height over attnPos
        self.w_m3A0 = 0                     # entered-with-status1&0x20000 flag
        self.w_m3A4 = 0.0
        self.w_glob = SGlobe(300.0, 0, 0)   # m3A8 target globe
        self.w_m3B0 = 0.0                   # center cushion XZ
        self.w_m3B4 = 0.0                   # center cushion Y
        # follow work (blip frames)
        self.f_m37C = 0                     # approach frame count
        self.f_m380 = 0.0
        self.f_m384 = 0.0
        self.f_m388 = 0
        self.f_m38C = 0
        self.f_m390 = 0
        self.f_m392 = 0
        self.f_m394 = 0.0
        self.f_m398 = 0.0
        self.f_m39C = 0.0
        self.f_m3A0 = 0.0
        self.f_m3A4 = 0.0
        self.f_m3A8 = 0.0
        self.f_m3AC = 0.0
        self.f_m3B0 = 0.0
        self.f_m3B4 = 0
        self.f_m3B8 = 0.0
        self.f_m3BC = 0.0
        self.f_m3C0 = (0.0, 0.0, 0.0)
        self.f_m3CC = (0.0, 0.0, 0.0)
        self.f_m3D8 = 1
        self.f_m3D9 = 0
        self.f_m3DC = 0.75
        self.f_m3E0 = 0.01
        self.f_m3E4 = 0.01
        self.f_m3E8 = 0.01
        self.f_m3EC = 0.75
        self.f_m3F0 = 0.25
        # misc
        self.lockon_target = None           # camera's mpLockonTarget (attn pos of the actor)

    # ------------------------------------------------------------ per-frame step
    def step(self, pad, link, attn, status0=0, status1=0):
        # Run prologue
        self.flags &= 0xEFEB63FE
        # checkGroundInfo (open flat floor): m354 = floor under player, m360 = on-floor
        self.m354 = self.floor_y
        self.m360 = 1
        # Att()
        self.lockon_target = attn.get("target_attn") if attn.get("truth") else None
        # updatePad
        self._update_pad(pad)
        # flag 0x1000 from LockonTruth (JP Run:71-78)
        if attn.get("truth"):
            self.flags |= 0x1000
        # nextType: constant. nextMode:
        next_mode = self._next_mode(self.cur_mode, attn, status0, status1)
        if next_mode != self.cur_mode and next_mode in TYPE_JUMP:
            self._on_mode_change(self.cur_mode, next_mode)
            self.cur_mode = next_mode
        if self.cur_mode not in TYPE_JUMP:
            self.cur_mode = 0
        style = TYPE_JUMP[self.cur_mode]
        if style is not self.cur_style:
            self.m11C = 0                    # onStyleChange
            self.cur_style = style
        self.flags &= ~0x20
        if self.cur_mode == 12:
            self.flags |= 0x20
        self.flags &= 0x7FFFFFFF
        # m148 (forward peek): style flag 4 only (FN08); no BG ahead on the open floor -> 0
        if not (style["flags"] & 0x004):
            self.m148 = 0
        # (else m148 += (forwardCheckAngle() - m148) * FwdCushion == stays 0 with no walls)
        self.m068 = 9
        # engine
        if style["engine"] == "manual":
            self._manual(style, link, status0, status1)
        else:
            self._follow(style, link, status0, status1)
        self.m108 += 1
        self.m11C += 1
        # Run tail
        # (bank decay skipped: bank stays 0 on land)
        fl = style["flags"]
        if fl & 1:
            self.m068 = 0x3F
        elif fl & 2:
            self.m068 = 0xF
        if fl & 0x400:
            self.m068 |= 0x40
        # floor clamp of the committed center (FloorMargin spring; margin never binds on the
        # courtyard floor -- asserted by the oracle gate)
        self.center = self.vc_center
        self.eye_committed_pending = True
        self.fovy = self.vc_fovy
        # bumpCheck (no BG hit, no water/roof above): commit
        if self.flags & 0x4000:
            raise NotImplementedError("bumpCheck 0x4000 recovery (wall) not modeled")
        self.eye = self.vc_eye
        self.dir = self.vc_dir.copy()        # plain copy (no Formal)
        # DMC / mAngleY
        ang = _s16(pad.get("main_angle", 0) - self.dmc_stick)
        if self.mval < SETUP["DMCValue"] or not (-sang_from_deg(SETUP["DMCAngle"]) <= ang
                                                 <= sang_from_deg(SETUP["DMCAngle"])):
            self.dmc_on = 0
        if self.dmc_on:
            self.angleY = self.dmc_frozen & 0xFFFF
        else:
            self.angleY = (self.dir.inc - 0x8000) & 0xFFFF
        return self.angleY

    # ------------------------------------------------------------ pad
    def _update_pad(self, pad):
        self.mx = f32(pad["mx"])
        self.my = f32(pad["my"])
        self.mval = f32(pad["mval"])
        self.cx = f32(pad["cx"])
        self.cy = f32(pad["cy"])
        self.cval = f32(pad["cval"])
        self.trigL = f32(pad["trigL"])
        if self.trigL > SETUP["m0A0"]:
            self.m19B = 0 if self.m19A else 1
            self.m19A = 1
        else:
            self.m19B = 0
            self.m19A = 0

    # ------------------------------------------------------------ nextMode (JP 80160ed8)
    def _next_mode(self, cur, attn, status0, status1):
        nm = cur
        if cur in (4, 10, 11, 13, 14):
            self.m144 = 1
            self.m184 = 0
        elif cur == 12:
            if ((self.cval < 0.01 and self.dir.r < SETUP["m098"])
                    or (self.flags & 0x80000000)):
                self.m144 = 1
                self.m184 = 0
            elif self.m19B:
                self.m144 = 1
                self.m184 = 0
        else:
            if cur in (5, 6):
                self.m144 = 1
                self.m184 = 0
            if cur in (5, 6, 1):
                self.lockon_target = None
            if self.m19B:
                self.m144 = 1
                self.m184 = 0
            elif not (self.cy > 0.0 or self.cval <= SETUP["m09C"]):
                self.m144 = 0
            elif cur in (0, 19):
                if (self.mval < 0.5 and not attn.get("truth")
                        and not (status0 & 0x100000)):
                    if self.m184 == 1:
                        if self.cy < SETUP["cstick_m00"]:
                            self.m184 = 0
                    elif self.cy > SETUP["cstick_m04"]:
                        self.m184 = 1
        if self.flags & 0x4000000:
            if status0 & 0x80000000:
                self.flags |= 0x8000
            self.m144 = 1
            self.flags &= ~0x4000000
        # (force-lock NPC_MD branch skipped: mLockOnActorId always -1 here)
        if cur == 12 and self.m144:
            nm = 0
        elif (status0 & 0x200000) or (status1 & 8):
            nm = 14
        elif status0 & 0x80000080:
            nm = 17
        elif status0 & 0x800000:
            nm = 12 if self.m144 == 0 else 18
        elif status1 & 0x10:
            nm = 15
        elif status0 & 0x2000:
            nm = 4
        elif (status0 & 0x25000) and not attn.get("lockon", attn.get("truth")):
            nm = 10
        elif (status0 & 0x80000) and not attn.get("lockon", attn.get("truth")):
            nm = 11
        elif self.m144 == 0:
            nm = 12
        elif status1 & 2:
            nm = 5
        elif status1 & 4:
            nm = 6
        elif status0 & 0x60:
            nm = 6
        elif status0 & 0x61:
            nm = 5
        elif (status0 & 0x406) and cur != 12:
            if self.lockon_target is not None:
                nm = 8
            # else keep nm
        elif attn.get("truth") and not (status0 & 0xC000000):
            nm = 2
        elif attn.get("lockon", attn.get("truth")):
            nm = 1
        elif ((status0 & 0x400000) and not (status0 & 0x36A02371)
              and not (status1 & 0x11)):
            nm = 2       # boomerang-wait force lock (not reachable on this route)
        elif status1 & 0x80000:
            nm = 19
        else:
            if cur == 12:
                if self.m144:
                    nm = 0
            else:
                nm = 0
        if nm == 12 and 12 not in TYPE_JUMP:
            self.m144 = 1
            nm = cur
        if nm not in TYPE_JUMP and nm != cur:
            return cur
        if nm == 1:
            self.flags |= 0x100000
        return nm

    def _on_mode_change(self, cur, nxt):
        self.m108 = 0
        self.m100 = self.m101 = self.m102 = 0
        self.m110 = 1
        self.m14C = 0.0
        self.flags &= 0xFFFFFEE1
        self.flags &= 0xFFFFDFFF
        if nxt == 7:
            self.flags |= 0x10
        elif nxt == 0:
            if cur == 1 and TYPE_JUMP.get(0) is TYPE_JUMP.get(1):
                self.m110 = 0
        elif nxt == 1:
            if cur == 0 and TYPE_JUMP.get(0) is TYPE_JUMP.get(1):
                self.m110 = 0

    # ------------------------------------------------------------ manualCamera (JP 8017527c)
    def _manual(self, style, link, status0, status1):
        p = style["p"]
        hgt_rate, hgt_lo, hgt_hi = p[9], p[6], p[7]
        r_rate, r_lo, r_hi = p[14], p[11], p[12]
        pit_rate, pit_lo, pit_hi = p[19], p[16], p[17]
        yaw_scale = p[24]
        fov_rate, fov_lo, fov_hi = p[29], p[26], p[27]
        cush = p[21]                      # 0.5
        cush_slow = p[20]                 # 0.33
        off_x, off_z = p[1], p[0]

        target = self.lockon_target
        locked = bool(self.flags & 0x1000) and target is not None

        if self.m11C == 0:
            self.m100 = self.m101 = self.m102 = 1
            self.w_m394 = 1.0 if locked else 0.0
            attn_pos = link["attn_pos"]
            self.w_m398 = f32(self.vc_center[1] - attn_pos[1])
            self.w_m3A4 = f32(r_lo)
            self.vc_dir = SGlobe.from_vec(_vsub(self.vc_eye, self.vc_center))
            self.w_m3A0 = 1 if (status1 & 0x20000) else 0
            self.w_glob = self.vc_dir.copy()
            self.w_delta = (0.0, 0.0, 0.0)
            # m3B8 = 0 (unused in this path)

        # status-driven param overrides (all inert at status0/1 == 0)
        if status0 & 0x8000000:
            if r_rate < 4.0:
                r_rate = 4.0
            if hgt_rate < -10.0:            # dVar19 is hgt_lo actually; see note below
                pass
        elif ((status0 & 0x2800100) or (status1 & 0x10020)
              or False):                    # Cb1/Md flying: not on this route
            raise NotImplementedError("manualCamera flying/hang param override")
        elif status1 & 0x40000:
            r_rate = -10.0                  # dVar13 = _10013
            pit_hi = 10.0                   # dVar12 = _6064

        if (not self.w_m3A0) and (status1 & 0x20000):
            self.m144 = 1
            self.flags |= 0x4000000

        ratio_x = stick_ratio(self.cx)
        ratio_y = stick_ratio(self.cy)

        cushA = cush                        # local_13c / local_140 (pitch / radius cushions)
        cush_pitch = f32(cush)
        cush_radius = f32(cush)
        cush_yaw = f32(cush)                # dVar22, never mutated
        cush_height = f32(cush)             # dVar21 (mutated, reused by fovy)

        if ((status0 & 0x6800061) or (status1 & 0x10000)) and not self.dmc_on:
            self._set_dmc()

        neg_ry = -float(ratio_y)
        # center height (m398)
        h_target = self.w_m398
        in_range, h_target = _lra(f32(neg_ry * f32(hgt_rate)), hgt_lo, hgt_hi, h_target)
        if not in_range:
            cush_height = f32(cush_slow)
        self.w_m398 = f32(self.w_m398 + f32(float(cush_height) * float(f32(h_target - self.w_m398))))
        if status0 & 0x100:
            if self.w_m398 < 30.0:
                self.w_m398 = f32(30.0)

        offset = (f32(off_x), self.w_m398, f32(off_z))

        if locked:
            # lock blend: target center slides toward relationalPos(player, target, offset, 0.5)
            lock_rel = self._relational_pos4(link, target, offset, 0.5)
            self.w_target = lock_rel
            norm_rel = self._relational_pos2(link, offset)
            # lineBGCheck(norm_rel -> lock_rel) miss on the open floor -> the blend path
            y = self._water_height(self.w_target)
            if self.w_target[1] < y:
                self.w_target = (self.w_target[0], y, self.w_target[2])
            self.w_delta = _vsub(self.w_target, norm_rel)
            if self.w_m394 < 1.0:
                self.w_m394 = f32(self.w_m394 + 0.05)
                self.w_target = _vadd(_vscale(self.w_delta, self.w_m394), norm_rel)
            elif self.w_m394 > 1.0:
                self.w_m394 = 1.0
        else:
            self.w_target = self._relational_pos2(link, offset)
            y = self._water_height(self.w_target)
            if self.w_target[1] < y:
                self.w_target = (self.w_target[0], y, self.w_target[2])
            if self.w_m394 > 0.0:
                self.w_m394 = f32(self.w_m394 - 0.05)
                self.w_target = _vadd(_vscale(self.w_delta, self.w_m394), self.w_target)
            elif self.w_m394 < 0.0:
                self.w_m394 = 0.0

        # center cushions m3B0/m3B4 (init: from the target-to-center distance)
        if self.m11C == 0:
            d = _vsub(self.w_target, self.vc_center)
            # PSVECSquareMag: (z*z + x*x) fused, + y*y, single precision
            sq = float(fadds(fmadds(d[2], d[2], fmuls(d[0], d[0])), fmuls(d[1], d[1])))
            dist = 0.0
            if sq > 0.0:
                g = frsqrte(sq)
                g = 0.5 * g * (3.0 - sq * g * g)
                g = 0.5 * g * (3.0 - sq * g * g)
                g = 0.5 * g * (3.0 - sq * g * g)
                dist = float(f32(sq * 0.5 * g * (3.0 - sq * g * g)))
            fac = f32(0.0)
            if dist <= 100.0:
                fac = f32(1.0 - f32(dist / 100.0))
            self.w_m3B0 = f32(float(p[3]) * float(fac))
            self.w_m3B4 = f32(float(p[4]) * float(fac))
        else:
            self.w_m3B0 = f32(self.w_m3B0 + f32(0.05 * f32(p[3] - self.w_m3B0)))
            self.w_m3B4 = f32(self.w_m3B4 + f32(0.05 * f32(p[4] - self.w_m3B4)))

        diff = _vsub(self.w_target, self.vc_center)
        move = (f32(diff[0] * self.w_m3B0), f32(diff[1] * self.w_m3B4),
                f32(diff[2] * self.w_m3B0))
        self.vc_center = _vadd(self.vc_center, move)
        # (the no-lock center ground check is a BG line check -> miss)

        # target globe: radius / pitch / yaw
        r_target = self.w_glob.r
        in_range, r_target = _lra(f32(neg_ry * f32(r_rate)), r_lo, r_hi, r_target)
        if not in_range:
            cush_radius = f32(cush_slow)
        pit_deg = sang_deg(self.w_glob.az)
        in_range, pit_deg = _lra(f32(neg_ry * f32(pit_rate)), pit_lo, pit_hi, pit_deg)
        if not in_range:
            cush_pitch = f32(cush_slow)
        yaw_deg = sang_deg(self.w_glob.inc)
        new_az = _trunc(f32(DEG2S16 * pit_deg))
        new_inc = _trunc(f32(DEG2S16 * f32(yaw_deg + f32(float(ratio_x) * float(yaw_scale)))))
        self.w_glob = SGlobe(r_target, new_az, new_inc)

        if locked:
            self.flags |= 0x2000

        # view-cache globe chases the target globe
        self.vc_dir.r = f32(self.vc_dir.r + f32(float(cush_radius)
                                                * float(f32(self.w_glob.r - self.vc_dir.r))))
        self.vc_dir.az = _s16(self.vc_dir.az
                              + sang_mul(_s16(self.w_glob.az - self.vc_dir.az), cush_pitch))
        self.vc_dir.inc = _s16(self.vc_dir.inc
                               + sang_mul(_s16(self.w_glob.inc - self.vc_dir.inc), cush_yaw))
        self.vc_eye = _vadd(self.vc_center, self.vc_dir.xyz())

        # fovy
        fov_target = self.vc_fovy
        in_range, fov_target = _lra(f32(neg_ry * f32(fov_rate)), fov_lo, fov_hi, fov_target)
        if not in_range:
            cush_height = f32(cush_slow)     # fresh param[20] read; value identical
        self.vc_fovy = f32(self.vc_fovy + f32(float(cush_height)
                                              * float(f32(fov_target - self.vc_fovy))))
        # (flying fovy noise / bank blocks: status1 & 0x60 only)
        if status1 & 0x60:
            raise NotImplementedError("manualCamera flying fovy/bank")

    # ------------------------------------------------------------ followCamera (blip paths)
    def _follow(self, style, link, status0, status1):
        p = style["p"]
        if not (self.m108 == 0 or self.m100 == 0):
            raise NotImplementedError("followCamera main path (post-approach) not ported")
        # pre-init springs (run every frame)
        if self.m108 == 0:
            self.f_m3AC = 0.0
            self.f_m3B0 = 0.0
            self.f_m3D9 = 0
        if (not (status0 & 0x300)) or (status0 & 0x2000000):
            self.f_m3B0 = f32(self.f_m3B0 + f32(0.06 * f32(p[0] - self.f_m3B0)))
        elif p[0] > -10.0:
            self.f_m3B0 = -10.0
        if status1 & 0x40000:
            self.m148 = 0
        if status0 & 0xA5000 and (self.flags & 0x200):
            raise NotImplementedError("followCamera peep/fly m3AC branch")
        self.f_m3AC = f32(self.f_m3AC + f32(0.06 * f32(p[1] - self.f_m3AC)))
        offset = (self.f_m3AC, f32(p[5]), self.f_m3B0)

        if self.m108 == 0:
            self.vc_dir = SGlobe.from_vec(_vsub(self.vc_eye, self.vc_center))
            self.f_m394 = 0.9
            self.f_m388 = 0x50
            self.f_m398 = f32(p[11])
            self.f_m39C = f32(p[10])
            self.f_m390 = self.f_m392 = 0
            self.f_m38C = 0
            self.f_m3BC = self.f_m3A0 = sang_deg(self.dir.az)
            self.f_m3C0 = self.vc_center
            self.f_m3CC = self.vc_eye
            self.f_m3E0 = self.f_m3E4 = self.f_m3E8 = 0.01
            self.f_m3DC = 0.75
            self.f_m3EC = f32(p[3])
            self.f_m3F0 = f32(p[4])
            self.f_m3B4 = 0
            self.f_m3D8 = 1
            self.f_m3A8 = self.vc_fovy
            self.f_m3B8 = 0.0
            self.f_m3A4 = f32(link["pos"][1])
            if (self.flags & 0x8000) or not self.m110:
                self.m100 = self.m101 = self.m102 = 1
                self.f_m37C = 1
            else:
                rel = self._relational_pos2(link, offset)
                yaw = (_s16(link["facing"] - 0x8000) if (self.flags & 0x100000)
                       else self.vc_dir.inc)
                g = SGlobe(f32(p[10]), sang_from_deg(p[15]), yaw)
                target_eye = _vadd(rel, g.xyz())
                # m37C = trunc(3.8*sqrtf(dist/max(10,height)))+1; the min's second operand
                # never binds in the oracle (data-underdetermined; land-camera.md Open).
                d1 = float(xyz_abs(_vsub(target_eye, self.eye)))
                d2 = float(f32(4.0 * xyz_abs(_vsub(target_eye, self.center))))
                dd = d2 if d1 > d2 else d1
                height = float(link.get("height", 125.0))
                if height < 10.0:
                    height = 10.0
                self.f_m37C = _trunc(f32(3.8 * sqrtf_c(f32(abs(f32(dd)) / f32(height))))) + 1
            self.f_m398 = self.f_m39C = self.dir.r
            self.f_m3A8 = self.fovy
            self.f_m380 = float(self.f_m37C * (self.f_m37C + 1) >> 1)
            self.f_m384 = 0.0

        rel = self._relational_pos2(link, offset)
        rel = (rel[0], self._water_height(rel), rel[2])
        if self.m100 == 0:
            self.f_m384 = float(self.f_m37C - self.m108)
            ratio = f32(self.f_m384 / self.f_m380)
            self.f_m3C0 = _vadd(self.f_m3C0, _vscale(_vsub(rel, self.f_m3C0), ratio))
            self.vc_center = _vadd(self.vc_center,
                                   _vscale(_vsub(self.f_m3C0, self.vc_center), f32(p[3])))
            # (near-center BG recheck: miss)
            r_lim = self.vc_dir.r
            if r_lim < p[11]:
                r_lim = f32(p[11])
            elif r_lim > p[10]:
                r_lim = f32(p[10])
            az = self.vc_dir.az
            lo = sang_from_deg(p[16])
            hi = sang_from_deg(p[17])
            if az < lo:
                az = lo
            if hi < az:
                az = hi
            tgt = SGlobe(r_lim, az, _s16(self.angleY - 0x8000))
            self.vc_dir.r = f32(self.vc_dir.r + f32(float(ratio)
                                                    * float(f32(tgt.r - self.vc_dir.r))))
            self.vc_dir.az = _s16(self.vc_dir.az
                                  + sang_mul(_s16(tgt.az - self.vc_dir.az), ratio))
            if self.flags & 0x100000:
                self.vc_dir.inc = _s16(self.vc_dir.inc
                                       + sang_mul(_s16(_s16(link["facing"] - 0x8000)
                                                       - self.vc_dir.inc), ratio))
            self.vc_eye = _vadd(self.vc_center, self.vc_dir.xyz())
            self.f_m3CC = self.vc_eye
            if self.f_m37C - 1 <= self.m108:
                self.m100 = self.m101 = self.m102 = 1
            self.f_m3A0 = sang_deg(self.vc_dir.az)
            self.f_m398 = self.f_m39C = self.vc_dir.r
            self.vc_fovy = f32(float(self.vc_fovy)
                               + float(f32(float(ratio) * float(f32(p[25] - self.vc_fovy)))))
            self.f_m380 = f32(self.f_m380 - self.f_m384)

    # ------------------------------------------------------------ helpers
    def _set_dmc(self):
        self.dmc_on = 1
        self.dmc_frozen = _s16(self.dir.inc - 0x8000)
        self.dmc_stick = 0        # set from pad main_angle by the caller path when needed

    def _relational_pos2(self, link, offset):
        """relationalPos(player, &offset): globe(offset); yaw += directionOf(player);
        attnPos + globe.Xyz()."""
        g = SGlobe.from_vec(offset)
        g.inc = _s16(link["facing"] + g.inc)
        return _vadd(link["attn_pos"], g.xyz())

    def _relational_pos4(self, link, target_attn, offset, scale):
        """relationalPos(player, target, &offset, 0.5)."""
        a1 = link["attn_pos"]
        a2 = target_attn
        mid = _vadd(a1, _vscale(_vsub(a2, a1), 0.5))
        dg = SGlobe.from_vec(_vsub(a2, a1))
        og = SGlobe.from_vec(offset)
        og.inc = _s16(link["facing"] + og.inc)
        ang = _s16(self.vc_dir.inc - dg.inc)
        dg.r = f32(float(scale) * float(f32(f32(0.5 * dg.r) * sang_cos(ang))))
        return _vadd(_vadd(mid, dg.xyz()), og.xyz())

    def _water_height(self, pos):
        """getWaterSurfaceHeight on the open courtyard: no roof, ground = floor_y; clamps to
        floor_y + 5 only if the point is that low (never for the camera center)."""
        g5 = f32(self.floor_y + 5.0)
        return g5 if g5 > pos[1] else f32(pos[1])
