import pytest

from harness.rollstab import roll_launch
from harness.rollstab.roll_launch import (
    GateInput,
    best_gate_input,
    optimize_constant_gate_launch,
    potential_speed_ceiling,
    synthetic_rest,
    trace_fast_launch,
)
from tww_sim.core.anim.foot_speedf import FootSpeedF


def test_exact_fast_acceleration_gate_and_potential_ceiling():
    gate = best_gate_input()
    ceiling = potential_speed_ceiling(gate)

    assert gate.delivered == (151, 199)
    assert gate.authored == (151, 199)
    assert gate.target_offset == -1481
    assert gate.cosine == pytest.approx(0.9898413419723511)
    assert ceiling["normal_speeds"] == pytest.approx([
        4.949206829071045,
        9.949207305908203,
        13.449207305908203,
        16.949207305908203,
    ])
    assert ceiling["roll_upper_bound"] == pytest.approx(25.923810958862305)


@pytest.mark.skipif(not FootSpeedF.available(), reason="anim keyframe data not present")
@pytest.mark.parametrize("low_life", [False, True])
def test_fast_launch_trace_reaches_the_proved_potential_ceiling(low_life):
    result = trace_fast_launch(synthetic_rest(low_life=low_life))
    ceiling = potential_speed_ceiling()

    assert result["pre_roll_normal_speed"] == ceiling["pre_roll_normal_speed"]
    assert result["roll_speed"] <= ceiling["roll_upper_bound"]
    assert result["roll_speed"] > 25.7


@pytest.mark.skipif(not FootSpeedF.available(), reason="anim keyframe data not present")
def test_seed_specific_gate_scan_can_beat_potential_optimum_in_actual_speedf(monkeypatch):
    seed = synthetic_rest()
    potential = best_gate_input()
    potential_gate_result = trace_fast_launch(seed, potential)
    nearby = GateInput(delivered=(104, 205), authored=(104, 205), target_offset=1504,
                       cosine=0.9896219968795776)
    monkeypatch.setattr(roll_launch, "gate_inputs", lambda: (potential, nearby))
    exact = optimize_constant_gate_launch(seed)

    assert exact["candidates_tested"] == 2
    assert exact["roll_speed"] >= potential_gate_result["roll_speed"]
    assert exact["gate"].delivered == (104, 205)
    assert exact["roll_speed"] == pytest.approx(25.80272674560547)
