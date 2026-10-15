#!/usr/bin/env python3
"""tww_sim/swim/arrow.py - arrow-swim 2-D front-end + facing BFS (live-validated 2026-06-27).

Split out of ``sim.py``; NOT on the ``SwimState`` bit-exact path. Models the 2-D arrow/charge
stepper (``ArrowState``/``run_arrow``) and the turnaround-snap reorient search (``reorient_chain``).
Re-exported through ``sim`` so ``from tww_sim.swim import sim as S`` callers keep ``S.ArrowState``,
``S.run_arrow``, ``S.reorient_chain``, ``S.arrow_sticks``, ``S.arrow_charge_rate`` working.

The model (decomp setSpeedAndAngleSwim, d_a_player_swim.inc:41 + slot-9 capture, capture_arrow.py):
  stickAngle = atan2(sx-128, -(sy-128))            # 0=down, 90=right, 180=up, 270=left
  m34E8 (world stick target) = stickAngle + 180 + camAngle
  SNAP: |angdiff(m34E8, facing)| > 135 (0x6000) -> facing := m34E8 (instant turnaround)
        else gradual cLib turn toward m34E8 at ~ARROW_TURN_RATE deg/frame
  speed delta (potential) = mStickDistance * 3 * cos(facing_after - facing_before)
  world move bearing = camAngle - facing;  displacement = CHARGE_DISP_FACTOR * |true_disp|
  BOTH the facing change and the speed delta LAG one frame (input[f-1] -> facing[f]).
Superswim alternates the stick fully back/forth; tilting that axis by alpha toward the target
rotates facing (180-2*alpha) deg/frame instead of 180, so at full-Y deflection (dist~1):
  charge_rate(alpha) = -3*dist*cos(2*alpha)   (alpha=0 -> -3 pure back)
  cross_drift(alpha) = disp*sin(alpha)/frame toward target (ACCUMULATES)
  along_move(alpha)  = disp*cos(alpha), sign ALTERNATES (net ~cancels, like charge)
Usable alpha in [0,~20deg]; past ~xbias 190 the backward-snap dies (tip-over -> forward release).
Live match (v=-300 slate): alpha 0/8/18 deg -> rate -3.00/-2.88/-2.44 (vs -3cos2a); dz/|move| =
sin(alpha) confirmed. Frame-exact vs the slot-9 capture (rotation 90->305->164->0, west drift).
"""
import math
from ..core.mathlib import (
    nfmod, angdiff_deg, _deadzone, stick_angle_deg, ARROW_STICK_DEADZONE,
)
from .sim import incr, true_disp, CHARGE_DISP_FACTOR, ARROW_TURN_RATE


def arrow_charge_rate(alpha_deg, dist=1.0):
    return -3.0 * dist * math.cos(2.0 * math.radians(alpha_deg))

def arrow_cross_drift(v, anim, air, alpha_deg, factor=CHARGE_DISP_FACTOR):
    """Per-frame cross-track displacement toward the target (magnitude)."""
    return factor * abs(true_disp(v, anim, air)) * math.sin(math.radians(alpha_deg))

# Tip-over guard: beyond this tilt the backward-snap dies and charging stops paying.
ARROW_ALPHA_MAX_DEG = 20.0
# Arrow-phase SPIN-UP: the first ~2 alternation frames are non-snap FORWARD frames that LOSE ~+3/fr
# until the 0<->180 swing establishes (live slot-9 f5-f6; spotcheck_frontend). Planner must charge it.
ARROW_SPINUP_FRAMES = 2

ARROW_SNAP_DEG = 135.0      # 0x6000 backward-snap cone half-not: |Δ|>135 snaps (ARROW_TURN_RATE in sim)

def stick_dist(sx, sy, gate=128.0 - ARROW_STICK_DEADZONE):
    """Normalized (dead-zoned) stick magnitude, clamped to 1 (full deflection). The
    clamp is CORRECT for the charge gain: a fixed-alpha live test (fixed_alpha.py)
    found the snap charge is exactly 3*cos(180-2*alpha) with an implied stick distance
    of 1.0000 at alpha=0/10/20 -- the game caps mStickDistance at the gate, so tilt
    changes the COS (snap angle 180-2*alpha), not the magnitude."""
    return min(math.hypot(_deadzone(sx), _deadzone(sy)) / gate, 1.0)

def m34e8_deg(sx, sy, cam_deg):
    sa = stick_angle_deg(sx, sy)
    if sa is None:
        return None
    return (sa + 180.0 + cam_deg) % 360.0

