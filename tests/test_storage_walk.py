from types import SimpleNamespace

from harness.collision.storage_walk import StorageWalkFamily, crossing_result, storage_active
from harness.rollstab.route_constraints import FacingRanges


def _seam():
    a = SimpleNamespace(func=lambda pos: 5. - pos[0])
    b = SimpleNamespace(func=lambda pos: 5. - pos[2])
    return SimpleNamespace(S=(5., 5.), wA=SimpleNamespace(pla=a),
                           wB=SimpleNamespace(pla=b))


def _frame(old, pos, flags=0x24):
    return dict(old=old, pos=pos, raw=pos, flags=flags, state=6,
                facing=1000, travel=1000, speed=15.)


def test_storage_requires_persistent_wall_none_and_a_walking_frame():
    trace = dict(native=dict(seeds=[dict(collision_flags=0x24)] * 3),
                 trace=[dict(after=dict(state=30)), dict(after=dict(state=6))])
    assert storage_active(trace)
    trace["native"]["seeds"][1] = dict(collision_flags=0x20)
    assert not storage_active(trace)


def test_storage_crossing_requires_clean_retained_motion():
    frames = [_frame((4., 0., 4.), (6., 0., 6.)),
              _frame((6., 0., 6.), (7., 0., 7.)),
              _frame((7., 0., 7.), (8., 0., 8.))]
    result = crossing_result(frames, _seam(), (), -1, FacingRanges(), False,
                             1., 14.5, False, FacingRanges())
    assert result.exact and result.dispatch_row == 0
    frames[1]["flags"] &= ~0x4
    assert not crossing_result(frames, _seam(), (), -1, FacingRanges(), False,
                               1., 14.5, False, FacingRanges()).exact


def test_storage_oob_landing_obeys_tolerance_and_speed():
    frames = [_frame((4., 0., 4.), (6., 0., 6.)),
              _frame((6., 0., 6.), (7., 0., 7.)),
              _frame((7., 0., 7.), (8., 0., 8.))]
    result = crossing_result(frames, _seam(), (), -1, FacingRanges(), True,
                             1., 14.5, False, FacingRanges())
    assert not result.exact
    result = crossing_result(frames, _seam(), (), -1, FacingRanges(), True,
                             2., 14.5, False, FacingRanges())
    assert result.exact


def test_storage_rows_accept_native_replay_call_signature():
    family = StorageWalkFamily.__new__(StorageWalkFamily)
    family.control_rows = (0,)
    family.base_rows = [dict(stickX=128, stickY=128, substickX=128, substickY=128)]
    rows = family.rows_from_controls((90, 250, 128, 100), False, retime_slash=False)
    assert rows[0]["stickX"] == 90 and rows[0]["substickY"] == 100
