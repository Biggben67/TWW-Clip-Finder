"""Offline regression for the seam-clip model (tww_sim.core.collision + harness.collision.seam_model).

Guards the two things that must not drift:
  1. Bit-exact reproduction of the live-captured LineCheck: for every triangle the game tested on the
     row-1 clip line (ganonl_seam_capture.json), the port's cross_lin_tri hit/miss matches the game's
     recorded return, using the game's STORED plane.
  2. The known GanonL row-1 displacement clips (collision leaves Link at the target).
"""
import json
import os

import struct

import pytest

from tww_sim.core.collision import Tri, Plane, cross_lin_tri, calc_pla
from harness.collision.seam_model import predict_clip
from harness.collision.angle_experiment import build_angle, S, LINK_Y
from harness.collision.gap_search import find_clip

_CAP = os.path.join(os.path.dirname(__file__), "..", "harness", "collision",
                    "ganonl_seam_capture.json")


def _bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


_GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "calc_pla_ram.json")


def _f_from_hex(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def test_calc_pla_bit_exact_vs_ram():
    """calc_pla (frsqrte-based cM3d_CalcPla port) must reproduce the game's RAM-stored planes
    bit-for-bit — this is what lets the sim run faithfully on synthetic geometry."""
    data = json.load(open(_CAP))
    for t in data[:4]:
        p = calc_pla(t["A"], t["B"], t["C"])
        for got, want in [(p.nx, t["n"][0]), (p.ny, t["n"][1]), (p.nz, t["n"][2]), (p.d, t["D"])]:
            assert _bits(got) == _bits(want), f"tri n={t['n']}: {got!r} != {want!r}"


def test_calc_pla_golden_ram_planes():
    """Full-precision RAM golden (Hyrule, hex-encoded f32) covering the Force25Bit-sensitive
    triangles — the ones that were 1-2 ULP off before the exact PSVECCrossProduct lanes, fused
    Newton fnmsubs, and the 25-bit frC round in VECMag. calc_pla is bit-exact on all 4506 Hyrule
    tris; these 10 are the permanent offline guard (poly 4/20/37/72/127/128 exercise the 25-bit
    path, 0/1/2/5 are the always-exact cases)."""
    for t in json.load(open(_GOLDEN)):
        A = [_f_from_hex(h) for h in t["A"]]
        B = [_f_from_hex(h) for h in t["B"]]
        C = [_f_from_hex(h) for h in t["C"]]
        p = calc_pla(A, B, C)
        want = [int(t["n"][0], 16), int(t["n"][1], 16), int(t["n"][2], 16), int(t["D"], 16)]
        got = [_bits(p.nx), _bits(p.ny), _bits(p.nz), _bits(p.d)]
        assert got == want, f"poly {t['poly']}: got {[hex(g) for g in got]} != {[hex(w) for w in want]}"


def test_linecheck_matches_captured_game_returns():
    data = json.load(open(_CAP))
    checked = 0
    for d in data:
        if not d.get("A"):
            continue
        tri = Tri(d["A"], d["B"], d["C"], plane=Plane(*d["n"], d["D"]))
        hit, _ = cross_lin_tri(tuple(d["ls"]), tuple(d["le"]), tri, a=True, b=False)
        assert hit == bool(d["ret"]), f"tri n={d['n']}: port hit={hit}, game ret={d['ret']}"
        checked += 1
    assert checked >= 9   # the 4 seam walls + roof/other tris the game line-checked


def test_row1_clips():
    clipped, info = predict_clip((-817.6296387, -37307.21875), (-855.1299438, -37343.96094))
    assert clipped, info
    assert not info["line_hit"] and not info["wall_hit"], info


def test_short_displacement_blocks():
    # Under the 35 u cylinder radius toward the wall: WallCorrect must push back (no clip).
    clipped, info = predict_clip((-817.6296387, -37307.21875), (-830.0, -37320.0))
    assert not clipped, info


def test_analytic_gap_finds_grid_false_negatives():
    """The analytic gap search (gap_search.find_clip) must find a clip at the two synthetic corner
    angles the OLD brute-force grid spuriously reported unclippable: interior 90 deg (alpha=90) and
    120 deg (alpha=60). Both DO clip; the grid missed the ~1e-3-u offset razor. Guards against any
    regression back to grid-style false negatives."""
    for alpha in (90.0, 60.0):
        ok, rec = find_clip(build_angle(alpha), S, LINK_Y, dir_half_deg=30.0, dir_step_deg=1.0)
        assert ok, f"alpha={alpha}: analytic search failed to find a clip (false negative)"
        assert rec is not None


@pytest.mark.slow
def test_flat_seam_unclippable():
    """A real FLAT (180 deg / coplanar) vertical seam is unclippable, verified at fan resolution.

    SLOW (~55s, deselected by default; runs in CI / ``pytest -m slow``): this is a full-resolution
    characterization sweep -- ~9.7M bit-exact ``crr_pos_walls`` calls (61 directions x 160k offsets).
    The cost is intrinsic: ``off_step`` (5e-8) is deliberately finer than the seam's plane fan
    (~1.4e-7 here), and the module docstring makes "no gap found" trustworthy ONLY when the offset
    step is finer than the fan -- so the resolution cannot be coarsened without weakening the proof.
    The fast bit-exact guards (calc_pla goldens, row-1 clips, the 1727 anchor) stay in the default run.
    Golden = the Hyrule flat wall at x=-157.578 (GZLJ01), seam pair poly 2360/2355 whose stored
    planes differ by only 1 ULP in nx + 5 ULP in D. The analytic gap search, scanning the offset
    an order of magnitude finer than that fan, finds NO clip: the two coplanar quads tile the wall,
    so a crossing past the seam for one triangle lands inside the neighbour's footprint and its
    ~1-ULP-different plane still catches it. There is no angular divergence (unlike a real corner)
    to make both miss. See knowledge/mechanics/seam-clip.md."""
    from tww_sim.core.collision import Tri, Plane
    g = json.load(open(os.path.join(os.path.dirname(__file__), "golden", "flat_seam_ram.json")))
    tris = [Tri([_f_from_hex(x) for x in t["v"][0]],
                [_f_from_hex(x) for x in t["v"][1]],
                [_f_from_hex(x) for x in t["v"][2]],
                plane=Plane(*[_f_from_hex(x) for x in t["n"]], _f_from_hex(t["D"])))
            for t in g["tris"]]
    ok, rec = find_clip(tris, tuple(g["seam_xz"]), g["link_y"],
                        dir_half_deg=30.0, dir_step_deg=1.0, off_half=0.004, off_step=5e-8)
    assert not ok, f"flat seam unexpectedly clipped: {rec}"


def _load_hyrule_1727():
    """Build the 4 seam Tris (STORED planes) + anchor from the live-captured hex golden."""
    from tww_sim.core.collision import Tri, Plane
    g = json.load(open(os.path.join(os.path.dirname(__file__), "golden",
                                     "hyrule_seam_1727_ram.json")))
    tris = [Tri([_f_from_hex(x) for x in t["v"][0]],
                [_f_from_hex(x) for x in t["v"][1]],
                [_f_from_hex(x) for x in t["v"][2]],
                plane=Plane(*[_f_from_hex(x) for x in t["n"]], _f_from_hex(t["D"])))
            for t in g["tris"]]
    link_y = _f_from_hex(g["seam_v_hex"][1])   # Link floor Y == the seam vertex Y (~0.163)
    old = (_f_from_hex(g["old_hex"][0]), _f_from_hex(g["old_hex"][1]))
    new = (_f_from_hex(g["new_hex"][0]), _f_from_hex(g["new_hex"][1]))
    return tris, link_y, old, new


@pytest.mark.slow
def test_hyrule_1727_f32_clip_anchor():
    """Live-confirmed Hyrule seam clip at (-1727,-990) reproduced in the model as an f32 anchor.
    Ground truth (handoff-06d, live): old~(-1692.31,-955.02) -> new~(-1727.37,-990.66), disp~49.99,
    Link y~0.163. This guards TWO things:
      1. The exact f32 (old,new) pair clips (collision leaves Link at new).
      2. min_f32_clip — the RELIABLE f32-lattice search — finds the seam clippable with a
         minimum displacement matching the live ~50u (NOT the double-precision phantom the old
         double search reported). See knowledge/mechanics/seam-clip.md (f32 viability)."""
    from tww_sim.core.collision import crr_pos_walls
    from tww_sim.core.fp import f32 as _f
    from harness.collision.gap_search import min_f32_clip, settle
    tris, link_y, old, new = _load_hyrule_1727()

    # (1) the exact captured f32 pair clips
    o = (old[0], link_y, old[1])
    _, info = crr_pos_walls(o, (new[0], link_y, new[1]), tris)
    assert not info["line_hit"] and not info["wall_hit"], info

    # (2) reliable f32-lattice search re-finds it near the live ~50u displacement
    settled = settle(tris, old, link_y)
    assert abs(settled[0] - old[0]) < 1e-3 and abs(settled[2] - old[1]) < 1e-3   # old already settled
    r = min_f32_clip(tris, settled, (-1727.37, -990.66), link_y, box_ulps=400)
    assert r is not None, "min_f32_clip found no clip at a live-confirmed clippable seam"
    assert 49.0 < r["disp"] < 51.0, f"min f32 displacement {r['disp']} off the live ~49.99"
    assert r["n_clips"] >= 1


def test_hyrule_1727_short_displacement_blocks():
    """Control: a sub-cylinder step toward the same seam must be blocked (no phantom clip)."""
    from tww_sim.core.collision import crr_pos_walls
    tris, link_y, old, _ = _load_hyrule_1727()
    o = (old[0], link_y, old[1])
    _, info = crr_pos_walls(o, (-1710.0, link_y, -972.0), tris)   # ~24u step, under the radius
    assert info["line_hit"] or info["wall_hit"], info
