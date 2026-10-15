"""DTM-row brute force for the three-magic grass outcome after Barrier Skip.

The immutable starting movie state belongs in slot 5 at input row 368265.
Trials alter only isolated sword draw/put-away edges while Link has negative
mNormalSpeed. A successful three-small-magic outcome is saved to slot 10.
"""

from __future__ import annotations

from importlib import reload
from pathlib import Path
import random
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dolphin_dtm as dtm
from dolphin import controller, event, gui, memory, savestate
import barrier_magic_rng_core

reload(barrier_magic_rng_core)
from barrier_magic_rng_core import build_schedule, eligible_pulse_rows, schedule_signature


SCRIPT_NAME = "Barrier Grass Magic Brute Force"
LOG_PATH = Path(__file__).with_name("Barrier Grass Magic Brute Force.log")
# dolphin.controller uses zero-based ports.  This TAS build's dolphin_dtm
# module uses the one-based GameCube lane number instead.
LIVE_CONTROLLER = 0
DTM_CONTROLLER = 1
PLAYER_PTR = 0x803AD860
M_NORMAL_SPEED = 0x34E4
M_EQUIP_ITEM = 0x3488
M_CUR_PROC = 0x3100
UPPER2_RATE = 0x2FB0
SWORD_ITEM = 0x0103
CUT_PROCS = frozenset((0x41, 0x42))

ACTOR_LIST_HEAD = 0x803654CC
ACTOR_NODE_NEXT = 0x00
ACTOR_NODE_GPTR = 0x0C
ACTOR_PROC_ID = 0x08
PROC_ITEM = 257
ITEM_TYPE = 0x63A
SMALL_MAGIC = 9

DEFAULT_START_ROW = 368265
DEFAULT_ACTIONABLE_ROW = 370097
DEFAULT_RESULT_ROW = 370281
DEFAULT_BASE_SLOT = 5
DEFAULT_SUCCESS_SLOT = 10
NO_PULSE_START_ROW = 368481
NO_PULSE_END_ROW = 369089
FINAL_SETTLE_ROWS = 96
BUTTON_HOLD_ROWS = 5
INITIAL_SETTLE_ROWS = 48
MINIMUM_PULSE_GAP = 64
AUTHOR_LEAD_ROWS = 6
EQUIP_STABLE_ROWS = 12
EQUIP_CHANGE_TIMEOUT_ROWS = 48
MAX_RANDOM_PULSES = 10
MAX_ACTOR_NODES = 4096


_window = gui.window(SCRIPT_NAME)
_enabled_control = _window.checkbox("Enabled", checked=False)
_start_row_control = _window.input_text("First editable input row", str(DEFAULT_START_ROW))
_actionable_row_control = _window.input_text("Sword actionable by row", str(DEFAULT_ACTIONABLE_ROW))
_result_row_control = _window.input_text("No-drop timeout row", str(DEFAULT_RESULT_ROW))
_base_slot_control = _window.input_text("Immutable base slot", str(DEFAULT_BASE_SLOT))
_success_slot_control = _window.input_text("Three-magic save slot", str(DEFAULT_SUCCESS_SLOT))
_seed_control = _window.input_text("Random seed (blank = random)", "")
_start_button = _window.button("Start / restart search")
_status_control = _window.text("Save the row-368265 starting state to slot 5, then start.")
_log_control = _window.text("Log: %s" % LOG_PATH)

_enabled = False
_running = False
_phase = "idle"
_message = "Ready"
_start_row = DEFAULT_START_ROW
_actionable_row = DEFAULT_ACTIONABLE_ROW
_result_row = DEFAULT_RESULT_ROW
_deadline_row = DEFAULT_ACTIONABLE_ROW - FINAL_SETTLE_ROWS
_native_start_row = None
_native_actionable_row = None
_native_result_row = None
_native_deadline_row = None
_movie_row_scale = 1
_metadata_uses_movie_rows = True
_base_slot = DEFAULT_BASE_SLOT
_success_slot = DEFAULT_SUCCESS_SLOT
_rng = random.Random()
_base_rows = {}
_trial_base_rows = {}
_negative_rows = set()
_baseline_magic = set()
_baseline_last_row = None
_baseline_last_negative = False
_schedule = []
_schedule_by_row = {}
_pulse_buttons = {}
_pulse_blocks = {}
_plan_index = 0
_pending_expected_drawn = None
_pending_change_deadline = None
_last_live_drawn = None
_live_equip_stable_since = None
_seen_schedules = set()
_trial = 0
_last_row = None
_last_actual_pulse = None
_trial_invalid = None
_base_sword_drawn = False
_actionable_checked = False
_reload_requested = False
_next_phase = "baseline"
_host_updates = 0
_frame_updates = 0


