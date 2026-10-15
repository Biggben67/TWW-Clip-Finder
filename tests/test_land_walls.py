#!/usr/bin/env python3
"""Offline unit tests for the Phase-W per-frame wall response (land/walls.py + the
core.collision acch_* layer + the proc wall feedback).

Synthetic-geometry behavior tests: head-on wall hold, oblique slide, the roll bonk
(FRONT_ROLL_CRASH) and the m3570 against-wall grind latch, plus pass-through inertness.
The live 0-ULP gates on minted kaze anchors live in tests/dolphin/ (goldens); these tests
pin the MECHANICS so refactors can't silently drop a term.
"""
import os
import sys

_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.fp import f32
from tww_sim.core.collision import Tri, Plane, acch_crr_pos, sqrtf_c
from tww_sim.core.mathlib import cM_atan2s
from tww_sim.land import LandState
from tww_sim.land.constants import FRONT_ROLL, FRONT_ROLL_CRASH, MOVE, WAIT, WAIT_TURN
from tww_sim.land.walls import load_geo_tris, WALL_H, WALL_R

A_BTN = 0x100


def _wall_z(z, lo=-50.0, hi=200.0, half=500.0):
    """A vertical wall quad at z facing -z (toward Link walking +z), spanning the cylinders."""
    n = (0.0, 0.0, -1.0)
    d = float(z)
    v = [(-half, lo, z), (half, lo, z), (half, hi, z), (-half, hi, z)]
    return [Tri(v[0], v[1], v[2], plane=Plane(*n, d)),
            Tri(v[0], v[2], v[3], plane=Plane(*n, d))]


def _walk(s, frames, sx=128, sy=255, btn_at=None):
    for f in range(1, frames + 1):
        s.step(sx, sy, buttons=A_BTN if f == btn_at else 0)
    return s


# --------------------------------------------------------------------- acch primitives
def test_sqrtf_c_matches_console_shape():
    # frsqrte+3 Newton in double, rounded to f32: agrees with f32(sqrt) on these, and is
    # exactly reproducible (the live-gated corrected positions depend on this exact chain).
    assert sqrtf_c(2.0) == f32(2.0 ** 0.5)
    assert sqrtf_c(0.0) == 0.0
    assert sqrtf_c(-1.0) == -1.0          # MSL sqrtf returns x for x <= 0


def test_atan2s_cardinals():
    assert cM_atan2s(0.0, 1.0) == 0
    assert cM_atan2s(1.0, 0.0) == 0x4000
    assert cM_atan2s(0.0, -1.0) == 0x8000
    assert cM_atan2s(-1.0, 0.0) == 0xC000
    assert cM_atan2s(1.0, 1.0) == 0x2000


def test_acch_pass_through_far_from_walls():
    tris = _wall_z(1000.0)
    old = (0.0, 0.0, 0.0)
    new = (f32(1.25), f32(-2.5), f32(17.0))
    pos, info = acch_crr_pos(old, new, tris, speed_y=f32(-2.5))
    assert pos == new                       # untouched, bit-exact
    assert not info["wall_hit"] and not info["line_hit"]
    assert info["ran_line"]                 # the player's LINE_CHECK flag runs it every frame


def test_acch_wall_correct_pins_at_radius():
    tris = _wall_z(100.0)
    old = (0.0, -2.5, 60.0)
    new = (0.0, -2.5, 75.0)                 # cylinder (r=35) overlaps the z=100 face by 10
    pos, info = acch_crr_pos(old, new, tris, speed_y=f32(-2.5))
    assert info["wall_hit"] and all(info["cir_hit"])
    assert info["wall_angle"][0] == 0x8000  # cM_atan2s(0, -1)
    assert abs(pos[2] - 65.0) < 1e-4        # pushed out to ~100 - 35
    assert pos[0] == 0.0


# --------------------------------------------------------------------- stepper behavior
def test_walk_head_on_wall_hold():
    s = LandState(pos_x=0.0, pos_z=0.0, facing=0, travel=0, state=WAIT,
                  use_anim=False, native=False, walls=_wall_z(100.0))
    _walk(s, 25)
    assert s.wall_hit and all(s.wall_cir_hit)
    assert s.wall_angle[0] == 0x8000
    assert abs(s.pos_z - 65.0) < 1e-4       # held at the 35u tangent
    # setNormalSpeedF wall slow-down: head-on target = 17 * (1 - cos(0)*0.6) = 6.8
    assert s.nspeed == f32(f32(17.0) * f32(1.0 - f32(0.6)))


