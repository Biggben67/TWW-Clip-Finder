import pytest

from harness.rollstab import live_slash
from harness.rollstab.live_slash import (
    LiveState, _dtm_sticks, _ensure_standalone_savestates, _export_candidate,
    _facing_cache_key, _load_facing_cache, _save_facing_cache,
    _savestate_contains_xyz, _walk_rows,
    _walking_setup_rows, choose_feasible_roll_aim, parse_game_id,
    validate_rest_pose,
)
from harness.dtm.writer import build_dtm_from_sticks


def state(x, z):
    return LiveState(
        pid=1, stage="test", player=1, x=x, y=0.0, z=z,
        facing=0, travel=0, csangle=0, state=4, speedF=0.0,
        nspeed=0.0, stick_distance=0.0, animation_frame=0.0,
        target_facing=0, equip_item=0, sword_drawn=True,
    )


def test_critical_health_waitatob_rest_is_accepted():
    live = state(1.0, 2.0)
    live.life = 1
    live.rest_mode = 0
    live.rest_d_rate = 0.6
    validate_rest_pose(live)


def test_settled_critical_health_blend_is_accepted():
    live = state(1.0, 2.0)
    live.life = 1
    live.rest_mode = live_slash.REST_MODE_BLEND
    live.rest_d_rate = live_slash.STEADY_WAITB_RATE
    validate_rest_pose(live)


def test_critical_health_normal_waits_blend_is_rejected():
    live = state(1.0, 2.0)
    live.life = 1
    live.rest_mode = live_slash.REST_MODE_BLEND
    live.rest_d_rate = live_slash.STEADY_WAITS_RATE
    with pytest.raises(RuntimeError, match="between modeled phases"):
        validate_rest_pose(live)


def test_unknown_critical_health_transition_is_rejected():
    live = state(1.0, 2.0)
    live.life = 1
    live.rest_mode = 0
    live.rest_d_rate = 0.4
    with pytest.raises(RuntimeError, match="between modeled phases"):
        validate_rest_pose(live)


def test_unsettled_wait_pose_is_rejected():
    live = state(1.0, 2.0)
    live.life = 12
    live.rest_d_rate = 0.4
    with pytest.raises(RuntimeError, match="steady WAITS"):
        validate_rest_pose(live)


def test_dtm_sticks_are_one_frame_per_authored_row():
    rows = [
        {"frame": 0, "stickX": 79, "stickY": 252, "cstickX": 128,
         "cstickY": 0, "buttons": 0x100},
        {"frame": 1, "stickX": 101, "stickY": 183, "cstickX": 128,
         "cstickY": 0, "buttons": 0},
    ]
    assert _dtm_sticks(rows) == [
        {"stickX": 79, "stickY": 252, "substickX": 128, "substickY": 0,
         "buttons": 0x100, "triggerL": 0, "triggerR": 0},
        {"stickX": 101, "stickY": 183, "substickX": 128, "substickY": 0,
         "buttons": 0, "triggerL": 0, "triggerR": 0},
    ]


def test_prepared_walk_movie_buffers_b_before_the_solver_old():
    hit = {"N": 18, "sticks": [[49, 235]] * 19}
    rows = _walk_rows(hit, tail_frames=5)
    assert rows[16]["buttons"] == 0x200
    assert rows[17]["buttons"] == 0
    assert rows[18]["stickX"] == 49
    assert rows[19]["stickX"] == 128
    assert len(rows) == 23




def test_savestate_coordinate_gate_requires_exact_f32_xyz(tmp_path):
    path = tmp_path / "prepared_final.sav"
    expected = (
        live_slash._pack_f32(-514.0672607421875)
        + live_slash._pack_f32(0.0)
        + live_slash._pack_f32(-1335.6031494140625)
    )
    path.write_bytes(b"prefix" + expected + b"suffix")
    assert _savestate_contains_xyz(
        str(path), -514.0672607421875, 0.0, -1335.6031494140625
    )
    assert not _savestate_contains_xyz(
        str(path), -514.0671997070312, 0.0, -1335.6031494140625
    )


def test_walking_setup_cdown_turns_then_slashes_at_speed_cap():
    hit = {
        "transition_frame": 14, "b_frame": 12,
        "turn_down_frame": 4, "walk_start_frame": 10,
    }
    rows = _walking_setup_rows(hit, tail_frames=3)
    assert rows[0] == {
        "frame": 0, "stickX": 128, "stickY": 128,
        "cstickX": 128, "cstickY": 0, "buttons": 0,
        "delivery_absorber": False,
    }
    assert rows[4] == {
        "frame": 4, "stickX": 128, "stickY": 1,
        "cstickX": 128, "cstickY": 0, "buttons": 0,
        "delivery_absorber": False,
    }
    assert rows[12]["buttons"] == 0x200
    assert rows[13]["buttons"] == 0
    assert all((row["stickX"], row["stickY"]) == (128, 128) for row in rows[:4])
    assert all((row["stickX"], row["stickY"]) == (128, 128) for row in rows[5:10])
    assert all((row["stickX"], row["stickY"]) == (128, 254) for row in rows[10:])
    assert all((row["cstickX"], row["cstickY"]) == (128, 0) for row in rows)
    assert all(not (row["buttons"] & 0x100) for row in rows)


