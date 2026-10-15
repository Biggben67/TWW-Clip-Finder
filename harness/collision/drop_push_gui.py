"""Desktop setup finder for bomb and small-pot B-drop seam clips."""
from __future__ import annotations

import queue
import os
import multiprocessing
import struct
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from harness.collision.find_drop_push_candidate import (
    find_candidates,
    prepare_search,
)
from harness.collision.room_collision import (
    load_live_room_collision,
    load_room_collision,
)
from harness.gui_common import (
    load_gui_settings,
    parse_seam_coordinates,
    save_gui_settings,
)
from harness.rollstab import live_slash
from harness.dolphin_control import DolphinControl
from portable_bootstrap import load_selected_iso


SETTINGS_PATH = os.path.join(
    Path(__file__).resolve().parents[2], "_generated", "drop_push_gui_settings.json"
)
SETTING_KEYS = (
    "seam_x", "seam_y", "seam_z", "use_live", "stage", "room",
    "object_type", "frames", "facings", "max_results", "stop_first",
    "oob_landing", "oob_tolerance", "collision_path",
    "teleport_on_result",
)


def load_settings(path=SETTINGS_PATH):
    return load_gui_settings(str(path), SETTING_KEYS)


def save_settings(data, path=SETTINGS_PATH):
    save_gui_settings(data, str(path), SETTING_KEYS)


def _stored_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().casefold() in ("1", "true", "yes", "on")


def parse_frame_spec(spec):
    """Parse displayed animation positions such as ``11`` or ``1-10,51``."""
    values = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_text, hi_text = part.split("-", 1)
            lo, hi = int(lo_text), int(hi_text)
            step = 1 if hi >= lo else -1
            values.extend(range(lo, hi + step, step))
        else:
            values.append(int(part))
    values = list(dict.fromkeys(values))
    if not values or any(frame < 1 or frame > 60 for frame in values):
        raise ValueError("animation positions must be between 1 and 60")
    return values


def parse_facing_spec(spec):
    """Parse inclusive facing-angle ranges."""
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_text, hi_text = part.split("-", 1)
            lo, hi = int(lo_text, 0), int(hi_text, 0)
        else:
            lo = hi = int(part, 0)
        if lo < 0 or hi < 0 or lo > 0xFFFF or hi > 0xFFFF or hi < lo:
            raise ValueError("facing angles must be an ascending range within 0-65535")
        ranges.append((lo, hi, 16))
    if not ranges:
        raise ValueError("at least one facing range is required")
    return ranges


def f32_bits(value):
    return struct.unpack(">I", struct.pack(">f", value))[0]


def _coordinate_box(seam, region=None):
    x, y, z = seam
    ymin, ymax = y - 220.0, y + 220.0
    if region:
        room_ys = [vertex[1] for tri in region for vertex in tri["v"]]
        ymin = min(ymin, min(room_ys))
        ymax = max(ymax, max(room_ys))
    return (x - 160.0, x + 160.0, ymin, ymax, z - 160.0, z + 160.0)


def ensure_drop_animation_data(iso_path, generated_dir=None):
    """Rebuild the copyrighted local animation cache when cleanup removed it."""
    if generated_dir is None:
        generated_dir = Path(__file__).resolve().parents[2] / "_generated" / "anim"
    else:
        generated_dir = Path(generated_dir)
    grab_path = generated_dir / "link_anim_grab.json"
    skeleton_path = generated_dir / "link_skeleton.json"
    missing = [path for path in (grab_path, skeleton_path) if not path.is_file()]
    if not missing:
        return []
    if not iso_path:
        raise FileNotFoundError(
            "Bomb/pot animation data is missing. Select your Wind Waker ISO in "
            "'Game ISO / collision'; it remains available while live room collision is enabled."
        )
    source = Path(iso_path)
    if source.suffix.lower() != ".iso" or not source.is_file():
        raise FileNotFoundError(
            "Bomb/pot animation data is missing and the selected animation source is not "
            "an existing .iso file: %s" % source
        )
    generated_dir.mkdir(parents=True, exist_ok=True)
    written = []
    if not grab_path.is_file():
        from harness.anim.parse_bck import extract_animation_sets
        written.extend(extract_animation_sets(
            str(source), which="link_anim_grab", outdir=str(generated_dir)
        ))
    if not skeleton_path.is_file():
        from harness.anim.parse_bmd import extract_skeleton
        written.append(extract_skeleton(str(source), outdir=str(generated_dir)))
    return written


