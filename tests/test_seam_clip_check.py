"""Regression guard for the out-of-the-box seam-clip scanner
(:mod:`harness.collision.seam_clip_check`). Offline (no Dolphin): the GanonL synthetic seam, the
live-confirmed Hyrule (-1727,-990) f32 clip, and a flat seam that must be rejected."""
import pytest

import json
import os
import struct

from harness.collision.seam_clip_check import clip_check, ROLL_STAB_MAX

_G = os.path.join(os.path.dirname(__file__), "golden")


def _fh(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def _load(name):
    """Return (tris, link_y, S) from a hex golden (4 seam tris + stored planes)."""
    from tww_sim.core.collision import Tri, Plane
    g = json.load(open(os.path.join(_G, name)))
    tris = [Tri([_fh(x) for x in t["v"][0]], [_fh(x) for x in t["v"][1]], [_fh(x) for x in t["v"][2]],
                plane=Plane(*[_fh(x) for x in t["n"]], _fh(t["D"]))) for t in g["tris"]]
    if "seam_v_hex" in g:                       # hyrule golden: seam vertex as hex xyz
        sv = [_fh(x) for x in g["seam_v_hex"]]
        return tris, sv[1], (sv[0], sv[2])
    return tris, g["link_y"], tuple(g["seam_xz"])   # flat golden: plain floats


def test_scanner_finds_ganonl_clip():
    """GanonL grand-staircase seam — reachable by a bare roll-stab (disp < 49.22)."""
    from harness.collision.seam_model import SEAM_TRIS, LINK_Y
    S = (-847.632, -37336.613)
    r = clip_check(SEAM_TRIS, [], S, SEAM_TRIS[1], SEAM_TRIS[2],
                   require_standable=False, override_link_y=LINK_Y)
    assert r["clips"], r
    assert r["reachable_rollstab"] and not r["needs_push"]
    assert r["disp"] <= ROLL_STAB_MAX
    assert r["floor"] < r["disp"] < r["floor"] + 5.0    # near-minimal, not the old ~60 over-estimate


def test_scanner_finds_hyrule_1727_needs_push():
    """Live-confirmed Hyrule (-1727,-990) f32 clip: found, and correctly classified needs-push
    (disp ~49.96 > the 49.22 roll-stab ceiling). Guards against the ULP-scaled false-negative."""
    tris, link_y, S = _load("hyrule_seam_1727_ram.json")
    r = clip_check(tris, [], S, tris[1], tris[2], require_standable=False, override_link_y=link_y)
    assert r["clips"], r
    assert r["needs_push"] and not r["reachable_rollstab"]
    assert 49.0 < r["disp"] < 51.0, r["disp"]


@pytest.mark.slow
def test_scanner_rejects_flat_seam():
    """A flat (coplanar) seam must be screened out — no LineCheck miss, unclippable."""
    tris, link_y, S = _load("flat_seam_ram.json")
    r = clip_check(tris, [], S, tris[1], tris[2], require_standable=False, override_link_y=link_y)
    assert not r["clips"], r


def test_scanner_requires_standable_floor():
    """With require_standable and no ground mesh, a clippable seam is dropped (no valid old)."""
    from harness.collision.seam_model import SEAM_TRIS
    S = (-847.632, -37336.613)
    r = clip_check(SEAM_TRIS, [], S, SEAM_TRIS[1], SEAM_TRIS[2], require_standable=True)
    assert not r["clips"]
    assert "standable floor" in r["reason"]


def _tri_dict(poly, v0, v1, v2):
    """A region_tris dict (poly, verts, stored-plane normal via calc_pla) like the live/ISO readers."""
    from tww_sim.core.collision import Tri
    T = Tri(v0, v1, v2)
    return dict(poly=poly, v=[v0, v1, v2], n=(T.pla.nx, T.pla.ny, T.pla.nz), T=T)


def test_enumerate_pairs_near_coincident_seam_vertices():
    """enumerate_seams must PAIR two walls whose shared seam vertex is stored with a small XZ offset
    (the Hyrule false-negative: -1232.40 vs -1232.49). A hard round(x,2) bucket split them and dropped
    the corner. Also: genuinely-distant edges (units apart) must NOT merge into a phantom corner."""
    from harness.collision.seam_scan import enumerate_seams
    # two vertical walls meeting at a ~90deg corner; their seam-edge X differs by 0.09u
    wallA = _tri_dict(0, (-1232.40, 0.0, 1765.95), (-1232.40, 200.0, 1765.95), (-1127.0, 0.0, 1621.0))
    wallB = _tri_dict(1, (-1232.49, 0.0, 1765.95), (-1232.49, 200.0, 1765.95), (-1232.49, 0.0, 1900.0))
    box = (-1400.0, -1000.0, -10.0, 100.0, 1500.0, 2000.0)
    seams = enumerate_seams([wallA, wallB], box)
    assert len(seams) == 1, seams
    assert set(seams[0]["polys"]) == {0, 1} and not seams[0].get("coplanar")
    # wallC (12u away) must NOT merge into the {0,1} corner; post the coplanar-seam change it is its
    # OWN single-normal (coplanar, interior 180) edge, but the corner stays exactly the {0,1} pairing.
    wallC = _tri_dict(2, (-1220.0, 0.0, 1765.95), (-1220.0, 200.0, 1765.95), (-1220.0, 0.0, 1900.0))
    seams2 = enumerate_seams([wallA, wallB, wallC], box)
    corner = [s for s in seams2 if not s.get("coplanar")]
    solo = [s for s in seams2 if s.get("coplanar")]
    assert len(corner) == 1 and set(corner[0]["polys"]) == {0, 1}, seams2
    assert len(solo) == 1 and set(solo[0]["polys"]) == {2}, seams2


def test_scanner_finds_hyrule_near_coincident_clip_offline():
    """End-to-end regression for the near-coincident-vertex fix on REAL geometry: the live-confirmed
    Hyrule seam at (-1232.49, 0.16, 1765.95) that the pre-fix dump missed. Also guards the yspan fix
    (a wall split into lower+upper tris must still register as reaching the floor). Offline via a
    captured region fixture (no Dolphin)."""
    from harness.collision.seam_scan import load_region_tris
    from harness.collision.seam_clip_check import scan_region
    path = os.path.join(_G, "hyrule_nearcoincident_region.json")
    region, stage = load_region_tris(path)
    box = (-1500.0, -1000.0, -50.0, 100.0, 1500.0, 2000.0)
    clips = scan_region(region, box, require_standable=True, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] + 1232.49) < 0.5 and abs(c["S"][2] - 1765.95) < 0.5]
    assert hits, [tuple(round(x, 2) for x in c["S"]) for c in clips]
    assert hits[0]["reachable_rollstab"] and 36.0 < hits[0]["disp"] < 39.0, hits[0]


