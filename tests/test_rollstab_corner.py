#!/usr/bin/env python3
"""Phase-W CORNER-gate regression: replay the live corner golden from REST with the traversal-
ordered wall mesh and require pos (bit-exact) + proc + facing on EVERY row.

Golden = tests/golden/rollstab_corner.json -- a per-frame live trace of a clean-DTM walk straight
into the kaze r11 110-degree seam vertex on the minted kaze_r11_wallcorner anchor (verified CORNER
GATE BIT-EXACT live, 2026-07-10; harness/rollstab/cornergate.py). It pins the MULTI-WALL
WallCorrect: when the cylinder wedges between wallA (poly 705) and wallB (poly 713) both correct in
one frame, and the game does them in DZB traversal order (wallA before wallB, reconstructed by
harness/rollstab/capture_walls.py -> fixtures/kaze_r11_walls_ordered.json).

Second assertion: the order is LOAD-BEARING -- replaying with wallA/wallB swapped must DIVERGE from
the golden, so an ordering regression cannot pass. Requires the anim keyframe dump (skips without).
"""
import json
import os
import struct
import sys

import pytest


_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _rb not in sys.path:
    sys.path.insert(0, _rb)



from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from tww_sim.core.anim.foot_speedf import FootSpeedF   # noqa: E402
from tww_sim.land.walls import load_ordered_mesh, _mk_tri  # noqa: E402
from harness.rollstab import rest as C                 # noqa: E402

GOLD = os.path.join(_rb, 'tests', 'golden', 'rollstab_corner.json')
MESH_PATH = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')
WALL_A_POLY, WALL_B_POLY = 705, 713

pytestmark = pytest.mark.skipif(not FootSpeedF.available(),
                                reason='anim keyframe dump absent (_generated/anim)')


def bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _replay(walls):
    log = json.load(open(GOLD))
    s = C.rest_state(log['anchor'], walls=walls)
    rows = []
    for k, (sx, sy, b) in enumerate(log['stream']):
        s.step(sx, sy, buttons=b)
        rows.append((s.pos_x, s.pos_z, s.state & 0xFF, s.facing & 0xFFFF))
    return log, rows


def test_corner_gate_bitexact():
    walls = load_ordered_mesh(MESH_PATH)
    log, rows = _replay(walls)
    for k, (px, pz, proc, face) in enumerate(rows):
        if k >= len(log['frames']):
            break
        lf = log['frames'][k]
        assert bits(px) == bits(lf['pos_x']), (k, px, lf['pos_x'])
        assert bits(pz) == bits(lf['pos_z']), (k, pz, lf['pos_z'])
        assert proc == lf['proc'], (k, proc, lf['proc'])
        assert face == (lf['facing'] & 0xFFFF), (k, face, lf['facing'])


def test_corner_order_is_load_bearing():
    """Swapping wallA/wallB in the mesh must break the bit-exact match -- proof the gate actually
    tests the traversal ordering (not a trajectory where order happens not to matter)."""
    mesh = json.load(open(MESH_PATH))
    iA = next(i for i, p in enumerate(mesh['polys']) if p['poly'] == WALL_A_POLY)
    iB = next(i for i, p in enumerate(mesh['polys']) if p['poly'] == WALL_B_POLY)
    sw = mesh['polys'][:]
    sw[iA], sw[iB] = sw[iB], sw[iA]
    log, rows = _replay([_mk_tri(p) for p in sw])
    ndiff = sum(1 for k, (px, pz, _, _) in enumerate(rows)
                if k < len(log['frames'])
                and (bits(px) != bits(log['frames'][k]['pos_x'])
                     or bits(pz) != bits(log['frames'][k]['pos_z'])))
    assert ndiff > 0, 'swapped wallA/wallB still matched the golden -- the gate does not test order'
