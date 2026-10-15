"""Gates for the Phase-T fast coupled shove engine + the LIVE Tetra seam clip (2026-07-11).

Layers:
  * the wall cull is exact (culled couple_replay == full mesh, bit-identical) on the roll6 fixture;
  * the Co-centre FK chain-consts decomposition == roll_co_center bit-exactly;
  * the native ``_shovec`` engine == the Python coupled engine (old/new/push/genuine + every
    per-step position) on the fixture placement, a grid, and the WINNING clip placement;
  * the live clip fixture (``hyrule_tetra_clip_live.json``) replays 0-ULP through the CLIP frame
    (both actors from the placement row; Link on every roll row) and its live endpoint is the
    engine's genuine ``new``. That capture is the TELEPORT-STAGED validation (a mid-run placement
    hack, not the accepted push-aside mechanism -- session 21b): it locks the engine + graze push +
    acceptance chain, while the no-hack staging search stays open.

Anim-data-dependent pieces skip when ``_generated/anim`` is absent; native pieces skip without
the built ``_shovec`` .pyd.
"""
import json
import os
import sys

import pytest

_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.anim import body_cyl

pytestmark = pytest.mark.skipif(not body_cyl.available(),
                                reason="needs _generated/anim (dev-supplied)")

CLIP_PLACEMENT = (-1625.9922189608035, -923.4329080655332)   # the live-confirmed winning hit
CLIP_THRUST = 13
CLIP_NEW = (-1727.45263671875, -990.7470703125)


def _fs():
    from harness.rollstab import fast_shove as FS
    return FS


def _native_ok():
    try:
        import tww_sim.core._shovec  # noqa: F401
        return True
    except ImportError:
        return False


def test_chain_consts_bitexact():
    from tww_sim.core.fp import f32, fadds, fmuls
    for facing, lean, frame in ((40842, 0, 10.0), (40874, 500, 3.5), (12345, -1200 & 0xFFFF, 20.5)):
        rc, nc = body_cyl.roll_co_chain_consts(facing, frame, shape_z=lean)
        for (px, pz) in ((-1690.25, -955.1), (-1362.3699951171875, -608.79), (0.5, -0.5)):
            def chain(vals, p):
                t = f32(p)
                for c in vals:
                    t = fadds(c, t)
                return t
            cx = fmuls(0.5, fadds(chain([c[0] for c in rc], f32(px)), chain([c[0] for c in nc], f32(px))))
            cz = fmuls(0.5, fadds(chain([c[1] for c in rc], f32(pz)), chain([c[1] for c in nc], f32(pz))))
            assert (cx, cz) == body_cyl.roll_co_center(f32(px), f32(pz), facing, frame, shape_z=lean)


@pytest.mark.slow
def test_cull_is_exact_on_roll6():
    FS = _fs()
    from harness.rollstab.cc_stepper import couple_replay
    from tww_sim.land.walls import load_ordered_mesh
    fix = FS.load_fixture()
    full = load_ordered_mesh(FS.WALLS_FIX)
    culled = FS.load_walls(fix)
    assert len(culled) < len(full)

    def run(walls):
        return couple_replay(fix['frames'], fix['tetra_placed_at'], fix['tetra_placed_xz'],
                             walls, fix['ground_y'], sword_drawn=True)
    a, b = run(full), run(culled)
    assert all(x['sim_link'] == y['sim_link'] and x['sim_tetra'] == y['sim_tetra']
               for x, y in zip(a, b))


@pytest.mark.skipif(not _native_ok(), reason="_shovec .pyd not built")
def test_native_engine_bitexact_and_clip():
    FS = _fs()
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    rows = fix['frames']
    entry = next(i for i, r in enumerate(rows) if r['link']['proc'] == 30)
    placed_step = fix['tetra_placed_at'] - entry - 1

    # fixture inputs: the fixture placement + a small grid, native == python bit-identically
    inputs = FS.fixture_inputs(fix)
    ctx, _ = FS.build_ctx(fix, walls, inputs)
    grid = [tuple(fix['tetra_placed_xz'])] + [(x, z) for x in (-1690.0, -1650.0)
                                              for z in (-955.0, -915.0)]
    assert FS.gate_vs_reference(ctx, fix, walls, inputs, grid, placed_step) == []

    # the winning clip schedule: genuine at the exact placement, and bit-matched vs python
    inputs = FS.make_inputs(CLIP_THRUST)
    ctx, sch = FS.build_ctx(fix, walls, inputs)
    ps = sch['cut_step'] - 1
    res = ctx.run_one(CLIP_PLACEMENT[0], CLIP_PLACEMENT[1], ps)
    assert res['genuine']
    assert res['new'] == CLIP_NEW
    ref, _ = FS.py_reference(fix, walls, inputs, CLIP_PLACEMENT, ps)
    assert ref['genuine'] and ref['new'] == res['new'] and ref['push'] == res['push']


def test_live_clip_fixture_replays_bitexact():
    """The locked live clip capture: Link 0-ULP on every roll row through the CLIP frame; Tetra
    0-ULP from her placement row. (Pre-placement Tetra rows are the parked free-fall, out of
    scope; the post-clip CUT tail is the known descoped gap.)"""
    FS = _fs()
    from harness.rollstab.cc_stepper import couple_replay
    path = os.path.join(_rb, 'fixtures', 'hyrule_tetra_clip_live.json')
    fix = json.load(open(path))
    walls = FS.load_walls(fix)
    res = couple_replay(fix['frames'], fix['tetra_placed_at'], fix['tetra_placed_xz'],
                        walls, fix['ground_y'], sword_drawn=True)
    clip = next(r for r in res if r['proc'] in (0x41, 0x42))
    assert clip['live_link'] == CLIP_NEW                      # the live endpoint IS the clip
    for r in res:
        if r['f'] <= clip['f']:
            assert (r['dlx'], r['dlz']) == (0, 0), "Link diverged at f%d" % r['f']
        if fix['tetra_placed_at'] <= r['f'] <= clip['f']:
            assert (r['dtx'], r['dtz']) == (0, 0), "Tetra diverged at f%d" % r['f']
