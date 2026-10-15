"""Regression guards for non-authoritative measured endpoint diagnostics."""
from pathlib import Path

import pytest

from tww_sim.core import drop_release as dr
from harness.collision.drop_push_clip import (
    DropFrame,
    prove_drop,
    _resolved_prop_clip_flags,
    rotate_local,
    validate_calibrated_table,
    verify_setup,
)
from harness.collision.find_drop_push_candidate import find_candidates, prepare_search
from harness.collision.seam_scan import load_region_tris


ROOT = Path(__file__).resolve().parents[1]
GANONM_CACHE = ROOT / "_generated_ganonm_r0_iso_region.json"
GANONM_BOX = (400.0, 700.0, -80.0, 50.0, -1500.0, -1300.0)
GANONM_SEAM = (586.023132, -50.0, -1413.401733)
FAILED_SEAM_3 = (-584.995605, 24.830962, -1413.985596)


def test_prepare_search_resolves_supplied_y_to_collision_seam_height():
    if not GANONM_CACHE.exists() or not dr.available():
        pytest.skip("GanonM cache or generated grab animation unavailable")
    region, _stage = load_region_tris(str(GANONM_CACHE))
    target = (GANONM_SEAM[0], GANONM_SEAM[1] - 500.0, GANONM_SEAM[2])
    box = (
        target[0] - 160.0,
        target[0] + 160.0,
        -1000.0,
        1000.0,
        target[2] - 160.0,
        target[2] + 160.0,
    )
    context = prepare_search(region, box, target)
    assert context.seam_target[1] == context.seam["test_y"]
    assert context.seam_target[1] != target[1]


@pytest.mark.skipif(not dr.available(), reason="generated grab animation unavailable")
def test_measured_row_round_trips_through_bomb_and_small_pot_co():
    row = DropFrame(4, -1.91815507, 52.6955032, 52.73040277)
    report = validate_calibrated_table([row])
    assert report["bomb"]["max_error"] < 1e-5
    assert report["pot_small"]["max_error"] < 1e-5


@pytest.mark.skipif(not GANONM_CACHE.exists(), reason="GanonM room cache not generated")
def test_documented_animation_position_5_uses_the_console_trig_bucket_only_as_diagnostic():
    region, _stage = load_region_tris(str(GANONM_CACHE))
    measured_row_4 = DropFrame(
        frame=4,
        local_dx=-1.91815507,
        local_dz=52.6955032,
        speed=52.73040277,
        local_angle_deg=87.91531191,
        local_angle_s16=-379.5058851,
    )
    old = (596.77209472656, -50.0, -1378.4049072266)

    results = verify_setup(
        region,
        GANONM_BOX,
        GANONM_SEAM,
        [measured_row_4],
        frame=5,
        old=old,
        facings=list(range(36255, 36273)),
    )

    by_facing = {row["facing"]: row for row in results}
    expected = rotate_local(measured_row_4.local_dx, measured_row_4.local_dz, 36256)
    assert all(rotate_local(measured_row_4.local_dx, measured_row_4.local_dz, facing) == expected
               for facing in range(36256, 36272))
    assert rotate_local(measured_row_4.local_dx, measured_row_4.local_dz, 36255) != expected
    assert rotate_local(measured_row_4.local_dx, measured_row_4.local_dz, 36272) != expected

    result = by_facing[36256]

    assert result["table_frame"] == 4
    assert not result["endpoint_crosses"]
    assert not result["authoritative"]
    assert result["model"] == "rotated_free_space_endpoint"
    assert result["crr_info"]["line_hit"]
    assert not result["crr_info"]["wall_hit"]
    assert not result["resolved_behind"]
    assert any(value >= 0.0 for value in result["resolved_plane_values"])
    assert result["stable_delta"] == 0.0


