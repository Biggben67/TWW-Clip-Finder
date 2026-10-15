#!/usr/bin/env python3
"""land/walls.py - the opt-in per-frame wall response for LandState (ROADMAP Phase W).

Wires core.collision's player-faithful ``acch_crr_pos`` into the stepper at the game's exact
point in the frame: procs -> posMove (position integration) -> **mAcch.CrrPos** -> ground snap
-> end-of-frame draw (d_a_player_main.cpp:11407-11411, setWorldMatrix 11551). The pass takes
the POST-integration, PRE-snap position with the mid-frame gravity dip and writes back the
corrected position plus the per-cylinder wall-hit state the procs read NEXT frame
(setNormalSpeedF's wall slow-down 2311, the roll bonk 6838/6869, procWait's L wall-snap 6097).

Scope (gated live on the kaze r11 anchors, see tests/dolphin/): GROUNDED procs on a FLAT floor
-- walk/roll/cut/turn/slip. The ballistic hops keep their own y integration and skip the wall
pass for now (no wall gate exercises them yet); GetWallAddY (slope lift) is 0 on flat ground
and becomes Phase G's problem. Mesh contract: WALL tris in the game's WallCorrect traversal
order -- order only matters when two non-coplanar walls engage in one frame (corners).
"""
from __future__ import annotations
import json

from ..core.fp import f32, fadds, fmuls
from ..core.collision import Tri, Plane, acch_crr_pos, cross_lin_tri
from ..core.mathlib import cM_atan2s, cM_ssin_s16, cM_scos_s16, s16_signed

# Link's wall cylinders in the normal ground state (setBgCheckParam 10680 + create 12204):
# heights {30.1, 89.9, 125.0}, radius 35 on all three. Crawl/swim/hang states differ.
WALL_H = (30.1, 89.9, 125.0)
WALL_R = 35.0
# mAutoJump.field_0xC: the grounded per-frame speed.y at CrrPos time (the gravity dip --
# added pre-CrrPos, snap-zeroed after; see mechanics/wall-response.md).
GRAVITY = f32(-2.5)


def _mk_tri(t):
    return Tri(t["v"][0], t["v"][1], t["v"][2],
               plane=Plane(t["n"][0], t["n"][1], t["n"][2], t["d"]))


def load_geo_tris(path):
    """Wall tris from a *_geo.json fixture (kaze_r11_geo.json layout: wallA/wallB/barrier with
    stored plane n/d). Order: wallA, wallB, then the barrier set -- the corner pair first. Used by
    the single-face gates; for a CORNER gate use :func:`load_ordered_mesh` (game traversal order)."""
    geo = json.load(open(path))
    return [_mk_tri(geo["wallA"]), _mk_tri(geo["wallB"])] + [_mk_tri(t) for t in geo["barrier"]]


def load_ordered_mesh(path):
    """Wall tris from a *_walls_ordered.json fixture (``{polys:[{v,n,d}, ...]}``, captured by
    ``harness/rollstab/capture_walls``) in the game's WallCorrect traversal order. Feed THIS at a
    corner: when the cylinder overlaps two non-coplanar walls in one frame the sim corrects against
    them in the same order the game does (far polys are visited too and simply no-op)."""
    mesh = json.load(open(path))
    return [_mk_tri(t) for t in mesh["polys"]]


def cull_walls(tris, xmin, zmin, xmax, zmax, margin=250.0):
    """Order-preserving XZ AABB cull (the Phase-W speed edge): drop tris whose XZ bounding box
    misses the run's region expanded by ``margin``. Far polys are exact no-ops in both LineCheck
    (the swept segment stays inside the region) and WallCorrect (interaction reach is bounded by
    wall_r + the r-offset, << margin), so the culled pass is BIT-IDENTICAL to the full mesh for
    any trajectory confined to the region -- validate per run (gate: tests/test_shove_fixture.py).
    Region = the AABB of every position either actor visits; pick ``margin`` >= wall reach
    (2*wall_r) + the largest single-frame displacement (cut lunge ~50u) with headroom."""
    x0, z0, x1, z1 = xmin - margin, zmin - margin, xmax + margin, zmax + margin
    out = []
    for t in tris:
        xs = (t.v0[0], t.v1[0], t.v2[0])
        zs = (t.v0[2], t.v1[2], t.v2[2])
        if max(xs) < x0 or min(xs) > x1 or max(zs) < z0 or min(zs) > z1:
            continue
        out.append(t)
    return out