def _log(message):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), str(message))
    try:
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
    except Exception:
        pass
    print("[%s] %s" % (SCRIPT_NAME, message))


def _log_exception(context, exc):
    _log("%s: %s\n%s" % (context, exc, traceback.format_exc()))


def _show_status():
    try:
        _status_control.set(_message if _enabled_control.checked else "Disabled")
    except Exception:
        pass


try:
    LOG_PATH.write_text("", encoding="utf-8")
except Exception:
    pass
_log("script loaded; log path=%s" % LOG_PATH)


def _parse_int(control, default, minimum, maximum):
    try:
        value = int(str(control.value).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _metadata():
    meta = dtm.get_metadata()
    if not meta or meta.get("kind") != "gc":
        raise RuntimeError("play a GameCube DTM before starting the search")
    return meta


def _raw_current_row():
    meta = _metadata()
    value = meta.get("current_input_row", meta.get("CurrentInputRow"))
    if value is None:
        raise RuntimeError("this Dolphin build does not expose current_input_row")
    return int(value)


def _current_row():
    raw = _raw_current_row()
    if _native_start_row is None or not _metadata_uses_movie_rows:
        return raw
    return _native_start_row + ((raw - _start_row) // _movie_row_scale)


def _display_row(native_row):
    if _native_start_row is None:
        return int(native_row)
    return _start_row + ((int(native_row) - _native_start_row) * _movie_row_scale)


def _pulse_block_allowed(start_row, end_row):
    display_start = _display_row(start_row)
    display_end = _display_row(end_row)
    return display_end < NO_PULSE_START_ROW or display_start > NO_PULSE_END_ROW


def _row_state_or_none(row):
    try:
        state = dtm.get_gc(int(row), DTM_CONTROLLER)
    except Exception:
        return None
    return dict(state) if state is not None else None


def _pad_distance(movie_state, live_state):
    score = 0
    for key in ("StickX", "StickY", "CStickX", "CStickY", "TriggerLeft", "TriggerRight"):
        score += abs(int(movie_state.get(key, 0)) - int(live_state.get(key, 0)))
    for key in ("A", "B", "X", "Y", "Z", "L", "R", "Start", "Up", "Down", "Left", "Right"):
        if bool(movie_state.get(key, False)) != bool(live_state.get(key, False)):
            score += 512
    return score


def _resolve_row_mapping(raw_row):
    global _native_start_row, _native_actionable_row, _native_result_row
    global _native_deadline_row, _movie_row_scale, _metadata_uses_movie_rows

    if _row_state_or_none(_start_row) is not None:
        scale = 1
        native_start = _start_row
    else:
        scale = 2
        estimate = (_start_row - 1) // scale
        live = controller.get_gc_buttons(LIVE_CONTROLLER)
        candidates = []
        for candidate in range(max(0, estimate - 4), estimate + 5):
            state = _row_state_or_none(candidate)
            if state is not None:
                candidates.append((_pad_distance(state, live), abs(candidate - estimate), candidate))
        if not candidates:
            raise RuntimeError(
                "movie row %d and its controller-1 half-row neighborhood are unavailable" % _start_row
            )
        native_start = min(candidates)[2]

    for label, movie_row in (
        ("actionable", _actionable_row),
        ("timeout", _result_row),
        ("draw deadline", _deadline_row),
    ):
        if (movie_row - _start_row) % scale:
            raise RuntimeError(
                "%s movie row %d has the wrong parity for start row %d with row scale %d"
                % (label, movie_row, _start_row, scale)
            )

    _movie_row_scale = scale
    _native_start_row = native_start
    _native_actionable_row = native_start + ((_actionable_row - _start_row) // scale)
    _native_result_row = native_start + ((_result_row - _start_row) // scale)
    _native_deadline_row = native_start + ((_deadline_row - _start_row) // scale)
    _metadata_uses_movie_rows = abs(raw_row - _start_row) <= abs(raw_row - native_start)
    _log(
        "row mapping raw=%d display_start=%d native_start=%d scale=%d metadata_domain=%s "
        "native_actionable=%d native_timeout=%d"
        % (raw_row, _start_row, _native_start_row, _movie_row_scale,
           "movie" if _metadata_uses_movie_rows else "controller",
           _native_actionable_row, _native_result_row)
    )


def _valid_ptr(value):
    return 0x80000000 <= int(value) < 0x81800000


def _player():
    pointer = int(memory.read_u32(PLAYER_PTR))
    if not _valid_ptr(pointer):
        raise RuntimeError("Link is not loaded")
    return pointer


def _link_state():
    player = _player()
    return {
        "speed": float(memory.read_f32(player + M_NORMAL_SPEED)),
        "equip": int(memory.read_u16(player + M_EQUIP_ITEM)),
        "proc": int(memory.read_u32(player + M_CUR_PROC)),
        "upper_rate": float(memory.read_f32(player + UPPER2_RATE)),
    }


def _iter_item_actors():
    node = int(memory.read_u32(ACTOR_LIST_HEAD))
    seen = set()
    for _ in range(MAX_ACTOR_NODES):
        if not _valid_ptr(node) or node in seen:
            return
        seen.add(node)
        actor = int(memory.read_u32(node + ACTOR_NODE_GPTR))
        if _valid_ptr(actor) and int(memory.read_u16(actor + ACTOR_PROC_ID)) == PROC_ITEM:
            yield actor
        node = int(memory.read_u32(node + ACTOR_NODE_NEXT))


def _magic_actors():
    result = set()
    try:
        for actor in _iter_item_actors():
            if int(memory.read_u8(actor + ITEM_TYPE)) == SMALL_MAGIC:
                result.add(actor)
    except Exception:
        pass
    return result


def _get_row(row):
    state = dtm.get_gc(int(row), DTM_CONTROLLER)
    if state is None:
        raise RuntimeError("DTM row %d is unavailable" % row)
    return dict(state)


def _set_row(row, state):
    expected = dict(state)
    if not dtm.set_gc(int(row), DTM_CONTROLLER, expected):
        raise RuntimeError("failed to edit DTM row %d" % row)
    actual = dtm.get_gc(int(row), DTM_CONTROLLER)
    if actual is None:
        raise RuntimeError("DTM row %d disappeared after set_gc" % row)
    for key in ("A", "B"):
        if bool(actual.get(key, False)) != bool(expected.get(key, False)):
            raise RuntimeError(
                "DTM row %d failed %s readback (wanted %s, got %s)"
                % (row, key, bool(expected.get(key, False)), bool(actual.get(key, False)))
            )


def _capture_base_rows():
    global _base_rows
    _base_rows = {
        row: _get_row(row)
        for row in range(_native_start_row - 1, _native_actionable_row + 2)
    }


def _restore_base_rows():
    for row, state in _base_rows.items():
        _set_row(row, state)


def _author_button(row, button=None, source_rows=None):
    rows = _base_rows if source_rows is None else source_rows
    state = dict(rows[row])
    state["A"] = False
    state["B"] = False
    if button is not None:
        state[button] = True
    _set_row(row, state)


def _make_clean_trial_rows():
    rows = {row: dict(state) for row, state in _base_rows.items()}
    for row in _negative_rows:
        state = rows.get(row)
        if state is not None:
            state["A"] = False
            state["B"] = False
    return rows


def _preserve_dtm_for_slot(slot):
    function = getattr(dtm, "save_to_savestate_slot", None)
    if function is None:
        raise RuntimeError("this Dolphin build lacks dtm.save_to_savestate_slot")
    if not function(int(slot)):
        raise RuntimeError("failed to associate the edited DTM with slot %d" % slot)


def _make_schedule(trial_rows):
    candidates = eligible_pulse_rows(
        _negative_rows, trial_rows, _native_start_row, _native_deadline_row,
    )
    candidates = [
        row for row in candidates
        if row >= _native_start_row + INITIAL_SETTLE_ROWS
        and row + BUTTON_HOLD_ROWS - 1 <= _native_deadline_row
        and all(offset in _negative_rows for offset in range(row, row + BUTTON_HOLD_ROWS))
        and _pulse_block_allowed(row, row + BUTTON_HOLD_ROWS - 1)
    ]
    if not candidates:
        raise RuntimeError("baseline found no isolated negative-speed A/B rows before the draw deadline")
    for _ in range(1000):
        schedule = build_schedule(
            candidates, _rng, MINIMUM_PULSE_GAP, MAX_RANDOM_PULSES,
        )
        signature = schedule_signature(schedule)
        if signature not in _seen_schedules:
            _seen_schedules.add(signature)
            return schedule
    raise RuntimeError("the available negative-speed rows produced no new schedules")


def _prepare_trial():
    global _schedule, _schedule_by_row, _pulse_buttons, _pulse_blocks
    global _trial, _trial_base_rows, _plan_index
    global _pending_expected_drawn, _pending_change_deadline
    global _last_live_drawn, _live_equip_stable_since
    global _last_actual_pulse, _trial_invalid, _actionable_checked
    _restore_base_rows()
    _trial_base_rows = _make_clean_trial_rows()
    removed_edges = []
    for row in _negative_rows:
        if row in _trial_base_rows:
            original = _base_rows[row]
            if original.get("A", False) or original.get("B", False):
                removed_edges.append(
                    "%d:%s" % (
                        _display_row(row),
                        "A" if original.get("A", False) else "B",
                    )
                )
            _set_row(row, _trial_base_rows[row])
    _schedule = _make_schedule(_trial_base_rows)
    _schedule_by_row = {pulse.row: pulse for pulse in _schedule}
    _pulse_buttons = {}
    _pulse_blocks = {}
    _plan_index = 0
    _pending_expected_drawn = None
    _pending_change_deadline = None
    _last_live_drawn = None
    _live_equip_stable_since = None
    _preserve_dtm_for_slot(_base_slot)
    _trial += 1
    _last_actual_pulse = None
    _trial_invalid = None
    _actionable_checked = False
    print("[%s] trial %d authored pulses: %s" % (
        SCRIPT_NAME,
        _trial,
        ", ".join("%d%s" % (_display_row(pulse.row),
                              "(ensure drawn)" if pulse.ensure_drawn else "")
                  for pulse in _schedule) or "none",
    ))
    print("[%s] cleared original A/B on %d negative-speed row(s)" % (
        SCRIPT_NAME, len(_negative_rows),
    ))
    _log("trial %d prepared; %d cleared negative rows; readback passed; pulses=%s" % (
        _trial, len(_negative_rows),
        ",".join("%d%s" % (_display_row(pulse.row),
                             "F" if pulse.ensure_drawn else "")
                 for pulse in _schedule) or "none",
    ))
    _log("original negative-speed A/B edges removed: %s" % (
        ",".join(removed_edges) or "none",
    ))


def _request_reload(next_phase, reason):
    global _reload_requested, _next_phase, _message
    _reload_requested = True
    _next_phase = next_phase
    _message = reason
    _show_status()


def _begin_search():
    global _running, _phase, _message, _start_row, _actionable_row, _result_row
    global _deadline_row, _base_slot, _success_slot, _rng, _negative_rows
    global _baseline_magic, _baseline_last_row, _baseline_last_negative
    global _seen_schedules, _trial, _last_row
    global _reload_requested, _next_phase, _base_rows, _trial_base_rows, _native_start_row
    global _base_sword_drawn, _actionable_checked, _pulse_buttons, _pulse_blocks
    global _plan_index, _pending_expected_drawn, _pending_change_deadline
    global _last_live_drawn, _live_equip_stable_since

    _metadata()
    _log("begin requested; metadata=%r" % _metadata())
    if _base_rows and _phase != "success":
        _restore_base_rows()
    _start_row = _parse_int(_start_row_control, DEFAULT_START_ROW, 0, 2_000_000_000)
    _actionable_row = _parse_int(_actionable_row_control, DEFAULT_ACTIONABLE_ROW, _start_row + 2, 2_000_000_000)
    _result_row = _parse_int(_result_row_control, DEFAULT_RESULT_ROW, _actionable_row + 1, 2_000_000_000)
    _base_slot = _parse_int(_base_slot_control, DEFAULT_BASE_SLOT, 0, 99)
    _success_slot = _parse_int(_success_slot_control, DEFAULT_SUCCESS_SLOT, 0, 99)
    _deadline_row = _actionable_row - FINAL_SETTLE_ROWS
    seed_text = str(_seed_control.value).strip()
    _rng = random.Random(int(seed_text)) if seed_text else random.Random()
    _base_rows = {}
    _trial_base_rows = {}
    _native_start_row = None
    _negative_rows = set()
    _baseline_magic = set()
    _baseline_last_row = None
    _baseline_last_negative = False
    _seen_schedules = set()
    _trial = 0
    _pulse_buttons = {}
    _pulse_blocks = {}
    _plan_index = 0
    _pending_expected_drawn = None
    _pending_change_deadline = None
    _last_live_drawn = None
    _live_equip_stable_since = None
    _base_sword_drawn = False
    _actionable_checked = False
    _last_row = None
    _running = True
    _phase = "loading"
    _reload_requested = False
    _next_phase = "baseline"
    _message = "Initializing the current state as the unmodified baseline"
    _log("configuration display_start=%d actionable=%d timeout=%d base_slot=%d "
         "success_slot=%d dtm_gc_lane=%d live_gc_port=%d no_pulse=%d-%d" % (
        _start_row, _actionable_row, _result_row, _base_slot, _success_slot,
        DTM_CONTROLLER, LIVE_CONTROLLER + 1, NO_PULSE_START_ROW, NO_PULSE_END_ROW,
    ))
    _complete_loaded_phase()


def _load_requested_state():
    global _reload_requested, _phase, _last_row
    _reload_requested = False
    _phase = "loading"
    _last_row = None
    _log("loading slot %d; next_phase=%s" % (_base_slot, _next_phase))
    savestate.load_from_slot(_base_slot)
    _log("savestate.load_from_slot(%d) returned" % _base_slot)


def _start_loaded_phase(row):
    global _phase, _baseline_magic, _message, _base_sword_drawn
    global _last_live_drawn, _live_equip_stable_since
    if row > _native_start_row + 4:
        raise RuntimeError(
            "current/loaded state resumes at controller-1 row %d, after required row %d (slot %d)" % (
                row, _native_start_row, _base_slot,
            )
        )
    _phase = _next_phase
    _log("starting loaded phase=%s at native_row=%d display_row=%d" % (
        _phase, row, _display_row(row),
    ))
    _baseline_magic = _magic_actors()
    if _phase == "baseline":
        _base_sword_drawn = _link_state()["equip"] == SWORD_ITEM
        _message = (
            "Baseline: movie/controller row scale %d:1; recording negative speed"
            % _movie_row_scale
        )
    else:
        initial_state = _link_state()
        _last_live_drawn = initial_state["equip"] == SWORD_ITEM
        _live_equip_stable_since = row
        _log("trial starts with live sword_drawn=%s equip=0x%X proc=0x%X" % (
            _last_live_drawn, initial_state["equip"], initial_state["proc"],
        ))
        _message = "Trial %d: planned action opportunities %s" % (
            _trial,
            ", ".join(str(_display_row(pulse.row)) for pulse in _schedule) or "none",
        )
    _show_status()


def _complete_loaded_phase():
    raw_row = _raw_current_row()
    _log("completing loaded phase=%s raw_row=%d native_initialized=%s" % (
        _next_phase, raw_row, _native_start_row is not None,
    ))
    if _native_start_row is None:
        _resolve_row_mapping(raw_row)
        _capture_base_rows()
    _start_loaded_phase(_current_row())


def _record_baseline(row, state):
    global _baseline_last_row, _baseline_last_negative
    negative = state["speed"] < 0.0
    if _native_start_row <= row <= _native_deadline_row and negative:
        first = row
        if _baseline_last_negative and _baseline_last_row is not None:
            first = max(_native_start_row, _baseline_last_row + 1)
        _negative_rows.update(range(first, row + 1))
    _baseline_last_row = row
    _baseline_last_negative = negative


def _advance_live_action_plan(row, state):
    global _plan_index, _pending_expected_drawn, _pending_change_deadline
    global _last_live_drawn, _live_equip_stable_since, _trial_invalid, _message

    drawn = state["equip"] == SWORD_ITEM
    if _last_live_drawn is None or drawn != _last_live_drawn:
        _log("live sword state changed at display=%d: %s -> %s" % (
            _display_row(row), _last_live_drawn, drawn,
        ))
        _last_live_drawn = drawn
        _live_equip_stable_since = row

    if _pending_expected_drawn is not None:
        if drawn == _pending_expected_drawn:
            _log("authored sword action completed at display=%d; drawn=%s" % (
                _display_row(row), drawn,
            ))
            _pending_expected_drawn = None
            _pending_change_deadline = None
        elif row >= _pending_change_deadline:
            _trial_invalid = "authored sword action was ignored near row %d" % _display_row(row)
            _log(_trial_invalid)
            _pending_expected_drawn = None
            _pending_change_deadline = None
        else:
            return

    while _plan_index < len(_schedule):
        pulse = _schedule[_plan_index]
        if row < pulse.row - AUTHOR_LEAD_ROWS:
            return

        if pulse.ensure_drawn and drawn:
            _log("final draw action unnecessary at display=%d; sword already drawn" % (
                _display_row(row),
            ))
            _plan_index += 1
            return

        stable_rows = row - _live_equip_stable_since
        start_row = max(pulse.row, row + AUTHOR_LEAD_ROWS)
        end_row = start_row + BUTTON_HOLD_ROWS - 1
        rows_are_negative = all(
            candidate in _negative_rows for candidate in range(start_row, end_row + 1)
        )
        outside_no_pulse_interval = _pulse_block_allowed(start_row, end_row)
        ready = (
            stable_rows >= EQUIP_STABLE_ROWS
            and state["speed"] < 0.0
            and state["proc"] not in CUT_PROCS
            and rows_are_negative
            and outside_no_pulse_interval
        )
        if not ready:
            if end_row > _native_deadline_row:
                if pulse.ensure_drawn:
                    _trial_invalid = "no actionable negative-speed window remained for final sword draw"
                    _log(_trial_invalid)
                    _plan_index += 1
                    return
                _log("skipping expired random action opportunity at display=%d" % (
                    _display_row(pulse.row),
                ))
                _plan_index += 1
                continue
            return

        button = "A" if drawn else "B"
        for held_row in range(start_row, end_row + 1):
            _author_button(held_row, button, _trial_base_rows)
            _pulse_buttons[held_row] = button
        _pulse_blocks[start_row] = (end_row, button, drawn)
        _plan_index += 1
        _pending_expected_drawn = not drawn
        _pending_change_deadline = end_row + EQUIP_CHANGE_TIMEOUT_ROWS
        _message = "Trial %d: %s held at rows %d-%d; waiting for sword state change" % (
            _trial, button, _display_row(start_row), _display_row(end_row),
        )
        _show_status()
        _log("authored live-gated action display=%d-%d button=%s drawn_before=%s "
             "stable_rows=%d change_deadline=%d" % (
                 _display_row(start_row), _display_row(end_row), button, drawn,
                 stable_rows, _display_row(_pending_change_deadline),
             ))
        return


def _three_new_magic():
    return len(_magic_actors() - _baseline_magic) >= 3


def _save_success(row):
    global _running, _phase, _message
    _preserve_dtm_for_slot(_success_slot)
    savestate.save_to_slot(_success_slot)
    _running = False
    _phase = "success"
    _message = (
        "SUCCESS on trial %d at row %d: three small-magic actors; saved slot %d. Pulses: %s"
        % (_trial, _display_row(row), _success_slot,
           ", ".join(str(_display_row(p.row)) for p in _schedule))
    )
    _show_status()
    print("[%s] %s" % (SCRIPT_NAME, _message))


def _finish_attempt(reason):
    global _phase
    _log("finishing phase=%s trial=%d reason=%s" % (_phase, _trial, reason))
    _phase = "preparing"
    _prepare_trial()
    _request_reload("trial", "%s; loading trial %d" % (reason, _trial))


@event.on_hostupdate
def host_update():
    global _enabled, _running, _message, _host_updates
    _host_updates += 1
    requested = bool(_enabled_control.checked)
    if _host_updates <= 10 or _host_updates % 120 == 0:
        _log("host #%d requested=%s cached=%s running=%s phase=%s reload=%s" % (
            _host_updates, requested, _enabled, _running, _phase, _reload_requested,
        ))
    if _start_button.clicked or (requested and not _enabled):
        _log("host start edge: clicked=%s enabled_edge=%s" % (
            bool(_start_button.clicked), requested and not _enabled,
        ))
        try:
            _enabled_control.checked = True
        except Exception:
            pass
        requested = True
        try:
            _begin_search()
        except Exception as exc:
            _running = False
            _message = "Stopped: %s" % exc
            _log_exception("begin search failed", exc)
    elif not requested and _enabled:
        if _base_rows and _phase != "success":
            try:
                _restore_base_rows()
            except Exception as exc:
                _message = "Disabled; failed to restore original rows: %s" % exc
            else:
                _message = "Disabled; original DTM rows restored"
        else:
            _message = "Disabled"
        _running = False
    if requested and _running:
        try:
            if _reload_requested:
                _load_requested_state()
            elif _phase == "loading":
                _complete_loaded_phase()
        except Exception as exc:
            _running = False
            _message = "Stopped during state initialization: %s" % exc
            _log_exception("host state initialization failed", exc)
    _enabled = requested
    _status_control.set(_message if requested else "Disabled")


@event.on_savestateload
def state_loaded(from_slot, slot):
    global _last_row
    _log("savestate event from_slot=%r slot=%r phase=%s reload=%s" % (
        from_slot, slot, _phase, _reload_requested,
    ))
    _last_row = None


@event.on_frameadvance
def update():
    global _last_row, _message, _running, _trial_invalid, _actionable_checked, _frame_updates
    _frame_updates += 1
    if _frame_updates <= 10 or _frame_updates % 120 == 0:
        try:
            raw_debug = _raw_current_row()
        except Exception as exc:
            raw_debug = "error:%s" % exc
        _log("frame #%d enabled=%s running=%s phase=%s reload=%s raw_row=%s" % (
            _frame_updates, _enabled, _running, _phase, _reload_requested, raw_debug,
        ))
    if not _enabled or not _running:
        return
    try:
        if _reload_requested:
            _load_requested_state()
            return

        raw_row = _raw_current_row()
        if _phase == "loading":
            if _native_start_row is None:
                _resolve_row_mapping(raw_row)
                _capture_base_rows()
            row = _current_row()
            _start_loaded_phase(row)
        else:
            row = _current_row()
        if row == _last_row:
            return
        state = _link_state()

        if _phase == "baseline":
            _record_baseline(row, state)
            if _three_new_magic():
                _save_success(row)
                return
            if row >= _native_result_row:
                _finish_attempt("baseline recorded %d negative-speed rows" % len(_negative_rows))
                return

        elif _phase == "trial":
            _advance_live_action_plan(row, state)
            if any(start - 2 <= row <= block[0] + 2
                   for start, block in _pulse_blocks.items()):
                movie_row = _get_row(row) if row in _base_rows else {}
                _log(
                    "pulse vicinity display=%d native=%d authored=%s dtmA=%s dtmB=%s "
                    "speed=%.9f equip=0x%X proc=0x%X upperRate=%.6f"
                    % (_display_row(row), row, _pulse_buttons.get(row, "-"),
                       bool(movie_row.get("A", False)), bool(movie_row.get("B", False)),
                       state["speed"], state["equip"], state["proc"], state["upper_rate"])
                )
            if row in _pulse_blocks:
                _, button, expected_drawn = _pulse_blocks[row]
                actual_drawn = state["equip"] == SWORD_ITEM
                _log(
                    "action block start display=%d button=%s expected_drawn=%s "
                    "actual_drawn=%s proc=0x%X"
                    % (_display_row(row), button, expected_drawn,
                       actual_drawn, state["proc"])
                )
                if actual_drawn != expected_drawn:
                    _trial_invalid = (
                        "sword was not actionable in the expected state at row %d"
                        % _display_row(row)
                    )
            if row < _native_actionable_row and state["proc"] in CUT_PROCS:
                _trial_invalid = "manipulation entered sword-cut proc 0x%X" % state["proc"]
            if not _actionable_checked and row >= _native_actionable_row:
                _actionable_checked = True
                _log(
                    "actionable check display=%d native=%d equip=0x%X proc=0x%X "
                    "upperRate=%.6f"
                    % (_display_row(row), row, state["equip"], state["proc"],
                       state["upper_rate"])
                )
                if state["equip"] != SWORD_ITEM:
                    _trial_invalid = "sword was not drawn at actionable row"
                elif state["proc"] in CUT_PROCS:
                    _trial_invalid = "sword was in cut proc 0x%X at actionable row" % state["proc"]
            if _three_new_magic():
                _save_success(row)
                return
            if row >= _native_result_row:
                reason = "trial %d produced fewer than three magic drops" % _trial
                if _trial_invalid:
                    reason += " (%s)" % _trial_invalid
                _finish_attempt(reason)
                return

        _last_row = row
    except Exception as exc:
        _running = False
        _message = "Stopped: %s" % exc
        _log_exception("frame update failed", exc)


print("[%s] loaded; disabled by default" % SCRIPT_NAME)
