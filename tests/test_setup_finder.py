#!/usr/bin/env python3
"""Offline tests for the land setup finder (blocks.py + setup_finder.py).

These assert the STRUCTURAL / float-perfect properties that must hold regardless of the exact
ballistic constants (which are pending live 0-ULP calibration, see tests/dolphin): determinism,
re-simulation consistency (a returned plan re-runs to its reported endpoint bit-exactly), cost-ranked
output, and the ballistic sign/rough-magnitude sanity. No Dolphin needed.

Catalog note: WALK is intentionally absent (no frame-perfect-free way to stop it), so targets here are
reachable by the ballistic hops (backflip / sidehop), which move opposite / perpendicular to facing.
"""
import struct
import math

from tww_sim.land.blocks import (default_catalog, apply_block, new_state,
                                 BACKFLIP, SIDEHOP_LEFT, SIDEHOP_RIGHT)
from tww_sim.land.setup_finder import find_setups, expand_path


def _bits(x):
    return struct.pack("<f", x).hex()


def _backflip_z(n=1):
    """Resting pos_z after n backflips from the default standstill (facing +z), computed by the sim."""
    s = new_state(pos_z=764.079, facing=0)
    for _ in range(n):
        s = apply_block(s, BACKFLIP)["state"]
    return s.pos_z


def test_apply_block_is_deterministic():
    s = new_state(pos_z=764.079, facing=0)
    for b in default_catalog():
        r1 = apply_block(s, b)
        r2 = apply_block(s, b)
        assert _bits(r1["dz"]) == _bits(r2["dz"]) and _bits(r1["dx"]) == _bits(r2["dx"])
        assert r1["frames"] == r2["frames"]


def test_apply_block_does_not_mutate_source():
    s = new_state(pos_z=764.079, facing=0)
    px, pz, stt = s.pos_x, s.pos_z, s.state
    apply_block(s, BACKFLIP)
    assert s.pos_x == px and s.pos_z == pz and s.state == stt


def test_ballistic_sign_and_magnitude():
    """Backflip goes BACKWARD (opposite facing), sidehops go PERPENDICULAR (opposite signs). Ranges
    are loose sanity, not the 0-ULP truth (that is the live gate)."""
    s = new_state(pos_z=764.079, facing=0)                 # facing +z
    bf = apply_block(s, BACKFLIP)
    assert bf["dz"] < -200 and abs(bf["dx"]) < 1.0         # backward, on-axis
    left = apply_block(s, SIDEHOP_LEFT)
    right = apply_block(s, SIDEHOP_RIGHT)
    assert left["dx"] > 200 and right["dx"] < -200         # perpendicular, opposite signs
    assert abs(left["dz"]) < 1.0 and abs(right["dz"]) < 1.0
    assert abs(left["dx"] + right["dx"]) < 1e-3            # symmetric


def test_facing_seeds_the_block_frame():
    """A backflip is relative to facing: facing 180deg (0x8000, -z) makes the backflip move +z."""
    s = new_state(pos_z=1500.0, facing=0x8000)
    bf = apply_block(s, BACKFLIP)
    assert bf["dz"] > 200                                   # backward of -z facing = +z


def test_find_setups_ranked_and_within_tol():
    """Target = two backflips back (reachable by the ballistic catalog); expect the finder to land it."""
    s = new_state(pos_z=764.079, facing=0)
    tz = _backflip_z(2)                                     # exact 2-backflip resting z
    setups = find_setups(s, 0.0, tz, catalog=default_catalog(), tol=2.0, max_results=10)
    assert setups, "expected a ballistic setup to the 2-backflip target"
    keys = [(r.frames, round(r.diff, 4)) for r in setups]
    assert keys == sorted(keys)                             # ranked by (frames, diff)
    for r in setups:
        d = math.hypot(0.0 - r.pos_x, tz - r.pos_z)
        assert d <= 2.0 + 1e-6 and abs(r.diff - d) < 1e-4
    assert setups[0].blocks == ["backflip", "backflip"]    # the exact-hit cheapest plan


def test_resim_consistency_bit_exact():
    """THE float-perfect guarantee: a returned plan, expanded to per-frame inputs and re-run through a
    fresh sim, reproduces the reported endpoint position BIT-EXACTLY."""
    s = new_state(pos_z=764.079, facing=0)
    tz = _backflip_z(3)
    setups = find_setups(s, 0.0, tz, catalog=default_catalog(), tol=5.0, max_results=5)
    assert setups
    for r in setups[:3]:
        seq = expand_path(s, r.blocks, default_catalog())
        s2 = new_state(pos_z=764.079, facing=0)
        for inp in seq:
            s2.step(*inp)
        assert _bits(s2.pos_z) == _bits(r.pos_z), (r.blocks, r.pos_z, s2.pos_z)
        assert _bits(s2.pos_x) == _bits(r.pos_x)


def test_find_setups_deterministic():
    s = new_state(pos_z=764.079, facing=0)
    tz = _backflip_z(2)
    a = find_setups(s, 0.0, tz, tol=3.0, max_results=8)
    b = find_setups(s, 0.0, tz, tol=3.0, max_results=8)
    assert [(r.blocks, r.frames, _bits(r.pos_z)) for r in a] == \
           [(r.blocks, r.frames, _bits(r.pos_z)) for r in b]


def test_sidehop_reaches_offaxis_target():
    """A single sidehop from facing +z lands ~+323 in x; the finder should find it for an x target."""
    s = new_state(pos_z=764.079, facing=0)
    tx = apply_block(s, SIDEHOP_LEFT)["state"].pos_x
    setups = find_setups(s, tx, 764.079, tol=2.0, max_results=5)
    assert setups and setups[0].blocks == ["sidehop_l"]
