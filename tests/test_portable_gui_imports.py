"""Portable GUI imports must not depend on excluded collision fixtures."""

from pathlib import Path
import subprocess
import sys


def test_moving_gui_imports_without_kaze_fixture():
    code = r'''
import builtins
real_open = builtins.open

def open_without_fixture(path, *args, **kwargs):
    if str(path).replace("\\", "/").endswith("/fixtures/kaze_r11_geo.json"):
        raise AssertionError("moving GUI imported an excluded fixture")
    return real_open(path, *args, **kwargs)

builtins.open = open_without_fixture
import harness.rollstab.native_route_gui
import harness.collision.object_route_gui
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
