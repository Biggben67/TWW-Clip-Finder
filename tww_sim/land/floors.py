#!/usr/bin/env python3
"""land/floors.py - the opt-in per-frame GROUND response for LandState (ROADMAP Phase G).

Models the vertical half of ``dBgS_Acch::CrrPos`` plus the player's slope terms, at the game's
exact points in the frame:

  * **speedF slope scale** (posMoveFromFootPos, d_a_player_main.cpp:2408-2417): ``r3 =
    getGroundAngle(mAcch.m_gnd, current.angle.y)`` (the PREVIOUS frame's CrrPos ground poly,
    THIS frame's travel), ``sp7C.z *= cM_scos(r3)``, and the ``r3 < 0`` (uphill) ``*= 0.85``
    branch. ``getGroundAngle`` (:8598) = ``cM_atan2s(|n_xz| * cos(atan2s(nx,nz) - yaw), ny)`` --
    the atan table truncates ``ratio*1024``, so any slope under ~1/1024 (~0.056 deg) returns
    EXACTLY 0 and the scale is a bit-exact no-op (fmuls by 1.0). The GanonA micro-incline
    (0.022 deg) sits below the cell; the ~10-deg ramp does not.
  * **Gravity dip + GroundCheck snap** (posMoveFromFootPos:2464-2479 + d_bg_s_acch.cpp:122-153):
    ``speed.y += gravity`` (walk -2.5, clamp maxFallSpeed), ``pos += speed``; CrrPos then probes
    GroundCross at ``pos.y + 60`` (Link: m_ground_check_offset 60, m_ground_up_h 0) and snaps
    ``pos.y = ground_h`` / ``speed.y = 0`` iff ``ground_h > pos.y`` (the post-integration y).
    GroundCross = the MAX plane-cross y over candidate polys (order-independent, unlike
    WallCorrect): the block ground lists unconditionally plus wall-list polys with ny >= 0.014
    (cBgW::RwgGroundCheckGnd/Wall, c_bg_w.cpp:470-512), accepted by ``cM3d_CrossY_Tri_Front``
    with ``y < probe.y`` strictly.
  * **m35B8 foot ground-lift + m34E0 waist tilt** (footBgCheck :8712, setWaistAngle :9530):
    see :class:`GroundState`.

Scope gate: this module implements the MICRO-INCLINE tier bit-exactly (every getGroundAngle
term quantizes to 0). Where a genuinely sloped term would change FP behavior it RAISES
``SlopeNotModeled`` instead of silently approximating -- the ~10-deg ramp tier must port those
terms decomp-first (asm-checked fusion) before parks beyond the GanonA 630u zone can be simmed.

Mesh contract: ``*_floors.json`` = the room's GroundCross candidate set (ground-list polys +
wall-list polys with ny >= 0.014) with the game's STORED planes, in block-grid visit order
(ties between coplanar tris then resolve to the same poly the game records). Captured by
``harness/rollstab/capture_walls.py floors=1``.
"""
from __future__ import annotations
import json

from ..core.fp import f32, fadds, fsubs, fmuls, fmadds
from ..core.collision import Tri, Plane, ground_cross_y, cross_y_tri_front, fsqrt
from ..core.mathlib import cM_atan2s, cM_ssin_s16, cM_scos_s16, s16_signed, cLib_addCalc
from ..core.anim.fk import mtx_mult_vec
from .constants import (cLib_addCalcAngleS, WAIT, FREE_WAIT, WAIT_TURN,
                        SUBJECTIVITY, SIDE_STEP_LAND, BACK_JUMP_LAND, FRONT_ROLL,
                        FRONT_ROLL_CRASH, SIDE_STEP, BACK_JUMP)

NEG_INF = float('-inf')            # -G_CM3D_F_INF sentinel (GroundCross "no floor")
GND_CHECK_OFFSET = f32(60.0)       # dBgS_Acch m_ground_check_offset (Link default, ctor)
FOOT_PROBE_UP = f32(30.1)          # footBgCheck probe height above pos.y (:8748)
FOOT_GND_RANGE = f32(60.2)         # footBgCheck accept window sp5C.y - f1 < 60.2 (:8757)
UPHILL_SCALE = f32(0.85)           # posMoveFromFootPos r3 < 0 branch (:2416)


class SlopeNotModeled(NotImplementedError):
    """A ground term left the exactly-zero micro-incline tier (nonzero getGroundAngle cell /
    waist tilt / leg IK trigger). The ramp tier must be ported decomp-first before this state
    can be simmed -- see the module docstring."""


