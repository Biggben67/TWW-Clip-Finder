#!/usr/bin/env python3
"""Phase-G regression: the Tetra roll-stab spot's floor is FLAT (ROADMAP Phase G).

Fixture = fixtures/hyrule_tetra_ground.json -- a live DZB capture (flooded Hyrule, savestate slot 3;
harness/rollstab/capture_ground.py) of the WALKABLE ground plane sampled along the roll footprint
old->seam at the (-1727,-990) Tetra corner. Phase G's whole question is "is this floor flat?": if it
is, `getGroundAngle`'s slope term is 0 (the sim hardcodes r3=0 in the speedF cM_scos scale, and the
r3<0 x0.85 branch never fires) and the m35B8 per-foot ground-lift is provably 0, so the existing
flat-floor model (exact at kaze, also flat) applies to the Tetra clip UNCHANGED and no GroundCross /
getGroundAngle / m35B8 modeling is needed.

This encodes that finding as a contract: every sampled point along the roll footprint must be
covered by a walkable ground tri whose normal is (0,1,0) at f32 scale, on a single floor plane. If a
future capture at a different Tetra spot ever shows slope, this test goes RED -- the signal that
Phase G modeling has become load-bearing.

Independently verified at capture time (2026-07-10): only one walkable-band ground tri (poly 2917)
covers the whole roll region across a dense grid; its normal recomputed from raw vertices via
cross-product == the game's stored plane == (0, 1, 8e-08); the ~25-degree surface that shares the XZ
footprint sits ~560u overhead (Hyrule terrain) and Link's roll at Y~0.16 never touches it.
"""
import json
import os

_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(_rb, 'fixtures', 'hyrule_tetra_ground.json')

# f32 flat: normal (0,1,0). Tolerance covers f32 quantization of a horizontal DZB plane
# (measured live: nx=0, ny=1.0, nz=8e-08; vertex-Y spread 1.3e-4 over the tri).
NORMAL_TOL = 1e-4


def _fix():
    with open(FIX) as f:
        return json.load(f)


def test_tetra_floor_is_flat():
    fix = _fix()
    assert fix['stage'] == 'Hyrule', fix['stage']
    walk = [(s['t'], p) for s in fix['samples'] for p in s['polys']]
    assert walk, 'no walkable ground sampled along the roll footprint'
    for t, p in walk:
        nx, ny, nz = p['n']
        assert abs(nx) < NORMAL_TOL, (t, p['poly'], 'nx', nx)
        assert abs(ny - 1.0) < NORMAL_TOL, (t, p['poly'], 'ny', ny)
        assert abs(nz) < NORMAL_TOL, (t, p['poly'], 'nz', nz)
    assert fix['flat'] is True


def test_tetra_roll_footprint_covered():
    """Every sampled point old->just-short-of-seam must sit on a walkable floor tri (the roll never
    leaves the floor before the cut); only the seam endpoint NEW (behind the wall) has no floor."""
    fix = _fix()
    uncovered = [s['t'] for s in fix['samples'] if not s['polys']]
    assert not uncovered, ('roll footprint leaves the walkable floor at t=%s' % uncovered)


def test_tetra_floor_single_plane():
    """The footprint rides one floor height -- no step/lip the roll crosses."""
    fix = _fix()
    ys = fix['floor_ys']
    assert len(ys) == 1, ('expected a single floor Y, got %s' % ys)
