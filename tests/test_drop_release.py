import pytest

from tww_sim.core import drop_release as dr
from tww_sim.core.fp import f32


def test_decomp_throw_constants_are_exposed():
    assert dr.GRAB_THROW_SPEED_F == 19.0
    assert dr.GRAB_THROW_SPEED_Y == 34.0
    assert dr.GRAB_THROW_RELEASE_FRAME == 2.0
    assert dr.DROP_OBJECTS["bomb"].throw_speed_f == 19.0
    assert dr.DROP_OBJECTS["bomb"].throw_speed_y == 34.0


def test_tsubo_drop_init_overwrites_throw_speed():
    small = dr.DROP_OBJECTS["pot_small"]
    large = dr.DROP_OBJECTS["pot_large"]
    assert small.throw_speed_f == 36.0
    assert small.throw_speed_y == 27.0
    assert large.throw_speed_f == 43.0
    assert large.throw_speed_y == 22.0


def test_b_drop_keeps_bomb_and_small_pot_horizontal_position():
    hand_mid = (0.0, 0.0, 0.0)
    facing = 0
    bomb = dr.displacement_from_hands(hand_mid, facing, "bomb")
    pot = dr.displacement_from_hands(hand_mid, facing, "pot_small")
    assert bomb[0] == bomb[2] == 0.0
    assert pot[0] == pot[2] == 0.0
    assert bomb == pytest.approx((0.0, 27.1, 0.0), abs=1e-5)
    assert pot == pytest.approx((0.0, -6.0, 0.0), abs=1e-5)


def test_throw_is_a_separate_release_path():
    facing = 0x4000
    dx, _dy, dz = dr.displacement_from_hands(
        (0.0, 0.0, 0.0), facing, "bomb", release="throw"
    )
    assert dx == pytest.approx(19.0, abs=1e-5)
    assert abs(dz) < 1e-5


def test_measured_push_inverts_to_close_radius_30_centers():
    sep = dr.center_separation_from_measured_push(-1.91815507, 52.6955032)
    assert sep == pytest.approx((0.0513152, -1.4097299), abs=1e-5)
    assert (sep[0] ** 2 + sep[1] ** 2) ** 0.5 == pytest.approx(1.4106636, abs=1e-5)


@pytest.mark.parametrize("object_type", ["bomb", "pot_small"])
def test_coupled_b_drop_reconstructs_free_space_push(object_type):
    expected = (-1.91815507, 52.6955032)
    sep = dr.center_separation_from_measured_push(*expected, object_type=object_type)
    result = dr.b_drop_collision_step(
        link_pos=(0.0, 0.0, 0.0),
        link_co_center=(0.0, 0.0, 0.0),
        link_co_height=100.0,
        held_prop_pos=(sep[0], 0.0, sep[1]),
        object_type=object_type,
        walls=[],
    )
    assert (result.link_push[0], result.link_push[2]) == pytest.approx(expected, abs=2e-5)
    assert result.link_raw == pytest.approx((expected[0], 0.0, expected[1]), abs=2e-5)
    assert not result.prop_bg_info["wall_hit"]
    assert not result.link_bg_info["wall_hit"]


@pytest.mark.parametrize(
    "old,facing,animation_position,expected",
    [
        (
            (f32(-157.694931), 0.0, f32(-739.113281)),
            4683,
            51,
            (f32(-134.026428), f32(-692.197693)),
        ),
        (
            (f32(-566.3359375), 0.0, f32(-1365.3570556640625)),
            33952,
            11,
            (f32(-585.289917), f32(-1414.7666)),
        ),
    ],
)
def test_decomp_drop_matches_live_absolute_endpoint_bit_exact(
    old, facing, animation_position, expected
):
    pose = dr.decomp_b_drop_pose(old, facing, animation_position, object_type="bomb")
    result = dr.b_drop_collision_step(
        old,
        pose.link_co_center,
        pose.link_co_height,
        pose.held_prop_pos,
        "bomb",
        [],
        link_co_radius=pose.link_co_radius,
    )
    assert result.link_raw[0] == expected[0]
    assert result.link_raw[2] == expected[1]


def test_decomp_drop_uses_source_ordered_release_frames():
    pose = dr.decomp_b_drop_pose((0.0, 0.0, 0.0), 0, 11)
    assert pose.held_frame == 12.0
    assert pose.collision_under_frame == 13.0
    assert pose.equip_frame == f32(13.999)
