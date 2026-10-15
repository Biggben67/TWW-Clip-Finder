"""From-rest regression for the SHEATHED roll-stab anchor (kaze r11; root-caused + fixed session 38).

The sheathed-roll milestone (session 35 wired the mid-walk draw into the ROLL solver) needs a
SHEATHED anchor at the kaze roll seam that is REST BIT-EXACT so a solved from-rest clip delivers
0-ULP (the acceptance is f32 dust; dead-end #28). Session 36 minted one
(`kaze_r11_rollstab_sheathed@twwgz`, equip-only change off idle13, `mEquipItem` 0x100).

ROOT CAUSE (session 38, corrects sessions 36 + 37): the walk-entry foot-FK is BIT-EXACT -- session
37's `f312`-toe-stream story was a measurement artifact (it compared a sim MOVE frame against a live
WAIT frame). The sole divergence was a ONE-FRAME walk-entry alignment: the sheathed anchor needs DTM
alignment noops=1, idle13 needs 2. This is NOT in-game -- it is the anchor savestate's emulator
SUB-FRAME CAPTURE PHASE. idle13 (legacy translate-lineage mint) was captured MID-FRAME, so its first
post-load frame is a pure no-op re-display (proven: it mutates zero game state) -> +1 alignment noop.
The sheathed anchor (mint_current, boundary capture -- the canonical phase, same as the future
live-RAM UI feed) has no such re-display -> noops=1. `mint.capture_rest` now DERIVES this per anchor
(advances-until-d-changes) into `seed['rest_noops']`; `rest.rest_state` reads it (legacy seeds default
REST_NOOPS=2, keeping their locked goldens bit-exact). See dead-end #30 (corrected) + #25/#28.

Ground truth: `fixtures/sheathed_walkentry_golden.json` -- jitter-proof, emulator-frame-tagged, raw
mFootData per row. Aligned by the deterministic d_frame clock (immune to run_dtm row-0 poll jitter).
Live golden -- NEVER edit the fixture to make the sim pass.
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'sheathed_walkentry_golden.json')

try:
    from harness.rollstab import rest as C
    from harness.rollstab import geometry as G
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / sheathed golden unavailable")

ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


_GOLD0 = os.path.join(os.path.dirname(_HERE), 'fixtures', 'sheathed_walkentry_seed0_golden.json')


def _sim_rows(dtm_seed=1):
    """Seed rest_state (sheathed => model_draw auto-ON, no B => no draw; rest_noops=1 from the seed),
    replay the verification walk ([straight]*NPREF + [aim]*NCRUISE); one dict per row keyed by d_frame.
    `dtm_seed` picks the make_dtm leading-poll layout the stream is DELIVERED with (session 43)."""
    _, straight, aim = C.sticks_of(ANCHOR)
    stream = [straight] * C.NPREF + [aim] * C.NCRUISE
    s = C.rest_state(ANCHOR, dtm_seed=dtm_seed)
    rows = []
    for sx, sy in stream:
        s.step(sx, sy)
        rows.append(dict(d=s._foot.st.fc0.frame, pos_x=s.pos_x, pos_z=s.pos_z,
                         m3598=s._foot.st.m3598, m359C=s._foot.prev_f312))
    return rows


def test_sheathed_full_position_bitexact():
    """The sheathed from-rest walk must be BIT-EXACT (0 ULP) every row before its solver hits are
    trusted. Align to the golden by the deterministic d_frame clock (jitter-immune): every live row
    whose d_frame the sim reproduces must match pos, the WAIT<->MOVE blend m3598, and the toe stream
    m359C bit-for-bit."""
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR
    sim = _sim_rows()
    by_d = {_bits(r['d']): r for r in sim}
    matched = 0
    bad = []
    for gr in golden['rows']:
        sr = by_d.get(_bits(gr['d_frame']))
        if sr is None:
            continue
        matched += 1
        if not (_bits(sr['pos_x']) == _bits(gr['pos_x'])
                and _bits(sr['pos_z']) == _bits(gr['pos_z'])
                and abs(sr['m3598'] - gr['m3598']) < 1e-6
                and _bits(sr['m359C']) == _bits(gr['m359C'])):
            bad.append(gr['game_frame'])
    assert matched >= 12, "too few d_frame-aligned rows matched (%d)" % matched
    assert not bad, "sheathed from-rest diverged at game_frames %s" % bad


def test_sheathed_rest_bitexact_seed0():
    """Session 43: the roll-stab clip must ship via make_dtm seed=0 (the delivery fix -- seed=1 drops
    a clustered band fine, dead-end #34). Delivering with seed=0 shifts the leading-poll layout, so
    the sim's from-rest leading no-op count changes: MEASURED live (capture_walkentry seed=0,
    jitter-immune, d_frame-aligned) the seed-0 walk-entry is BIT-EXACT with rest_state(dtm_seed=0)
    (=> noops=2, one MORE than seed=1's noops=1). Locks the seed-0 REST model against the live golden
    so a seed-0 solve/deliver is trustworthy."""
    golden = json.load(open(_GOLD0))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    by_d = {_bits(r['d']): r for r in _sim_rows(dtm_seed=0)}
    matched, bad = 0, []
    for gr in golden['rows']:
        sr = by_d.get(_bits(gr['d_frame']))
        if sr is None:
            continue
        matched += 1
        if not (_bits(sr['pos_x']) == _bits(gr['pos_x'])
                and _bits(sr['pos_z']) == _bits(gr['pos_z'])
                and abs(sr['m3598'] - gr['m3598']) < 1e-6
                and _bits(sr['m359C']) == _bits(gr['m359C'])):
            bad.append(gr['game_frame'])
    assert matched >= 12, "too few d_frame-aligned rows matched (%d)" % matched
    assert not bad, "seed-0 from-rest diverged at game_frames %s" % bad


def test_s39_hit_not_genuine_under_seed0():
    """Session 43 (a load-bearing negative result): the session-39 hit's seed=1-composed stream BYTES
    (no absorber) are NOT genuine when DELIVERED via seed=0 -- its `old` shifts ~+0.588u in z off the
    f32 razor, because the seed-0 layout's extra leading no-op eats the crawl's `start[0]`. This guards
    the distinction the session-44 fix rests on: you cannot ship the raw seed=1 bytes via seed=0; you
    must RE-COMPOSE the recipe under `dtm_seed=0` (which prepends the compensating absorber -- see
    solver.run + test_sheathed_roll_clip::test_seed0_crawl_frame_acts). Re-composing IS genuine and
    ships (test_sheathed_ship_delivery); replaying the old bytes is not. Note this run uses the DEFAULT
    seed=1 compose (no dtm_seed) ON PURPOSE -- it is exactly the raw-bytes case that must stay off-razor."""
    from harness.rollstab import solver as SV
    from tww_sim.land.land import CUT_F, CUT_A
    MOVES = ((9, (73, 254), 2), (10, (99, 183)), (4, (96, 192)), (6, (98, 188)))
    START = ((77, 249), (98, 191))
    stream = [tuple(x) for x in SV.run(ANCHOR, MOVES, A_proj=-500.0, start=START, draw_at=3)['stream']]
    s = C.rest_state(ANCHOR, dtm_seed=0)
    rows = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        rows.append((s.state & 0xFF, s.pos_x, s.pos_z))
    ci = next((i for i, r in enumerate(rows) if r[0] in (CUT_F, CUT_A)), None)
    assert ci is not None
    old, new = (rows[ci - 1][1], rows[ci - 1][2]), (rows[ci][1], rows[ci][2])
    assert not G.genuine_clip(old, new), "s39 hit unexpectedly genuine under seed-0 (re-solve may be moot)"
