"""Solver `seam=` threading (session 46, generalization Phase 3).

`solver.run`/`base`/`search`/`start_family`/`fine_family`/`arc_family` no longer read a module-global
`geometry as G`; they take a per-seam `SeamGeo` (default None = the kaze r11 seam `geometry.SEAM`), so a
NEW enumerated seam solves via the same path. This is a pure refactor (no sim/physics change); it locks:

  1. the parameterized path reproduces the shipped seed-0 kaze hit BIT-EXACT, and the explicit
     `seam=geometry.SEAM` result is byte-identical to the default `seam=None` (the GATE for Phase 3);
  2. `seam` is genuinely honored -- a SeamGeo with a different camera yaw (=> a different roll facing
     `F`) makes `start_family(anchor, seam=other)` produce a DIFFERENT aim than the default. If the
     families had silently kept reading the module-global geometry, this would not move (guards against
     a reintroduced hardcode, [[no-overtuned-constants]]).

Recipe = the shipped kaze roll-stab hit (`_generated/rollstab_hits.json[0]`, the SAME constants
test_sheathed_roll_clip embeds; `_generated/` is gitignored so it is embedded, not read).
"""
import os
import struct

import pytest

try:
    from harness.rollstab import solver as SV
    from harness.rollstab import geometry as G
    from harness.rollstab.seamgeo import SeamGeo
    import json
    _rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _GEO = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json')))
    _HAVE = True
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness unavailable")

# the shipped seed-0 kaze roll-stab hit (matches tests/test_sheathed_roll_clip.py)
ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'
A_PROJ, DRAW_AT, DTM_SEED = -500.0, 3, 0
MOVES = ((9, (73, 254), 2), (10, (99, 183)), (4, (96, 192)), (6, (98, 188)))
START = ((77, 249), (98, 191))


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_explicit_seam_reproduces_shipped_hit_bitexact():
    """GATE (Phase 3): the shipped hit recomposes bit-for-bit via the parameterized path, whether the
    kaze seam is passed explicitly or defaulted. `default` == `explicit` down to the stream bytes."""
    kw = dict(A_proj=A_PROJ, start=START, draw_at=DRAW_AT, dtm_seed=DTM_SEED)
    r_def = SV.run(ANCHOR, MOVES, seam=None, **kw)       # default -> geometry.SEAM
    r_exp = SV.run(ANCHOR, MOVES, seam=G.SEAM, **kw)     # explicit kaze SeamGeo
    for r in (r_def, r_exp):
        assert r is not None and r.get('fired')
        assert (_bits(r['old'][0]), _bits(r['old'][1])) == (_bits(9072.208984375), _bits(308.028076171875))
        assert (_bits(r['new'][0]), _bits(r['new'][1])) == (_bits(9069.888671875), _bits(258.8625793457031))
        assert r['facing'] == G.F and r['genuine'] and r['clear']
    assert r_def['stream'] == r_exp['stream']


@pytest.mark.slow
def test_seam_param_is_honored_by_families():
    """`seam` genuinely threads through: a different-yaw SeamGeo has a different F, so its start-crawl
    aim differs from the kaze default. (If the families still read the module-global, this would not
    move.) The csangle used to DECODE sticks stays anchor-sourced -- only the seam's aim facing moves."""
    other = SeamGeo(_GEO, (G.SEAM.csangle + 4096) & 0xFFFF)
    assert other.F != G.SEAM.F                                   # different camera -> different facing
    default = SV.start_family(ANCHOR)                            # seam=None -> kaze F
    threaded = SV.start_family(ANCHOR, seam=other)               # other seam's F
    assert default and threaded
    assert default != threaded                                   # the seam's F reached the family aim


def test_default_seam_is_kaze():
    """The default `seam=None` binds to the kaze r11 seam (`geometry.SEAM`), so every pre-session-46
    invocation is unchanged: same F, same acceptance surface."""
    assert G.SEAM is not None and G.SEAM.F == G.F == 33295