def test_scanner_rejects_oob_skirt_floor():
    """The seam wall must be COLLIDABLE at Link's stance (a cylinder sample feet+WALL_H inside the
    wall span), not merely reach a floor. Hyrule's stage underside (floor Y~-100, wall span
    (-1945,-99.6)) tops out below the lowest cylinder sample, so the game never touches it — the
    plane-only model reported a phantom clip there (13 of the original 40 Hyrule dump clips were this
    OOB skirt). Offline via a captured region fixture."""
    from harness.collision.seam_scan import load_region_tris
    from harness.collision.seam_clip_check import scan_region
    path = os.path.join(_G, "hyrule_oob_skirt_region.json")
    region, stage = load_region_tris(path)
    box = (400.0, 700.0, -2100.0, 300.0, 1600.0, 1900.0)
    clips = scan_region(region, box, require_standable=True, verbose=False)
    assert clips == [], [tuple(round(x, 1) for x in c["S"]) for c in clips]


def test_scanner_rejects_step_riser():
    """A short wall whose CROWN is a walkable floor is a step/ledge riser: Link ascends onto the top
    floor ('pops up above') instead of clipping. Hyrule (735,-150,323): wall span (-150.3,-75.4) with
    a floor at -75.4 at its top, only ~75 u above the standing floor (< cylinder height). Must NOT be
    reported clippable. Offline via a captured region fixture."""
    from harness.collision.seam_scan import load_region_tris
    from harness.collision.seam_clip_check import scan_region
    path = os.path.join(_G, "hyrule_step_riser_region.json")
    region, stage = load_region_tris(path)
    box = (600.0, 900.0, -230.0, 50.0, 200.0, 500.0)
    clips = scan_region(region, box, require_standable=True, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] - 734.87) < 3 and abs(c["S"][2] - 322.73) < 3]
    assert not hits, [tuple(round(x, 1) for x in c["S"]) for c in clips]


