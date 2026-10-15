"""Phase G floors-mode offline gates (land/floors.py).

Three tiers, all synthetic geometry (calc_pla planes -- bit-exact per test_collision gates):
  1. FLAT equivalence: a floors= mesh over a perfectly flat y=0 floor must reproduce the
     flat (floors=None) straight walk STEP-IDENTICAL in x/z, with pos_y pinned to the floor
     and ground_hit true every frame. (The m35B8 residue only touches the base Y row, which
     cannot couple into toe x/z at lean 0 -- rotation-only-Y base.)
  2. MICRO-INCLINE: on a GanonA-class 0.00039 u/u slope, pos_y must follow the plane cross
     exactly, every getGroundAngle term must sit in the zero atan cell (r3 == 0), and the
     walk must complete without SlopeNotModeled.
  3. RAMP guard: on a ~10-deg slope the model must REFUSE (SlopeNotModeled), never silently
     approximate.

The live REST BIT-EXACT gate on the GanonA corridor (the anchor-seeded from-rest run) is the
authoritative 0-ULP test; these gates pin the offline semantics and the refuse-don't-guess
contract. See harness/rollstab/README.md ## Status (Phase G).
"""
import math
import os
import sys

import pytest

# >>> repo bootstrap
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if os.path.exists(os.path.join(_ROOT, "pyproject.toml")) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# <<<

from tww_sim.core.collision import Tri
from tww_sim.core.fp import f32
from tww_sim.land import LandState
from tww_sim.land.floors import (GroundState, SlopeNotModeled, get_ground_angle,
                                 ground_cross, NEG_INF)


def _quad(y_at, x0=-4000.0, x1=4000.0, z0=-4000.0, z1=9000.0):
    """Two tris covering [x0,x1]x[z0,z1] with vertex y from y_at(x, z) (calc_pla planes)."""
    v = lambda x, z: (x, y_at(x, z), z)
    return [Tri(v(x0, z0), v(x0, z1), v(x1, z1)),
            Tri(v(x0, z0), v(x1, z1), v(x1, z0))]


def _walk(st, frames_up=40, frames_idle=12):
    rows = []
    for _ in range(frames_up):
        st.step(128, 255)
        rows.append((st.pos_x, st.pos_y, st.pos_z, st.speedF, st.ground_hit))
    for _ in range(frames_idle):
        st.step(128, 128)
        rows.append((st.pos_x, st.pos_y, st.pos_z, st.speedF, st.ground_hit))
    return rows


ANIM = LandState(use_anim=True)._foot is not None
needs_anim = pytest.mark.skipif(not ANIM, reason="anim keyframe data absent")


@needs_anim
def test_flat_mesh_matches_flat_model():
    flat = _quad(lambda x, z: 0.0)
    a = LandState(pos_x=0.0, pos_z=100.0, facing=0, travel=0, native=False, foot_native=False)
    b = LandState(pos_x=0.0, pos_z=100.0, facing=0, travel=0, floors=flat)
    ra = _walk(a)
    rb = _walk(b)
    for i, (fa, fb) in enumerate(zip(ra, rb)):
        assert fa[0] == fb[0] and fa[2] == fb[2] and fa[3] == fb[3], \
            f"x/z/speedF diverged at frame {i}: {fa} vs {fb}"
        assert fb[1] == 0.0, f"pos_y left the flat floor at frame {i}: {fb[1]}"
        assert fb[4], f"ground_hit dropped at frame {i}"


@needs_anim
def test_micro_incline_follows_floor():
    slope = 0.00039                      # the GanonA rest-envelope micro-incline (u/u along +z)
    tris = _quad(lambda x, z: slope * z)
    st = LandState(pos_x=0.0, pos_z=100.0, facing=0, travel=0, floors=tris)
    rows = _walk(st, frames_up=60, frames_idle=10)
    # walked forward and climbed
    assert rows[-1][2] > 400.0
    assert rows[-1][1] > rows[0][1]
    for i, r in enumerate(rows):
        assert r[4], f"ground_hit dropped at frame {i}"
        # UPHILL frames: setStepsOffset (:9545) snaps pos.y to the cross ONE speedF ahead
        # (travel == 0 -> z + speedF); stopped rows sit at the local cross. Never below it.
        h, idx = ground_cross(tris, r[0], f32(r[1] + 60.0), r[2])
        ha, _ = ground_cross(tris, r[0], f32(r[1] + 60.0), f32(r[2] + r[3]))
        assert r[1] in (h, ha), \
            f"pos_y is neither the local nor the ahead plane cross at frame {i}: " \
            f"{r[1]} vs {h} / {ha}"
        assert r[1] >= h, f"pos_y sits below the floor at frame {i}: {r[1]} < {h}"
    # the whole corridor sits inside the zero atan cell
    for t in tris:
        assert get_ground_angle(t.pla, 0) == 0
        assert get_ground_angle(t.pla, 0x8000) == 0
    # m35B8 engaged (a real foot-ground offset, sub-unit) without leaving the tier
    assert st._gnd.m35b8 != 0.0
    assert abs(st._gnd.m35b8) < 0.1


@needs_anim
def test_ramp_refuses():
    tris = _quad(lambda x, z: -0.1737 * z)      # the >630u GanonA ramp class (~10 deg)
    st = LandState(pos_x=0.0, pos_z=100.0, facing=0, travel=0, floors=tris)
    with pytest.raises(SlopeNotModeled):
        for _ in range(60):
            st.step(128, 255)


def test_ground_cross_max_and_bounds():
    lo = _quad(lambda x, z: 0.0)
    hi = _quad(lambda x, z: 50.0)
    tris = lo + hi
    # probe above both -> the higher floor wins (max)
    h, idx = ground_cross(tris, 0.0, 60.0, 100.0)
    assert h == 50.0 and idx >= 2
    # probe between -> only the lower is below the probe
    h, _ = ground_cross(tris, 0.0, 30.0, 100.0)
    assert h == 0.0
    # outside the mesh -> no floor
    h, idx = ground_cross(tris, 99999.0, 60.0, 99999.0)
    assert h == NEG_INF and idx is None


def test_get_ground_angle_cells():
    flat = _quad(lambda x, z: 0.0)[0].pla
    assert get_ground_angle(flat, 0) == 0
    micro = _quad(lambda x, z: 0.00039 * z)[0].pla
    assert get_ground_angle(micro, 0) == 0          # below the 1/1024 atan cell
    ramp = _quad(lambda x, z: -0.1737 * z)[0].pla
    down = get_ground_angle(ramp, 0)                # +z walk on a floor FALLING in +z = downhill
    up = get_ground_angle(ramp, 0x8000)
    assert down > 0 and up < 0                      # r3 > 0 downhill, < 0 uphill (x0.85 branch)
