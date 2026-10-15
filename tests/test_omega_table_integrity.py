"""test_omega_table_integrity.py — offline guard on superswim/tables/omega_table_full.csv.

The 2-D camera-rate table (camera_arbitrary.CameraArbitrary) maps a held C-stick (csx,csy) to the
per-frame camera-rate command omega. It was gold re-dumped over the FULL 65536-cell grid
(harness/capture/omega_grid_redump.py: fast cam-reset + settle+verify, validated bit-identical to
loadstate-per-cell; 4-instance parallel via run_parallel_dump.py). The predecessor covered only
csx 0..15, so camera_arbitrary raised KeyError for off-grid (csx,csy) with csy != 128.

Offline invariants (no Dolphin): full coverage, bounded, correct saturation constants, and — the
strongest lock — the full grid must agree with every cell in the sparse gold capture omega_table.csv.
"""
import os, csv
import pytest

TBL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(TBL, "tww_sim", "core", "tables", "omega_table_full.csv")
FINE = os.path.join(TBL, "tww_sim", "core", "tables", "omega_table.csv")


def _load(p):
    return {(int(r["csx"]), int(r["csy"])): int(r["omega"]) for r in csv.DictReader(open(p))}


@pytest.fixture(scope="module")
def full():
    return _load(FULL)


def test_full_grid_complete(full):
    assert len(full) == 256 * 256, f"expected 65536 cells, got {len(full)}"
    missing = {(x, y) for x in range(256) for y in range(256)} - set(full)
    assert not missing, f"{len(missing)} (csx,csy) cells missing, e.g. {sorted(missing)[:10]}"


def test_omega_bounded(full):
    bad = [(c, v) for c, v in full.items() if abs(v) > 600]
    assert not bad, f"omega out of sane range (|omega|<=600): {bad[:10]}"


def test_saturation_constants(full):
    # pure-horizontal saturation at csy=128 (the camera_exact model constants)
    assert full[(255, 128)] == 546 and full[(175, 128)] == 546, "positive saturation != +546"
    assert full[(0, 128)] == -547 and full[(81, 128)] == -547, "negative saturation != -547"
    assert full[(128, 128)] == 0, "neutral csx not 0"


def test_matches_gold_fine_captures(full):
    """Every cell in the loadstate-gold omega_table.csv must match the full grid exactly."""
    fine = _load(FINE)
    bad = [(c, full.get(c), v) for c, v in fine.items() if full.get(c) != v]
    assert not bad, f"{len(bad)} cells disagree with gold omega_table.csv: {bad[:15]}"


def test_camera_exact_omega_cmd_matches_grid(full):
    """camera_exact.omega_cmd's hand-transcribed _OMEGA_POS/_OMEGA_NEG dicts + saturation must equal
    the authoritative full grid on the pure-horizontal row (csy=128) for every csx. Locks against
    silent drift — the dict was missing csx 109..112 (=-1), fixed 2026-07-01."""
    from tww_sim.core.camera import camera_exact as CE
    bad = [(csx, full[(csx, 128)], CE.omega_cmd(csx, 128))
           for csx in range(256) if CE.omega_cmd(csx, 128) != full[(csx, 128)]]
    assert not bad, f"{len(bad)} csx: omega_cmd != grid[csx,128]: {bad[:15]}"
