from harness.rollstab import seam_feasibility as feasibility
from harness.rollstab import walkstab
from harness.rollstab import live_slash
import math
import pytest


class FakeSeam:
    S = (0.0, 0.0)

    @staticmethod
    def wall_clearance(x, z):
        return x

    @staticmethod
    def cut_new(old, **_kwargs):
        return old[0], old[1] + 40.0


def test_best_walk_aim_prefers_wall_clear_dust(monkeypatch):
    unsafe = [(1.0, 0.0, 1.0, 0.0)] * 8
    safe = [(1.0, 0.0, 40.0, 0.0)]

    def fake_scan(_seam, facing, **_kwargs):
        hits = unsafe if facing == 0 else safe if facing == 1024 else []
        return len(hits), hits

    monkeypatch.setattr(feasibility, "scan_aim", fake_scan)
    facing, total, safe_count, witnesses = feasibility.best_walk_aim(
        FakeSeam(), fstep=1024, budget=1000, angle_lo=0, angle_hi=1024
    )
    assert (facing, total, safe_count) == (1024, 1, 1)
    assert witnesses == safe


def test_best_walk_aim_can_prioritize_deepest_post_seam_endpoint(monkeypatch):
    dense_shallow = [(39.0, 0.0, 40.0, -39.0)] * 8
    sparse_deep = [(30.0, 0.0, 40.0, -30.0)]

    def fake_scan(_seam, facing, **_kwargs):
        hits = dense_shallow if facing == 0 else sparse_deep if facing == 1024 else []
        return len(hits), hits

    monkeypatch.setattr(feasibility, "scan_aim", fake_scan)
    facing, total, safe_count, witnesses = feasibility.best_walk_aim(
        FakeSeam(), fstep=1024, budget=1000, angle_lo=0, angle_hi=1024,
        prefer_depth=True,
    )
    assert (facing, total, safe_count) == (1024, 1, 1)
    assert witnesses == sparse_deep


def test_best_walk_aim_can_return_all_depth_ranked_families(monkeypatch):
    shallow = [(39.0, 0.0, 40.0, -39.0)]
    deep = [(30.0, 0.0, 40.0, -30.0)]

    def fake_scan(_seam, facing, **_kwargs):
        hits = shallow if facing == 0 else deep if facing == 1024 else []
        return len(hits), hits

    monkeypatch.setattr(feasibility, "scan_aim", fake_scan)
    ranked = feasibility.best_walk_aim(
        FakeSeam(), fstep=1024, budget=1000, angle_lo=0, angle_hi=1024,
        prefer_depth=True, return_ranked=True,
    )
    assert [candidate[0] for candidate in ranked] == [1024, 0]


def test_best_walk_aim_prioritizes_persistent_oob_tail(monkeypatch):
    shallow_stable = [(39.0, 0.0, 40.0, -39.0)]
    deep_transient = [(30.0, 0.0, 40.0, -30.0)]

    def fake_scan(_seam, facing, **_kwargs):
        hits = shallow_stable if facing == 0 else deep_transient if facing == 1024 else []
        return len(hits), hits

    monkeypatch.setattr(feasibility, "scan_aim", fake_scan)
    monkeypatch.setattr(
        feasibility, "cut_tail_outcome",
        lambda _seam, facing, _hit, **_kwargs: {"next_oob": facing == 0},
    )
    facing, _total, _safe_count, _witnesses = feasibility.best_walk_aim(
        FakeSeam(), fstep=1024, budget=1000, angle_lo=0, angle_hi=1024,
        prefer_depth=True, prefer_stable=True,
    )
    assert facing == 0


def test_subjectivity_start_preflight_reports_wall_push(monkeypatch):
    from tww_sim.core import collision

    monkeypatch.setattr(
        collision, "acch_crr_pos",
        lambda old, new, walls, **kwargs: ((old[0] + 19.0, old[1], old[2]),
                                           {"wall_hit": True}),
    )
    assert live_slash._preflight_subjectivity_start([object()], 1.0, 2.0, 3.0) == 19.0


