"""Sheathed-roll WIRING gate (session 35): the mid-walk sword pull-out routed into the ROLL path.

WHAT THIS LOCKS (OFFLINE mechanics, not yet a live 0-ULP clip gate):
  * `rest.rest_state` auto-enables `model_draw` for a SHEATHED anchor (sword-drawn stays OFF ->
    byte-identical, covered by the 336-test suite staying green).
  * `solver.run(draw_at=..)` feeds a single B rising edge during the walk-up; with model_draw ON the
    sword draw completes before the A press (`sword_drawn` True), so the roll routes to a CUT_F.
  * The draw is LOAD-BEARING: with `draw_at=None` a sheathed walk stays sword-sheathed, the roll->CUT
    gate (`land/procs/roll.py:79`) fails, and NO CUT fires (the roll exits to MOVE).

Seeded from a SYNTHETIC sheathed seed (the drawn kaze roll idle13 seed with equip forced sheathed) so
this runs offline with no new anchor. The live 0-ULP gate on a real minted sheathed anchor is the
next (LIVE) increment -- see README ## Status. Once that anchor exists this file gains its live golden.
"""
import copy
import os

import pytest

try:
    from harness.rollstab import geometry as G
    from harness.rollstab import rest as C
    from harness.rollstab import solver as SOLV
    from tww_sim.land.land import CUT_F, CUT_A, MOVE
    _HAVE = C.rest_state is not None
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness import failed")

DRAWN = 'kaze_r11_rollstab_idle13@twwgz'


@pytest.fixture
def sheathed(monkeypatch):
    """Patch G.load_seed to return a SHEATHED variant of the drawn idle13 seed."""
    real = G.load_seed(DRAWN)
    sh = copy.deepcopy(real)
    sh['mEquipItem'] = 0x100                 # sheathed on back (session-34 capture)
    sh.pop('equip_item', None)
    sh['sword_drawn'] = False

    def _patched(anchor):
        return copy.deepcopy(sh) if anchor == DRAWN else real

    monkeypatch.setattr(G, 'load_seed', _patched)
    monkeypatch.setattr(C.G, 'load_seed', _patched)   # rest.py imports geometry as G
    SOLV._BASE.clear()
    yield DRAWN
    SOLV._BASE.clear()


def test_rest_state_sheathed_enables_model_draw(sheathed):
    s = C.rest_state(sheathed)
    assert s._model_draw is True
    assert s.sword_drawn is False
    assert s._foot.st._walk == 'walk' and s._foot.st._dash == 'dash'


def test_draw_b_flips_anim_set_and_stays_capped(sheathed):
    """A mid-walk draw completes at the speedF cap and swaps the foot anim set base->sword."""
    _, _straight, aim = C.sticks_of(sheathed)
    s = C.rest_state(sheathed)
    flipped_at = None
    capped = True
    for k in range(20):
        s.step(aim[0], aim[1], buttons=(G.B_BTN if k == 3 else 0))
        if s.sword_drawn and flipped_at is None:
            flipped_at = k
            assert s._foot.st._walk == 'walks' and s._foot.st._dash == 'dashs'
        if flipped_at is not None and abs(s.speedF - 17.0) > 1e-6:
            capped = False
    assert flipped_at == 8, "draw completes 5 frames after the raw B feed (feed@3 -> flip@8)"
    assert capped, "speedF holds at the 17 cap across the phase-preserved set swap"


def test_sheathed_roll_fires_cut_f(sheathed):
    """The full sheathed roll-stab code path: draw mid-walk -> roll -> CUT_F out of the roll."""
    r = SOLV.run(sheathed, moves=[], draw_at=3)
    assert r is not None and r.get('fired'), "a cut must fire out of the roll"
    assert r['cut_proc'] == CUT_F, "roll->CUT routes to the forward thrust"
    assert r['spF_at_A'] == 17.0, "the roll needs the full speedF-17 cap at the A press"
    # exactly one draw-B in the walk-up, before the roll's cut-B
    btns = [i for i, row in enumerate(r['stream']) if row[2] == G.B_BTN]
    assert len(btns) == 2, "one draw-B during the walk + one cut-B out of the roll"


def test_no_draw_no_cut(sheathed):
    """The draw is load-bearing: without it, the sheathed roll->CUT gate fails (no CUT fires)."""
    r = SOLV.run(sheathed, moves=[], draw_at=None)
    assert r is not None
    # sword never drawn -> _roll_exit routes to MOVE, not a CUT
    assert not r.get('fired'), "a sheathed roll must NOT fire a CUT (sword_drawn False)"
