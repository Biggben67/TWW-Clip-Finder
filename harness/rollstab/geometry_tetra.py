"""Seam geometry + clip acceptance for the flooded-Hyrule TETRA corner (Phase T).

The Phase-0 sibling of `geometry.py` (the kaze r11 corner), with the ONE structural difference that
makes the Tetra clip a north-star target: the kaze clip is a bare roll-stab (`new = old + LUNGE`),
but the Tetra corner at (-1727,-990) is a NEEDS-PUSH clip -- the 49.2202u lunge lands ~0.75u short of
the seam, and the CC push from a corner-braced Tetra (consumed in `posMove` BEFORE the cut lunge,
[[knowledge/mechanics/actor-push]]) steers it the rest of the way. So the acceptance endpoint is the
COUPLED `new = f32(old + push + lunge)` (the decomp `posMove` order: `+= m_cc_move`, then `+= thrust`,
then `CrrPos`; `harness/collision/tetra_clip.clip_with_push`), and `pred_genuine(old, push)` takes the
per-frame Link push vector.

Loads `fixtures/hyrule_tetra_geo.json` (built offline from the live golden by `make_tetra_geo.py`):
the two incident wall tris (wallA = +X wall poly 2915, wallB = +Z wall poly 2904, a 90.57-deg corner),
the full 4-tri CrrPos barrier, `link_y` (= the Phase-G flat floor 0.16327), the seam vertex S, and the
AUTHORITATIVE live-anchored clip target (`old`/`new`). The acceptance tests are otherwise identical to
`geometry.py`: exact f32 candidates, never a fitted ribbon ([[knowledge/strategy/seam-clip-solver]]).
"""
import os, json, math, sys
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.collision import Tri, Plane, crr_pos_walls
from tww_sim.core.fp import f32 as _f, fadds

GEO = json.load(open(os.path.join(_rb, 'fixtures', 'hyrule_tetra_geo.json')))

A_BTN, B_BTN = 0x100, 0x200
KROLL = 15                     # aim frames between the A roll init and the single B edge (== kaze)
F = 40874                      # roll facing at the Tetra corner (= world_angle_s16(new - old), 224.53deg)
# REAL enter_cut CUT_F lunge at F (LandState.enter_cut out of a 26u roll, bit-exact vs live; the
# coupled `new` == f32(old + push + LUNGE) reproduces the live golden endpoint 0-ULP -- verified).
LUNGE = (-34.4145622253418, -35.18904113769531)


def _mk(t):
    return Tri(t["v"][0], t["v"][1], t["v"][2],
               plane=Plane(t["n"][0], t["n"][1], t["n"][2], t["d"]))


wA, wB = _mk(GEO["wallA"]), _mk(GEO["wallB"])
TRIS = [_mk(t) for t in GEO["barrier"]]        # full CrrPos barrier (4 golden tris, game order)
LINK_Y = GEO["link_y"]
S = (GEO["S"][0], GEO["S"][2])
TARGET = GEO["target"]                          # authoritative live-anchored clip target (old/new)

_r = F / 65536.0 * 2 * math.pi
DIRX, DIRZ = math.sin(_r), math.cos(_r)
PX, PZ = -DIRZ, DIRX           # perp(F) axis (plan_search convention)


def p32(x, z):
    return (_f(x), LINK_Y, _f(z))


def in_front(p):
    return wA.pla.func(p) > 0 and wB.pla.func(p) > 0


def seg_blocked(a, b):
    _, info = crr_pos_walls(p32(a[0], a[1]), p32(b[0], b[1]), TRIS)
    return info["line_hit"] or info["wall_hit"]


def genuine_clip(old, new):
    po, pn = p32(old[0], old[1]), p32(new[0], new[1])
    _, info = crr_pos_walls(po, pn, TRIS)
    if info["line_hit"] or info["wall_hit"]:
        return False
    if not in_front(po):
        return False
    return wA.pla.func(pn) < 0 or wB.pla.func(pn) < 0


def coupled_new(old, push=(0.0, 0.0)):
    """The clip-frame endpoint in the decomp `posMove` order: current.pos += m_cc_move (the push
    from the prior frame's overlap), then += the cut lunge; all componentwise f32 adds. `push` is
    Link's per-frame `m_cc_move` XZ (0 => the bare roll-stab, matching the kaze `pred_genuine`)."""
    nx = fadds(fadds(_f(old[0]), _f(push[0])), _f(LUNGE[0]))
    nz = fadds(fadds(_f(old[1]), _f(push[1])), _f(LUNGE[1]))
    return (nx, nz)


def pred_genuine(old, push=(0.0, 0.0)):
    """genuine_clip against the coupled endpoint (bit-identical to the sim's cut `new`)."""
    return genuine_clip(old, coupled_new(old, push))


def perp(p):
    return (p[0] - S[0]) * PX + (p[1] - S[1]) * PZ


def along(p):
    return (p[0] - S[0]) * DIRX + (p[1] - S[1]) * DIRZ
