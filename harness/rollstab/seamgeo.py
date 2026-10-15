"""SeamGeo: a per-seam roll/wall-clip geometry + acceptance object, DERIVED from a corner
geometry fixture + the anchor camera yaw (csangle).

This generalizes the STANDARD bare roll-stab clip (formerly the kaze-hardcoded
`harness.rollstab.geometry`) to ANY enumerated seam. The two things that used to be pasted
by-inspection literals -- the roll facing `F` and the cut lunge -- are now COMPUTED from the seam:

  * F      = the thrust facing == the closest-reachable full-deflection stick decode to the seam's
             AIM direction at this camera yaw. `stick_for_bearing(aim, csangle, 1.0)` inverts the
             walk want-target (m34E8) to a byte stick, but the octagon clamp + byte quantization mean
             the reachable decode is the CLOSEST, not the exact, aim -- so F is that reachable
             want-target (the relationship documented in cornergate.py:10-11, now coded here).
             The AIM direction is per-seam: a CORNER seam (roll) aims INTO the corner along the
             interior bisector (the fixture's `bisector_deg`, the default); a NEARLY-FLAT seam
             (walk-stab, interior ~169 deg) is clipped by GRAZING toward the seam vertex S, so its aim
             is the bearing from the approach start to S (`bear_to_S`), passed as `aim_deg=`. Both go
             through the same derive_F stick-settle; only the source direction differs.
  * cut_new(old) = the CUT_F entry endpoint out of a full-cap roll (speedF `ROLL_SPEEDF`): the ANM_CUT
             joint-0 root translate (m3700 @ frame 4.0, facing-rotated) + the speedF lunge term,
             bit-identical to `LandState.enter_cut` / `walkstab.fast_cut` (verified 0-ULP). No frozen
             per-`old` delta: the endpoint is computed exactly at each candidate, so there is no magic
             extraction point to reproduce ([[no-overtuned-constants]]).

NOT for the Tetra push clip. That corner is a NEEDS-PUSH clip whose acceptance endpoint is the
COUPLED `new = f32(old + push + lunge)` and whose F is target-defined (`world_angle(new-old)`), not
a bisector decode. It is a standalone, single-seam solver (`geometry_tetra.py` / `solver_tetra.py` /
`pushaside.py` / `turnaround.py`) and stays separate.

A seam's geo fixture (reproducibly built by `capture_walls.py` / `make_tetra_geo.py`) supplies:
  wallA, wallB  -- the two incident wall tris (`plane.func(p) > 0` == in front)
  barrier       -- the full CrrPos barrier tri set, in the game's block-grid order
  S             -- the seam vertex [x, y, z]
  bisector_deg  -- the interior bisector world bearing (degrees)
  link_y        -- Link's world Y on the walkable floor at the corner
plus the anchor camera yaw `csangle`. The acceptance tests are exact f32 candidate tests, never a
fitted ribbon ([[knowledge/strategy/seam-clip-solver]]).
"""
import os, sys, math
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.collision import Tri, Plane, crr_pos_walls
from tww_sim.core.fp import f32 as _f
import tww_sim.core.mathlib as M
from tww_sim.core.mathlib import deg_to_s16, main_stick_decode
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.land.procs.cut import _cM_ssin_s16

A_BTN, B_BTN = 0x100, 0x200
KROLL = 15                     # aim frames between the A roll init and the single B edge
ROLL_SPEEDF = 26.0             # the full-cap roll's peak speedF carried into the CUT_F lunge
                               # (capped walk 17 -> roll 26; KB mechanics/roll-stab.md). NOT per-seam.

# General search-window bracket = fractions of the derived lunge reach -- seam-INDEPENDENT, NOT
# per-case distances (the same rule for every seam); rationale in SeamGeo.search_band. [[no-overtuned-constants]]
BAND_LO_FRAC, BAND_HI_FRAC = 0.80, 1.02


