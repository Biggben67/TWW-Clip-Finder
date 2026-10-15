"""Tk GUI for the live Dolphin slash-clip planner."""
from __future__ import annotations

import contextlib
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from harness.gui_common import (
    load_gui_settings,
    parse_seam_coordinates,
    save_gui_settings,
)
from harness.rollstab import live_slash


SETTINGS_PATH = os.path.join(live_slash._GEN, "live_slash_gui_settings.json")
SETTING_KEYS = (
    "seam_x", "seam_y", "seam_z", "mode", "angle_lo", "angle_hi",
    "budget", "max_results", "iso", "game_id",
)


def load_settings(path=SETTINGS_PATH) -> dict:
    return load_gui_settings(path, SETTING_KEYS)


def save_settings(data: dict, path=SETTINGS_PATH) -> None:
    save_gui_settings(data, path, SETTING_KEYS)


class QueueWriter:
    def __init__(self, put):
        self.put = put
        self.pending = ""

    def write(self, text):
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line:
                self.put(("log", line))
        return len(text)

    def flush(self):
        if self.pending:
            self.put(("log", self.pending))
            self.pending = ""


class SlashClipGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TWW Prepared Slash Clip Finder")
        self.minsize(980, 680)
        self.geometry("1120x760")
        self.events = queue.Queue()
        self.result = None
        self.hits = []
        self._build()
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._poll)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=1)

        live = ttk.LabelFrame(self, text="Live Dolphin")
        live.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        live.columnconfigure(3, weight=1)
        ttk.Label(live, text="PID").grid(row=0, column=0, padx=(10, 5), pady=9)
        self.pid = ttk.Entry(live, width=10)
        self.pid.grid(row=0, column=1, padx=(0, 8), pady=9)
        ttk.Button(live, text="Refresh", command=self.refresh).grid(row=0, column=2, padx=4, pady=9)
        self.live_text = ttk.Label(live, text="Not connected", anchor="w")
        self.live_text.grid(row=0, column=3, sticky="ew", padx=10, pady=9)

        target = ttk.LabelFrame(self, text="Target and search")
        target.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        for col in (1, 3, 5, 7):
            target.columnconfigure(col, weight=1)
        self.x = self._field(target, "Seam X", 0, 0)
        self.y = self._field(target, "Seam Y", 0, 2)
        self.z = self._field(target, "Seam Z", 0, 4)
        for field in (self.x, self.y, self.z):
            field.bind("<<Paste>>", self._paste_seam)
        ttk.Label(target, text="Mode").grid(row=0, column=6, padx=(10, 5), pady=8)
        self.mode = ttk.Combobox(
            target,
            values=("Rolling slash", "Walking slash", "Walking Setup"),
            state="readonly",
        )
        self.mode.current(0)
        self.mode.grid(row=0, column=7, sticky="ew", padx=(0, 10), pady=8)

        self.angle_lo = self._field(target, "Angle start", 1, 0, "0")
        self.angle_hi = self._field(target, "Angle end", 1, 2, "65535")
        self.budget = self._field(target, "Budget/family (s)", 1, 4, "120")
        self.max_results = self._field(target, "Max results", 1, 6, "4")
        ttk.Label(target, text="JP ISO").grid(row=2, column=0, padx=(10, 5), pady=8)
        self.iso = ttk.Entry(target)
        self.iso.grid(row=2, column=1, columnspan=6, sticky="ew", padx=(0, 8), pady=8)
        ttk.Button(target, text="Browse...", command=self._browse_iso).grid(
            row=2, column=7, sticky="ew", padx=(0, 10), pady=8
        )
        self.game_id = self._field(target, "DTM game ID", 3, 0, "GZLJ01")
        ttk.Label(target, text="Written to the exported movie header").grid(
            row=3, column=2, columnspan=6, sticky="w", padx=(10, 5), pady=8
        )

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        actions.columnconfigure(1, weight=1)
        self.scan_button = ttk.Button(actions, text="Prepare and scan", command=self.scan)
        self.scan_button.grid(row=0, column=0, padx=(0, 10))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew")
        self.status_text = ttk.Label(actions, text="Ready", width=24, anchor="e")
        self.status_text.grid(row=0, column=2, padx=(10, 0))

        results = ttk.LabelFrame(self, text="Simulation candidates")
        results.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        cols = ("mode", "facing", "start_x", "start_z", "old_x", "old_z", "new_x", "new_z", "depth", "margin")
        self.tree = ttk.Treeview(results, columns=cols, show="headings", height=8)
        labels = ("Mode", "Facing", "Start X", "Start Z", "Old X", "Old Z", "New X", "New Z", "OOB depth", "Margin")
        widths = (85, 75, 125, 125, 125, 125, 125, 125, 75, 65)
        for key, label, width in zip(cols, labels, widths):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._select)

        detail_frame = ttk.LabelFrame(self, text="Exact input timeline")
        detail_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(6, 12))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.detail = tk.Text(detail_frame, wrap="none", height=12, font=("Consolas", 9))
        self.detail.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail.yview)
        detail_scroll.grid(row=0, column=1, sticky="ns", pady=8)
        self.detail.configure(yscrollcommand=detail_scroll.set, state="disabled")
        ttk.Button(detail_frame, text="Copy setup", command=self.copy_setup).grid(
            row=0, column=2, sticky="n", padx=8, pady=8
        )

    def _field(self, parent, label, row, column, initial=""):
        ttk.Label(parent, text=label).grid(row=row, column=column, padx=(10, 5), pady=8)
        field = ttk.Entry(parent)
        field.grid(row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=8)
        if initial:
            field.insert(0, initial)
        return field

    @staticmethod
    def _replace_entry(field, value):
        field.delete(0, "end")
        field.insert(0, str(value))

    def _paste_seam(self, _event=None):
        try:
            coordinates = parse_seam_coordinates(self.clipboard_get())
        except tk.TclError:
            return None
        if coordinates is None:
            return None
        for field, value in zip((self.x, self.y, self.z), coordinates):
            self._replace_entry(field, value)
        self.status_text.configure(text="Seam coordinates pasted")
        return "break"

    def _settings(self):
        return {
            "seam_x": self.x.get(),
            "seam_y": self.y.get(),
            "seam_z": self.z.get(),
            "mode": self.mode.get(),
            "angle_lo": self.angle_lo.get(),
            "angle_hi": self.angle_hi.get(),
            "budget": self.budget.get(),
            "max_results": self.max_results.get(),
            "iso": self.iso.get(),
            "game_id": self.game_id.get(),
        }

    def _load_settings(self):
        settings = load_settings()
        entries = {
            "seam_x": self.x,
            "seam_y": self.y,
            "seam_z": self.z,
            "angle_lo": self.angle_lo,
            "angle_hi": self.angle_hi,
            "budget": self.budget,
            "max_results": self.max_results,
            "iso": self.iso,
            "game_id": self.game_id,
        }
        for key, field in entries.items():
            if key in settings:
                self._replace_entry(field, settings[key])
        if settings.get("mode") in self.mode.cget("values"):
            self.mode.set(settings["mode"])

    def _save_settings(self):
        save_settings(self._settings())

    def _close(self):
        try:
            self._save_settings()
        finally:
            self.destroy()

    def _browse_iso(self):
        path = filedialog.askopenfilename(
            parent=self, title="Select JP Wind Waker ISO",
            filetypes=(("GameCube disc images", "*.iso *.gcm"), ("All files", "*.*")),
        )
        if path:
            self.iso.delete(0, "end")
            self.iso.insert(0, path)

    def _pid_value(self):
        value = self.pid.get().strip()
        return int(value, 0) if value else None

    def refresh(self):
        try:
            state = live_slash.status(self._pid_value())
            self.live_text.configure(
                text=(f"{state.stage} room {state.room} | "
                      f"pos ({state.x:.6f}, {state.y:.6f}, {state.z:.6f}) | "
                      f"speed {state.speedF:.3f} | facing {state.facing} | camera {state.csangle} | "
                      f"state {state.state} | life {state.life} | rest rate {state.rest_d_rate:.3f} | "
                      f"{'sword drawn' if state.sword_drawn else 'sword sheathed'}")
            )
            if not self.pid.get().strip():
                self.pid.insert(0, str(state.pid))
        except Exception as exc:
            messagebox.showerror("Dolphin connection failed", str(exc), parent=self)

    def scan(self):
        try:
            target = tuple(float(field.get().strip()) for field in (self.x, self.y, self.z))
            budget = float(self.budget.get().strip())
            want = int(self.max_results.get().strip())
            if budget <= 0 or want <= 0:
                raise ValueError("budget and max results must be positive")
            live_slash.parse_angle_range(self.angle_lo.get().strip(), self.angle_hi.get().strip())
            game_id = live_slash.parse_game_id(self.game_id.get().strip())
            pid = self._pid_value()
            self._save_settings()
        except Exception as exc:
            messagebox.showerror("Invalid search", str(exc), parent=self)
            return

        self.result = None
        self.hits = []
        self.tree.delete(*self.tree.get_children())
        self._set_detail("")
        self.scan_button.configure(state="disabled")
        self.progress.start(10)
        self.status_text.configure(text="Searching")

        def work():
            writer = QueueWriter(self.events.put)
            try:
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    result = live_slash.search_live(
                        target=target,
                        mode=self.mode.get(),
                        angle_lo=self.angle_lo.get().strip(),
                        angle_hi=self.angle_hi.get().strip(),
                        budget=budget,
                        want=want,
                        pid=pid,
                        iso_path=self.iso.get().strip(),
                        game_id=game_id,
                        log=lambda line: self.events.put(("log", line)),
                    )
                writer.flush()
                self.events.put(("done", result))
            except Exception as exc:
                writer.flush()
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self.status_text.configure(text=str(payload)[-32:])
                    self._append_detail(str(payload) + "\n")
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
        self.hits = result.get("hits", [])
        for i, hit in enumerate(self.hits):
            old, new = hit.get("old", (0, 0)), hit.get("new", (0, 0))
            setup = hit.get("setup", {})
            self.tree.insert("", "end", iid=str(i), values=(
                hit.get("mode", ""), hit.get("facing", ""),
                f"{setup.get('x', 0):.7f}", f"{setup.get('z', 0):.7f}",
                f"{old[0]:.7f}", f"{old[1]:.7f}", f"{new[0]:.7f}", f"{new[1]:.7f}",
                (f"{hit['post_seam_depth']:.3f}"
                 if hit.get("post_seam_depth") is not None else ""),
                hit.get("margin", ""),
            ))
        if self.hits:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._show_hit(0)
            self.status_text.configure(text=f"{len(self.hits)} setup(s) found")
        else:
            self.status_text.configure(text="No setup found")
            self._append_detail("\nNo exact wall-faithful setup was found in this budget/range.\n")

    def _stop_busy(self):
        self.progress.stop()
        self.scan_button.configure(state="normal")
        if self.status_text.cget("text") == "Searching":
            self.status_text.configure(text="Ready")

    def _select(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self._show_hit(int(selected[0]))

    def _show_hit(self, index):
        hit = self.hits[index]
        old, new = hit["old"], hit["new"]
        setup = hit.get("setup", {})
        b_frame = hit.get("b_frame")
        transition_frame = hit.get("transition_frame")
        timing = ""
        if b_frame is not None:
            normalization = ""
            if hit.get("turn_down_frame") is not None:
                normalization = (
                    f"C-down exit; down-turn frame: {hit['turn_down_frame']}; "
                    f"settled frame: {hit['turn_settle_frame']}; "
                    f"up begins: {hit['walk_start_frame']}\n"
                )
            timing = (
                normalization
                + f"B input frame: {b_frame} (Link is still in MOVE; do not validate Old here)\n"
                f"CUT_F transition frame: {transition_frame} "
                "(state 66; validate Old immediately before the lunge)\n"
            )
        else:
            timing = f"Predicted transition frame: {transition_frame}\n"
        verification = (
            "Verification: Dolphin exact control-pipe CUT_F transition.\n\n"
            if hit.get("verification") == "dolphin_exact"
            else "This is a simulation candidate. Load/play the exported DTM to verify it in Dolphin.\n\n"
        )
        next_frame = hit.get("next_frame") or {}
        persistence = (
            "Yes" if next_frame.get("next_oob") else
            "No (WallCorrect push-out)" if next_frame else "Not evaluated"
        )
        next_position = next_frame.get("next")
        next_line = (
            f"Next CUT_F frame: ({next_position[0]:.9f}, {next_position[1]:.9f})  "
            f"Remains OOB: {persistence}\n"
            if next_position else f"Remains OOB next frame: {persistence}\n"
        )
        header = (
            f"Mode: {hit['mode']}\nSlash facing: {hit.get('facing')}\n"
            f"Prepared start: ({setup.get('x', 0):.9f}, {setup.get('y', 0):.9f}, "
            f"{setup.get('z', 0):.9f})\n"
            f"Start facing: {setup.get('facing')}  Camera: {setup.get('camera')}\n"
            f"Old: ({old[0]:.9f}, {old[1]:.9f})\n"
            f"New: ({new[0]:.9f}, {new[1]:.9f})\n"
            + (
                f"Normal speed: {hit.get('normal_speed', 0):.6f}  "
                f"Slope-adjusted speedF: {hit.get('speedF', 0):.6f}\n"
                if hit.get("normal_speed") is not None else ""
            )
            +
            f"Post-seam depth: {hit.get('post_seam_depth', 0):.6f}\n"
            f"{next_line}"
            f"{timing}"
            f"DTM game ID: {hit.get('dtm_game_id')}\n"
            f"Complete DTM: {hit.get('dtm_path')}\n"
            f"Start state: {hit.get('start_savestate', setup.get('savestate'))}\n"
            f"{verification}"
        )
        self._set_detail(header + hit["input_summary"])

    def _set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _append_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.insert("end", text)
        self.detail.see("end")
        self.detail.configure(state="disabled")

    def copy_setup(self):
        selected = self.tree.selection()
        if not selected:
            return
        hit = self.hits[int(selected[0])]
        setup = hit.get("setup", {})
        text = (
            f"TWW {hit['mode']} slash clip\n"
            f"prepared=({setup.get('x')}, {setup.get('y')}, {setup.get('z')}) "
            f"start_facing={setup.get('facing')} camera={setup.get('camera')}\n"
            f"slash_facing={hit.get('facing')} old={hit['old']} new={hit['new']}\n"
            f"dtm={hit.get('dtm_path')} game_id={hit.get('dtm_game_id')}\n"
            f"start_state={hit.get('start_savestate', setup.get('savestate'))}\n"
            f"b_input_frame={hit.get('b_frame')} "
            f"cut_f_transition_frame={hit.get('transition_frame')}\n"
            "Validate old only when Link enters CUT_F (state 66), not on the B input row.\n"
            f"{hit['input_summary']}"
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_text.configure(text="Setup copied")


def main():
    SlashClipGUI().mainloop()


if __name__ == "__main__":
    main()