def test_walking_setup_authors_b_for_the_two_frame_input_delay(monkeypatch):
    from harness.rollstab import rest as rest_model
    from tww_sim.land.constants import MOVE, SUBJECTIVITY, WAIT, WAIT_TURN

    class FakeState:
        def __init__(self):
            self.state = SUBJECTIVITY
            self.speedF = 0.0
            self.nspeed = 0.0
            self.pos_x = 1.0
            self.pos_z = 2.0
            self.facing = 1234
            self.calls = 0
            self.wall_hit = False
            self._input_delay = 2
            self._inbuf = [(128, 128, 0, 0, 128, 128)] * self._input_delay
            self._abtn_prev = 0

        def step(self, sx, sy, buttons=0, triggerL=0, csx=128, csy=128):
            self._inbuf.append((sx, sy, buttons, triggerL, csx, csy))
            delivered = self._inbuf.pop(0)
            self._abtn_prev = delivered[2]
            self.calls += 1
            if self.calls == 4:
                self.state = WAIT
            elif self.calls == 5:
                self.state = WAIT_TURN
            elif self.calls == 10:
                self.state = WAIT
            elif self.calls == 20:
                self.state = MOVE
                self.speedF = 17.0
                self.nspeed = 17.0

        def enter_cut_from_move(self, *_args, **_kwargs):
            self.pos_x = 3.0
            self.pos_z = 4.0

    monkeypatch.setattr(rest_model, "rest_state", lambda *_args, **_kwargs: FakeState())
    hit = live_slash._walking_setup_sim("unused.json", type("Seam", (), {"TRIS": []})())
    assert hit["transition_frame"] == 20
    assert hit["b_frame"] == 18
    assert hit["turn_down_frame"] == 4
    assert hit["walk_start_frame"] == 10
    rows = _walking_setup_rows(hit, tail_frames=2)
    assert rows[18]["buttons"] == 0x200
    assert rows[19]["buttons"] == 0


def test_live_walking_measurement_replays_cdown_turnaround(monkeypatch):
    class Control:
        def __init__(self):
            self.calls = []

        def advance_with(self, **values):
            self.calls.append(values)

    def live(proc, speed=0.0, normal=0.0, x=1.0, z=2.0):
        value = state(x, z)
        value.state = proc
        value.speedF = speed
        value.nspeed = normal
        return value

    from tww_sim.land.constants import MOVE, SUBJECTIVITY, WAIT, WAIT_TURN
    after = [
        live(SUBJECTIVITY), live(SUBJECTIVITY), live(SUBJECTIVITY), live(WAIT),
        live(WAIT), live(WAIT_TURN), live(WAIT_TURN), live(WAIT_TURN),
        live(WAIT_TURN), live(WAIT), live(MOVE, 4.0, 6.0),
        live(MOVE, 13.969406127929688, 17.0, 3.0, 4.0),
    ]
    before = [live(SUBJECTIVITY)] + after[:-1]
    frames = [item for pair in zip(before, after) for item in pair]
    monkeypatch.setattr(live_slash, "read_state", lambda _reader: frames.pop(0))

    control = Control()
    speed_frame, measured, normalization = live_slash._measure_live_walking_old(
        object(), control
    )
    assert speed_frame == 11
    assert (measured.x, measured.z, measured.speedF, measured.nspeed) == (
        3.0, 4.0, 13.969406127929688, 17.0
    )
    assert normalization == {
        "turn_down_frame": 4,
        "turn_settle_frame": 9,
        "walk_start_frame": 10,
    }
    assert len(control.calls) == 12
    assert control.calls[4]["stickY"] == 1
    assert control.calls[10]["stickY"] == 254
    assert all(call["substickY"] == 0 for call in control.calls)
    assert all(call["buttons"] == 0 for call in control.calls)


def test_live_calibration_requires_exact_target_seam_dust():
    hits = [
        (40.0, 0.0, -550.0183715820312, -1395.183837890625),
        (40.2, 0.1, -550.2144775390625, -1395.23388671875),
    ]
    assert live_slash._matching_exact_dust(
        (-550.2144775390625, -1395.23388671875), hits
    ) == hits[1]
    assert live_slash._matching_exact_dust(
        (-633.342041015625, -1322.1488037109375), hits
    ) is None


def test_subjectivity_yaw_plan_never_leaves_selected_range():
    plan = live_slash._subjectivity_yaw_plan(44043, 47104, 46500, 52000)
    assert plan == (5, 47318)
    assert live_slash.angle_in_range(plan[1], 46500, 52000)


def test_subjectivity_yaw_plan_reports_unreachable_narrow_range():
    assert live_slash._subjectivity_yaw_plan(44043, 47104, 47100, 47110) is None

