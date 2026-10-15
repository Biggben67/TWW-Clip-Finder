"""Capture the CURRENT live Dolphin state as a test-owned DTM anchor savestate.

The anchor is written to tests/dolphin/anchors/<name>@<isokey>.sav so it travels WITH the
tests and is never clobbered by an editor saving over savestate slot 9. The '@<isokey>'
tag tells run_dtm which iso to boot (resolved as <ISOS_DIR>/<isokey>.iso), so the iso is
never ambiguous again.

Set up the slate however you like first (loadstate, writename potential_speed/air, charge,
reorient, ...), then capture. Prints the captured controllable values so you can record the
expected endpoint.

Usage:
    python capture_anchor.py name=arrow_charged iso=twwgz
    python capture_anchor.py name=cruise_cold   iso=twwgz   from_slot=9   # load slot first
"""
import os, sys
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from harness.dtm.run_dtm import ANCHOR_DIR, iso_for_anchor


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    name = o.get('name')
    iso = o.get('iso')
    if not name or not iso:
        raise SystemExit("need name=<test> iso=<isokey> (e.g. name=arrow_charged iso=twwgz)")

    if 'from_slot' in o:
        D.control_pipe_quiet("pause")
        D.control_pipe_quiet("savestate", {"action": "load", "slot": int(o['from_slot'])})

    h, m = D.attach()
    vals = {k: D.read_named(h, m, k) for k in
            ("potential_speed", "anim_frame", "air", "link_state", "facing")}
    vals["facing_deg"] = vals["facing"] * 360.0 / 65536.0

    os.makedirs(ANCHOR_DIR, exist_ok=True)
    path = os.path.join(ANCHOR_DIR, f"{name}@{iso}.sav")
    D.control_pipe_quiet("savestate", {"action": "save", "path": path.replace('\\', '/')})

    # round-trips through the same name->iso resolver run_dtm uses (fails loud if no iso)
    resolved = iso_for_anchor(path)
    print(f"captured {os.path.basename(path)}")
    print(f"  iso resolves to: {resolved}")
    print(f"  slate: v={vals['potential_speed']:.3f} anim={vals['anim_frame']:.4f} "
          f"air={vals['air']} state={vals['link_state']} "
          f"facing={vals['facing']} ({vals['facing_deg']:.1f} deg)")
    print(f"  use:   python run_dtm.py seq=... anchor={name}@{iso}")


if __name__ == "__main__":
    main()
