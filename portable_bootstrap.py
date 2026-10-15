"""Create private Link animation caches from a user-selected JP disc image."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "_generated" / "anim"
CONFIG_PATH = ROOT / "_generated" / "portable_iso.json"
ANIMATION_FILES = (
    "link_anim_walk_dash.json",
    "link_anim_cuts.json",
    "link_anim_grab.json",
    "link_skeleton.json",
)


def load_selected_iso(config_path=CONFIG_PATH):
    try:
        path = Path(json.loads(Path(config_path).read_text(encoding="utf-8"))["iso"])
        return str(path) if path.is_file() else ""
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def _select_iso(explicit, config_path):
    if explicit:
        return Path(explicit)
    for path in (os.environ.get("TWW_ISO"), load_selected_iso(config_path)):
        if path and Path(path).is_file():
            return Path(path)
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        choice = filedialog.askopenfilename(
            parent=root, title="Select your Japanese Wind Waker ISO",
            filetypes=(("GameCube ISO", "*.iso"), ("All files", "*.*")),
        )
    finally:
        root.destroy()
    if not choice:
        raise RuntimeError("No ISO selected; no game assets were installed")
    return Path(choice)


def _validate_iso(path):
    if not path.is_file() or path.suffix.lower() != ".iso":
        raise ValueError("Select an existing Japanese Wind Waker .iso file")
    with path.open("rb") as disc:
        game_id = disc.read(6)
    if game_id not in (b"GZLJ01", b"GZLJ11"):
        raise ValueError("Expected a Japanese Wind Waker ISO (GZLJ01 or GZLJ11)")


def ensure_animation_cache(iso_path, cache_dir=CACHE_DIR):
    """Only the ignored cache receives extracted models and animation keyframes."""
    iso_path = Path(iso_path).resolve()
    _validate_iso(iso_path)
    cache_dir = Path(cache_dir)
    stat = iso_path.stat()
    identity = {"iso": str(iso_path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    stamp = cache_dir / "source.json"
    try:
        current = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = None
    if current == identity and all((cache_dir / name).is_file() for name in ANIMATION_FILES):
        return False

    from harness.anim import parse_bck, parse_bmd

    cache_dir.mkdir(parents=True, exist_ok=True)
    print("Extracting Link animations and skeleton from your ISO...")
    animations = parse_bck._gcm_read_object_arc(str(iso_path), "LkAnm")
    parse_bck.extract_animation_sets(animations, outdir=str(cache_dir))
    model = parse_bmd._gcm_read_object_arc(str(iso_path), "Link")
    parse_bmd.extract_skeleton(model, outdir=str(cache_dir))
    stamp.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", help="Use this ISO without opening a file dialog")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    args = parser.parse_args(argv)
    config = args.cache_dir.parent / "portable_iso.json"
    try:
        iso = _select_iso(args.iso, config).resolve()
        ensure_animation_cache(iso, args.cache_dir)
        if load_selected_iso(config) != str(iso):
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps({"iso": str(iso)}, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, IndexError) as exc:
        print("Setup failed: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