@pytest.mark.slow
def test_oblique_octagon_corners_not_false_negatives():
    """An obtuse corner clips only OFF the bisector, often across a wide window that excludes the
    head-on zone. The double-precision screen is orientation-dependent and returned EMPTY for 2 of 8
    identical kaze octagon (135°) facets, so the scanner false-negatived them (they live-CLIP). The
    coarse full-front oblique grid (phase-2b) must catch them. Offline fixture; tested via clip_check on
    the two previously-missed corners (a full scan_region would also hit the slow unclippable facets)."""
    from harness.collision.seam_scan import load_region_tris, _gather
    from harness.collision.seam_clip_check import clip_check, _seam_walls
    from harness.collision.seam_scan import enumerate_seams
    region, stage = load_region_tris(os.path.join(_G, "kaze_octagon_region.json"))
    box = (13300.0, 14100.0, -5200.0, -4900.0, 9050.0, 9850.0)
    seams = enumerate_seams(region, box)
    ground = [t for t in region if t["n"][1] >= 0.5]
    for sx, sz in [(13700.7, 9448.5), (13618.0, 9366.0)]:
        seam = min(seams, key=lambda s: (s["S"][0] - sx) ** 2 + (s["S"][2] - sz) ** 2)
        wA, wB = _seam_walls(region, seam)
        polyset = set(seam["polys"])
        ys = [v[1] for t in region if t["poly"] in polyset for v in t["v"]]
        r = clip_check(_gather(region, seam["S"], seam["S"][1]), ground,
                       (seam["S"][0], seam["S"][2]), wA, wB, require_standable=True,
                       yspan=(min(ys), max(ys)))
        assert r["clips"], ((sx, sz), r["reason"])


def test_reported_seam_y_is_standable_floor():
    """The reported seam Y must be the STANDABLE floor where the clip is performed, not the wall's base
    vertex. GanonL's staircase walls are based at y~5762 but the walkable floor is y~5852 (~90 u up);
    the wall is vertical so the clip is height-invariant, and the dump/viewer must place the seam at the
    reachable height. Regression for the GT-flagged (1105, 5762 -> 5852, -36491) case. Offline fixture."""
    from harness.collision.seam_scan import load_region_tris
    from harness.collision.seam_clip_check import scan_region
    path = os.path.join(_G, "ganonl_seamY_region.json")
    region, stage = load_region_tris(path)
    box = (1000.0, 1200.0, 5700.0, 6000.0, -36600.0, -36400.0)
    clips = scan_region(region, box, require_standable=True, verbose=False)
    assert clips, "expected the GanonL staircase clips in this region"
    for c in clips:
        assert abs(c["S"][1] - c["old"][1]) < 0.05, c          # seam Y == standable floor
        assert c["S"][1] > 5840.0, c                           # the floor (~5852), NOT the base (~5762)