class ArrowState:
    """2-D arrow/charge front-end stepper. Tracks facing (deg), world x/z, and the
    charge speed. Mirrors SwimState's 1-frame-lag discipline for the facing snap and
    the charge gain. Reuses true_disp() for the per-frame displacement magnitude.

    cam_deg = camera (csangle) in degrees; slates 9/10 use 270 (west). facing_deg
    default 90 (east) = the slot-9/10 start. Step takes a raw (sx, sy) stick."""
    def __init__(self, v=-300.0, anim=0.0, air=900, facing_deg=90.0, cam_deg=270.0):
        self.v = float(v)
        self.anim = float(anim)
        self.air = int(air)
        self.facing = float(facing_deg) % 360.0
        self.cam = float(cam_deg) % 360.0
        self.x = 0.0
        self.z = 0.0
        self._pending_facing = None   # facing snaps/turns land next frame
        self._pending_gain = None     # speed delta lands next frame (replaces decay)

    def clone(self):
        s = ArrowState.__new__(ArrowState)
        s.__dict__.update(self.__dict__)
        return s

    def move_bearing(self):
        return (self.cam - self.facing) % 360.0

    def step(self, sx, sy):
        """Advance one frame with raw stick (sx, sy). Returns (dx, dz, tag)."""
        # apply the lagged facing change + speed delta scheduled last frame
        if self._pending_facing is not None:
            self.facing = self._pending_facing % 360.0
            self._pending_facing = None
        v_pre = self.v                         # pre-update v: the anim RATE lags 1 frame
        if self._pending_gain is not None:     # (matches SwimState._advance_anim_55 and
            self.v += self._pending_gain       #  the real game) -> use v_pre for incr below,
            self._pending_gain = None          #  not the post-gain v (else anim drifts
        # decide this frame's facing change + speed delta from the stick (land next frame)
        m = m34e8_deg(sx, sy, self.cam)
        dist = stick_dist(sx, sy)
        if m is None:                          # neutral stick: coast, no turn/charge
            d_turn = 0.0
            tag = 'COAST'
        else:
            d = angdiff_deg(m, self.facing)
            if abs(d) > ARROW_SNAP_DEG:        # instant turnaround snap
                d_turn = d
                self._pending_facing = self.facing + d
                tag = 'SNAP'
            else:                              # gradual turn (no snap) -> forward/tip-over
                d_turn = max(-ARROW_TURN_RATE, min(ARROW_TURN_RATE, d))
                self._pending_facing = self.facing + d_turn
                tag = 'TURN'
            self._pending_gain = dist * 3.0 * math.cos(math.radians(d_turn))
        # Advance anim BEFORE displacement, like SwimState (state 55): rate lags 1 frame (v_pre) but
        # disp samples THIS frame's ADVANCED anim -- live-pinned (pre-advance over-predicted ~20%).
        self.anim = nfmod(self.anim + incr(v_pre, self.air), 23.0)   # pre-update v (lag)
        # move this frame along the CURRENT facing (the snap/gain land next frame)
        mag = CHARGE_DISP_FACTOR * abs(true_disp(self.v, self.anim, self.air))
        brg = math.radians(self.move_bearing())
        dx, dz = mag * math.cos(brg), mag * math.sin(brg)
        self.x += dx
        self.z += dz
        self.air -= 1
        return dx, dz, tag

def run_arrow(sticks, v=-300.0, anim=0.0, air=900, facing_deg=90.0, cam_deg=270.0):
    """sticks: iterable of (sx, sy). Returns per-frame rows (facing, x/z, v, bearing)."""
    s = ArrowState(v=v, anim=anim, air=air, facing_deg=facing_deg, cam_deg=cam_deg)
    rows = []
    x0, z0 = s.x, s.z
    for i, (sx, sy) in enumerate(sticks):
        dx, dz, tag = s.step(sx, sy)
        net = math.hypot(s.x - x0, s.z - z0)
        nb = math.degrees(math.atan2(s.z - z0, s.x - x0)) % 360.0 if net else 0.0
        mb = math.degrees(math.atan2(dz, dx)) % 360.0 if (dx or dz) else 0.0
        rows.append({"f": i + 1, "stick": (sx, sy), "facing": s.facing, "v": s.v,
                     "anim": s.anim, "air": s.air, "x": s.x, "z": s.z, "dx": dx,
                     "dz": dz, "tag": tag, "move_brg": mb, "net": net, "net_brg": nb})
    return rows

