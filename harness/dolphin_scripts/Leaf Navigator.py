"""Destination steering and optional four-frame Deku Leaf pump for TWW JP."""
from __future__ import annotations

from importlib import reload
from pathlib import Path
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dolphin import controller, event, gui, memory
import leaf_navigator_core

reload(leaf_navigator_core)
from leaf_navigator_core import choose_stick, pump_due


PAD = 0
PLAYER_POINTER = 0x803AD860
CAMERA_POINTER = 0x803AD380
GAME_FRAME = 0x803E9D34
FAN_GLIDE = 0x93
FALL = 0x27


def _pointer(address: int) -> int:
    value = int(memory.read_u32(address))
    if not 0x80000000 <= value < 0x81800000:
        raise ValueError("Link or camera is not loaded")
    return value


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _camera_angle() -> int:
    root = _pointer(CAMERA_POINTER)
    camera = _pointer(root + 0x34)
    return int(memory.read_u16(camera + 0x2B0)) & 0xFFFF


def _state() -> dict:
    if int(memory.read_u32(0x80000000)) != 0x475A4C4A:
        raise ValueError("Only the JP GZLJ memory layout is supported")
    player = _pointer(PLAYER_POINTER)
    return {
        "frame": int(memory.read_u32(GAME_FRAME)),
        "action": int(memory.read_u32(player + 0x3100)),
        "x": float(memory.read_f32(player + 0x120)),
        "z": float(memory.read_f32(player + 0x128)),
        "facing": int(memory.read_u16(player + 0x136)) & 0xFFFF,
        "turn_rate": _signed16(int(memory.read_u16(player + 0x33FC))),
        "normal_speed": float(memory.read_f32(player + 0x34E4)),
        "countdown": int(memory.read_u32(player + 0x349C)),
        "cancel_lockout": int(memory.read_u16(player + 0x33FA)),
        "camera": _camera_angle(),
    }


_window = gui.window("Leaf Navigator")
_enabled_control = _window.checkbox("Enabled", checked=False)
_x_control = _window.input_text("Destination X", "0")
_z_control = _window.input_text("Destination Z", "0")
_radius_control = _window.input_text("Arrival radius", "5")
_budget_control = _window.input_text("Minimum glide speed", "9.0")
_pump_control = _window.checkbox("Leaf pump", checked=False)
_leaf_button_control = _window.input_text("Leaf item button (X, Y, or Z)", "X")
_status = _window.text("Disabled")

_last_frame = None
_phase = "steer"
_held = (128, 128, False, False, False, False)
_owns_input = False
_message = "Waiting for leaf glide"
_last_enabled = False
_recovery_frames = 0


def _input(stick_x=128, stick_y=128, a=False, x=False, y=False, z=False) -> None:
    pad = controller.get_gc_buttons(PAD)
    pad["Connected"] = True
    pad["StickX"], pad["StickY"] = stick_x, stick_y
    pad["A"], pad["X"], pad["Y"], pad["Z"] = a, x, y, z
    controller.set_gc_buttons(PAD, pad)


def _hold(stick_x=128, stick_y=128, a=False, x=False, y=False, z=False) -> None:
    global _held, _owns_input
    _held = (stick_x, stick_y, a, x, y, z)
    _owns_input = True
    _input(*_held)


def _release() -> None:
    global _owns_input
    _owns_input = False


def _stop(message: str) -> None:
    global _message, _phase
    _message = message
    _phase = "stopped"
    _release()


@event.on_hostupdate
def host_update() -> None:
    global _last_enabled, _phase, _last_frame, _message, _recovery_frames
    enabled = bool(_enabled_control.checked)
    if enabled and not _last_enabled:
        _phase = "steer"
        _last_frame = None
        _recovery_frames = 0
        _message = "Waiting for leaf glide"
    elif not enabled and _last_enabled:
        _release()
    _last_enabled = enabled
    _status.set(_message if enabled else "Disabled")


@event.on_savestateload
def state_loaded(from_slot, slot) -> None:
    del from_slot, slot
    global _last_frame, _phase, _recovery_frames
    _last_frame = None
    _phase = "steer"
    _recovery_frames = 0


@event.on_frameadvance
def update() -> None:
    global _last_frame, _phase, _message, _recovery_frames
    if not _enabled_control.checked or _phase == "stopped":
        return
    try:
        state = _state()
        if state["frame"] == _last_frame:
            if _owns_input:
                _input(*_held)
            return
        _last_frame = state["frame"]

        leaf_button = str(_leaf_button_control.value).strip().upper()
        if leaf_button not in ("X", "Y", "Z"):
            _stop("Leaf item button must be X, Y, or Z")
            return
        destination_x = float(_x_control.value)
        destination_z = float(_z_control.value)
        radius = max(0.0, float(_radius_control.value))
        minimum_speed = max(0.0, min(12.0, float(_budget_control.value)))
        if not all(map(math.isfinite, (destination_x, destination_z, radius, minimum_speed))):
            raise ValueError("destination and minimum speed must be finite")

        if _phase == "cancel":
            if state["action"] not in (FAN_GLIDE, FALL):
                _stop("Leaf pump left glide through action %d" % state["action"])
                return
            # The A edge is not visible in Link's action until the following
            # update. Queue the item edge now, immediately after A's input row.
            _hold(_held[0], _held[1], x=leaf_button == "X",
                  y=leaf_button == "Y", z=leaf_button == "Z")
            _phase = "reequip"
            _recovery_frames = 0
            _message = "Leaf pump: %s queued after A" % leaf_button
            return
        if _phase == "reequip":
            if state["action"] == FAN_GLIDE and state["countdown"] <= 2:
                _stop("Leaf pump A was not accepted (countdown %d)" %
                      state["countdown"])
                return
            if state["action"] not in (FAN_GLIDE, FALL):
                _stop("Leaf pump entered action %d during re-equip" %
                      state["action"])
                return
            _hold(_held[0], _held[1])
            _phase = "recover"
            return
        if _phase == "recover":
            if state["action"] != FAN_GLIDE:
                _recovery_frames += 1
                if _recovery_frames > 20:
                    _stop("Leaf did not return to glide within 20 frames; stopped")
                else:
                    _hold(_held[0], _held[1])
                    _message = "Leaf pump: waiting for glide (%d/20)" % _recovery_frames
                return
            _phase = "steer"

        if state["action"] != FAN_GLIDE:
            _release()
            _message = "Waiting for leaf glide (action %d, frame %d)" % (
                state["action"], state["frame"],
            )
            return

        dx = destination_x - state["x"]
        dz = destination_z - state["z"]
        distance = math.hypot(dx, dz)
        if distance <= radius:
            _release()
            _message = "Destination reached (%.3f units)" % distance
            return

        sx, sy, target, predicted, _ = choose_stick(
            state["x"], state["z"], destination_x, destination_z,
            state["facing"], state["camera"], state["turn_rate"],
            state["normal_speed"], minimum_speed,
        )
        if pump_due(state["countdown"], state["cancel_lockout"],
                    bool(_pump_control.checked)):
            _hold(sx, sy, a=True)
            _phase = "cancel"
            _message = "Leaf pump: cancel queued at magic countdown 3"
            return
        _hold(sx, sy)
        _message = ("Distance %.3f | speed %.3f -> %.3f | facing %d -> stick %d | "
                    "magic in %d") % (
            distance, state["normal_speed"], predicted, state["facing"],
            target, state["countdown"],
        )
    except Exception as exc:
        _stop("Stopped: %s" % exc)
