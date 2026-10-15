"""OFFLINE regression locking the session-69 camera finding (ROADMAP Phase A exp.5).

Live RE proved there is NO free-space auto-camera follow that moves csangle: walking Link with a
centered C-stick (omega_cmd 0) leaves csangle bit-frozen regardless of facing/travel (dead-end #56,
knowledge/mechanics/camera.md). The ONLY csangle contamination without a C-stick input is bumpCheck
camera-WALL collision, which harness/rollstab/cam_clean.py DETECTS (per steer: detect, not model).

These goldens are LIVE captures (leash_cap.py, csangle per frame; arm omitted -- csangle drift is
the load-bearing signal, a lateral bumpCheck push that arm-compression alone misses):
  * cam_clean_open_golden.json     -- open flat arena straight walk: csangle drift == 0 EVERY frame
                                      (the invariant: no free-space follow). CLEAN.
  * cam_clean_ganona_straight_golden.json -- a straight-down-corridor walk in GanonA: csangle
                                      creeps +20 hw at f11 (bumpCheck). DIRTY. (The shipped clip's
                                      real approach walks the aim line, which the mint keeps clean.)
  * cam_clean_kaze157_screen_golden.json -- the mint.cam_clean_screen PARK-based probe (session 69
                                      fold-in) on the delivered kaze-r11 157 corridor: park on the
                                      aim line, freeze the cam at the aim csangle, walk 40 frames
                                      down the bearing with a fixed stick + centered horizontal
                                      C-stick. csangle drift == 0 AND the arm never pulls in. CLEAN
                                      -- the same verdict the mint relies on to accept a park.

Locked-test rules: a red row means the detector logic or the finding regressed; do NOT edit a
golden to make it pass.
"""
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIX = os.path.join(os.path.dirname(_HERE), 'fixtures')

try:
    from harness.rollstab.cam_clean import evaluate
    _HAVE = True
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="harness.rollstab.cam_clean unavailable")


def _rows(name):
    with open(os.path.join(_FIX, name)) as f:
        return json.load(f)["rows"]


def test_open_arena_csangle_frozen_no_free_space_follow():
    """THE invariant: a centered-C-stick walk in open space leaves csangle bit-frozen on EVERY
    frame. This is the live proof that there is no behind-Link follow feeding csangle."""
    rows = _rows("cam_clean_open_golden.json")
    assert len(rows) > 40
    assert all(r["cs"] == rows[0]["cs"] for r in rows)      # zero drift, every frame
    res = evaluate(rows, tol=0)
    assert res["clean"] is True
    assert res["max_dcs"] == 0
    assert res["first_drift"] is None


def test_corridor_straight_walk_flagged_dirty():
    """The detector flags bumpCheck contamination: the GanonA straight-corridor walk creeps
    csangle +20 hw at f11 under a centered C-stick (provably environmental, since free space is
    inert)."""
    rows = _rows("cam_clean_ganona_straight_golden.json")
    res = evaluate(rows, tol=0)
    assert res["clean"] is False
    assert res["max_dcs"] == 20
    assert res["first_drift"]["f"] == 11


def test_park_screen_kaze157_clean():
    """The park-based invariant screen (mint.cam_clean_screen) reports CLEAN on the delivered kaze
    157 corridor: a live capture of the fixed-stick / centered-horizontal-C-stick approach walk.
    csangle holds bit-frozen every frame AND the eye/center arm never pulls into a wall -- so the
    mint accepts this park + frozen csangle. This is the arm-inclusive golden (the screen reads the
    dCamera_c eye/center chain, unlike the csangle-only leash captures)."""
    rows = _rows("cam_clean_kaze157_screen_golden.json")
    assert len(rows) >= 40
    assert all("arm" in r for r in rows)                    # screen reads the arm, not just csangle
    assert all(r["cs"] == rows[0]["cs"] for r in rows)      # csangle bit-frozen, every frame
    res = evaluate(rows, tol=0)
    assert res["clean"] is True
    assert res["max_dcs"] == 0
    assert res["first_drift"] is None
    assert (rows[0]["arm"] - min(r["arm"] for r in rows)) / rows[0]["arm"] <= 0.15  # arm holds


def test_evaluate_tolerance_gate():
    """A tolerance above the observed drift accepts the corridor (a corridor whose creep stays
    under the from-rest budget is still usable); tol below it rejects."""
    rows = _rows("cam_clean_ganona_straight_golden.json")
    assert evaluate(rows, tol=20)["clean"] is True
    assert evaluate(rows, tol=19)["clean"] is False
