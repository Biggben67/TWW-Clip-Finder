#!/usr/bin/env python3
"""Phase-W wall-gate regression: replay the four live wall goldens from REST with the walls
mesh and require pos (bit-exact) + proc + facing on EVERY row.

Goldens = tests/golden/rollstab_wall_{headon,oblique,crash,grind}.json -- per-frame live traces
of clean-DTM runs on the minted kaze_r11_wallgate_faceB anchor (all four verified WALL GATE
BIT-EXACT live, 2026-07-10; harness/rollstab/wallgate.py). They pin the in-stepper CrrPos wall
response (LineCheck + WallCorrect + the gravity-dip slice heights + console sqrtf), the
setNormalSpeedF wall slow-down, the roll bonk (FRONT_ROLL_CRASH bounce/land/playout), and the
slow-roll grind. Requires the anim keyframe dump (skips without it, like test_rollstab_rest).
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
from tww_sim.core.anim.foot_speedf import FootSpeedF  # noqa: E402
from tww_sim.land.walls import load_geo_tris          # noqa: E402
from harness.rollstab import rest as C                # noqa: E402

GOLD = os.path.join(_rb, 'tests', 'golden', 'rollstab_wall_%s.json')
WALLS = load_geo_tris(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json'))

pytestmark = pytest.mark.skipif(not FootSpeedF.available(),
                                reason='anim keyframe dump absent (_generated/anim)')


def bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


@pytest.mark.parametrize('gate', ['headon', 'oblique', 'crash', 'grind'])
def test_wall_gate_bitexact(gate):
    log = json.load(open(GOLD % gate))
    s = C.rest_state(log['anchor'], walls=WALLS)
    for k, (sx, sy, b) in enumerate(log['stream']):
        s.step(sx, sy, buttons=b)
        if k >= len(log['frames']):
            break
        lf = log['frames'][k]
        assert bits(s.pos_x) == bits(lf['pos_x']), (gate, k, s.pos_x, lf['pos_x'])
        assert bits(s.pos_z) == bits(lf['pos_z']), (gate, k, s.pos_z, lf['pos_z'])
        assert (s.state & 0xFF) == lf['proc'], (gate, k, s.state, lf['proc'])
        assert (s.facing & 0xFFFF) == (lf['facing'] & 0xFFFF), (gate, k)