# Facing BFS: nodes = facing (bucketed FACING_GATE deg); edges = full-deflection sticks that SNAP
# (|angdiff|>135) to m34E8. Rotates facing onto the N-S/E-W axis whose alternation drifts to target.
FACING_GATE = 15.0          # facing-graph resolution (deg per node)

def stick_for_m34e8(target_deg, cam_deg=270.0, R=127.0):
    """Inverse of m34e8_deg: a full-deflection (sx, sy) whose world stick target is
    ~target_deg. stickAngle = target - 180 - cam; ax=R*sin, -ay=R*cos."""
    sa = math.radians((target_deg - 180.0 - cam_deg) % 360.0)
    sx = int(round(128.0 + R * math.sin(sa)))
    sy = int(round(128.0 - R * math.cos(sa)))
    return (max(0, min(255, sx)), max(0, min(255, sy)))

def snap_deltas(chain, facing_start, cam_deg=270.0):
    """Replay a reorient chain's facings and return the per-snap Δfacing (deg).
    Each snap sets facing := m34E8, so the charge it pays is 3·dist·cos(Δfacing)
    (decomp). Lets the planner price reorient speed-build exactly instead of assuming
    a full -3/frame. Non-snapping steps (shouldn't occur in a BFS chain) give 0."""
    f = facing_start % 360.0
    out = []
    for (sx, sy) in chain:
        m = m34e8_deg(sx, sy, cam_deg)
        if m is None or abs(angdiff_deg(m, f)) <= ARROW_SNAP_DEG:
            out.append(0.0)
            continue
        d = angdiff_deg(m, f)
        out.append(d)
        f = m % 360.0
    return out

def arrow_sticks(alpha_deg, drift_down=True):
    """Synthesize the two alternating arrow sticks for the N-S charge axis (facing 0/180,
    the slate's reoriented arrow axis): alternate X full (left/right -> snap facing 0<->180)
    with a Y-bias that tilts each snap by alpha toward the drift side. Inverse of the
    dead-zoned stick model: tan(alpha) = (|bias-128| - 15)/(128-15). drift_down=True biases
    Y down (the live-validated WEST drift on the slate). Returns [(sx,sy),(sx,sy)] to
    alternate. alpha=0 -> Y centered (pure charge). Validated vs the slot-9 capture:
    alpha=8 -> bias ~97 == the live (0,96)/(255,96)."""
    g = 128.0 - ARROW_STICK_DEADZONE
    off = 0.0 if alpha_deg <= 0 else ARROW_STICK_DEADZONE + g * math.tan(math.radians(alpha_deg))
    b = int(round(128 - off if drift_down else 128 + off))
    b = max(0, min(255, b))
    return [(0, b), (255, b)]

def reorient_chain(facing_start, facing_goal, cam_deg=270.0, tol=10.0, max_depth=6):
    """BFS over facing for a turnaround-snap chain from facing_start to within `tol`
    of facing_goal. A single snap can reach any facing >135deg away (the backward cone),
    so the graph nodes are facings (every FACING_GATE deg) and each edge is a synthesized
    full-deflection stick that snaps there. Every edge CHARGES. Returns the (sx, sy)
    list (or [] if already aligned, None if unreachable). Generalizes to any start/axis
    — DON'T hardcode the inputs (KNOWLEDGE §5.3)."""
    start = round(facing_start % 360.0 / FACING_GATE) * FACING_GATE % 360.0
    if abs(angdiff_deg(start, facing_goal)) <= tol:
        return []
    gates = [g * FACING_GATE for g in range(int(360.0 / FACING_GATE))]
    from collections import deque
    seen = {start: []}
    q = deque([start])
    while q:
        f = q.popleft()
        path = seen[f]
        if len(path) >= max_depth:
            continue
        for g in gates:
            if abs(angdiff_deg(g, f)) <= ARROW_SNAP_DEG:   # must be a >135deg snap
                continue
            stick = stick_for_m34e8(g, cam_deg)
            land = m34e8_deg(*stick, cam_deg)              # actual landing (gate-rounded)
            nf = round(land % 360.0 / FACING_GATE) * FACING_GATE % 360.0
            if nf in seen:
                continue
            seen[nf] = path + [stick]
            if abs(angdiff_deg(nf, facing_goal)) <= tol:
                return seen[nf]
            q.append(nf)
    return None
