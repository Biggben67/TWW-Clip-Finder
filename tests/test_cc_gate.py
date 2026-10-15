"""Offline gate for the CC-push COUPLED stepper against a LIVE capture (ROADMAP Phase C).

Replays a locked live capture (`fixtures/hyrule_cc_push.json`, from
`harness/rollstab/capture_cc_push.py` on slot 3) through the coupled Link+Tetra stepper WITHOUT
Dolphin and diffs every frame bit-for-bit. The scenario: Tetra teleported into the corner (WallCorrect
braces her), Link rolls in from far out and CONVERGES into her, and the Co push fires while she is
wall-braced -- the clip's push geometry, staged by teleport.

What this locks in as bit-exact (0 ULP), the wiring + coupled physics:
  * Link's wall-approach FRONT_ROLL, frame by frame (Phase-W corner walls in the stepper);
  * Tetra's teleport-into-corner WallCorrect eject + braced hold (Phase-C BG collision), coupled;
  * the CC push wired at the decomp point in posMove -- Link stays bit-exact right up to the frame the
    push is first consumed, proving the push is applied in the right place and nowhere else.

Push frames (2026-07-10): CLOSED. The overlap geometry (`body_cyl.roll_co_center`) is now fed the
body lean (`shape_z = m351C>>1`, the `setWorldMatrix` base z-tilt); the curved approach carries a
nonzero turn lean into the roll (seeded at roll entry from the live `m351C`) that shifts the animated
Co centre until it decays, and the OLD clean-pose centre made Link drift once the push converged. With
the lean fed in, every FRONT_ROLL push frame is bit-exact -- see `test_coupled_push_frames_bitexact`.
(The early-frame residual was NOT the oldframe-morf, as previously supposed; the morf touches only
roll frame 0. See `body_cyl.roll_co_center` + `knowledge/mechanics/actor-push.md`.)

Remaining open (separate gap, not the push): after the roll ENDS the neutral-hold capture decelerates
in MOVE (proc 6), and the roll->MOVE exit is not bit-exact (the known "mid-run stop -> re-walk" gap,
README Phase-W). The clip fires a CUT out of the roll, not a MOVE exit, so this does not gate it; the
push-frame test is scoped to the FRONT_ROLL frames.
"""
import json
import os

import pytest

_HERE = os.path.dirname(__file__)
_FIX = os.path.join(_HERE, "..", "fixtures", "hyrule_cc_push.json")
_WALLS = os.path.join(_HERE, "..", "fixtures", "hyrule_tetra_walls_ordered.json")

# The proven bit-exact window (see the fixture / capture): from Tetra's placement (f10) through the
# last frame before the push perturbs Link (f14). Every frame here is 0 ULP for BOTH actors.
PREPUSH_LAST = 14
FRONT_ROLL_PROC = 30            # daPyProc_FRONT_ROLL_e; the push-active roll frames


def _load():
    from tww_sim.land.walls import load_ordered_mesh
    from harness.rollstab.cc_stepper import couple_replay
    fix = json.load(open(_FIX))
    walls = load_ordered_mesh(_WALLS)
    res = couple_replay(fix["frames"], fix["tetra_placed_at"], fix["tetra_placed_xz"],
                        walls, fix["ground_y"])
    return fix, res


def test_fixture_present():
    assert os.path.exists(_FIX), "run: python -m harness.rollstab.capture_cc_push out=... (slot 3)"


@pytest.mark.slow
def test_coupled_prepush_and_brace_bitexact():
    """Link's wall-approach roll AND Tetra's teleport-into-corner brace are bit-exact (0 ULP) every
    frame from placement through the last pre-push frame -- and the push, once it engages, does not
    perturb any earlier frame. Proves the coupled stepper + the push wiring point."""
    _fix, res = _load()
    pre = [r for r in res if r["f"] <= PREPUSH_LAST]
    assert pre, "no pre-push frames in the capture"
    for r in pre:
        assert r["dlx"] == 0 and r["dlz"] == 0, (
            "Link not bit-exact at f%d (pre-push wall-held roll): dlx=%d dlz=%d"
            % (r["f"], r["dlx"], r["dlz"]))
        assert r["dtx"] == 0 and r["dtz"] == 0, (
            "Tetra not bit-exact at f%d (teleport-into-corner brace): dtx=%d dtz=%d"
            % (r["f"], r["dtx"], r["dtz"]))
    # sanity: the placement frame is inside this window and the push engages right after it.
    assert any(r["placed"] for r in pre)


@pytest.mark.slow
def test_coupled_push_frames_bitexact():
    """Link (and Tetra) stay bit-exact through EVERY push-active FRONT_ROLL frame -- the full coupled
    clip physics while the push is live. Closed 2026-07-10 by feeding the body lean (shape_z) to the
    Co centre; previously RED from the clean-pose centre drifting once the push converged. Scoped to
    the roll frames (proc == FRONT_ROLL): after the roll exits to MOVE the neutral-hold capture hits
    the separate roll->walk-exit gap (see the module docstring), which the clip's roll->CUT never
    touches."""
    _fix, res = _load()
    roll = [r for r in res if r["proc"] == FRONT_ROLL_PROC]
    assert len(roll) >= 10, "capture has too few FRONT_ROLL frames to be meaningful"
    for r in roll:
        assert r["dlx"] == 0 and r["dlz"] == 0, (
            "Link diverges at f%d (roll): dlx=%d dlz=%d" % (r["f"], r["dlx"], r["dlz"]))
        assert r["dtx"] == 0 and r["dtz"] == 0, (
            "Tetra diverges at f%d (roll): dtx=%d dtz=%d" % (r["f"], r["dtx"], r["dtz"]))