def sidle_blocks_roll(st):
    """The A-dispatch guard: TRUE when the game would offer SIDLE instead of the roll, so the
    sim must NOT roll (the sidle proc itself is deliberately unmodeled -- planners just avoid
    the input). Decomp setFrontWallType (d_a_player_main.cpp:4552) -> mFrontWallType == 2 ->
    setDoStatus SIDLE (2241), which preempts the ATTACK/roll in the doTrigger chain (4188):
      * mAcch.ChkWallHit() (LAST frame's CrrPos),
      * a 25+wallR line check along FACING at each cylinder height hits a steep wall
        (|normal.y| <= 0.05),
      * facing within 0x2000 of head-on (distanceAngleS(wall angle, facing+0x8000)).
    The deeper checks (the reflected same-plane confirm, the 149.9-height WHide polygon) are
    satisfied by any tall flat wall (kaze); revisit if a gate ever needs a short/complex wall."""
    if not st.wall_hit:
        return False
    sin = cM_ssin_s16(st.facing)
    cos = cM_scos_s16(st.facing)
    reach = fadds(25.0, WALL_R)
    for h in reversed(WALL_H):               # decomp scans i = 2..0
        start = (st.pos_x, fadds(st.pos_y, h), st.pos_z)
        end = (fadds(start[0], fmuls(sin, reach)), start[1], fadds(start[2], fmuls(cos, reach)))
        cur_end, hit = end, None
        for tri in st._walls:                # LineCross: nearest front crossing
            crossed, pt = cross_lin_tri(start, cur_end, tri, a=True, b=False)
            if crossed:
                cur_end, hit = pt, tri
        if hit is not None:
            n = hit.pla
            if abs(n.ny) > 0.05:
                return False
            wall_ang = cM_atan2s(n.nx, n.nz)
            return abs(s16_signed(wall_ang - (st.facing + 0x8000))) <= 0x2000
    return False


def wall_pass(st, old_x, old_z, y_old=None, y_mid=None, sy=None, snap=True):
    """One mAcch.CrrPos wall pass on LandState ``st`` (call right after position integration).

    Grounded default: old = the frame-start position (the framework copies current->old before
    execute, so old.pos.y is the SNAPPED ground height); new = the integrated position with the
    y dip -- posMoveFromFootPos added gravity to the snap-zeroed speed.y and integrated it
    BEFORE CrrPos, so WallCorrect's slice heights see y = ground + gravity, speed.y = gravity.
    ``snap=True`` then applies the flat-floor GroundCheck (ground_h > dipped y always -> pos.y
    stays the ground height, speed.y re-zeroed). Airborne callers (the crash bounce) pass their
    true (y_old, y_mid, sy) and snap=False -- the caller runs its own ground check after."""
    if sy is None:
        sy = GRAVITY
        y_old = st.pos_y
        y_mid = fadds(y_old, sy)
    pos, info = acch_crr_pos((old_x, y_old, old_z), (st.pos_x, y_mid, st.pos_z),
                             st._walls, speed_y=sy, wall_h=WALL_H, wall_r=WALL_R)
    st.pos_x = pos[0]
    st.pos_z = pos[2]
    if snap:
        # GroundCheck: field_0xb8 (ground) > field_0xb4 (the dipped y at CrrPos start) -> snap.
        st.ground_hit = True
    st.wall_hit = info["wall_hit"]
    st.wall_cir_hit = tuple(info["cir_hit"])
    st.wall_angle = tuple(info["wall_angle"])
    st.line_hit = info["line_hit"]