@pytest.mark.skipif(not GANONM_CACHE.exists(), reason="GanonM room cache not generated")
def test_clip_verifier_fails_closed_when_box_contains_no_seam():
    region, _stage = load_region_tris(str(GANONM_CACHE))
    with pytest.raises(ValueError, match="no seam"):
        _resolved_prop_clip_flags(
            region,
            (0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
            GANONM_SEAM,
            (596.77209472656, 0.0, -1378.4049072266),
            (581.2888, 0.0, -1428.8109),
        )


@pytest.mark.skipif(not GANONM_CACHE.exists() or not dr.available(),
                    reason="GanonM cache or generated grab animation unavailable")
def test_calibrated_center_model_reproduces_documented_ganonm_clip():
    region, _stage = load_region_tris(str(GANONM_CACHE))
    measured_row_4 = DropFrame(
        frame=4,
        local_dx=-1.91815507,
        local_dz=52.6955032,
        speed=52.73040277,
    )
    result = verify_setup(
        region,
        GANONM_BOX,
        GANONM_SEAM,
        [measured_row_4],
        frame=5,
        old=(596.77209472656, 0.0, -1378.4049072266),
        facings=[36255, 36256, 36271, 36272],
        calibrated=True,
    )

    by_facing = {row["facing"]: row for row in result}
    calibrated = by_facing[36256]["calibrated"]
    assert calibrated["status"] == "calibrated_center_prediction"
    assert calibrated["coupled_crosses"]
    assert not calibrated["step"].prop_bg_info["wall_hit"]
    assert not calibrated["step"].link_bg_info["line_hit"]
    assert not calibrated["step"].link_bg_info["wall_hit"]
    assert by_facing[36271]["calibrated"]["coupled_crosses"]
    assert not by_facing[36255]["calibrated"]["coupled_crosses"]
    assert not by_facing[36272]["calibrated"]["coupled_crosses"]
    assert not by_facing[36256]["acch_clips"]


@pytest.mark.skipif(not GANONM_CACHE.exists() or not dr.available(),
                    reason="GanonM cache or generated grab animation unavailable")
def test_reported_false_setup_depends_on_linecheck_snap():
    region, _stage = load_region_tris(str(GANONM_CACHE))
    table = [DropFrame(4, -1.91815507, 52.6955032, 52.73040277)]
    result = verify_setup(
        region,
        (-650.0, -500.0, -50.0, 100.0, -1500.0, -1300.0),
        FAILED_SEAM_3,
        table,
        frame=5,
        old=(-571.0882568359375, 0.0, -1377.645751953125),
        facings=[36960],
        calibrated=True,
    )[0]

    # The old solver counted this as a clip only because CrrPos LineCheck
    # projected a deep wall hit back onto the corner. It failed in-game.
    assert not result["calibrated"]["coupled_crosses"]
    assert result["calibrated"]["resolved"]["crr_info"]["line_hit"]
    assert result["calibrated"]["step"].link_bg_info["wall_hit"]
    assert not result["calibrated"]["generator_grade"]


@pytest.mark.skipif(not GANONM_CACHE.exists(), reason="GanonM room cache not generated")
@pytest.mark.parametrize("object_type", ["bomb", "pot_small"])
def test_seam_only_solver_generates_matching_no_linecheck_setup(object_type):
    region, _stage = load_region_tris(str(GANONM_CACHE))
    measured_row_50 = DropFrame(
        frame=50,
        local_dx=1.01451576,
        local_dz=52.5379944,
        speed=52.54778871,
    )
    hits = prove_drop(
        region,
        (-650.0, -500.0, -50.0, 100.0, -1500.0, -1300.0),
        FAILED_SEAM_3,
        [measured_row_50],
        frame=51,
        limit=1,
        object_type=object_type,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert hit["coupled"]["coupled_crosses"]
    assert hit["facing_range"] is not None
    assert hit["facing"] in hit["accepted_facings"]
    assert hit["frame"] == 51
    assert hit["table_frame"] == 50
    assert hit["facing"] == 36384
    assert hit["facing_range"] == (36384, 36399)
    assert hit["old"] == (
        -567.333740234375,
        0.0,
        -1367.901611328125,
    )
    assert hit["old_bits"] == (0xC40DD55C, 0xC4AAFCDA)
    assert hit["endpoint_model_error"] <= 1e-5
    assert not hit["resolved"]["crr_info"]["line_hit"]
    assert not hit["info"]["line_hit"]
    assert not hit["collision_step"].prop_bg_info["wall_hit"]
    assert not hit["collision_step"].link_bg_info["wall_hit"]


@pytest.mark.skipif(not GANONM_CACHE.exists(), reason="GanonM room cache not generated")
def test_old_direct_endpoint_model_would_use_the_wrong_csv_row():
    region, _stage = load_region_tris(str(GANONM_CACHE))
    measured_row_5 = DropFrame(
        frame=5,
        local_dx=2.56147838,
        local_dz=52.8165817,
        speed=52.87865802,
    )

    with pytest.raises(ValueError, match="maps to missing table frame 4"):
        verify_setup(
            region,
            GANONM_BOX,
            GANONM_SEAM,
            [measured_row_5],
            frame=5,
            old=(596.77209472656, -50.0, -1378.4049072266),
            facings=[36256],
        )


@pytest.mark.skipif(not GANONM_CACHE.exists() or not dr.available(),
                    reason="GanonM cache or generated grab animation unavailable")
@pytest.mark.parametrize("object_type", ["bomb", "pot_small"])
def test_decomp_solver_proves_thin_oob_seam_landing(object_type):
    region, _stage = load_region_tris(str(GANONM_CACHE))
    seam = (-584.995605, 16.695562, -1413.985596)
    box = (-650.0, -500.0, -50.0, 100.0, -1500.0, -1300.0)
    context = prepare_search(region, box, seam)
    hits = find_candidates(
        context,
        11,
        object_type=object_type,
        facing_ranges=((41472, 41472, 16),),
        phases=(0.99995, 0.99995, 0.00001),
        limit=1,
        require_oob_landing=True,
        oob_tolerance=0.005,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert hit.oob_landing
    assert hit.facing_range == (41472, 41487)
    assert hit.old == (-538.1468505859375, 0.0, -1389.37939453125)
    assert hit.resolved == (-584.9979248046875, -1413.98681640625)
    assert hit.seam_distance < 0.005
    assert hit.wall_depths[0] > 0.0 and hit.wall_depths[1] > 0.0
    assert hit.landing_floor == hit.old[1]
    assert hit.stable_delta == 0.0
