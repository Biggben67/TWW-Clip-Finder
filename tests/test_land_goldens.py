"""OFFLINE land-tech regression: the LandState sim vs per-frame LIVE recordings.

The port of the live land playback suite (tests/dolphin/run_land_tests.py) to offline
recorded-golden tests -- Dereck's post-s66 steer: capture each frame's live game state ONCE
(tests/dolphin/record_land_goldens.py), then every future comparison is sim-vs-recording
with no live-playback layer. Each golden in fixtures/land_goldens/ holds the anchor's
frame-0 seed, the delivered input seq, and EVERY frame's live state; capture-time gates
guaranteed the recording met the same locked expectations the live suite asserted
(delivery cross-checked against a one-shot advanceseq; sim_checks + tech checks + the
0-ULP pos_z gate all green at mint time).

Asserted PER FRAME, bit-exact (f32 by bits, angles as s16): proc state, mNormalSpeed,
facing (shape_angle.y), travel (current.angle.y), pos_z -- and pos_x on the cases whose
golden carries assert_pos_x=true (measured exact at capture; the L-target/turn cases whose
pos_x the live gate never asserted stay un-asserted, honestly). The transient turn procs
(WAIT_TURN 23 / MOVE_TURN 24 / SLIP 25) are covered by the per-frame state compare -- the
recording SEES the transient, so the sim must enter it on the same frame (stronger than the
old live gate's end-state + sim.visited proof).

These are LIVE goldens: locked-test rules apply (tests/dolphin/README.md) -- NEVER edit a
fixture to make the sim pass. A red row means the sim (or a deliberate anchor/tech change)
regressed; re-record only after such a deliberate change, via record_land_goldens.py.
"""
import glob
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD_DIR = os.path.join(os.path.dirname(_HERE), 'fixtures', 'land_goldens')

try:
    from tww_sim.land.land import LandState
    _HAVE = LandState()._foot is not None   # anim keyframe data present -> pos is modeled
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="LandState anim data unavailable")

_FILES = sorted(glob.glob(os.path.join(_GOLD_DIR, '*_golden.json')))


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _load(path):
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize('path', _FILES, ids=[os.path.basename(p)[:-12] for p in _FILES])
def test_land_tech_bitexact(path):
    g = _load(path)
    assert g['anchor'] == 'land_flatwalk@twwgz'
    seed = g['seed']
    sim = LandState(pos_z=seed['pos_z'], facing=int(seed['shape_angle_y']),
                    travel=int(seed['travel_angle']), csangle=int(seed['csangle']),
                    state=int(seed['link_state']), nspeed=seed['potential_speed'],
                    idle_frame=seed['anim_frame'])
    assert not getattr(sim, '_pos_fallback', False) and sim._foot is not None
    bad = []
    for k, (el, live) in enumerate(zip(g['seq'], g['frames'])):
        sim.step(el['stickX'], el['stickY'],
                 buttons=el.get('buttons', 0), triggerL=el.get('triggerL', 0))
        row = []
        if sim.state != int(live['link_state']):
            row.append(f"state {sim.state}!={int(live['link_state'])}")
        if _bits(sim.nspeed) != _bits(live['potential_speed']):
            row.append(f"nspeed {sim.nspeed!r}!={live['potential_speed']!r}")
        if int(sim.facing) & 0xFFFF != int(live['shape_angle_y']) & 0xFFFF:
            row.append(f"facing {int(sim.facing) & 0xFFFF}!={int(live['shape_angle_y']) & 0xFFFF}")
        if int(sim.travel) & 0xFFFF != int(live['travel_angle']) & 0xFFFF:
            row.append(f"travel {int(sim.travel) & 0xFFFF}!={int(live['travel_angle']) & 0xFFFF}")
        if _bits(sim.pos_z) != _bits(live['pos_z']):
            row.append(f"pos_z {sim.pos_z!r}!={live['pos_z']!r}")
        if g['assert_pos_x'] and _bits(sim.pos_x) != _bits(live['pos_x']):
            row.append(f"pos_x {sim.pos_x!r}!={live['pos_x']!r}")
        if row:
            bad.append(f"f{k}: " + '; '.join(row))
    assert not bad, f"{g['case']}: {len(bad)} non-bit-exact frames vs the live recording:\n" \
                    + '\n'.join(bad[:12])


def test_goldens_present():
    """All 14 live cases must have a recorded golden -- a silently missing fixture would
    hollow the suite out (the parametrize list is built from whatever files exist)."""
    want = {'walk_run', 'walk_y171', 'brakeslide', 'ebs', 'face_left', 'brake_right',
            'roll_run', 'roll_slow', 'roll_settle', 'roll_ebs',
            'waitturn', 'moveturn', 'slip', 'wiggle_ebs_roll'}
    have = {os.path.basename(p)[:-12] for p in _FILES}
    assert want <= have, f"missing land goldens: {sorted(want - have)}"


def test_wiggle_chain_signature():
    """The wiggle golden must carry the WHOLE chain (guards a bad re-record, since the
    per-frame gate would happily match a recording where the roll never fired): roll @ the
    26 cap -> wiggle-EBS preserving ~-23.23 -> second roll @ ~24.087 -> ends stopped."""
    g = _load(os.path.join(_GOLD_DIR, 'wiggle_ebs_roll_golden.json'))
    states = [int(f['link_state']) for f in g['frames']]
    pots = [f['potential_speed'] for f in g['frames']]
    rolls = [p for s, p in zip(states, pots) if s == 30]
    assert any(abs(v - 26.0) < 0.05 for v in rolls), "first roll at the 26 cap missing"
    assert abs(min(pots) - (-23.227)) < 0.05, f"wiggle-EBS ~-23.23 missing [{min(pots):.3f}]"
    assert any(abs(v - 24.087) < 0.1 for v in rolls), "second roll @~24.087 missing"
    assert states[-1] == 4, f"does not end stopped [{states[-1]}]"
