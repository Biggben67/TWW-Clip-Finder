"""Minimal client for the Zelda TAS Edition local Dolphin control pipe."""
from __future__ import annotations

import json
import os
import time


class DolphinControl:
    def __init__(self, pid: int):
        self.pid = int(pid)
        self.path = rf"\\.\pipe\DolphinControl-{self.pid}"

    def command(self, command: str, values: dict | None = None) -> dict:
        request = {"cmd": command}
        if values:
            request.update(values)
        deadline = time.monotonic() + 5.0
        last_error = None
        while True:
            try:
                pipe = open(self.path, "r+b", buffering=0)
                break
            except OSError as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Dolphin's controller pipe is unavailable. In Zelda TAS Edition, enable "
                        "Tools > Enable Control Pipe, then retry."
                    ) from last_error
                time.sleep(0.02)
        with pipe:
            pipe.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
            response = bytearray()
            while not response.endswith(b"\n"):
                chunk = pipe.read(1)
                if not chunk:
                    break
                response.extend(chunk)
        if not response:
            raise RuntimeError(f"Dolphin control pipe returned no response for {command}")
        try:
            result = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(f"invalid Dolphin control response: {response!r}") from exc
        if not result.get("ok", False):
            raise RuntimeError(result.get("error") or f"Dolphin command failed: {command}")
        return result

    def pause(self) -> dict:
        return self.command("pause")

    def advance(self, frames: int = 1) -> dict:
        return self.command("advance", {"frames": int(frames)})

    def advance_with(self, **values) -> dict:
        defaults = dict(
            stickX=128, stickY=128, substickX=128, substickY=0,
            buttons=0, triggerL=0, triggerR=0, frames=1,
        )
        defaults.update(values)
        return self.command("advancewith", defaults)

    def save_state(self, path: str) -> dict:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return self.command("savestate", {"action": "save", "path": path.replace("\\", "/")})

    def load_state(self, path: str) -> dict:
        return self.command("savestate", {"action": "load", "path": path.replace("\\", "/")})