def gnd_spz(st, v):
    """posMoveFromFootPos tail for LandState's non-foot speedF branches: the Phase G slope scale
    (``sp7C.z *= cM_scos(r3); r3 < 0 -> *= 0.85``, :2414-2417) then the |z| < 0.05 snap (:2418).
    Identity scale when floors are off or r3 == 0 (flat paths byte-identical)."""
    v = f32(v)
    if st._gnd is not None:
        v = st._gnd.scale_speedf(v, st.travel)
    return 0.0 if abs(v) < 0.05 else v


# footBgCheck's r29 idle arm = the ModeFlg_00000001 procs (d_a_player_main_data.inc), and the
# r23 foot-tracking exclusion = the MIDAIR/0x8000/... flag set (:8771) among modeled procs.
GND_IDLE_STATES = frozenset((WAIT, FREE_WAIT, WAIT_TURN, SUBJECTIVITY,
                             SIDE_STEP_LAND, BACK_JUMP_LAND))
GND_R23_EXCLUDED = frozenset((FRONT_ROLL, FRONT_ROLL_CRASH, SIDE_STEP, BACK_JUMP))


def gnd_frame_end(st):
    """Phase G end-of-frame ground pass on LandState ``st``, the game's execute order
    (11552-11556): setWaistAngle (the m34E0 chase) then footBgCheck (the m35B8 foot ground-lift
    from the two delayed-foot probes) against THIS frame's fresh worldBase -- the returned m35B8
    is baked into the deferred draw base (base y += / m37B4 y -=, :8794-8796) via the foot
    engine's ``m35b8`` attribute."""
    from ..core.anim import fk as _fk
    foot = st._foot
    # setStepsOffset (:11528): walk anim modes only; WAIT freezes m35C4. May SNAP pos.y
    # up to the ahead-floor (uphill branch).
    if foot.st.m34C3 in (1, 4, 9, 10):
        st.pos_y = st._gnd.steps_offset(st.pos_x, st.pos_y, st.pos_z, st.speedF,
                                        st.travel, st._gnd.y_old)
    # setWaistAngle (:9530): target 0 in the flag-1/MIDAIR/0x8000 modes; chases toward
    # 0.7 * m34E2 * |nspeed/max| otherwise. Micro-incline tier: raises if it leaves 0.
    excluded = st.state in GND_IDLE_STATES or st.state in GND_R23_EXCLUDED
    st._gnd.update_m34e0(st.nspeed, st.max_nspeed, excluded=excluded)
    # footBgCheck (:8712): stored feet t1 + last draw's WAIST vs the fresh base, whose
    # translate y = pos.y + m35C4 (setWorldMatrix :9561; m3608 == 0 on this tier).
    waist = foot.ff.last_waist
    if waist is None:
        waist = foot.ff.waist_from_old()
        foot.ff.last_waist = waist
    base_y = fadds(f32(st.pos_y), st._gnd.m35c4)
    base, inv = _fk.world_base(st.pos_x, base_y, st.pos_z, st.facing, st._draw_lean)
    r23_excluded = (not st.ground_hit) or st.state in GND_R23_EXCLUDED
    foot.m35b8 = st._gnd.foot_bg_check(foot.t1, waist, base, inv, st.pos_y,
                                       r29_idle=st.state in GND_IDLE_STATES,
                                       r23_excluded=r23_excluded)
    # The deferred draw consumes THIS frame's field_0x030 (jointBeforeCB :276/:282) and
    # rides THIS frame's m35C4 (FootSpeedF._apply_base) -- same timing as the m35B8 bake.
    foot.ff.foot030 = (st._gnd.foot030[0], st._gnd.foot030[1])
    foot.m35c4 = st._gnd.m35c4


def _mk_tri(t):
    return Tri(t["v"][0], t["v"][1], t["v"][2],
               plane=Plane(t["n"][0], t["n"][1], t["n"][2], t["d"]))


def load_floor_mesh(path):
    """Floor tris from a ``*_floors.json`` fixture (``{polys:[{v,n,d}, ...]}``) -- the room's
    GroundCross candidate set in the game's block-grid visit order."""
    mesh = json.load(open(path))
    return [_mk_tri(t) for t in mesh["polys"]]