def teleport_static_candidate(pid, candidate):
    """Place Link without advancing the game or changing the movie cursor."""
    control = DolphinControl(pid)
    state = control.command("status").get("state")
    if state not in ("running", "paused"):
        raise RuntimeError("Dolphin must be running or paused to teleport Link")
    was_running = state == "running"
    if was_running:
        control.pause()
    try:
        reader = live_slash.open_dolphin(pid, writable=True)
        try:
            x, y, z = candidate.old
            facing = int(candidate.facing) & 0xFFFF
            player = reader.u32(live_slash.PLAYER_PTR)
            if not 0x80000000 <= player < 0x81800000:
                raise RuntimeError("Link is not loaded in Dolphin")
            actor_base = player - 0xD8
            position = b"".join(struct.pack(">f", value) for value in (x, y, z))
            angle = struct.pack(">H", facing)
            writes = [(actor_base + offset, position) for offset in (0x10C, 0x120)]
            writes.append((player + 0x120, position))
            writes.extend((address, position[index * 4:(index + 1) * 4])
                          for index, address in enumerate(live_slash._DEBUG_POS))
            writes.extend((address, angle) for address in (
                player + 0x12E, player + 0x136, live_slash._DEBUG_FACING,
            ))
            original = [(address, reader.read_bytes(address, len(data))) for address, data in writes]
            try:
                for address, data in writes:
                    reader.write_bytes(address, data)
                after = live_slash.read_state(reader)
                if (tuple(map(f32_bits, (after.x, after.y, after.z))) !=
                        tuple(map(f32_bits, (x, y, z))) or after.facing != facing):
                    raise RuntimeError("Dolphin did not retain the requested position and facing")
            except Exception:
                for address, data in reversed(original):
                    reader.write_bytes(address, data)
                raise
            return after
        finally:
            reader.close()
    finally:
        if was_running:
            control.command("resume")


class _ProgressMessages:
    """Keep progress traffic bounded without delaying results or errors."""
    def __init__(self, messages):
        self.messages = messages
        self.last_update = -float("inf")

    def put(self, message):
        if message[0] in ("progress", "status"):
            now = time.monotonic()
            if now - self.last_update < 0.1:
                return
            self.last_update = now
        self.messages.put(message)


_SCAN_TERMINALS = frozenset(("done", "cancelled", "error"))


def _scan_process(inputs, messages, cancel_event):
    try:
        _run_scan(inputs, _ProgressMessages(messages), cancel_event)
    except Exception as exc:
        messages.put(("error", str(exc)))


def _relay_scan(process, source, destination, cancel_event):
    """Only this thread touches process IPC; Tk never waits on a pipe read."""
    terminal = None
    try:
        while True:
            try:
                message = source.get(timeout=0.1)
            except queue.Empty:
                if process.is_alive():
                    continue
                break
            if message[0] in _SCAN_TERMINALS:
                terminal = message
                break
            destination.put(message)
        process.join(timeout=1.0)
        if terminal is None:
            terminal = (("cancelled",) if cancel_event.is_set() else
                        ("error", "Search process exited unexpectedly (code %s)" % process.exitcode))
    except Exception as exc:
        terminal = (("cancelled",) if cancel_event.is_set() else
                    ("error", "Search process connection failed: %s" % exc))
    finally:
        source.close()
    destination.put(terminal)


