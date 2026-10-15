"""From-rest 0-ULP regression: the rollstab sim vs LIVE Dolphin traces (kaze r11, 2026-07-10).

Locks the from-rest-exact model -- WAIT(4) rest-blend seeding + per-idle-frame re-init, the
2-row DTM alignment no-ops, the end-of-frame (post-integration) deferred foot draw, Link's real
world Y in the pose base, the setMoveSlantAngle turn lean, and dtm_make's 255->254 stick
calibration -- to two clean-DTM live captures on the idle13 anchor:

  * rollstab_rest_cruise.json -- the rest.py verification stream (straight prefix + aim
    cruise), with the per-frame anim fields (d/w frame ctrls, m359C).
  * rollstab_rest_ship.json   -- a full plan stream (bearing arcs + two partial-magnitude dips +
    A-press roll + B-edge cut), with per-frame pos/facing/proc + the stored foot poses.

Every compared row must be BIT-EXACT (f32-identical). These are live-Dolphin goldens: NEVER
edit the fixtures to make the sim pass (tests/dolphin/README.md, locked-tests rule). Rows at
and after the CUT are excluded in the ship trace: the cut's clip/block verdict is collision
(harness.rollstab.geometry), outside the LandState scope.
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(_HERE, 'golden')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None
except Exception:                                    # anim data / harness unavailable
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / anim data unavailable")

ANCHOR = 'kaze_r11_rollstab_idle13@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _gold(name):
    return json.load(open(os.path.join(_GOLD, name)))


def test_rest_cruise_bitexact():
    """The verification stream from REST: pos + both frame ctrls + m359C, 0-ULP every row."""
    calib = _gold('rollstab_rest_cruise.json')
    assert calib['anchor'] == ANCHOR
    s = C.rest_state(ANCHOR)
    _, straight, aim = C.sticks_of(ANCHOR)
    stream = [straight] * C.NPREF + [aim] * C.NCRUISE
    bad = []
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy)
        if k >= len(calib['frames']):
            break
        lf = calib['frames'][k]
        st = s._foot.st
        if not (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])
                and _bits(st.fc0.frame) == _bits(lf['d_frame'])
                and _bits(st.fc1.frame) == _bits(lf['w_frame'])
                and _bits(s._foot.prev_f312) == _bits(lf['m359C'])):
            bad.append(k)
    assert not bad, f"rows diverged from the live cruise trace: {bad}"


def _ship_diff(pose_rows):
    """Replay the ship stream from REST; return the rows in `pose_rows` whose pose (or any row
    whose pos/facing/proc) diverges from the live trace. Cut rows excluded (collision scope)."""
    gold = _gold('rollstab_rest_ship.json')
    assert gold['anchor'] == ANCHOR
    frames = gold['frames']
    cut_row = next(i for i, f in enumerate(frames) if f['proc'] in (0x42, 0x41))
    s = C.rest_state(ANCHOR)
    bad = []
    for k, (sx, sy, b) in enumerate(gold['stream']):
        s.step(sx, sy, buttons=b)
        if k >= cut_row:
            break
        lf = frames[k]
        ok = (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])
              and (s.facing & 0xFFFF) == (lf['facing'] & 0xFFFF)
              and (s.state & 0xFF) == lf['proc'])
        if ok and k in pose_rows and k + 1 < cut_row:
            live_pose = frames[k + 1]['feet']        # mFootData at row k+1 == pose drawn row k
            ok = all(_bits(s._foot.t1[i]) == _bits(live_pose[i]) for i in range(12))
        if not ok:
            bad.append(k)
    return bad, cut_row


def test_rest_ship_bitexact():
    """A full plan stream (arcs + dips + roll) from REST: pos/facing/proc 0-ULP through the
    pre-cut row, and the drawn foot pose (toe stream t1) f32-identical to the live stored
    mFootData on every WALK row (entry, arcs, both dips, cruise)."""
    bad, cut_row = _ship_diff(pose_rows=set(range(0, 22)))
    assert not bad, f"rows diverged from the live ship trace: {bad}"


def test_rest_roll_pose_bitexact():
    """The FRONT_ROLL rows' drawn poses, 0-ULP vs live.

    RED from 2026-07-10 to session 56 (late roll rows 32-36 drifted 1-122 ULP), and the suspects
    listed on the old marker -- the jointBeforeCB thigh lean, m35C4, the foot lift -- were all
    wrong. The real cause was `JMAEulerToQuat`'s half-angle being taken UNSIGNED
    (`quat.euler_to_quat`): a late-roll joint rotation crosses into negative s16, and halving the
    raw u16 lands 2048 sin-table entries away -- the equivalent NEGATED quaternion, whose
    independently-rounded table magnitudes differ by tens of ULP. Fixing the sign-extension closed
    this and a console-delivery frontier that used to sit on the same term."""
    bad, cut_row = _ship_diff(pose_rows=set(range(22, 45)))
    assert not bad, f"roll pose rows diverged: {bad}"