def _mk(t):
    return Tri(t["v"][0], t["v"][1], t["v"][2],
               plane=Plane(t["n"][0], t["n"][1], t["n"][2], t["d"]))


_CUT_L0 = None


def _cut_root_translate():
    """The CUT_F joint-0 (root) mTranslate at CUT_START (4.0) -- a CONSTANT (m3700_prev==0 in
    _cut_init, m34C2==1), facing-INDEPENDENT. Cached once so a fresh SeamGeo never re-evals the
    J3D tree. (Same value walkstab.cut_lunge_const caches.)"""
    global _CUT_L0
    if _CUT_L0 is None:
        from tww_sim.land.land import LandState
        from tww_sim.land.constants import CUT_F
        s = LandState(native=False)
        _CUT_L0 = s._cut_m3700_at(CUT_F, s.CUT_START)
    return _CUT_L0


def derive_F(aim_deg, csangle):
    """The thrust facing for a seam: the walk want-target (m34E8) of the closest-reachable
    full-deflection stick to the seam's AIM direction at this camera yaw. `stick_for_bearing` inverts
    m34E8 -> a byte stick (clamp-aware); decoding it back and re-adding csangle gives the reachable
    want-target, which the octagon/quantization pin near, not on, the aim. `aim_deg` is the interior
    bisector for a corner seam, or the bearing-to-S for a nearly-flat seam (see the module docstring)."""
    aim = deg_to_s16(float(aim_deg) % 360.0)
    stk = stick_for_bearing(aim, int(csangle) & 0xFFFF, 1.0)
    ang, _m = main_stick_decode(*stk)
    return (ang + 0x8000 + (int(csangle) & 0xFFFF)) & 0xFFFF


