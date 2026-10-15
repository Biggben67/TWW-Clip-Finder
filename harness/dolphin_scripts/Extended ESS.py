"""Live, camera-only Extended ESS for TWW JP (GZLJ01 and GZLJ11).

Requires the sibling extended_ess_core.py and existing tww_sim package.
No savestates or game-memory writes. Normal MOVE + ESS + manual land camera
only; unsupported camera modes and prediction mismatches relinquish control.
"""

from collections import deque
from dataclasses import asdict
import json
import math
from pathlib import Path
from importlib import reload
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dolphin import controller, event, gui, memory
import extended_ess_core

# Dolphin can retain imported helpers when the GUI script is reloaded.
reload(extended_ess_core)
from extended_ess_core import Pad, State, advance, choose_camera, ess_input
from tww_sim.core.mathlib import s16_signed


PLAYER_POINTER = 0x803AD860
CAMERA_POINTER = 0x803AD380
STYLE_TABLE = 0x803485AC
GAME_FRAME = 0x803E9D34


def pointer(address):
    value = memory.read_u32(address)
    if not 0x80000000 <= value < 0x81800000:
        raise ValueError("Player/camera is not loaded")
    return value


def snapshot():
    if memory.read_u32(0x80000000) != 0x475A4C4A:  # GZLJ; disc revision is unrestricted.
        raise ValueError("Only the JP GZLJ memory layout is supported")
    p = pointer(PLAYER_POINTER)
    camera = pointer(pointer(CAMERA_POINTER) + 0x34) + 0x244
    state_id = memory.read_u32(p + 0x3100)
    if state_id != 6:
        raise ValueError("Waiting for untargeted MOVE brakeslide (state %d)" % state_id)
    speed = memory.read_f32(p + 0x17C)
    velocity = memory.read_f32(p + 0x34E4)
    if not math.isfinite(speed) or not math.isfinite(velocity) or speed >= 0 or velocity >= 0:
        raise ValueError("Waiting for negative speed")
    mode = memory.read_u32(camera + 0x13C)
    if mode != 12 or memory.read_u32(camera + 0x11C) < 2:
        raise ValueError("Waiting for settled manual/free camera (mode %d)" % mode)
    style = memory.read_u32(camera + 0x510)
    if style >= 512:
        raise ValueError("Invalid camera style")
    row = STYLE_TABLE + style * 0x84 + 4
    scale = memory.read_f32(row + 24 * 4)
    cushion = memory.read_f32(row + 21 * 4)
    max_speed = memory.read_f32(p + 0x1D0)
    if not (0 < scale <= 30 and 0 < cushion <= 1 and 0 < max_speed <= 100):
        raise ValueError("Unsupported camera/movement parameters")
    state = State(
        velocity, memory.read_u16(p + 0x12E), memory.read_u16(p + 0x136),
        memory.read_u16(camera + 0x6C), memory.read_u16(camera + 0x42),
        memory.read_u16(camera + 0x3AE), max_speed, scale, cushion,
    )
    if abs(s16_signed(state.controlled - state.view_yaw - 0x8000)) > 8192:
        raise ValueError("Camera yaw is outside the manual-camera model")
    return state


def get_pad(buttons):
    return Pad(*(int(buttons.get(key, 128)) for key in
                 ("StickX", "StickY", "CStickX", "CStickY")))


def polled_pad():
    # This is the real queued PADStatus, not a queue inferred from callback
    # counts. Live pulse tests show this poll acts on the next game update.
    return Pad(*(memory.read_u8(0x803E4410 + offset) for offset in (2, 3, 4, 5)))


def interrupted(buttons):
    return any(buttons.get(key, False) for key in ("L", "R", "A", "B", "X", "Y", "Z", "Start")) or (
        int(buttons.get("TriggerLeft", 0)) > 30 or
        int(buttons.get("TriggerRight", 0)) > 30
    )


_window = gui.window("Extended ESS")
_toggle = _window.checkbox("Enabled", checked=False)
_margin_control = _window.input_text("Threshold clearance (angle units)", "16")
_save_trace = _window.button("Save diagnostic trace")
_status = _window.text("Disabled")
_enabled = False
_margin = 16
_message = "Disabled"
_fault = ""
_last_frame = None
_trace = deque(maxlen=180)
_expected = None
_mismatches = 0
_output = None
_held_signature = None


def reset():
    global _last_frame, _expected, _mismatches, _output, _held_signature
    _last_frame = None
    _expected = None
    _mismatches = 0
    _output = None
    _held_signature = None


