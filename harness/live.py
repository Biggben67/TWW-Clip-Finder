"""Live-game write helper shared across the harness.

``wnamed`` writes a value to a NAMED_ADDRS field in the running game (used to seed air /
potential_speed before a replay). Lifted out of run_tests.py, where ~40 scripts referenced it.
Depends on ``dolphin_mem`` from the parent ``../tools/`` (reached via the bootstrap below).
Dolphin command reference: ../tools/DOLPHIN_CONTROL.md (the single source of truth).
"""
import os, sys, struct

# Locate the repo root (marker: pyproject.toml) and the parent ../tools/ (dolphin_mem, dtm_make).
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, 'pyproject.toml')):
    _d = os.path.dirname(_d)
_REPO = _d
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TOOLS = os.path.join(os.path.dirname(_REPO), 'tools')  # locate tools/
if _TOOLS not in sys.path:
    sys.path.append(_TOOLS)

import dolphin_mem as D


def wnamed(h, m, name, value):
    """Write ``value`` to the NAMED_ADDRS field ``name`` in the live game (chain-resolved)."""
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, m, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    D.write_bytes(h, m, addr, data)