class SeamGeo:
    """Geometry + exact clip acceptance for one standard roll/wall seam (see module docstring)."""

    A_BTN, B_BTN, KROLL, ROLL_SPEEDF = A_BTN, B_BTN, KROLL, ROLL_SPEEDF

    def __init__(self, geo, csangle, roll_speedf=ROLL_SPEEDF, aim_deg=None):
        self.geo = geo
        self.csangle = int(csangle) & 0xFFFF
        self.roll_speedf = roll_speedf
        self.wA, self.wB = _mk(geo["wallA"]), _mk(geo["wallB"])
        self.BARRIER = [_mk(t) for t in geo["barrier"]]
        # The CrrPos barrier the r=35 cylinder sweeps: the fixture's explicit `tris` (game block-grid
        # order) when present, else the legacy [wA,wA,wB]+barrier composition (byte-identical for roll).
        self.TRIS = ([_mk(t) for t in geo["tris"]] if "tris" in geo
                     else [self.wA, self.wA, self.wB] + self.BARRIER)
        self.LINK_Y = geo["link_y"]
        self.S = (geo["S"][0], geo["S"][2])
        # aim_deg: per-seam thrust direction. Explicit arg wins; else the fixture may DECLARE its
        # clippable aim (`"aim_deg"`, e.g. the 97-deg corner's ~90 grazing aim); else the interior bisector.
        self.aim_deg = aim_deg if aim_deg is not None else geo.get("aim_deg", geo["bisector_deg"])
        self.F = derive_F(self.aim_deg, self.csangle)
        _r = self.F / 65536.0 * 2 * math.pi
        self.DIRX, self.DIRZ = math.sin(_r), math.cos(_r)
        self.PX, self.PZ = -self.DIRZ, self.DIRX      # perp(F) axis (plan_search convention)

    # --- exact acceptance -----------------------------------------------------------------
    def p32(self, x, z):
        return (_f(x), self.LINK_Y, _f(z))

    def in_front(self, p):
        return self.wA.pla.func(p) > 0 and self.wB.pla.func(p) > 0

    def seg_blocked(self, a, b):
        _, info = crr_pos_walls(self.p32(a[0], a[1]), self.p32(b[0], b[1]), self.TRIS)
        return info["line_hit"] or info["wall_hit"]

    def genuine_clip(self, old, new):
        po, pn = self.p32(old[0], old[1]), self.p32(new[0], new[1])
        if not self.in_front(po):
            return False
        if not (self.wA.pla.func(pn) < 0 or self.wB.pla.func(pn) < 0):
            return False
        _, info = crr_pos_walls(po, pn, self.TRIS)
        return not (info["line_hit"] or info["wall_hit"])

    def cut_new(self, old, facing=None, speedf=None, travel=None):
        """The CUT_F entry endpoint from `old` -- bit-identical to `LandState.enter_cut(CUT_F,
        aim=None)`: the speedF foot term fired along `travel` (current.angle.y as CARRIED into the
        dispatch; procCutF_init never writes it) + the root translate rotated by `facing` (shape); the
        two component f32 adds, per candidate. `facing`/`speedf` default to the seam's thrust facing F
        + `roll_speedf` (the roll-stab out-of-a-roll cut, where travel==facing); a walk-stab cut passes
        the runtime walk `facing`, per-frame `nspeed`, AND the dispatch-frame `travel` (the walk's
        travel AFTER that frame's setSpeedAndAngleNormal chase -- see LandState.enter_cut_from_move;
        omitting it assumes travel==facing, which is ~0.03u off at a 100-hw residue: session 75)."""
        fac = self.F if facing is None else facing
        trv = fac if travel is None else travel
        sp = self.roll_speedf if speedf is None else speedf
        L0 = _cut_root_translate()
        speedF = 0.0 if abs(sp) < 0.05 else sp
        s = _cM_ssin_s16(fac)
        c = M.cM_scos_s16(fac)
        st = s if trv == fac else _cM_ssin_s16(trv)
        ct = c if trv == fac else M.cM_scos_s16(trv)
        add_x = _f(_f(L0[2] * s) + _f(L0[0] * c))
        add_z = _f(_f(L0[2] * c) - _f(L0[0] * s))
        nx = _f(_f(_f(old[0]) + _f(speedF * st)) + add_x)
        nz = _f(_f(_f(old[1]) + _f(speedF * ct)) + add_z)
        return (nx, nz)

    def pred_genuine(self, old, facing=None, speedf=None, travel=None):
        """genuine_clip against the REAL cut endpoint at `old` (bit-identical to the sim's cut
        `new`) -- the pure-geometry dust test used by maps/rankers. Args as `cut_new`."""
        return self.genuine_clip(old, self.cut_new(old, facing, speedf, travel))

    def perp(self, p):
        return (p[0] - self.S[0]) * self.PX + (p[1] - self.S[1]) * self.PZ

    def along(self, p):
        return (p[0] - self.S[0]) * self.DIRX + (p[1] - self.S[1]) * self.DIRZ

    def perp_to_ray(self, old, new):
        """Signed perpendicular distance from S to the ACTUAL cut ray old->new (table-exact geometry).
        ~0 for a clip -- the razor quantity a nearly-flat seam threads (walk-stab's `perp_ray`). Unlike
        `perp(p)` (a point's offset along the fixed F-perp axis), this measures the real fired ray, so
        it is exact regardless of any facing quantization between the walk facing and F."""
        dx, dz = new[0] - old[0], new[1] - old[1]
        L = math.hypot(dx, dz) or 1.0
        return ((self.S[0] - old[0]) * dz - (self.S[1] - old[1]) * dx) / L

    @property
    def LUNGE(self):
        """The cut lunge as an origin-referenced (dx, dz) -- a pure function of (F, ROLL_SPEEDF),
        for the roll-stab reach magnitude (~49.2202u). Informational: acceptance uses `cut_new(old)`
        per candidate, so no consumer depends on this being evaluated at a particular `old`."""
        return self.cut_new((0.0, 0.0))

    # --- derived reachable band (Phase-5 generalization: no per-seam hardcoded ranges) ----
    def reach_at(self, speedf=None):
        """The CUT_F lunge DISPLACEMENT magnitude at `speedf` (default the roll cap `roll_speedf`).
        This is the FAR edge of the reachable clip band: `old` must sit within a lunge-length of the
        seam for `new` to cross it. Fully DERIVED from the cut model (`cut_new`), no pasted distance --
        the roll uses the fixed roll cap; a walk-stab passes its capped walk speedF (17)."""
        nx, nz = self.cut_new((0.0, 0.0), speedf=speedf)
        return math.hypot(nx, nz)

    @property
    def reach(self):
        """The roll-stab lunge reach (|LUNGE|, at `roll_speedf`)."""
        return self.reach_at()

    def search_band(self, speedf=None, lo_frac=BAND_LO_FRAC, hi_frac=BAND_HI_FRAC):
        """The distance-to-S window to FOCUS the search on (NOT the reachability guard -- that is the
        walled physics re-sim in the solvers). A general relative bracket around the derived lunge
        reach: `[reach*lo_frac, reach*hi_frac]`. Same rule for every seam; the fractions are
        seam-independent ([[no-overtuned-constants]]). `speedf` picks the reach (roll cap by default,
        the walk cap 17 for a walk-stab). Returns (d2S_lo, d2S_hi)."""
        R = self.reach_at(speedf)
        return (R * lo_frac, R * hi_frac)

    def d2S(self, p):
        """Straight-line distance from `p=(x,z)` to the seam vertex S."""
        return math.hypot(p[0] - self.S[0], p[1] - self.S[1])

    def wall_clearance(self, x, z):
        """XZ distance from (x,z) to the NEARER incident seam wall (edge distance of the wallA/wallB
        tris). A walk-reachable `old` needs clearance > Link's ~35u WallCorrect radius, else the
        approach walk brakes on the wall (the wall-faithful reject). Shared so the feasibility
        detector can report WALK-reachable dust, not just geometrically-genuine dust
        ([[oneshot-no-manual-tweaking]] -- reuse the detector, don't re-derive clearance per caller)."""
        from harness.collision.seam_scan import _tri_xz_edge_dist
        va = [tuple(v) for v in self.geo["wallA"]["v"]]
        vb = [tuple(v) for v in self.geo["wallB"]["v"]]
        return min(_tri_xz_edge_dist(va, x, z), _tri_xz_edge_dist(vb, x, z))

    # --- reachability (is a WallCorrect-standable old able to clip this seam?) ------------
    def roll_reachable(self):
        """Is there a WallCorrect-STANDABLE `old` whose clip threads this seam -- i.e. is the seam
        reachable by a free roll, not just geometrically clippable? Defers DIRECTLY to the shipped
        analytic locator's geometry-first core (`seam_locator.locate_geo`) on THIS seam's own walls +
        barrier + flat floor (`LINK_Y`) -- it settles a real standable old and f32-verifies the clip
        from it, so a seam whose only genuine dust hugs a wall (inside Link's ~35u WallCorrect hold)
        yields no standable clip and is correctly rejected. Returns the locator clip dict
        (`old`/`new`/`disp`/`interior`/`floor`, full f32) or None (== not roll-reachable).

        This is the ACCURATE reachability screen. It replaces the old proxies -- the disp-floor tier
        (`floor <= 49.22`, which the 97-deg corner PASSED) and a nearest-wall distance heuristic (which
        false-NEGATED the proven kaze seam, whose reachable old is deep but close to ONE wall).
        LIVE-VALIDATED (session 53): None for the 97-deg corner (its roll is held 35u off wallA,
        bit-exact vs live) and a clip for the proven + mirror seams (both roll-delivered). NOTE the
        locator `disp` is a DEEP-first upper bound: a non-None result proves a standable clip EXISTS;
        for the precise roll-stab reach, confirm `pred_genuine` at a `search_band` old."""
        from harness.collision.seam_locator import locate_geo
        return locate_geo(self.BARRIER, [], self.S, self.wA, self.wB,
                          override_link_y=self.LINK_Y, require_standable=False)
