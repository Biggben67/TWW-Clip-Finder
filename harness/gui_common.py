"""Small, dependency-free helpers shared by the Tk clip finders."""
from __future__ import annotations

import json
import os


def parse_seam_coordinates(text: str):
    """Return normalized strings for a comma-separated X, Y, Z paste."""
    parts = [part.strip() for part in str(text).strip().strip("()[]").split(",")]
    if len(parts) != 3 or any(not part for part in parts):
        return None
    try:
        tuple(float(part) for part in parts)
    except ValueError:
        return None
    return tuple(parts)


def load_gui_settings(path: str, keys) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as source:
            data = json.load(source)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: str(data[key]) for key in keys if key in data}


def save_gui_settings(data: dict, path: str, keys) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = {key: str(data[key]) for key in keys if key in data}
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2)
    os.replace(temporary, path)