def save_trace():
    path = Path(__file__).with_name("Extended ESS diagnostics.json")
    path.write_text(json.dumps(dict(version=3, clearance=_margin, message=_message,
                                   fault=_fault, frames=list(_trace)), indent=2))
    return path


@event.on_hostupdate
def host_update():
    global _enabled, _margin, _fault, _message
    enabled = bool(_toggle.checked)
    settings_error = ""
    try:
        margin = int(str(_margin_control.value))
        if not 0 <= margin <= 8192:
            raise ValueError()
    except (ValueError, TypeError):
        enabled = False
        margin = _margin
        settings_error = "Invalid clearance: use 0-8192 angle units"
    if (enabled, margin) != (_enabled, _margin):
        reset()
        _fault = ""
    _enabled, _margin = enabled, margin
    if _save_trace.clicked:
        try:
            _message = "Diagnostic saved to " + str(save_trace())
        except OSError as exc:
            _message = "Could not save diagnostic: " + str(exc)
    _status.set(settings_error or _fault or (_message if enabled else "Disabled"))


@event.on_savestateload
def state_loaded(from_slot, slot):
    global _fault
    reset()
    _fault = ""


@event.on_frameadvance
def update():
    global _last_frame, _expected, _output, _message, _fault, _mismatches, _held_signature
    if not _enabled or _fault:
        return
    buttons = controller.get_gc_buttons(0)
    held = get_pad(buttons)
    signature = (held.x, held.y, held.cy)
    if interrupted(buttons) or not ess_input(held):
        reset()
        _message = "Waiting for ESS with no action/target buttons"
        return
    try:
        frame = memory.read_u32(GAME_FRAME)
        live = snapshot()
        if frame == _last_frame and signature == _held_signature:
            if _output is not None:
                buttons["CStickX"] = _output
                controller.set_gc_buttons(0, buttons)
            return
        if (_last_frame is not None and ((frame - _last_frame) & 0xFFFFFFFF) != 1
                or signature != _held_signature):
            reset()
        _last_frame, _held_signature = frame, signature
        queued = polled_pad()
        record = dict(frame=frame, live=asdict(live), held=asdict(held),
                      queued=asdict(queued), expected=asdict(_expected) if _expected else None)
        _trace.append(record)
        residual = ""
        if _expected is not None:
            speed_error = abs(live.velocity - _expected.velocity)
            yaw_error = abs(s16_signed(live.controlled - _expected.controlled))
            travel_error = abs(s16_signed(live.travel - _expected.travel))
            facing_error = abs(s16_signed(live.facing - _expected.facing))
            residual = "\nPrediction error: speed %.6f, camera %d, travel %d, facing %d" % (
                speed_error, yaw_error, travel_error, facing_error,
            )
            # The player branch should match closely. Small committed-camera
            # corrections are a measured disturbance, not a timing failure.
            mismatch = (speed_error > 0.005 or max(travel_error, facing_error) > 16
                        or yaw_error > max(128, _margin // 2))
            _mismatches = _mismatches + 1 if mismatch else 0
            if _mismatches >= 2 or facing_error > 21845:
                _fault = "Assistance stopped: live prediction mismatch." + residual
                try:
                    save_trace()
                except OSError:
                    pass
                reset()
                return
        plan = choose_camera(live, held, (queued,), margin=_margin)
        if plan is None:
            # Relinquish control rather than repeatedly issuing a stale pulse.
            _output = None
            _message = "No safe camera continuation in the lookahead" + residual
            issued = held
        else:
            _output = plan.cx
            issued = Pad(held.x, held.y, plan.cx, held.cy)
            buttons["CStickX"] = plan.cx
            controller.set_gc_buttons(0, buttons)
            record["plan"] = asdict(plan)
            _message = ("%s | speed %.6f | C-X %d\n"
                        "Predicted %df loss %.6f | neutral %.6f | saving %.6f%s") % (
                "Neutral camera" if plan.cx == 128 else "Steering",
                live.velocity, plan.cx, plan.evaluated_frames, plan.loss, plan.neutral_loss,
                plan.neutral_loss - plan.loss, residual,
            )
        record["issued"] = asdict(issued)
        _expected = advance(live, queued).state
    except Exception as exc:
        reset()
        _message = str(exc)


print("[Extended ESS] loaded; camera-only JP MOVE controller, disabled by default")