def ground_cross(tris, px, probe_y, pz):
    """cBgS::GroundCross over a candidate set: the MAX plane-cross y over tris that pass
    ``cM3d_CrossY_Tri_Front`` at (px, pz) with ``y < probe_y`` strictly (RwgGroundCheckCommon,
    c_bg_w.cpp:470). Returns ``(ground_h, tri_index)`` -- ``(NEG_INF, None)`` when no floor.
    Order-independent for the height; visit order breaks exact-tie poly identity like the game
    (strict ``y > now_y``: the first coplanar tri wins)."""
    px = f32(px); pz = f32(pz); probe_y = f32(probe_y)
    now_y = NEG_INF
    idx = None
    for i, t in enumerate(tris):
        y = ground_cross_y(t.pla, px, pz)
        if y < probe_y and y > now_y and cross_y_tri_front(t.v0, t.v1, t.v2, px, pz):
            now_y = y
            idx = i
    return now_y, idx


def get_ground_angle(pla, yaw):
    """daPy_lk_c::getGroundAngle (d_a_player_main.cpp:8598): the signed slope angle of the
    ground plane along heading `yaw` (s16). cBgW_CheckBGround gate (ny >= 0.5) then
    ``atan2s(|n_xz| * cos(atan2s(nx,nz) - yaw), ny)``. Table-exact: slopes under ~1/1024
    truncate to 0."""
    if pla is None or not (pla.ny >= 0.5):
        return 0
    ang = cM_atan2s(pla.nx, pla.nz)
    cos = cM_scos_s16(s16_signed((ang - yaw) & 0xFFFF))
    xz = fsqrt(fadds(fmuls(pla.nx, pla.nx), fmuls(pla.nz, pla.nz)))
    return s16_signed(cM_atan2s(fmuls(xz, cos), pla.ny))


