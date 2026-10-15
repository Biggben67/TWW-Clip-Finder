# >>> repo bootstrap
import os
import sys
_d = os.path.dirname(os.path.abspath(__file__))
while _d and not os.path.exists(os.path.join(_d, 'pyproject.toml')):
    _p = os.path.dirname(_d)
    if _p == _d:
        break
    _d = _p
if _d not in sys.path:
    sys.path.insert(0, _d)
# <<< repo bootstrap
"""Differential 0-ULP gate for the native coupled-actor primitives (`_anmc.cm_atan2s` +
`_anmc.co_move_pair_xz`): the attention cone gate / `setShapeAngleToAtnActor` re-aim, and the
`dCcS::SetPosCorrect` CC push.

Each must be BIT-FOR-BIT identical to its pure-Python twin (`mathlib.cM_atan2s`,
`cc_push.co_move_pair`) -- no tolerance (`[[zero-ulp-tests-only]]`). If the .pyd is absent the
module is a no-op. The tables are wired at `foot_fk` import (init_atan_table / init_rank_table),
so importing the native module through the normal path leaves them ready."""
import struct

import pytest

from tww_sim.core import mathlib as S
from tww_sim.core import cc_push
from tww_sim.core.anim import foot_fk  # side effect: inits the atan + rank tables in _anmc

_N = foot_fk._N


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


# A deterministic pseudo-random stream (no Math.random / stdlib random dependence for reproducibility).
def _lcg(seed):
    x = seed & 0xFFFFFFFF
    while True:
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        yield x / float(0x7FFFFFFF)


@pytest.mark.skipif(_N is None, reason="native _anmc not built")
def test_cm_atan2s_native_matches_python_bit_exact():
    # Edge grid (near-zero, on-axis, octant boundaries) + a dense pseudo-random sweep.
    edge = [0.0, 1e-7, 1e-6, 2.0 ** -18, 1e-5, 0.1, 1.0, -1.0, 41.0, -41.0,
            535.0, 1727.0, -990.0, 3.5, -0.0001]
    for a in edge:
        for b in edge:
            assert (S.cM_atan2s(a, b) & 0xFFFF) == (_N.cm_atan2s(a, b) & 0xFFFF), (a, b)
    g = _lcg(1)
    for _ in range(40000):
        a = (next(g) - 0.5) * 4000.0
        b = (next(g) - 0.5) * 4000.0
        assert (S.cM_atan2s(a, b) & 0xFFFF) == (_N.cm_atan2s(a, b) & 0xFFFF), (a, b)


@pytest.mark.skipif(_N is None, reason="native _anmc not built")
def test_co_move_pair_native_matches_python_bit_exact():
    # Link (R=30, weight 120) vs a type-5 Zl1 (R=50, weight 0x8C). Sweep the separations a push
    # actually visits (feet 41-85 u apart, so rim contact through no contact) plus deep overlap.
    CO_H = 104.6
    g = _lcg(7)
    n = 0
    for _ in range(40000):
        lx = -1800.0 + next(g) * 600.0
        lz = -1100.0 + next(g) * 1300.0
        tx = lx + (next(g) - 0.5) * 180.0
        tz = lz + (next(g) - 0.5) * 180.0
        v1, v2 = cc_push.co_move_pair((lx, 0.0, lz), 30.0, CO_H, (tx, 0.0, tz), 50.0, CO_H,
                                      cc_push.WEIGHT_LINK, cc_push.WEIGHT_TETRA_V5)
        c1, c2 = _N.co_move_pair_xz(lx, lz, 30.0, CO_H, tx, tz, 50.0, CO_H,
                                    cc_push.WEIGHT_LINK, cc_push.WEIGHT_TETRA_V5)
        assert _bits(v1[0]) == _bits(c1[0]) and _bits(v1[2]) == _bits(c1[2]), (lx, lz, tx, tz, v1, c1)
        assert _bits(v2[0]) == _bits(c2[0]) and _bits(v2[2]) == _bits(c2[2]), (lx, lz, tx, tz, v2, c2)
        n += 1
    assert n == 40000