def _run_scan(inputs, messages, cancel_event):
    (seam, frames, facing_ranges, max_results, object_type, stop_first,
     require_oob_landing, oob_tolerance, opts, use_live, pid) = inputs
    try:
        report = lambda text: messages.put(("status", text))
        messages.put(("status", "Checking bomb/pot animation data..."))
        written = ensure_drop_animation_data(opts.get("animation_iso"))
        if written:
            messages.put(("status", "Extracted bomb/pot animation data"))
        if use_live:
            region, live_state, bg = load_live_room_collision(pid, status=report)
            stage = live_state.stage
            room = live_state.room
            messages.put(("live_state", live_state, bg))
        else:
            region, _loaded_box, stage = load_room_collision(opts, status=report)
            room = opts["room"]
        box = _coordinate_box(seam, region)
        context = prepare_search(region, box, seam)
        if context.seam_target[1] != seam[1]:
            messages.put(("matched_y", context.seam_target[1]))
        all_hits = []
        frame_count = len(frames)
        if require_oob_landing:
            profiles = (
                ("Fast OOB", 512, (0.9995, 1.0000, 0.00005)),
                ("Expanded OOB", 128, (0.9997, 1.00001, 0.00001)),
                ("Exhaustive OOB", 16, (0.9998, 1.000004, 0.000002)),
            )
        else:
            profiles = (
                ("Fast", 512, (0.46, 0.98, 0.02)),
                ("Expanded", 128, (0.45, 0.98, 0.005)),
                ("Exhaustive", 16, (0.45, 0.98, 0.002)),
            )
        for profile_index, (profile_name, profile_step, phases) in enumerate(profiles):
            pass_hits = 0
            profile_ranges = []
            for lo, hi, _original_step in facing_ranges:
                span = hi - lo
                profile_ranges.append((lo, hi, 16 if span < profile_step else profile_step))
            for index, frame in enumerate(frames):
                if cancel_event.is_set():
                    messages.put(("cancelled",))
                    return

                def frame_progress(done, total, frame_index=index, active_frame=frame,
                                   active_profile=profile_name):
                    overall = 100.0 * (frame_index + (float(done) / total)) / frame_count
                    messages.put((
                        "progress", overall, active_profile, active_frame, done, total
                    ))

                hits = find_candidates(
                    context,
                    frame,
                    object_type=object_type,
                    facing_ranges=profile_ranges,
                    phases=phases,
                    limit=max_results,
                    progress=frame_progress,
                    cancelled=cancel_event.is_set,
                    require_oob_landing=require_oob_landing,
                    oob_tolerance=oob_tolerance,
                )
                if cancel_event.is_set():
                    messages.put(("cancelled",))
                    return
                if hits:
                    all_hits.extend(hits)
                    pass_hits += len(hits)
                    messages.put(("hits", hits))
                    if stop_first:
                        break
            if pass_hits:
                break
            if profile_index + 1 < len(profiles):
                messages.put(("profile", profile_name))
            if cancel_event.is_set():
                messages.put(("cancelled",))
                return
        messages.put(("done", stage, room, len(all_hits)))
    except Exception as exc:
        messages.put(("error", str(exc)))


class DropPushApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TWW Bomb / Pot Push Finder")
        self.root.minsize(1080, 720)
        self.messages = queue.Queue()
        self.process_context = multiprocessing.get_context("spawn")
        self.cancel_event = self.process_context.Event()
        self.worker = None
        self.scan_process = None
        self.teleport_worker = None
        self.closed = False
        self.candidates = {}

        self._build_ui()
        self._load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(75, self._drain_messages)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        live = ttk.LabelFrame(outer, text="Live Dolphin", padding=10)
        live.grid(row=0, column=0, sticky="ew")
        live.columnconfigure(4, weight=1)
        self.use_live = tk.BooleanVar(value=True)
        self.pid = tk.StringVar(value="")
        ttk.Checkbutton(
            live, text="Use current room collision", variable=self.use_live,
            command=self._toggle_source,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(live, text="PID").grid(row=0, column=1, padx=(16, 6))
        ttk.Entry(live, textvariable=self.pid, width=10).grid(row=0, column=2)
        ttk.Button(live, text="Refresh", command=self.refresh_live).grid(
            row=0, column=3, padx=(8, 12)
        )
        self.live_text = tk.StringVar(value="Not connected")
        ttk.Label(live, textvariable=self.live_text, anchor="w").grid(
            row=0, column=4, sticky="ew"
        )

        target = ttk.LabelFrame(outer, text="Target seam", padding=10)
        target.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for column in (1, 3, 5):
            target.columnconfigure(column, weight=1)
        self.seam_x = tk.StringVar(value="")
        self.seam_y = tk.StringVar(value="")
        self.seam_z = tk.StringVar(value="")
        ttk.Label(target, text="X").grid(row=0, column=0, padx=(0, 6))
        seam_x_entry = ttk.Entry(target, textvariable=self.seam_x, width=18)
        seam_x_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(target, text="Y").grid(row=0, column=2, padx=(12, 6))
        seam_y_entry = ttk.Entry(target, textvariable=self.seam_y, width=18)
        seam_y_entry.grid(row=0, column=3, sticky="ew")
        ttk.Label(target, text="Z").grid(row=0, column=4, padx=(12, 6))
        seam_z_entry = ttk.Entry(target, textvariable=self.seam_z, width=18)
        seam_z_entry.grid(row=0, column=5, sticky="ew")
        self.seam_entries = (seam_x_entry, seam_y_entry, seam_z_entry)
        for entry in self.seam_entries:
            entry.bind("<<Paste>>", self._paste_seam)

        settings = ttk.LabelFrame(outer, text="Search", padding=10)
        settings.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        self.stage = tk.StringVar(value="")
        self.room = tk.StringVar(value="")
        self.object_type = tk.StringVar(value="bomb")
        self.frames = tk.StringVar(value="1-60")
        self.facings = tk.StringVar(value="0-65535")
        self.max_results = tk.StringVar(value="10")
        self.stop_first = tk.BooleanVar(value=True)
        self.oob_landing = tk.BooleanVar(value=False)
        self.oob_tolerance = tk.StringVar(value="0.005")
        self.collision_path = tk.StringVar(value="")
        self.teleport_on_result = tk.BooleanVar(value=False)

        ttk.Label(settings, text="Stage").grid(row=0, column=0, sticky="w")
        self.stage_entry = ttk.Entry(settings, textvariable=self.stage, width=16)
        self.stage_entry.grid(row=0, column=1, sticky="ew", padx=(6, 16))
        ttk.Label(settings, text="Room").grid(row=0, column=2, sticky="w")
        self.room_entry = ttk.Entry(settings, textvariable=self.room, width=8)
        self.room_entry.grid(row=0, column=3, sticky="ew", padx=(6, 16))
        ttk.Label(settings, text="Object").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            settings,
            textvariable=self.object_type,
            values=("bomb", "pot_small"),
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="ew", padx=(6, 0))

        ttk.Label(settings, text="Animation positions").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.frames).grid(row=1, column=1, sticky="ew", padx=(6, 16), pady=(10, 0))
        ttk.Label(settings, text="Facing angles").grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.facings).grid(
            row=1, column=3, sticky="ew", padx=(6, 16), pady=(10, 0)
        )
        ttk.Label(settings, text="Max results").grid(row=1, column=4, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.max_results, width=12).grid(row=1, column=5, sticky="ew", padx=(6, 0), pady=(10, 0))

        ttk.Label(settings, text="Game ISO / collision").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.collision_entry = ttk.Entry(settings, textvariable=self.collision_path)
        self.collision_entry.grid(
            row=2, column=1, columnspan=4, sticky="ew", padx=(6, 6), pady=(10, 0)
        )
        self.browse_button = ttk.Button(settings, text="Browse...", command=self._browse)
        self.browse_button.grid(row=2, column=5, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            settings,
            text="Stop after the first animation position with results",
            variable=self.stop_first,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        oob_options = ttk.Frame(settings)
        oob_options.grid(row=3, column=3, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Checkbutton(
            oob_options,
            text="Land on OOB seam within",
            variable=self.oob_landing,
        ).grid(row=0, column=0)
        ttk.Entry(oob_options, textvariable=self.oob_tolerance, width=8).grid(
            row=0, column=1, padx=(6, 4)
        )
        ttk.Label(oob_options, text="units").grid(row=0, column=2)

        ttk.Checkbutton(
            settings, text="Teleport to first static result",
            variable=self.teleport_on_result,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=10)
        actions.columnconfigure(2, weight=1)
        self.scan_button = ttk.Button(actions, text="Scan seam", command=self.start_scan)
        self.scan_button.grid(row=0, column=0)
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel_scan, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(8, 12))
        self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=2, sticky="ew")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(actions, textvariable=self.status).grid(row=0, column=3, padx=(12, 0))

        results = ttk.Frame(outer)
        results.grid(row=4, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        columns = ("frame", "object", "landing", "facing", "x", "y", "z", "end_x", "end_z")
        self.tree = ttk.Treeview(results, columns=columns, show="headings", height=10)
        headings = {
            "frame": "Frame",
            "object": "Object",
            "landing": "Landing",
            "facing": "Facing range",
            "x": "Start X",
            "y": "Start Y",
            "z": "Start Z",
            "end_x": "Resolved X",
            "end_z": "Resolved Z",
        }
        widths = {"frame": 60, "object": 80, "landing": 95, "facing": 110, "x": 145, "y": 100,
                  "z": 145, "end_x": 145, "end_z": 145}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                anchor="e" if column not in ("object", "landing") else "w",
            )
        scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(results, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        detail_row = ttk.Frame(outer)
        detail_row.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        detail_row.columnconfigure(0, weight=1)
        self.details = tk.Text(detail_row, height=12, wrap="none", state="disabled")
        self.details.grid(row=0, column=0, sticky="nsew")
        ttk.Button(detail_row, text="Copy setup", command=self.copy_setup).grid(row=0, column=1, sticky="n", padx=(8, 0))
        self.teleport_button = ttk.Button(
            detail_row, text="Teleport selected", command=self.teleport_selected
        )
        self.teleport_button.grid(row=1, column=1, sticky="n", padx=(8, 0), pady=(8, 0))
        self._toggle_source()

    @staticmethod
    def _replace_variable(variable, value):
        variable.set(str(value))

    def _paste_seam(self, _event=None):
        try:
            coordinates = parse_seam_coordinates(self.root.clipboard_get())
        except tk.TclError:
            return None
        if coordinates is None:
            return None
        for variable, value in zip(
            (self.seam_x, self.seam_y, self.seam_z), coordinates
        ):
            variable.set(value)
        self.status.set("Seam coordinates pasted")
        return "break"

    def _settings(self):
        return {
            "seam_x": self.seam_x.get(),
            "seam_y": self.seam_y.get(),
            "seam_z": self.seam_z.get(),
            "use_live": self.use_live.get(),
            "stage": self.stage.get(),
            "room": self.room.get(),
            "object_type": self.object_type.get(),
            "frames": self.frames.get(),
            "facings": self.facings.get(),
            "max_results": self.max_results.get(),
            "stop_first": self.stop_first.get(),
            "oob_landing": self.oob_landing.get(),
            "oob_tolerance": self.oob_tolerance.get(),
            "collision_path": self.collision_path.get(),
            "teleport_on_result": self.teleport_on_result.get(),
        }

    def _load_settings(self):
        settings = load_settings()
        variables = {
            "seam_x": self.seam_x,
            "seam_y": self.seam_y,
            "seam_z": self.seam_z,
            "stage": self.stage,
            "room": self.room,
            "object_type": self.object_type,
            "frames": self.frames,
            "facings": self.facings,
            "max_results": self.max_results,
            "oob_tolerance": self.oob_tolerance,
            "collision_path": self.collision_path,
        }
        for key, variable in variables.items():
            if key in settings:
                variable.set(settings[key])
        if not settings.get("collision_path"):
            self.collision_path.set(load_selected_iso())
        self.use_live.set(_stored_bool(settings.get("use_live"), True))
        self.stop_first.set(_stored_bool(settings.get("stop_first"), True))
        self.oob_landing.set(_stored_bool(settings.get("oob_landing"), False))
        self.teleport_on_result.set(_stored_bool(settings.get("teleport_on_result"), False))
        self._toggle_source()

    def _save_settings(self):
        save_settings(self._settings())

    def _close(self):
        if self.teleport_worker is not None and self.teleport_worker.is_alive():
            messagebox.showinfo("Teleport in progress", "Wait for Dolphin to settle before closing.", parent=self.root)
            return
        self.closed = True
        self.cancel_event.set()
        try:
            self._save_settings()
        finally:
            if self.scan_process is not None and self.scan_process.is_alive():
                self.scan_process.terminate()
                self.scan_process.join(timeout=0.2)
            self.root.destroy()

    def _pid_value(self):
        value = self.pid.get().strip()
        return int(value, 0) if value else None

    def _toggle_source(self):
        state = "disabled" if self.use_live.get() else "normal"
        for widget in (self.stage_entry, self.room_entry):
            widget.configure(state=state)
        self.collision_entry.configure(state="normal")
        self.browse_button.configure(state="normal")

    def _set_live_state(self, state, bg=None):
        self.pid.set(str(state.pid))
        self.stage.set(state.stage)
        self.room.set(str(state.room))
        suffix = "" if bg is None else " | collision BG %d" % bg
        self.live_text.set(
            "%s room %d | pos (%.6f, %.6f, %.6f) | speed %.3f | "
            "facing %d | animation %.3f%s"
            % (
                state.stage, state.room, state.x, state.y, state.z,
                state.speedF, state.facing, state.animation_frame, suffix,
            )
        )

    def refresh_live(self):
        try:
            self._set_live_state(live_slash.status(self._pid_value()))
        except Exception as exc:
            messagebox.showerror("Dolphin connection failed", str(exc), parent=self.root)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select collision source",
            filetypes=(
                ("Supported collision sources", "*.json *.dae *.iso"),
                ("Region cache", "*.json"),
                ("Collada", "*.dae"),
                ("Game disc", "*.iso"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.collision_path.set(path)

    def _inputs(self):
        seam = (float(self.seam_x.get()), float(self.seam_y.get()), float(self.seam_z.get()))
        frames = parse_frame_spec(self.frames.get())
        if self.frames.get().strip() == "1-60":
            frames = [11, 5, 51] + [frame for frame in frames if frame not in (11, 5, 51)]
        facing_ranges = parse_facing_spec(self.facings.get())
        max_results = int(self.max_results.get())
        if max_results < 1:
            raise ValueError("max results must be at least 1")
        oob_tolerance = float(self.oob_tolerance.get())
        if not 0.0 < oob_tolerance <= 1.0:
            raise ValueError("OOB seam distance must be greater than 0 and at most 1 unit")
        path = self.collision_path.get().strip()
        opts = {
            "stage": self.stage.get().strip(),
            "room": None,
            "cache": None,
            "dae": None,
            "iso": None,
            "animation_iso": path if Path(path).suffix.lower() == ".iso" else None,
            "box": _coordinate_box(seam),
        }
        use_live = self.use_live.get()
        if not use_live:
            if not opts["stage"]:
                raise ValueError("stage must not be empty for offline collision")
            opts["room"] = int(self.room.get())
        if path and not use_live:
            suffix = Path(path).suffix.lower()
            if suffix == ".json":
                opts["cache"] = path
            elif suffix == ".dae":
                opts["dae"] = path
            elif suffix == ".iso":
                opts["iso"] = path
            else:
                raise ValueError("collision source must be a .json, .dae, or .iso file")
        return (
            seam,
            frames,
            facing_ranges,
            max_results,
            self.object_type.get(),
            self.stop_first.get(),
            self.oob_landing.get(),
            oob_tolerance,
            opts,
            use_live,
            self._pid_value(),
        )

    def start_scan(self):
        if self.worker is not None and self.worker.is_alive():
            return
        if self.teleport_worker is not None and self.teleport_worker.is_alive():
            return
        try:
            inputs = self._inputs()
            self._save_settings()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Invalid search", str(exc), parent=self.root)
            return
        self.cancel_event.clear()
        self.candidates.clear()
        items = self.tree.get_children()
        if items:
            self.tree.delete(*items)
        self._set_details("")
        self.progress["value"] = 0
        self.progress.configure(mode="indeterminate")
        self.progress.start(50)
        self.status.set("Loading collision...")
        self.scan_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        process_messages = self.process_context.Queue()
        self.worker = self.process_context.Process(
            target=_scan_process, args=(inputs, process_messages, self.cancel_event), daemon=True,
        )
        self.scan_process = self.worker
        try:
            self.worker.start()
        except Exception as exc:
            process_messages.close()
            self.worker = self.scan_process = None
            self._finish_worker()
            self.status.set("Search failed to start")
            messagebox.showerror("Search failed", str(exc), parent=self.root)
            return
        threading.Thread(
            target=_relay_scan,
            args=(self.worker, process_messages, self.messages, self.cancel_event), daemon=True,
        ).start()

    def cancel_scan(self):
        self.cancel_event.set()
        self.status.set("Cancelling...")
        self.cancel_button.configure(state="disabled")

    def _drain_messages(self):
        deadline = time.monotonic() + 0.012
        try:
            for _ in range(64):
                if time.monotonic() >= deadline:
                    break
                message = self.messages.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, value, profile, frame, done, total = message
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress["value"] = value
                    self.status.set("%s, frame %d: angle %d/%d" % (profile, frame, done, total))
                elif kind == "status":
                    self.status.set(message[1])
                elif kind == "live_state":
                    self._set_live_state(message[1], message[2])
                elif kind == "matched_y":
                    self.seam_y.set("%.9f" % message[1])
                elif kind == "profile":
                    self.progress["value"] = 0
                    self.status.set("%s pass found no result; expanding search" % message[1])
                elif kind == "hits":
                    for candidate in message[1]:
                        self._add_candidate(candidate)
                elif kind == "done":
                    _, stage, room, count = message
                    self.progress["value"] = 100
                    self.status.set(
                        "%s room %d: %d result%s"
                        % (stage, room, count, "" if count == 1 else "s")
                    )
                    self._finish_worker()
                    if count and self.teleport_on_result.get():
                        self.teleport_selected()
                elif kind == "cancelled":
                    self.status.set("Cancelled")
                    self._finish_worker()
                elif kind == "teleport_done":
                    self.status.set("Teleported to static setup, facing %d" % message[1].facing)
                    if self.worker is None or not self.worker.is_alive():
                        self.scan_button.configure(state="normal")
                    self.teleport_button.configure(state="normal")
                    self._set_live_state(message[1])
                elif kind == "teleport_error":
                    self.status.set("Teleport failed")
                    if self.worker is None or not self.worker.is_alive():
                        self.scan_button.configure(state="normal")
                    self.teleport_button.configure(state="normal")
                    messagebox.showerror("Teleport failed", message[1], parent=self.root)
                elif kind == "error":
                    self.status.set("Search failed")
                    self._finish_worker()
                    messagebox.showerror("Search failed", message[1], parent=self.root)
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(75, self._drain_messages)

    def _finish_worker(self):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if self.teleport_worker is None or not self.teleport_worker.is_alive():
            self.scan_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _add_candidate(self, candidate):
        facing = "%d-%d" % candidate.facing_range
        landing = (
            "OOB %.6f" % candidate.seam_distance
            if candidate.oob_landing else "Clip"
        )
        iid = self.tree.insert("", "end", values=(
            candidate.frame,
            candidate.object_type,
            landing,
            facing,
            "%.9f" % candidate.old[0],
            "%.9f" % candidate.old[1],
            "%.9f" % candidate.old[2],
            "%.9f" % candidate.resolved[0],
            "%.9f" % candidate.resolved[1],
        ))
        self.candidates[iid] = candidate
        if len(self.tree.selection()) == 0:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected()

    def _selected_candidate(self):
        selected = self.tree.selection()
        return self.candidates.get(selected[0]) if selected else None

    def _format_candidate(self, candidate):
        return (
            "Animation Position: {frame}\n"
            "X: {x!r}\n"
            "Y: {y!r}\n"
            "Z: {z!r}\n"
            "Angle Range: {facing_lo}-{facing_hi}\n"
            "Endpoint X/Z: {end_x!r}, {end_z!r}\n"
            "OoB Seam: {oob}"
        ).format(
            frame=candidate.frame,
            facing_lo=candidate.facing_range[0],
            facing_hi=candidate.facing_range[1],
            x=candidate.old[0],
            y=candidate.old[1],
            z=candidate.old[2],
            end_x=candidate.resolved[0],
            end_z=candidate.resolved[1],
            oob="Yes" if candidate.oob_landing else "No",
        )

    def _show_selected(self, _event=None):
        candidate = self._selected_candidate()
        self._set_details(self._format_candidate(candidate) if candidate is not None else "")

    def _set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def copy_setup(self):
        candidate = self._selected_candidate()
        if candidate is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._format_candidate(candidate))
        self.status.set("Setup copied")

    def teleport_selected(self):
        if self.teleport_worker is not None and self.teleport_worker.is_alive():
            return
        candidate = self._selected_candidate()
        if candidate is None:
            messagebox.showinfo("Teleport", "Select a stationary setup result first.", parent=self.root)
            return
        self._save_settings()
        self.scan_button.configure(state="disabled")
        self.teleport_button.configure(state="disabled")
        self.status.set("Preparing static setup in Dolphin...")
        self.teleport_worker = threading.Thread(
            target=self._teleport_worker,
            args=(self._pid_value(), candidate),
            daemon=True,
        )
        self.teleport_worker.start()

    def _teleport_worker(self, pid, candidate):
        try:
            if pid is None:
                pid = live_slash.status().pid
            result = teleport_static_candidate(pid, candidate)
            self.messages.put(("teleport_done", result))
        except Exception as exc:
            self.messages.put(("teleport_error", str(exc)))


def main():
    root = tk.Tk()
    DropPushApp(root)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