class GroundState:
    """Per-LandState ground bookkeeping: the CrrPos ground poly + hit flag, the m35B8 foot
    ground-lift chase, the m34E0/m34E2 waist-tilt ints, and footBgCheck's per-foot probe
    hysteresis (mFootData field_0x024 anchor + field_0x001 counter).

    Seed the rest fields from the anchor's live RAM capture (m35B8, foot024, foot001); they are
    history-dependent (the probe freeze latches 5 frames after the feet last moved 10u)."""

    __slots__ = ("tris", "gnd_pla", "gnd_idx", "ground_hit", "ground_h",
                 "m35b8", "m34e0", "m34e2", "foot024", "foot001", "foot030",
                 "m35c4", "y_old")

    def __init__(self, tris, m35b8=0.0, m34e0=0, m34e2=0, foot024=None, foot001=(5, 5),
                 gnd_pla=None, ground_hit=True, m35c4=0.0):
        self.tris = tris
        self.gnd_pla = gnd_pla             # mAcch.m_gnd plane (previous CrrPos best poly)
        self.gnd_idx = None
        self.ground_hit = bool(ground_hit)
        self.ground_h = NEG_INF
        self.m35b8 = f32(m35b8)
        self.m34e0 = int(m34e0)            # waist ground-tilt chase (setWaistAngle)
        self.m34e2 = int(m34e2)            # getGroundAngle(m_gnd, shape_angle.y) (execute :11498)
        # footBgCheck probe hysteresis (field_0x024 midpoint + field_0x001 countdown);
        # None => lazy-seed from the first frame's feet (minted anchors must pass captures).
        self.foot024 = [tuple(map(f32, p)) for p in foot024] if foot024 is not None else None
        self.foot001 = list(foot001)
        # mFootData[i].field_0x030, the non-plant CLOTCH lift (:8816) -- fresh each frame,
        # never chased, no seed field. See knowledge/model/ground-model.md.
        self.foot030 = [f32(0.0), f32(0.0)]
        # m35C4, the setStepsOffset walk base-Y lift (:9524): ~0.7*|dy| at cruise, 0.0 on
        # flat, FROZEN during WAIT -> seeded (rest_m35C4). See knowledge/model/ground-model.md.
        self.m35c4 = f32(m35c4)
        self.y_old = None                  # old.pos.y (start-of-frame), set per step by LandState

    def clone(self):
        c = GroundState.__new__(GroundState)
        c.tris = self.tris
        c.gnd_pla = self.gnd_pla
        c.gnd_idx = self.gnd_idx
        c.ground_hit = self.ground_hit
        c.ground_h = self.ground_h
        c.m35b8 = self.m35b8
        c.m34e0 = self.m34e0
        c.m34e2 = self.m34e2
        c.foot024 = list(self.foot024) if self.foot024 is not None else None
        c.foot001 = list(self.foot001)
        c.foot030 = list(self.foot030)
        c.m35c4 = self.m35c4
        c.y_old = self.y_old
        return c

    # ---------------------------------------------------------------- setStepsOffset (m35C4)
    def steps_offset(self, px, py, pz, speedF, travel, y_old):
        """daPy_lk_c::setStepsOffset (:9524, called at :11528 when m34C3 in (1,4,9,10)): the
        walk-step base-Y lift. Chases m35C4 to 0 (cLib_addCalc min step 5.0 == exact 0 at walk
        magnitudes), probes the floor ONE speedF ahead of pos, then (a) ahead-floor HIGHER:
        SNAPS current.pos.y up to it and m35C4 -= 0.7*rise; (b) else: m35C4 += 0.7*(this
        frame's y drop, old.pos.y - pos.y) when >= 0. setWorldMatrix builds the draw base at
        pos.y + m35C4 + m3608 (m3608 == 0 here), so the drawn pose AND footBgCheck's
        r30[1][3] ride m35C4 above pos.y -- the missing term behind the s66 GanonA foot030
        residual (0.7 * one frame's dy, ~4.9e-3 at cruise). The m34E2 tan terms are exactly
        +-0.0 on the zero-atan tier, and x - (+-0.0) == x in f32, so they are dropped.
        Returns the (possibly snapped) pos.y."""
        self.m35c4 = cLib_addCalc(self.m35c4, f32(0.0), f32(0.5), f32(25.0), f32(5.0))
        if self.m34e2 != 0:
            raise SlopeNotModeled("setStepsOffset with m34E2 != 0 -- ramp tier not ported")
        probe_x = fadds(f32(px), fmuls(f32(speedF), cM_ssin_s16(travel)))
        probe_z = fadds(f32(pz), fmuls(f32(speedF), cM_scos_s16(travel)))
        probe_y = fadds(f32(py), FOOT_PROBE_UP)
        d5, _ = ground_cross(self.tris, probe_x, probe_y, probe_z)
        fv = fsubs(d5, f32(py)) if d5 != NEG_INF else NEG_INF
        if fv > 0.0:
            py = d5                                      # current.pos.y = dVar5 (:9545)
            self.m35c4 = fsubs(self.m35c4, fmuls(fv, f32(0.7)))
        else:
            fv = fsubs(f32(y_old), f32(py))              # (old.pos - current.pos).y (:9548)
            if fv >= 0.0:
                self.m35c4 = fadds(self.m35c4, fmuls(fv, f32(0.7)))
        return py

    # ---------------------------------------------------------------- speedF slope scale
    def speedf_r3(self, travel, gcode_8=False):
        """posMoveFromFootPos:2408-2413: r3 for THIS frame's speedF scale -- the PREVIOUS
        frame's CrrPos ground poly at THIS frame's current.angle.y. 0 when airborne / no poly /
        ground code 8."""
        if not self.ground_hit or self.gnd_pla is None or gcode_8:
            return 0
        return get_ground_angle(self.gnd_pla, int(travel) & 0xFFFF)

    def scale_speedf(self, spz, travel):
        """Apply ``sp7C.z *= cM_scos(r3); if (r3 < 0) sp7C.z *= 0.85`` (:2414-2417). Called on
        the pre-snap speedF (the |z| < 0.05 snap runs after, in the caller). Bit-exact no-op at
        r3 == 0 (skip == fmuls by 1.0)."""
        r3 = self.speedf_r3(travel)
        if r3 == 0:
            return spz
        spz = fmuls(spz, cM_scos_s16(r3))
        if r3 < 0:
            spz = fmuls(spz, UPHILL_SCALE)
        return spz

    # ---------------------------------------------------------------- CrrPos ground half
    def crrpos_ground(self, px, py, pz):
        """dBgS_Acch GroundCheck (d_bg_s_acch.cpp:122-153) after the wall pass: probe at
        ``py + 60``, snap iff ``ground_h > py``. Returns (new_py, new_speed_y_or_None):
        speed_y is zeroed only on a snap. Updates gnd poly / ground_hit / ground_h."""
        probe_y = fadds(f32(py), GND_CHECK_OFFSET)
        h, idx = ground_cross(self.tris, px, probe_y, pz)
        self.ground_h = h
        if h != NEG_INF:
            self.gnd_idx = idx
            self.gnd_pla = self.tris[idx].pla
            if h > py:                      # field_0xb8 > field_0xb4: snap + kill speed.y
                self.ground_hit = True
                return f32(h), 0.0
        self.ground_hit = False
        return f32(py), None

    # ---------------------------------------------------------------- end-of-frame ground ints
    def update_m34e2(self, facing):
        """execute :11455/:11493-11499: m34E2 = getGroundAngle(m_gnd, shape_angle.y) when a
        ground height was found this frame (GetGroundH() != -INF), else 0."""
        if self.ground_h != NEG_INF and self.gnd_pla is not None:
            self.m34e2 = get_ground_angle(self.gnd_pla, int(facing) & 0xFFFF)
        else:
            self.m34e2 = 0

    def update_m34e0(self, nspeed, max_nspeed, excluded=False, gcode_8=False):
        """setWaistAngle (:9530, called right after setWorldMatrix): chase m34E0 toward
        ``0.7 * m34E2 * clamp(|nspeed/max|, 1)`` (0 in the excluded modes / ground code 8) with
        addCalcAngleS(2, 0x800, 0x200)."""
        if excluded or gcode_8:
            target = 0
        else:
            f1 = f32(abs(f32(nspeed)) / f32(max_nspeed))
            if f1 > 1.0:
                f1 = f32(1.0)
            # (s16)(0.7f * m34E2 * fVar1): two f32 products then C truncation toward zero.
            target = int(fmuls(fmuls(f32(0.7), f32(float(self.m34e2))), f1))
        self.m34e0 = s16_signed(cLib_addCalcAngleS(self.m34e0 & 0xFFFF, target & 0xFFFF,
                                                   2, 0x800, 0x200))
        if self.m34e0 != 0:
            raise SlopeNotModeled("m34E0 waist tilt engaged (%d) -- ramp tier not ported"
                                  % self.m34e0)

    # ---------------------------------------------------------------- footBgCheck (m35B8)
    def foot_bg_check(self, t1, waist, base, inv, py, r29_idle, r23_excluded, roll_like=False):
        """daPy_lk_c::footBgCheck (:8712-8855), micro-incline tier: update m35B8 from the two
        delayed-foot ground probes. Returns m35B8 (the caller bakes it into the draw base y and
        the m37B4 y row).

        t1     = the foot stream's last-drawn flat 12-tuple [Rtoe, Ltoe, Rheel, Lheel] xyz
                 (model-local == mFootData field_0x018/0x00C stored by this frame's
                 posMoveFromFootPos).
        waist  = last draw's WAIST joint WORLD translate (x, y, z) (getAnmMtx(WAIST) col 3).
        base   = THIS frame's fresh worldBase (pre-m35B8), inv = its fresh PSMTXInverse.
        py     = current.pos.y (post-CrrPos).
        r29_idle = checkModeFlg(ModeFlg_00000001) (WAIT family): arms the 10u/5-frame probe
                 freeze.
        r23_excluded = ChkGroundHit()==0 or an excluded mode flag (MIDAIR/0x8000/SWIM/...):
                 m35B8 chases 0 (the FRONT_ROLL / crash / hop case).
        """
        # r31 = concat(m37B4_fresh, anmMtx(WAIST)) rows [1] and [2], translate column only
        # (mtx_concat: ab[i][3] = fadds(fmadds(a_i2, b_23, fmadds(a_i1, b_13, fmuls(a_i0, b_03))), a_i3)).
        wx, wy, wz = waist
        r31y = fadds(fmadds(inv[1][2], wz, fmadds(inv[1][1], wy, fmuls(inv[1][0], wx))), inv[1][3])
        r31z = fadds(fmadds(inv[2][2], wz, fmadds(inv[2][1], wy, fmuls(inv[2][0], wx))), inv[2][3])
        # f28/f27 = sin/cos(m34E0) (:8725). Micro-incline tier: m34E0 == 0 -> 0.0 / 1.0 exact.
        if self.m34e0 != 0:
            raise SlopeNotModeled("footBgCheck with m34E0 != 0 -- ramp tier not ported")
        sp18 = [0.0, 0.0]
        found = [0, 0]
        if self.foot024 is None:
            # Lazy seed: fresh probes this frame (exact for a never-frozen entry; minted rest
            # anchors must pass the captured values instead).
            self.foot024 = [None, None]
        for i in range(2):                  # 0 = right foot (toe idx 0, heel idx 6), 1 = left
            o = i * 3
            sp74 = (fmuls(fadds(t1[o + 0], t1[o + 6 + 0]), 0.5),
                    fmuls(fadds(t1[o + 1], t1[o + 6 + 1]), 0.5),
                    fmuls(fadds(t1[o + 2], t1[o + 6 + 2]), 0.5))
            prev = self.foot024[i]
            if prev is not None:
                # sp50.abs2XZ() < 10^2 (:8736): cXyz abs2XZ = fmadds(dz, dz, fmuls(dx, dx)).
                dx = fsubs(sp74[0], prev[0]); dz = fsubs(sp74[2], prev[2])
                near = fmadds(dz, dz, fmuls(dx, dx)) < 100.0
            else:
                near = False
            if near and r29_idle:
                if self.foot001[i] != 0:
                    self.foot001[i] -= 1
                else:
                    sp74 = prev             # frozen probe point
            else:
                self.foot001[i] = 5
            self.foot024[i] = sp74
            # f26 (:8746): r31y + cos(m34E0)*(sp74.y - r31y) + sin(m34E0)*(sp74.z - r31z);
            # zero-tilt tier: fmadds(1.0, x, y)==fadds(x, y) and the sin term is exactly +0.
            f26 = fadds(r31y, fsubs(sp74[1], r31y))
            # world probe point: sp68 = mDoMtx_multVec(base_fresh, sp74) (:8747, PSMTXMultVec
            # ps_sum0 grouping); the probe y comes from pos.y (:8748), only world x/z are used.
            sp68 = mtx_mult_vec(base, sp74)
            sp68x, sp68z = sp68[0], sp68[2]
            probe_y = fadds(f32(py), FOOT_PROBE_UP)
            f1, idx = ground_cross(self.tris, sp68x, probe_y, sp68z)
            if f1 != NEG_INF and fsubs(probe_y, f1) < FOOT_GND_RANGE:
                sp18[i] = f1
                found[i] = 1
                # the per-foot ground angles (field_0x002/0x004 chase targets, :8846-8853)
                # must stay in the zero cell on this tier.
                pla = self.tris[idx].pla
                if get_ground_angle(pla, 0) != 0 or get_ground_angle(pla, 0x4000) != 0:
                    raise SlopeNotModeled("foot ground poly leaves the zero atan cell")
            else:
                sp18[i] = f32(py)
                found[i] = 0
            sp18[i] = fsubs(sp18[i], fsubs(sp74[1], f26))
        # r23 (:8770-8782) + the f1 target (:8783-8793).
        if r23_excluded:
            f1t = f32(0.0)
        else:
            f1t = fsubs(sp18[1] if sp18[0] > sp18[1] else sp18[0], f32(py))
        self.m35b8 = cLib_addCalc(self.m35b8, f1t, f32(0.5), f32(7.5), f32(2.5))
        # The per-foot CLOTCH lift + leg IK block (:8794-8825): leg ANGLES stay 0 on this
        # tier (guarded), the field_0x030 lift is UNGATED. See knowledge/model/ground-model.md.
        if r23_excluded:
            self.foot030[0] = f32(0.0)
            self.foot030[1] = f32(0.0)
        else:
            plant = 1 if sp18[0] > sp18[1] else 0     # r23: the LOWER foot
            other = 1 - plant                          # r28
            # r30[1][3] after += m35B8 (:8795): the base TRANSLATE y (pos.y + m35C4), not
            # raw pos.y.
            base_y = fadds(base[1][3], self.m35b8)
            if abs(fsubs(sp18[plant], base_y)) >= 0.1:
                raise SlopeNotModeled("setLegAngle would engage on the plant foot (drop %.4f)"
                                      % fsubs(sp18[plant], base_y))
            self.foot030[plant] = f32(0.0)
            f1 = fsubs(sp18[other], base_y)
            if f1 > 0.0 or r29_idle:
                # :8816, ungated -- only the leg ANGLES have the setLegAngle 0.1 early-return
                self.foot030[other] = fmuls(f32(0.3), f1)
                if abs(fmuls(f32(0.7), f1)) >= 0.1:
                    raise SlopeNotModeled("setLegAngle would engage on the free foot "
                                          "(0.7*f1 %.4f)" % fmuls(f32(0.7), f1))
            else:
                self.foot030[other] = f32(0.0)
        return self.m35b8
