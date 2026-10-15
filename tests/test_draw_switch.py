"""Gate the mid-walk SWORD PULL-OUT model (session 34), live-data 0-ULP.

The scanner's ROLL dispatch needs a SHEATHED anchor to draw the sword mid-walk (roll->cut requires
sword_drawn). The sim froze the foot anim set (WALK/DASH vs sword WALKS/DASHS) at FootSpeedF
construction, so it could not represent the draw. Decomp (d_a_player_main.cpp): getAnmData keys the
leg table off mEquipItem (12951), setMoveAnime re-fetches it every frame (12734), and procMove's
steady setBlendMoveAnime(-1.0f) (6229) passes i_morf<0 -> NO oldframe-morf. So the swap is an
INSTANTANEOUS, phase-preserved pose jump the frame mEquipItem flips to daPyItem_SWORD_e (3976).

Model: FootSpeedF.draw_sword() flips _walk/_dash base->sword; LandState(model_draw=True) auto-triggers
it DRAW_DELAY acted-frames after a B rising edge while walking sheathed.

Live capture (harness.rollstab.capture_draw -> fixtures/walk_draw.json): on land_flatwalk, a straight
UP walk drawn at the start (UP+B) then decelerated through the WALK<->DASH blend. mEquipItem flips 5
frames after the raw B feed. The DASHS legs differ from DASH, so the switch TIMING matters:
- the from-rest walk with the anim-set switch (auto model_draw=True) is 0-ULP vs live, and
- BOTH naive baselines DRIFT: never-draw (stays DASH) misses the post-draw decel frames; always-drawn
  (DASHS from frame 0) misses the pre-draw DASH accel frame.

Offline (no Dolphin): the live per-frame pos_z log is replayed from the fixture.
"""
import json
import os

import pytest


from tests._anim_data import WALK_DASH, require
require(WALK_DASH, "the walk/dash anim banks")
from harness.rollstab.validate_draw import run, run_auto, _summ

_HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(_HERE, os.pardir, 'fixtures', 'walk_draw.json')


@pytest.fixture(scope='module')
def fix():
    with open(FIX) as f:
        return json.load(f)


def test_auto_model_bit_exact(fix):
    """LandState(model_draw=True) fed the RAW captured inputs (incl. UP+B) reproduces the live walk
    pos_z BIT-FOR-BIT on every frame -- the full chain B edge -> INPUT_DELAY -> DRAW_DELAY -> anim-set
    flip is 0-ULP."""
    mx, bad = _summ(run_auto(fix))
    assert mx == 0, f"auto draw model off by {mx} ULP on rows {bad}"


def test_switch_at_flip_frame_bit_exact(fix):
    """Poking the anim-set switch at the live mEquipItem-flip frame reproduces live 0-ULP."""
    mx, bad = _summ(run(fix, switch_at=fix['f_flip']))
    assert mx == 0, f"switch@{fix['f_flip']} off by {mx} ULP on rows {bad}"


def test_never_draw_drifts(fix):
    """Never drawing (stays base DASH) DRIFTS on the post-draw DASHS decel frames -- proves the sword
    leg set genuinely differs and the draw must be modeled (not left sheathed)."""
    mx, bad = _summ(run(fix))            # sword=False, no switch
    assert mx > 0 and bad, "never-draw unexpectedly matched live -- the DASHS decel frames should drift"


def test_always_drawn_drifts(fix):
    """Drawing from frame 0 (DASHS the whole walk) DRIFTS on the pre-draw DASH accel frame -- proves
    the switch TIMING matters, not just the final set (the static sword_drawn=True is wrong)."""
    mx, bad = _summ(run(fix, always_sword=True))
    assert mx > 0 and bad, "always-drawn unexpectedly matched live -- the pre-draw DASH frame should drift"


def test_switch_one_frame_early_drifts(fix):
    """The switch lower bound is pinned by physics (the pre-flip _dash accel frame feeds the next
    frame's speedF via the 1-frame toe delay): switching one frame BEFORE the live flip drifts."""
    mx, _ = _summ(run(fix, switch_at=fix['f_flip'] - 1))
    assert mx > 0, "switching one frame early should drift (the pre-flip DASH accel frame is discriminating)"
