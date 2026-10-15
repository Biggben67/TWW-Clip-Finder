"""Phase-T go/no-go gate: the flooded-Hyrule TETRA-corner seam-clip ACCEPTANCE FOUNDATION.

Locks in what this session established (ROADMAP Phase T, first increment): the Tetra corner at
(-1727,-990) is a NEEDS-PUSH clip, and the coupled acceptance model reproduces the live-confirmed
clip 0-ULP. The facts asserted here are live-data-backed -- every geometry value comes from the
live RAM golden `tests/golden/hyrule_seam_1727_ram.json` (savestate slot 3), lifted into the
rollstab-convention fixture `fixtures/hyrule_tetra_geo.json` by `harness/rollstab/make_tetra_geo.py`
and served by the acceptance module `harness/rollstab/geometry_tetra.py`.

What "go" means for building the coupled solver next:
  * the bare 49.2202u roll-stab lunge is BLOCKED (lands ~0.7507u short of the seam);
  * a ~0.7506u Link CC push (the ~1.5u corner-braced-Tetra overlap x the 0.50 rank-table share)
    steers `new` behind the seam, reproducing the live golden endpoint BIT-EXACT;
  * the approach razor is threadable -- with the push fixed, `old` clips over a ~0.86u along-band at
    ~8% f32 density (kaze-like dust, not a single lottery point). The push itself is NOT a free
    continuous knob: the coupled sim produces it bit-exactly from Tetra's f32 placement, so the
    solver tests the exact f32 candidate (the seam-clip-solver discipline, extended to placement).

Pure-geometry + offline (no Dolphin, fast). If a future capture at this corner drifts, this goes RED.
"""
import math
import struct

from harness.rollstab import geometry_tetra as GT


def _push_for_target():
    """Link's per-frame CC push that closes the target clip: new - old - lunge (all f32)."""
    from tww_sim.core.fp import f32 as _f
    old = GT.TARGET["old"]
    new = GT.TARGET["new"]
    return (_f(new[0] - old[0] - GT.LUNGE[0]), _f(new[1] - old[1] - GT.LUNGE[1]))


def test_geo_loads_from_live_golden():
    """The fixture matches the live-anchored corner: facing, the two incident wall polys, the flat
    floor Y (= Phase G's 0.16327), and a ~90.57-deg corner."""
    assert GT.F == 40874                                   # world_angle_s16(new - old), 224.53 deg
    assert GT.GEO["wallA"]["poly"] == 2915                 # +X wall (tetra_clip tris[1] convention)
    assert GT.GEO["wallB"]["poly"] == 2904                 # +Z wall (tris[2])
    assert abs(GT.LINK_Y - 0.16327300667762756) < 1e-9     # flat Tetra floor (Phase G)
    assert abs(GT.GEO["interior"] - 90.566) < 0.01
    assert math.isclose(math.hypot(*GT.LUNGE), 49.2202, rel_tol=1e-5)


def test_target_old_is_a_valid_front_of_corner_position():
    old = (GT.TARGET["old"][0], GT.TARGET["old"][1])
    assert GT.in_front(GT.p32(old[0], old[1]))


def test_bare_rollstab_is_blocked_needs_push():
    """The 49.2202u lunge alone does NOT clip -- it lands ~0.7507u short of the seam. This is the
    whole reason the Tetra push exists in the north-star route."""
    old = (GT.TARGET["old"][0], GT.TARGET["old"][1])
    new = (GT.TARGET["new"][0], GT.TARGET["new"][1])
    assert GT.pred_genuine(old) is False                   # push defaults to 0 == the bare roll
    bare = GT.coupled_new(old)
    short = math.hypot(new[0] - bare[0], new[1] - bare[1])
    assert 0.74 < short < 0.76                             # ~0.7507u short (live-anchored)


def test_coupled_push_reproduces_live_clip_bit_exact():
    """new == f32(old + push + lunge) reproduces the live golden endpoint 0-ULP, and it is a genuine
    clip (CrrPos not blocked, old in front of both walls, new behind the seam)."""
    old = (GT.TARGET["old"][0], GT.TARGET["old"][1])
    new = (GT.TARGET["new"][0], GT.TARGET["new"][1])
    push = _push_for_target()
    assert 0.74 < math.hypot(*push) < 0.76                 # ~0.7506u on Link (~1.5u overlap x 0.50)
    coupled = GT.coupled_new(old, push)
    assert coupled == new                                  # BIT-EXACT vs the live capture
    assert GT.pred_genuine(old, push) is True


def test_approach_razor_is_a_threadable_band_not_a_point():
    """With the push fixed at the authoritative value, `old` clips over a wide along-band at ~8% f32
    density -- kaze-like dust the from-rest knobs can thread, NOT a single lottery point. Asserting
    the band EXISTS (not a fitted width): >=150 genuine f32 samples over the +-0.5u ray scan, spanning
    >=0.5u. (Do not tighten into a fitted ribbon -- seam-clip-solver.md.)"""
    push = _push_for_target()
    hits = []
    al = -0.5
    while al <= 0.5:
        from tww_sim.core.fp import f32 as _f
        ox = _f(GT.TARGET["old"][0] + al * GT.DIRX)
        oz = _f(GT.TARGET["old"][1] + al * GT.DIRZ)
        if GT.pred_genuine((ox, oz), push):
            hits.append(al)
        al += 0.0002
    assert len(hits) >= 150                                # dense enough to thread (measured ~394)
    assert (max(hits) - min(hits)) >= 0.5                  # wide band (measured ~0.857u)
