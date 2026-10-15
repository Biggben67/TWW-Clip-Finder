"""Tk front end for live route capture and smart slash-clip refinement."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from harness.gui_common import load_gui_settings, parse_seam_coordinates, save_gui_settings
from harness.rollstab import live_slash
from harness.rollstab.barrier_slash import capture_manual_route, discover_recorded_route
from harness.collision.live_moving_drop import _load_state_settled
from harness.dolphin_control import DolphinControl
from harness.rollstab.recorded_route import _active_controllers, extract_route
from harness.rollstab.smart_route_search import search_trace


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "_generated" / "smart_slash_route"
SETTINGS_PATH = OUTPUT_DIR / "settings.json"
SETTING_KEYS = (
    "pid", "seam_x", "seam_y", "seam_z", "state_dir", "game_id", "base_slot",
    "final_slot", "controller", "evaluation_cap", "random_seed", "auto_route",
)


def _slot_name(game_id: str, slot: int) -> str:
    return f"{game_id}.s{int(slot):02d}"


def validated_game_id(value: str) -> str:
    """Return the validated ID as filename text, not DTM-header bytes."""
    return live_slash.parse_game_id(value).decode("ascii")


def _gameplay_score(route) -> int:
    return sum(
        1 for row in route.rows
        if ((int(row.get("stickX", 0)), int(row.get("stickY", 0))) != (0, 0)
            or (int(row.get("substickX", 0)), int(row.get("substickY", 0))) != (0, 0)
            or int(row.get("buttons", 0))
            or int(row.get("triggerL", 0)) or int(row.get("triggerR", 0)))
    )


def route_from_slots(state_dir, game_id, base_slot, final_slot, controller):
    state_dir = Path(state_dir)
    start = state_dir / _slot_name(game_id, base_slot)
    end = state_dir / _slot_name(game_id, final_slot)
    movie = Path(str(end) + ".dtm")
    missing = [str(path) for path in (start, end, movie) if not path.is_file()]
    if missing:
        raise RuntimeError("missing route file(s): " + ", ".join(missing))
    active = _active_controllers(movie.read_bytes()[:256])
    routes = {index: extract_route(movie, start, end, controller=index) for index in active}
    ranked = sorted(routes.values(), key=_gameplay_score, reverse=True)
    requested = routes.get(controller) if controller is not None else None
    if requested is None or (_gameplay_score(requested) == 0 and _gameplay_score(ranked[0]) > 0):
        return ranked[0]
    return requested


class SmartRouteGUI(tk.Tk):
    settings_path = SETTINGS_PATH
    setting_keys = SETTING_KEYS
    def __init__(self):
        super().__init__()
        self.title("TWW Smart Slash Route Finder")
        self.geometry("1120x760")
        self.minsize(920, 650)
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.result = None
        self._build()
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._poll)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        live = ttk.LabelFrame(self, text="Live Dolphin")
        live.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        live.columnconfigure(3, weight=1)
        ttk.Label(live, text="PID").grid(row=0, column=0, padx=(10, 5), pady=9)
        self.pid = ttk.Entry(live, width=10)
        self.pid.grid(row=0, column=1, padx=(0, 8), pady=9)
        ttk.Button(live, text="Refresh", command=self.refresh).grid(row=0, column=2, padx=4)
        self.live_text = ttk.Label(live, text="Not connected", anchor="w")
        self.live_text.grid(row=0, column=3, sticky="ew", padx=10, pady=9)

        target = ttk.LabelFrame(self, text="Target seam")
        target.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        for column in (1, 3, 5):
            target.columnconfigure(column, weight=1)
        self.x = self._field(target, "X", 0, 0)
        self.y = self._field(target, "Y", 0, 2)
        self.z = self._field(target, "Z", 0, 4)
        for field in (self.x, self.y, self.z):
            field.bind("<<Paste>>", self._paste_seam)

        route = ttk.LabelFrame(self, text="Recorded route")
        route.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        for column in (1, 3, 5, 7):
            route.columnconfigure(column, weight=1)
        ttk.Label(route, text="State folder").grid(row=0, column=0, padx=(10, 5), pady=8)
        self.state_dir = ttk.Entry(route)
        self.state_dir.grid(row=0, column=1, columnspan=6, sticky="ew", padx=(0, 8), pady=8)
        ttk.Button(route, text="Browse...", command=self._browse_state_dir).grid(
            row=0, column=7, sticky="ew", padx=(0, 10), pady=8
        )
        self.game_id = self._field(route, "Game ID", 1, 0, "GZLJ01")
        self.base_slot = self._field(route, "Base slot", 1, 2, "5")
        self.final_slot = self._field(route, "Final slot", 1, 4, "10")
        self.controller = self._field(route, "GC controller", 1, 6, "Auto")
        self.evaluation_cap = self._field(route, "Evaluation cap", 2, 0, "30000")
        self.random_seed = self._field(route, "Search seed", 2, 2, "615507812")
        self.auto_route = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            route, text="Use newest bracketed recording instead of slots",
            variable=self.auto_route,
        ).grid(row=2, column=4, columnspan=4, sticky="w", padx=(10, 5), pady=8)

        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew", padx=12, pady=6)
        actions.columnconfigure(2, weight=1)
        self.search_button = ttk.Button(actions, text="Capture and search", command=self.search)
        self.search_button.grid(row=0, column=0, padx=(0, 8))
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=2, sticky="ew")
        self.status = ttk.Label(actions, text="Ready", width=30, anchor="e")
        self.status.grid(row=0, column=3, padx=(10, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.grid(row=4, column=0, sticky="nsew", padx=12, pady=(6, 12))
        result_frame = ttk.LabelFrame(body, text="Best route")
        result_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            result_frame,
            columns=("status", "phase", "dispatch", "facing", "old", "new", "ray"),
            show="headings", height=4,
        )
        for key, label, width in (
            ("status", "Status", 90), ("phase", "Search path", 135),
            ("dispatch", "Slash row", 80), ("facing", "Facing", 75),
            ("old", "Old X, Z", 220), ("new", "New X, Z", 220),
            ("ray", "Ray error", 100),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        body.add(result_frame, weight=1)

        log_frame = ttk.LabelFrame(body, text="Capture and search log")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="none", font=("Consolas", 9), height=18)
        self.log.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=8)
        self.log.configure(yscrollcommand=scroll.set, state="disabled")
        ttk.Button(log_frame, text="Copy result", command=self.copy_result).grid(
            row=0, column=2, sticky="n", padx=8, pady=8
        )
        body.add(log_frame, weight=4)

    def _field(self, parent, label, row, column, initial=""):
        ttk.Label(parent, text=label).grid(row=row, column=column, padx=(10, 5), pady=8)
        field = ttk.Entry(parent)
        field.grid(row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=8)
        if initial:
            field.insert(0, initial)
        return field

    @staticmethod
    def _replace(field, value):
        field.delete(0, "end")
        field.insert(0, str(value))

    def _paste_seam(self, _event=None):
        try:
            values = parse_seam_coordinates(self.clipboard_get())
        except tk.TclError:
            return None
        if values is None:
            return None
        for field, value in zip((self.x, self.y, self.z), values):
            self._replace(field, value)
        self.status.configure(text="Seam coordinates pasted")
        return "break"

    def _settings(self):
        return {
            "pid": self.pid.get(),
            "seam_x": self.x.get(), "seam_y": self.y.get(), "seam_z": self.z.get(),
            "state_dir": self.state_dir.get(), "game_id": self.game_id.get(),
            "base_slot": self.base_slot.get(), "final_slot": self.final_slot.get(),
            "controller": self.controller.get(), "evaluation_cap": self.evaluation_cap.get(),
            "random_seed": self.random_seed.get(),
            "auto_route": "1" if self.auto_route.get() else "0",
        }

    def _load_settings(self):
        data = load_gui_settings(str(self.settings_path), self.setting_keys)
        fields = {
            "pid": self.pid,
            "seam_x": self.x, "seam_y": self.y, "seam_z": self.z,
            "state_dir": self.state_dir, "game_id": self.game_id,
            "base_slot": self.base_slot, "final_slot": self.final_slot,
            "controller": self.controller, "evaluation_cap": self.evaluation_cap,
            "random_seed": self.random_seed,
        }
        for key, value in data.items():
            if key in fields:
                self._replace(fields[key], value)
        self.auto_route.set(data.get("auto_route", "0").lower() in ("1", "true", "yes", "on"))

    def _save_settings(self):
        save_gui_settings(self._settings(), str(self.settings_path), self.setting_keys)

    def _close(self):
        self.cancelled.set()
        self._save_settings()
        self.destroy()

    def _browse_state_dir(self):
        path = filedialog.askdirectory(parent=self, title="Select Dolphin StateSaves folder")
        if path:
            self._replace(self.state_dir, path)

    def _pid(self):
        value = self.pid.get().strip()
        return int(value, 0) if value else None

    def refresh(self):
        try:
            state = live_slash.status(self._pid())
            if not self.pid.get().strip():
                self.pid.insert(0, str(state.pid))
            self.live_text.configure(text=(
                f"{state.stage} room {state.room} | pos ({state.x:.6f}, {state.y:.6f}, "
                f"{state.z:.6f}) | speed {state.speedF:.3f} | facing {state.facing} | "
                f"camera {state.csangle} | state {state.state}"
            ))
        except Exception as exc:
            messagebox.showerror("Dolphin connection failed", str(exc), parent=self)

    def _inputs(self):
        target = tuple(float(item.get().strip()) for item in (self.x, self.y, self.z))
        state_dir = Path(self.state_dir.get().strip())
        if not state_dir.is_dir():
            raise ValueError("select a valid Dolphin StateSaves folder")
        game_id = validated_game_id(self.game_id.get().strip())
        controller_text = self.controller.get().strip()
        controller = None if controller_text.lower() in ("", "auto") else int(controller_text) - 1
        if controller is not None and controller not in range(4):
            raise ValueError("GC controller must be Auto or 1 through 4")
        cap = int(self.evaluation_cap.get().strip())
        if cap < 1000:
            raise ValueError("evaluation cap must be at least 1000")
        return {
            "target": target, "state_dir": state_dir, "game_id": game_id,
            "base_slot": int(self.base_slot.get().strip()),
            "final_slot": int(self.final_slot.get().strip()),
            "controller": controller, "cap": cap,
            "seed": int(self.random_seed.get().strip()), "pid": self._pid(),
        }

    def search(self):
        try:
            options = self._inputs()
            options["auto_route"] = bool(self.auto_route.get())
            self._save_settings()
        except Exception as exc:
            messagebox.showerror("Invalid search", str(exc), parent=self)
            return
        self.cancelled.clear()
        self.result = None
        self.tree.delete(*self.tree.get_children())
        self._set_log("")
        self.search_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(10)
        self.status.configure(text="Capturing route")

        def emit(line):
            self.events.put(("log", str(line)))

        def work():
            try:
                state = live_slash.status(options["pid"])
                emit(f"Attached to Dolphin PID {state.pid}: {state.stage} room {state.room}.")
                if options["auto_route"]:
                    route = discover_recorded_route(
                        options["state_dir"], options["game_id"], options["controller"]
                    )
                else:
                    route = route_from_slots(
                        options["state_dir"], options["game_id"],
                        options["base_slot"], options["final_slot"], options["controller"],
                    )
                emit(
                    f"Route: {route.start_state.name} -> VI {route.end_vi}, "
                    f"{len(route.rows)} gameplay rows, controller {route.controller + 1}."
                )
                control = DolphinControl(state.pid)
                self._prepare_capture(control, emit)
                control.pause()
                self._load_capture_base(control, route, emit)
                trace = self._capture_route(options, state.pid, route, emit)
                if self.cancelled.is_set():
                    raise RuntimeError("search cancelled")
                self.events.put(("phase", "Searching simulation"))
                result = self._solve_trace(options, trace, emit)
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _prepare_capture(self, control, emit):
        pass

    def _load_capture_base(self, control, route, emit):
        _load_state_settled(control, route.start_state)
        emit(f"Loaded selected base state {route.start_state.name} at VI {route.start_vi}.")

    def _capture_route(self, options, pid, route, emit):
        return capture_manual_route(pid, options["target"], route, OUTPUT_DIR / "capture", log=emit)

    def _solve_trace(self, options, trace, emit):
        return search_trace(
            trace, OUTPUT_DIR / "result", evaluation_cap=options["cap"],
            random_seed=options["seed"], log=emit, cancelled=self.cancelled.is_set,
        )

    def cancel(self):
        self.cancelled.set()
        self.status.configure(text="Cancelling")

    def _poll(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self._append_log(payload + "\n")
                    self.status.configure(text=payload[-38:])
                elif event == "phase":
                    self.status.configure(text=payload)
                elif event == "done":
                    self._finish(payload)
                elif event == "error":
                    self._stop_busy()
                    messagebox.showerror("Search failed", payload, parent=self)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _finish(self, result):
        self._stop_busy()
        self.result = result
        exact = bool(result.get("exact"))
        old, new = result["old"], result["new"]
        self.tree.insert("", "end", values=(
            "Proved" if exact else "Near miss", result.get("phase"),
            result.get("dispatch_row"), result.get("facing"),
            f"{old[0]:.9f}, {old[1]:.9f}", f"{new[0]:.9f}, {new[1]:.9f}",
            f"{result.get('ray_error', 0):.9f}",
        ))
        self.status.configure(text="Exact clip exported" if exact else "No exact clip found")
        if exact:
            self._append_log(f"\nDTM: {result['movie']}\n")
        else:
            self._append_log("\nNo movie was exported because the best route was not exact.\n")

    def _stop_busy(self):
        self.progress.stop()
        self.search_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _set_log(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("1.0", text)
        self.log.configure(state="disabled")

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def copy_result(self):
        if not self.result:
            return
        self.clipboard_clear()
        self.clipboard_append(json.dumps(self.result, indent=2))
        self.status.configure(text="Result copied")


def main():
    SmartRouteGUI().mainloop()


if __name__ == "__main__":
    main()
