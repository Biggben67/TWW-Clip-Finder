"""Live route finder using tww_engine's persistent C++ replay worker."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from harness.gui_common import load_gui_settings
from portable_bootstrap import load_selected_iso
from harness.rollstab.native_route_playback import capture_native_route
from harness.rollstab.native_route import search_native_trace
from harness.rollstab.route_constraints import FacingRanges
from harness.rollstab.smart_route_gui import ROOT, SETTING_KEYS, SmartRouteGUI

OUTPUT = ROOT / "_generated" / "native_slash_route"


class NativeRouteGUI(SmartRouteGUI):
    settings_path = OUTPUT / "settings.json"
    setting_keys = (*SETTING_KEYS, "engine_exe", "iso", "workers", "mode",
                    "facing_ranges", "widen_facing", "prioritize_full_speed")
    facing_label = "Slash facing ranges"

    def __init__(self):
        super().__init__()
        self.title("TWW C++ Slash Route Finder")
        self.geometry("1220x860")

    def _build(self):
        super()._build()
        for widget in self.evaluation_cap.master.grid_slaves(row=2, column=0):
            if isinstance(widget, ttk.Label):
                widget.configure(text="Eval cap / range")
        for widget in self.grid_slaves():
            row = int(widget.grid_info()["row"])
            if row >= 3:
                widget.grid_configure(row=row + 1)
        self.rowconfigure(4, weight=0)
        self.rowconfigure(5, weight=1)
        panel = ttk.LabelFrame(self, text="Native engine")
        panel.grid(row=3, column=0, sticky="ew", padx=12, pady=6)
        panel.columnconfigure(1, weight=1)
        bundled_worker = Path("TWW Engine") / "finder" / "bin" / "tww_slash_worker.exe"
        default = (bundled_worker if (ROOT / bundled_worker).is_file() else
                   ROOT.parent / "TWW Engine" / "finder" / "bin" / "tww_slash_worker.exe")
        self.engine_exe = self._field(panel, "C++ worker", 0, 0, str(default))
        ttk.Button(panel, text="Browse...", command=lambda: self._browse(self.engine_exe, "*.exe")).grid(row=0, column=2, padx=8)
        self.iso = self._field(panel, "JP ISO", 1, 0)
        ttk.Button(panel, text="Browse...", command=lambda: self._browse(self.iso, "*.iso *.gcm")).grid(row=1, column=2, padx=8)
        self.workers = self._field(panel, "CPU workers", 2, 0, "0")
        self.mode = tk.StringVar(value="Both")
        ttk.Combobox(panel, values=("Both", "Walking", "Rolling"), textvariable=self.mode,
                     state="readonly", width=15).grid(row=2, column=2, padx=8)
        self.facing_ranges = self._field(panel, self.facing_label, 3, 0, "0-65535")
        self.widen_facing = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text="Widen after no hit", variable=self.widen_facing).grid(
            row=3, column=2, padx=8)
        self.prioritize_full_speed = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text="Prioritize full speed", variable=self.prioritize_full_speed).grid(
            row=4, column=1, sticky="w", padx=8, pady=(2, 6))

    def _browse(self, widget, pattern):
        path = filedialog.askopenfilename(parent=self, filetypes=(("Files", pattern), ("All", "*.*")))
        if path:
            self._replace(widget, path)

    def _settings(self):
        result = super()._settings()
        result.update(engine_exe=self.engine_exe.get(), iso=self.iso.get(),
                      workers=self.workers.get(), mode=self.mode.get(),
                      facing_ranges=self.facing_ranges.get(),
                      widen_facing="1" if self.widen_facing.get() else "0",
                      prioritize_full_speed="1" if self.prioritize_full_speed.get() else "0")
        return result

    def _load_settings(self):
        super()._load_settings()
        data = load_gui_settings(str(self.settings_path), self.setting_keys)
        for key in ("engine_exe", "iso", "workers", "facing_ranges"):
            if key in data:
                self._replace(getattr(self, key), data[key])
        if not data.get("iso"):
            self._replace(self.iso, load_selected_iso())
        if data.get("mode") in ("Both", "Walking", "Rolling"):
            self.mode.set(data["mode"])
        self.widen_facing.set(data.get("widen_facing", "1").lower() in ("1", "true", "yes", "on"))
        self.prioritize_full_speed.set(data.get("prioritize_full_speed", "0").lower()
                                       in ("1", "true", "yes", "on"))

    def _inputs(self):
        result = super()._inputs()
        executable = Path(self.engine_exe.get().strip())
        if not executable.is_absolute():
            executable = ROOT / executable
        iso = Path(self.iso.get().strip())
        if not executable.is_file() or not iso.is_file():
            raise ValueError("select the built C++ worker and a JP game ISO")
        workers = int(self.workers.get())
        if not 0 <= workers <= 16:
            raise ValueError("CPU workers must be 0 (automatic) through 16")
        result.update(executable=executable, iso=iso, workers=workers, mode=self.mode.get(),
                      facing_ranges=FacingRanges.parse(self.facing_ranges.get()),
                      widen_facing=self.widen_facing.get(),
                      prioritize_full_speed=self.prioritize_full_speed.get())
        return result

    def _capture_route(self, options, pid, route, emit):
        return capture_native_route(pid, options["target"], route, OUTPUT / "capture", log=emit,
                                    cancelled=self.cancelled.is_set)

    def _load_capture_base(self, control, route, emit):
        # Native capture saves the current state before attaching the complete route movie.
        pass

    def _prepare_capture(self, control, emit):
        # Pipe requests run on the capture thread, never block Tk's event loop.
        status = control.command("status")
        if not status.get("playing"):
            raise RuntimeError("Pause the original movie in read-only playback before capture. "
                               "This Dolphin build cannot attach a stopped movie without restarting.")

    def _solve_trace(self, options, trace, emit):
        return search_native_trace(
            trace, OUTPUT / "result", executable=options["executable"], iso=options["iso"],
            workers=options["workers"], mode=options["mode"], evaluation_cap=options["cap"],
            random_seed=options["seed"], log=emit, cancelled=self.cancelled.is_set,
            allow_mode_fallback=False, facing_ranges=options.get("facing_ranges", "0-65535"),
            widen_facing=options.get("widen_facing", True),
            prioritize_full_speed=options.get("prioritize_full_speed", False),
        )

    def _finish(self, result):
        super()._finish(result)
        self._log_facing_result(result)
        if result.get("exact"):
            self.tree.item(self.tree.get_children()[0], values=(
                "Simulated", result.get("phase"), result.get("dispatch_row"), result.get("facing"),
                "%0.9f, %0.9f" % tuple(result["old"]), "%0.9f, %0.9f" % tuple(result["new"]),
                "%0.9f" % result.get("ray_error", 0),
            ))
            self._append_log("Native simulation candidate exported; verify DTM playback in Dolphin.\n")
            self.status.configure(text="Simulation candidate exported")

    def _log_facing_result(self, result):
        if result.get("facing_range_widened"):
            self._append_log("Search range after widening: %s (requested %s).\n"
                             % (result["applied_facing_ranges"], result["requested_facing_ranges"]))


def main():
    NativeRouteGUI().mainloop()


if __name__ == "__main__":
    main()

