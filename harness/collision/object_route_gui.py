"""Separate GUI for recorded-route moving bomb/pot B-drop refinement."""
import math
import tkinter as tk
from tkinter import ttk

from harness.gui_common import load_gui_settings
from harness.rollstab.native_route_gui import NativeRouteGUI
from harness.rollstab.smart_route_gui import ROOT, SmartRouteGUI
from harness.collision.object_route_capture import capture_object_route, verify_object_candidate
from harness.collision.object_route import search_object_trace

OUTPUT = ROOT / "_generated" / "moving_object_route"


class MovingObjectGUI(NativeRouteGUI):
    settings_path = OUTPUT / "settings.json"
    setting_keys = (*tuple(key for key in NativeRouteGUI.setting_keys if key != "mode"),
                    "require_oob", "oob_tolerance", "oob_min_speed",
                    "roll_on_clip", "roll_facing_ranges")
    facing_label = "Pre-push facing ranges"

    def __init__(self):
        super().__init__()
        self.title("TWW Moving Object Drop Finder")

    def _build(self):
        super()._build()
        self.tree.heading("dispatch", text="Push row")
        panel = next(widget for widget in self.grid_slaves(row=3) if isinstance(widget, ttk.LabelFrame))
        for widget in panel.grid_slaves(row=2, column=2):
            widget.destroy()
        ttk.Label(panel, text="Bomb / small pot: automatic").grid(row=2, column=2, padx=8)
        landing = ttk.Frame(panel)
        landing.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        self.require_oob = tk.BooleanVar(value=False)
        ttk.Checkbutton(landing, text="Land on OoB seam",
                        variable=self.require_oob).grid(row=0, column=0, padx=8)
        self.oob_tolerance = self._field(landing, "Seam tolerance (units)", 0, 1, "1")
        self.oob_tolerance.configure(width=8)
        self.oob_min_speed = self._field(landing, "Min speed (roll / OoB)", 0, 3, "14.5")
        self.oob_min_speed.configure(width=8)
        roll = ttk.Frame(panel)
        roll.grid(row=5, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        self.roll_on_clip = tk.BooleanVar(value=False)
        ttk.Checkbutton(roll, text="Roll through clip", variable=self.roll_on_clip).grid(
            row=0, column=0, padx=8)
        self.roll_facing_ranges = self._field(roll, "Roll facing on push frame", 0, 1, "37000-43000")
        self.roll_facing_ranges.configure(width=20)

    def _settings(self):
        result = super()._settings()
        result.update(require_oob="1" if self.require_oob.get() else "0",
                      oob_tolerance=self.oob_tolerance.get(), oob_min_speed=self.oob_min_speed.get(),
                      roll_on_clip="1" if self.roll_on_clip.get() else "0",
                      roll_facing_ranges=self.roll_facing_ranges.get())
        return result

    def _load_settings(self):
        super()._load_settings()
        data = load_gui_settings(str(self.settings_path), self.setting_keys)
        self.require_oob.set(data.get("require_oob", "0").lower() in ("1", "true", "yes", "on"))
        if "oob_tolerance" in data:
            self._replace(self.oob_tolerance, data["oob_tolerance"])
        if "oob_min_speed" in data:
            self._replace(self.oob_min_speed, data["oob_min_speed"])
        self.roll_on_clip.set(data.get("roll_on_clip", "0").lower() in ("1", "true", "yes", "on"))
        if "roll_facing_ranges" in data:
            self._replace(self.roll_facing_ranges, data["roll_facing_ranges"])

    def _inputs(self):
        result = super()._inputs()
        tolerance = float(self.oob_tolerance.get())
        if not math.isfinite(tolerance) or not 0 < tolerance <= 1:
            raise ValueError("OoB seam tolerance must be greater than 0 and at most 1 unit")
        speed = float(self.oob_min_speed.get())
        if not math.isfinite(speed) or not 0 <= speed <= 17:
            raise ValueError("minimum clip speed must be between 0 and 17")
        from harness.rollstab.route_constraints import FacingRanges
        roll_ranges = FacingRanges.parse(self.roll_facing_ranges.get().strip())
        result.update(require_oob=self.require_oob.get(), oob_tolerance=tolerance, oob_min_speed=speed,
                      roll_on_clip=self.roll_on_clip.get(), roll_facing_ranges=roll_ranges)
        return result

    def _capture_route(self, options, pid, route, emit):
        self.capture_pid = pid
        return capture_object_route(pid, options["target"], route, OUTPUT / "capture", log=emit,
                                    cancelled=self.cancelled.is_set)

    def _solve_trace(self, options, trace, emit):
        if trace["object"]["object_type"] == "storage_walk":
            from harness.collision.storage_walk import search_storage_trace
            return search_storage_trace(
                trace, OUTPUT / "result", executable=options["executable"], iso=options["iso"],
                workers=options["workers"], evaluation_cap=options["cap"],
                random_seed=options["seed"], log=emit, cancelled=self.cancelled.is_set,
                facing_ranges=options["facing_ranges"], require_oob=options["require_oob"],
                oob_tolerance=options["oob_tolerance"], oob_min_speed=options["oob_min_speed"],
                roll_on_clip=options["roll_on_clip"],
                roll_facing_ranges=options["roll_facing_ranges"])
        return search_object_trace(trace, OUTPUT / "result", executable=options["executable"],
                                   iso=options["iso"], workers=options["workers"],
                                   evaluation_cap=options["cap"], random_seed=options["seed"],
                                   log=emit, cancelled=self.cancelled.is_set,
                                   facing_ranges=options["facing_ranges"], widen_facing=options["widen_facing"],
                                   require_oob=options["require_oob"], oob_tolerance=options["oob_tolerance"],
                                   oob_min_speed=options["oob_min_speed"],
                                   roll_on_clip=options["roll_on_clip"],
                                   roll_facing_ranges=options["roll_facing_ranges"],
                                   verify_candidate=lambda family, result: verify_object_candidate(
                                       family, result, self.capture_pid, OUTPUT / "verification", emit))

    def _finish(self, result):
        SmartRouteGUI._finish(self, result)
        if result.get("object_type") == "storage_walk":
            self.tree.heading("dispatch", text="Cross row")
            self.tree.heading("facing", text="Cross facing")
            self.tree.item(self.tree.get_children()[0], values=(
                "Simulated" if result.get("exact") else "Near route", result.get("phase"),
                result.get("dispatch_row"), result.get("facing"),
                "%0.9f, %0.9f" % tuple(result["old"]),
                "%0.9f, %0.9f" % tuple(result["new"]),
                "%0.9f" % result.get("ray_error", 0)))
            if result.get("exact"):
                self._append_log("Storage walk inputs: %s\n" % result["input_file"])
                self._append_log("Native crossing reproduced; verify DTM playback in Dolphin.\n")
                self.status.configure(text="Storage walk candidate exported")
            return
        self._log_facing_result(result)
        self.tree.heading("facing", text="Roll facing" if result.get("roll_on_clip") else "Pre-push facing")
        self.tree.item(self.tree.get_children()[0], values=(
            "Live verified" if result.get("live_verified") else "Near route", result.get("phase"),
            result.get("dispatch_row"),
            result.get("roll_facing") if result.get("roll_on_clip") else result.get("facing"),
            "%0.9f, %0.9f" % tuple(result["old"]), "%0.9f, %0.9f" % tuple(result["new"]),
            "%0.9f" % result.get("ray_error", 0)))
        if result.get("exact"):
            if result.get("roll_on_clip"):
                self._append_log("Front roll on push frame: facing %d, A input row %d.\n"
                                 % (result["roll_facing"], result["roll_input_row"]))
            if result.get("require_oob"):
                self._append_log("OoB seam landing: %.6f units from seam, speed %.6f.\n"
                                 % (result["landing_distance"], result["landing_speed"]))
            self._append_log("Inputs: %s\n" % result["input_file"])
            self._append_log("Live-verified push; retained past the seam for %d subsequent frame(s).\n"
                             % result.get("retention_frames", 0))
            self.status.configure(text="Live-verified moving drop exported")


def main():
    MovingObjectGUI().mainloop()


if __name__ == "__main__":
    main()