def test_clean_dtm_writer_repeats_each_game_frame_four_polls(tmp_path):
    out = tmp_path / "slash.dtm"
    info = build_dtm_from_sticks([
        {"stickX": 79, "stickY": 252, "substickX": 128,
         "substickY": 0, "buttons": 0x200},
        {"stickX": 128, "stickY": 128, "substickX": 128,
         "substickY": 0, "buttons": 0},
    ], str(out), polls=4, seed=0, game_id=b"GZLJ11")
    data = out.read_bytes()
    assert data[:4] == b"DTM\x1a"
    assert data[4:10] == b"GZLJ11"
    assert data[12] == 1
    assert info == {"frames": 2, "rows": 8, "bytes": 320, "polls": 4, "seed": 0}
    assert data[256:264] == bytes((0x04, 0x40, 0, 0, 79, 252, 128, 0))
    assert data[256:288] == data[256:264] * 4


def test_dtm_writer_accepts_arbitrary_six_character_game_id(tmp_path):
    out = tmp_path / "custom.dtm"
    build_dtm_from_sticks([], str(out), game_id="ABC123")
    assert out.read_bytes()[4:10] == b"ABC123"


def test_game_id_defaults_and_validates():
    assert parse_game_id("") == b"GZLJ01"
    assert parse_game_id("GZLJ11") == b"GZLJ11"
    assert parse_game_id("ABC123") == b"ABC123"
    with pytest.raises(ValueError, match="exactly 6"):
        parse_game_id("GZLJ1")


def test_candidate_export_contains_complete_timeline(tmp_path, monkeypatch):
    source = tmp_path / "prepared.sav"
    source.write_bytes(b"state")
    monkeypatch.setattr(live_slash, "CANDIDATE_DIR", str(tmp_path / "candidates"))
    hit = {
        "setup": {"savestate": str(source)},
        "transition_frame": 1,
        "input_rows": [
            {"stickX": 128, "stickY": 255, "cstickX": 128, "cstickY": 0, "buttons": 0},
            {"stickX": 128, "stickY": 255, "cstickX": 128, "cstickY": 0, "buttons": 0x200},
            {"stickX": 128, "stickY": 128, "cstickX": 128, "cstickY": 0, "buttons": 0},
        ],
    }
    _export_candidate(hit, 0, b"GZLJ11", log=lambda _line: None)
    movie = (tmp_path / "candidates" / "clip_01.dtm").read_bytes()
    assert movie[4:10] == b"GZLJ11"
    assert len(movie) == 256 + 3 * 4 * 8
    assert movie[256 + 4 * 8] & 0x04
    assert (tmp_path / "candidates" / "clip_01.dtm.sav").read_bytes() == b"state"
    assert hit["verification"] == "simulation_candidate"


def test_facing_cache_round_trip_and_key_scope(tmp_path):
    geo = {"S": [1.0, 2.0, 3.0], "wallA": {"poly": 1}}
    payload = (0, geo, 1234, 26.0, 45.0)
    assert _facing_cache_key(payload) == _facing_cache_key((99, geo, 1234, 26.0, 45.0))
    assert _facing_cache_key(payload) != _facing_cache_key((0, geo, 1235, 26.0, 45.0))
    path = tmp_path / "facings.json"
    entries = {_facing_cache_key(payload): [[1.25, -2.5]]}
    _save_facing_cache(entries, str(path))
    assert _load_facing_cache(str(path)) == entries


def test_density_screen_reuses_complete_cache(monkeypatch):
    class Candidate:
        geo = {"S": [1.0, 2.0, 3.0]}
        csangle = 1234
        roll_speedf = 26.0
        aim_deg = 45.0
        F = 8192

        @staticmethod
        def perp(point):
            return point[0]

        @staticmethod
        def along(point):
            return point[1]

    candidate = Candidate()
    payload = (0, candidate.geo, candidate.csangle, candidate.roll_speedf, candidate.aim_deg)
    monkeypatch.setattr(
        live_slash, "_load_facing_cache",
        lambda: {_facing_cache_key(payload): [[1.25, -2.5]]},
    )
    logs = []
    selected = choose_feasible_roll_aim([candidate], log=logs.append)
    assert selected is candidate
    assert selected._witness_olds == [(1.25, -2.5)]
    assert "reused 1/1" in logs[0]


class FakeMovieControl:
    def __init__(self, *, recording=False, playing=False):
        self.recording = recording
        self.playing = playing
        self.calls = []

    def command(self, name, values=None):
        self.calls.append((name, values))
        if name == "recordstop":
            self.recording = False
        return {"ok": True, "recording": self.recording, "playing": self.playing}


def test_active_recording_is_backed_up_and_stopped(tmp_path, monkeypatch):
    control = FakeMovieControl(recording=True)
    monkeypatch.setattr(live_slash, "CLIP_STATE_DIR", str(tmp_path))
    logs = []
    _ensure_standalone_savestates(control, log=logs.append)
    stop = [call for call in control.calls if call[0] == "recordstop"]
    assert len(stop) == 1
    assert stop[0][1]["path"].endswith(".dtm")
    assert not control.recording
    assert "standalone" in logs[0]


def test_active_movie_playback_is_rejected():
    with pytest.raises(RuntimeError, match="playing a movie"):
        _ensure_standalone_savestates(FakeMovieControl(playing=True))
