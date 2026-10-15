"""Session-57 Phase-A'/B2 ranking: the TRUE 2D dust metric (`_dust2d` + `_dust_dist`).

The session-56 B2 ranker (`_dcol`) measured perp distance to a 1e-3-ROUNDED column set -- a
candidate could rank razor-close (dcol 1e-5) while sitting 3-12u of along away from any real
dust (dead-end #41's measurement). The fix ranks against the EXACT sliver point cloud in the
seam's (along, perp) frame with the drill's x200 perp weighting. These tests lock:

  1. `_dust_dist`'s outward-walk nearest lookup == brute force, on adversarial synthetic clouds.
  2. `_dust2d`'s disk cache round-trips bit-identically (a draw pays the scan once per seam).
  3. The scan's points are genuinely dust: every returned (along, perp) maps to a pred_genuine
     point, and the cloud is consistent with the `_genuine_perps` column band that windows it.
"""
import math
import random

import pytest

try:
    from harness.rollstab import solver as SV
    from harness.rollstab.geometry import SEAM as KAZE
    _HAVE = True
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness unavailable")


def _brute(P, A, along, perp, pw=200.0):
    return min((math.hypot((p - perp) * pw, a - along) for p, a in zip(P, A)),
               default=float('inf'))


def test_dust_dist_matches_bruteforce():
    rng = random.Random(57)
    for trial in range(20):
        pts = sorted((rng.uniform(-0.2, 0.2), rng.uniform(-50.0, -35.0))
                     for _ in range(rng.randrange(1, 60)))
        P = [p for p, _ in pts]
        A = [a for _, a in pts]
        for _ in range(50):
            q_perp = rng.uniform(-3.0, 3.0)
            q_along = rng.uniform(-55.0, -30.0)
            assert SV._dust_dist(P, A, q_along, q_perp) == pytest.approx(
                _brute(P, A, q_along, q_perp), abs=0.0)


def test_dust_dist_empty_cloud_is_inf():
    assert SV._dust_dist([], [], -40.0, 0.0) == float('inf')


@pytest.mark.slow
def test_dust2d_cache_roundtrip_and_points_are_genuine():
    # Coarse steps keep the scan to a few thousand pred_genuine calls; the cache key includes
    # the steps, so this never collides with a real draw's cache.
    kw = dict(astep=1.0, pstep=5e-4, pmargin=0.002)
    P1, A1 = SV._dust2d(KAZE, **kw)
    P2, A2 = SV._dust2d(KAZE, **kw)          # second call must come from the disk cache
    assert (P1, A1) == (P2, A2)
    assert P1 == sorted(P1)
    assert len(P1) == len(A1) and len(P1) > 0     # the kaze seam has genuine dust in band
    from tww_sim.core.fp import f32 as _F
    Sx, Sz = KAZE.S
    for p, a in list(zip(P1, A1))[:50]:
        x = Sx + a * KAZE.DIRX + p * KAZE.PX
        z = Sz + a * KAZE.DIRZ + p * KAZE.PZ
        assert KAZE.pred_genuine((_F(x), _F(z)))
    gp = SV._genuine_perps(KAZE)
    assert gp and min(P1) >= gp[0] - 0.002 - 5e-4 and max(P1) <= gp[-1] + 0.002 + 5e-4