def test_walking_setup_retries_rejected_facing(monkeypatch):
    candidates = [
        (1000, 2, 1, [(1.0, 0.0, 40.0, 0.0)]),
        (2000, 1, 1, [(1.0, 0.0, 40.0, 0.0)]),
    ]
    monkeypatch.setattr(
        feasibility, "best_walk_aim", lambda *_args, **_kwargs: candidates
    )
    monkeypatch.setattr(live_slash, "SeamGeo", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(live_slash, "_load_state", lambda *_args: None)
    monkeypatch.setattr(live_slash, "_enter_subjectivity_start", lambda *_args, **_kwargs: None)
    attempts = []

    def attempt(*_args, candidate=None, **_kwargs):
        # candidate is positional in the production call.
        current = _args[6]
        attempts.append(current[0])
        if current[0] == 1000:
            raise RuntimeError("teleport overlaps wall")
        return {"facing": 2000}, object()

    monkeypatch.setattr(live_slash, "_attempt_simple_walking_setup", attempt)
    hit, _seam = live_slash._prepare_simple_walking_setup(
        object(), object(), {"S": [0, 0, 0]}, 0, 0, 65535, 120,
        log=lambda _line: None,
    )
    assert attempts == [1000, 2000]
    assert hit["facing"] == 2000


def test_walk_facing_range_wraps():
    assert feasibility._angle_in_range(65000, 64000, 1000)
    assert feasibility._angle_in_range(500, 64000, 1000)
    assert not feasibility._angle_in_range(2000, 64000, 1000)
    grid = feasibility._angle_grid(64000, 1000, 2048)
    assert grid[0] == 64000 and grid[-1] == 1000
    assert len(grid) >= 32
    assert 20480 in feasibility._angle_grid(20000, 23000, 2048)


def test_walkstab_uses_selected_physical_facing(monkeypatch):
    monkeypatch.setattr(walkstab, "TARGET_FACING", 32768)
    monkeypatch.setattr(walkstab, "ANGLE_LO", 32000)
    monkeypatch.setattr(walkstab, "ANGLE_HI", 33000)
    assert walkstab.search_bearing() == 32768
    assert walkstab.facing_allowed(32768)
    assert not walkstab.facing_allowed(34000)

def test_walk_anchor_uses_physical_witness_and_preserves_camera(tmp_path, monkeypatch):
    witness = (36.0, 0.0, 100.0, 200.0)
    monkeypatch.setattr(
        feasibility, "best_walk_aim",
        lambda *_args, **_kwargs: (16384, 2, 1, [witness]),
    )

    class Probe:
        S = (0.0, 0.0)

        def __init__(self, _geo, _camera):
            pass

        @staticmethod
        def wall_clearance(x, z):
            return 50.0

        @staticmethod
        def cut_new(old, **_kwargs):
            return old[0], old[1] - 40.0

        @staticmethod
        def perp_to_ray(old, new):
            return 0.0

    captured = {}

    def fake_mint(_reader, _control, _base, x, z, y, facing, camera, settle_walk, log):
        captured.update(x=x, z=z, y=y, facing=facing, camera=camera, settle=settle_walk)
        return {"link_x": x, "link_y": y, "link_z": z}

    monkeypatch.setattr(live_slash, "SeamGeo", Probe)
    monkeypatch.setattr(
        live_slash, "_refine_walk_feasibility",
        lambda _probe, _camera, _lo, _hi, coarse, log: coarse,
    )
    monkeypatch.setattr(live_slash, "_mint_prepared", fake_mint)
    monkeypatch.setattr(live_slash, "_walking_center_ray",
                        lambda _module, _target: (0.0, (100.0, 200.0),
                                                  (100.0, 160.0), 16384))
    monkeypatch.setattr(walkstab, "configure", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(walkstab, "genuine_clip", lambda *_args: (True, "clip"))
    monkeypatch.setattr(live_slash, "GEO_PATH", str(tmp_path / "geo.json"))
    geo = {"S": [0.0, 0.0, 0.0], "link_y": 3.0}
    _seed, prepared, selected, target_old = live_slash._prepare_walk_anchor(
        object(), object(), geo, 23441, 0, 65535, 120, log=lambda _line: None
    )
    assert selected[0] == 16384
    assert target_old == (100.0, 200.0)
    assert prepared["aim_deg"] == 90.0
    assert captured["camera"] == 23441
    assert captured["facing"] == 16384
    assert captured["x"] == pytest.approx(100.0 - 200.0 * math.sin(math.pi / 2))
    assert captured["z"] == pytest.approx(200.0 - 200.0 * math.cos(math.pi / 2))

def test_walk_anchor_corrects_perpendicular_and_along_error():
    seed = {"link_x": 100.0, "link_z": 200.0}
    x, z = live_slash._shift_walk_park(
        seed, old=(9.0, -6.0), target_old=(0.0, 0.0)
    )
    assert x == pytest.approx(91.0)
    assert z == pytest.approx(206.0)


def test_walk_feasibility_refines_to_controller_reachable_safe_facing(monkeypatch):
    monkeypatch.setattr(
        live_slash, "_controller_walk_facings",
        lambda _camera, _lo, _hi: [32715, 32607],
    )
    safe = (36.9, -0.14, 585.3134, -1376.4982)

    def fake_scan(_probe, facing, **_kwargs):
        return (1, [safe]) if facing == 32607 else (0, [])

    monkeypatch.setattr(feasibility, "scan_aim", fake_scan)

    class Probe:
        @staticmethod
        def wall_clearance(x, z):
            return 40.0

    result = live_slash._refine_walk_feasibility(
        Probe(), 26267, 0, 65535, (32768, 2, 1, []), log=lambda _line: None
    )
    assert result == (32607, 1, 1, [safe])

def test_walking_center_ray_uses_nearest_frame_when_band_is_skipped():
    class Seed:
        csangle = 0

    class FakeWalk:
        SEAM = (0.0, 0.0)

        @staticmethod
        def search_bearing():
            return 100

        @staticmethod
        def seed():
            return Seed()

        @staticmethod
        def _sfbd(*_args):
            return 1, 1

        @staticmethod
        def _sfb(*_args):
            return 1, 1

        @staticmethod
        def _dtm(stick):
            return stick

        @staticmethod
        def _stream_k(*_args):
            return [(1, 1)]

        @staticmethod
        def bounds():
            return {"NLO": 1, "NHI": 2}

        @staticmethod
        def _walk_fast(_sticks, _limit):
            return [
                (1, 46.0, 0.0, 100, 17.0, 100),
                (2, 29.0, 0.0, 100, 17.0, 100),
            ]

        @staticmethod
        def fast_cut(x, z, _facing, _speed, _travel):
            return x, z - 40.0

        @staticmethod
        def perp_ray(_old, _new):
            return 0.0

    _rho, old, _new, _cb = live_slash._walking_center_ray(
        FakeWalk(), target_old=(35.0, 0.0)
    )
    assert old == (29.0, 0.0)


def test_f32_wait_offsets_reach_negative_float_neighbour():
    assert live_slash._f32_offset(-1185.09765625, -1) == -1185.0975341796875

def test_walk_band_targets_proven_nonzero_rho(monkeypatch):
    monkeypatch.setattr(walkstab, "TARGET_OLD", (1.0, 1.0))
    monkeypatch.setattr(walkstab, "SEAM", (0.0, 0.0))
    monkeypatch.setattr(
        walkstab, "bounds",
        lambda: {"NLO": 1, "NHI": 1, "WIN_LO": 4.0, "WIN_HI": 6.0},
    )
    monkeypatch.setattr(
        walkstab, "_walk_fast",
        lambda _sticks, _limit: [(1, 3.0, 4.0, 100, 17.0, 100)],
    )
    monkeypatch.setattr(walkstab, "fast_cut", lambda *_args: (5.0, 6.0))
    monkeypatch.setattr(walkstab, "perp_ray", lambda _old, _new: -1.309525)
    monkeypatch.setattr(walkstab, "target_rho", lambda: -1.309525)
    error, frame, snap = walkstab._band_perp([(1, 1)])
    assert error == pytest.approx(0.0)
    assert frame == 1
    assert snap[:2] == (3.0, 4.0)
