"""Clippable corner-angle sweep on SYNTHETIC seams — enabled by the bit-exact cM3d_CalcPla in
tww_sim.core.collision (frsqrte port). Fix wall A (vertical); pivot wall B about the shared vertical
seam edge by turn angle alpha (B stays vertical); build each triangle's plane with calc_pla (bit-exact
to what the game would compute for those vertices), then decide clippability with the ANALYTIC gap
search in :mod:`gap_search` (not a brute-force start x aim x D grid — that grid has false negatives
on the sub-1e-3-u offset razor and spuriously reported 90.0 and 120.0 as unclippable).

Findings (see knowledge/mechanics/seam-clip.md):
  * Near-90 corners DO clip (interior 80-137 all clippable), matching live confirmation. The old grid
    reported False at exactly-90.0 and 120.0; the analytic search confirms both clip (grid misses).
  * There is NO clean geometric angle cutoff: clippability at a given angle is governed by the
    per-triangle plane FAN (a sub-ULP property of the exact vertices). Whether a *specific* real seam
    clips depends on its exact coordinates.
  * Reflex/concave corners (turn the other way) clip over a wider range.

    python -m harness.collision.angle_experiment
"""
import math

from tww_sim.core.collision import Tri
from harness.collision.gap_search import characterize

A_FAR = (-513.3269653320312, -37420.58203125)
S = (-847.6320190429688, -37336.61328125)
YB, YT = 5834.38037109375, 7334.38134765625
LINK_Y = 5852.66
_B_FAR0 = (-1085.3291015625, -36967.18359375)
_L = math.hypot(_B_FAR0[0]-S[0], _B_FAR0[1]-S[1])
_vA = (S[0]-A_FAR[0], S[1]-A_FAR[1]); _m = math.hypot(*_vA)
_uA = (_vA[0]/_m, _vA[1]/_m)


def build_angle(alpha_deg):
    """Wall A (fixed) + wall B pivoted by alpha about the seam. alpha=0 -> B straight-continues A."""
    a = math.radians(alpha_deg)
    dx = _uA[0]*math.cos(a) - _uA[1]*math.sin(a)
    dz = _uA[0]*math.sin(a) + _uA[1]*math.cos(a)
    bf = (S[0] + _L*dx, S[1] + _L*dz)
    A_up = ((A_FAR[0], YB, A_FAR[1]), (A_FAR[0], YT, A_FAR[1]), (S[0], YT, S[1]))
    A_lo = ((A_FAR[0], YB, A_FAR[1]), (S[0], YT, S[1]),         (S[0], YB, S[1]))
    B1 = ((S[0], YB, S[1]), (S[0], YT, S[1]), (bf[0], YT, bf[1]))
    B2 = ((S[0], YB, S[1]), (bf[0], YT, bf[1]), (bf[0], YB, bf[1]))
    return [Tri(*A_up), Tri(*A_lo), Tri(*B1), Tri(*B2)]


def clippable(alpha_deg):
    """(clippable, min_displacement) for this corner, via the analytic gap search."""
    info = characterize(build_angle(alpha_deg), S, LINK_Y)
    return info["clippable"], (info.get("min_displacement") if info["clippable"] else None)


if __name__ == "__main__":
    print(f"{'turn':>6} {'interior':>9} {'clippable':>10} {'minD':>6}")
    for alpha in (43.1, 60, 75, 85, 88, 90, 92, 95, 100, 120, 137, -43.1, -90):
        ok, D = clippable(alpha)
        print(f"{alpha:+6.1f} {180-alpha:9.1f} {str(ok):>10}" + (f" {D:6.1f}" if ok else ""))