def test_walk_oblique_slides_along_wall():
    # 45-degree stick into the wall: z pins at the tangent, x keeps sliding.
    s = LandState(pos_x=0.0, pos_z=0.0, facing=0x2000, travel=0x2000, state=WAIT,
                  use_anim=False, native=False, walls=_wall_z(100.0))
    _walk(s, 14, sx=218, sy=218)            # diagonal stick into the face
    assert s.wall_hit
    z_pin = s.pos_z
    x_before = s.pos_x
    _walk(s, 10, sx=218, sy=218)
    assert abs(s.pos_z - z_pin) < 0.5       # normal push holds z at the face
    assert abs(s.pos_x - x_before) > 10.0   # tangential motion survives (slide)


def test_roll_bonk_crash():
    s = LandState(pos_x=0.0, pos_z=0.0, facing=0, travel=0, state=WAIT,
                  use_anim=False, native=False, walls=_wall_z(300.0))
    _walk(s, 12, btn_at=10)                 # walk to cap, A (2-frame delay) -> roll at 25.6625
    assert s.state == FRONT_ROLL
    assert s._roll_m3570                    # started clear of the wall: crash armed
    crashed = landed = exited = False
    for _ in range(60):
        pre = s.speedF
        s.step(128, 255)
        if s.state == FRONT_ROLL_CRASH and not crashed:
            crashed = True
            # procFrontRollCrash_init: reversed travel, mNormalSpeed = speedF*0.4, vy=7
            assert s.travel == 0x8000
            assert s.nspeed == f32(pre * f32(0.4))
        if crashed and not landed and s.ground_hit and s.pos_y == 0.0:
            landed = True
            s.step(128, 255)                # the proc reads the ground hit next frame
            assert s.nspeed == 0.0          # landing zeroed mNormalSpeed
        if landed and s.state != FRONT_ROLL_CRASH:
            exited = True                   # frame > 20 + held stick -> checkNextMode(1)
            break
    assert crashed and landed and exited
    # travel is reversed post-crash and the stick still points forward: the exit's
    # checkNextMode sees a >0x7800 reversal from a standstill -> the WAIT_TURN pivot.
    assert s.state == WAIT_TURN


def test_sidle_guard_blocks_headon_roll():
    # A pressed while pinned head-on: the game offers SIDLE (WHIDE_READY), never the roll.
    # The sim forbids the roll and raises the sticky planner-rejection flag.
    s = LandState(pos_x=0.0, pos_z=0.0, facing=0, travel=0, state=WAIT,
                  use_anim=False, native=False, walls=_wall_z(100.0))
    _walk(s, 25)                            # pinned at 65, wall flags latched
    assert s.wall_hit and not s.sidle_blocked
    s.step(128, 255, buttons=A_BTN)
    s.step(128, 255)
    s.step(128, 255)
    assert s.state == MOVE                  # no roll happened
    assert s.sidle_blocked                  # ...and the planner signal latched


def test_roll_against_wall_grinds_no_crash():
    # A roll STARTED wall-hit head-on grinds (m3570 latch). Reach it obliquely (outside the
    # sidle window), then flick the stick head-on + A: the roll snaps INTO the wall, m3570=0.
    from tww_sim.land.plan_land import stick_for_bearing
    obl = stick_for_bearing(0x2800, 0, 1.0)
    s = LandState(pos_x=0.0, pos_z=0.0, facing=0x2800, travel=0x2800, state=WAIT,
                  use_anim=False, native=False, walls=_wall_z(100.0))
    _walk(s, 30, sx=obl[0], sy=obl[1])      # oblique pin: sliding along the face
    assert s.wall_hit and abs(((s.facing + 0x8000) & 0xFFFF) - 0x8000) > 0x2000
    s.step(128, 255, buttons=A_BTN)         # head-on stick + A
    s.step(128, 255)
    s.step(128, 255)
    assert s.state == FRONT_ROLL and not s.sidle_blocked
    assert not s._roll_m3570                # latch: crash disabled
    for _ in range(20):
        s.step(128, 255)
        assert s.state != FRONT_ROLL_CRASH
    assert abs(s.pos_z - 65.0) < 0.5        # ground at the face through the whole roll


def test_walls_off_attrs_inert():
    s = LandState(use_anim=False, native=False)
    _walk(s, 10)
    assert not s.wall_hit and s.wall_cir_hit == (False, False, False)


def test_kaze_fixture_loads():
    tris = load_geo_tris(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json'))
    assert len(tris) == 6
    assert WALL_H == (30.1, 89.9, 125.0) and WALL_R == 35.0
