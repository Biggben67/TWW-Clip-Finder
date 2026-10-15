"""stick_angle_capture.py - capture the game's EXACT mMainStickAngle(sx,sy) for a set of
raw main-stick (sx,sy) values, live from Dolphin, and cache them in stick_angle_table.csv.

WHY: the per-frame swim speed gain (setSpeedAndAngleSwim) is
    gain = mStickDistance * 3 * cM_scos(d_turn)
where d_turn comes from the facing chase toward m34E8 = mMainStickAngle(sx,sy) + 0x8000 +
camAngle. For ARBITRARY main-stick directions (sx != 128) the gain is sensitive to the EXACT
stickAngle (the cos of the snap-turn). The closed-form atan2 + dead-zone-15 model
(superswim_sim.stick_angle_deg) is only good to ~0.86deg (worst 156 s16) because the game
applies the GC radial gate normalization, not a simple per-axis dead-zone. The shipped
INPUT_DUMP_MAIN.csv matches live EXACTLY but is a SPARSE sample (and only covers y<=214).

HOW (no new RE needed): on a charge build, consecutive full/near-full sticks point ~180deg
apart so the facing SNAPS to m34E8 every frame. On a snap frame the game sets
    facing[f] = m34E8[f] = mMainStickAngle(stick[f-1... see ordering]) ...
Concretely (1-frame facing-snap lag, live-pinned in cap_randcharge): the stick supplied on
frame f produces facing[f+1] = mMainStickAngle(stick[f]) + 0x8000 + csangle[f]. So
    mMainStickAngle(sx,sy) = (facing[f+1] - 0x8000 - csangle[f]) & 0xFFFF
read directly from the live snap. Verified == INPUT_DUMP_MAIN for every cell present (err 0).

We drive each wanted stick on alternating frames against an opposing filler stick (so every
wanted frame snaps), C-stick neutral-down (camera frozen -> csangle constant -> exact), and
read facing+csangle each frame. Cached to stick_angle_table.csv; re-runs only capture cells
not already cached. This GENERALIZES: any new capture's sticks get their exact angle once.

Usage:
  python stick_angle_capture.py <capture_csv> [<capture_csv> ...]   # capture all their sticks
  python stick_angle_capture.py --sticks 137,255 147,0 ...          # explicit list
"""
import sys, os, csv, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm

TABLE = os.path.join(HERE, "stick_angle_table.csv")
READS = ["csangle", "facing", "link_state"]


def load_table():
    t = {}
    if os.path.exists(TABLE):
        for r in csv.DictReader(open(TABLE)):
            t[(int(r["sx"]), int(r["sy"]))] = int(r["angle"])
    return t


def save_table(t):
    with open(TABLE, "w", newline="") as f:
        f.write("sx,sy,angle\n")
        for (sx, sy), a in sorted(t.items()):
            f.write(f"{sx},{sy},{a}\n")


def wnamed(h, m, name, value):
    e = dm.NAMED_ADDRS[name]; addr = dm.resolve_chain(h, m, e["base"], e["offsets"])
    tp = e["type"]; fmt, sz = dm.FMT[tp]
    data = (struct.pack(fmt, float(value)) if tp in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    dm.write_bytes(h, m, addr, data)


def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _capture_pass(want, filler_fn, slot=10):
    """Drive [filler, filler, wanted] triples and read each wanted stick's facing-snap.
    Holding the filler TWO frames fully settles facing (the snap is 1-frame lagged) so the
    wanted stick is reliably >135deg away. Returns {stick: angle} and a set of sticks that did
    NOT cleanly snap (caller retries those with a different filler)."""
    full = [(128, 255)]                       # lead charge: enter state 55
    idx = {}
    for s in want:
        f = filler_fn(s)
        full.append(f); full.append(f)        # 2-frame filler -> facing settles to filler dir
        idx[s] = len(full)
        full.append(s)
    full.append((128, 0))                     # trailing frame so the last snap is readable

    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = dm.attach()
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
    h, m = dm.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", -300.0)

    def snap_read():
        return {nm: dm.read_named(h, m, nm) for nm in READS}
    rows = [snap_read()]
    for (sx, sy) in full:
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": 128, "substickY": 0, "frames": 1})
        rows.append(snap_read())
    dm.control_pipe_quiet("clearinput")

    out, bad = {}, set()
    for s in want:
        j = idx[s]
        fac_pre = rows[j + 1]["facing"]; fac_next = rows[j + 2]["facing"]
        cam_at = rows[j + 1]["csangle"]
        if abs(_s16(fac_next - fac_pre)) < 0x6000:      # not a clean snap -> reject
            bad.add(s); continue
        out[s] = (fac_next - 0x8000 - cam_at) & 0xFFFF
    return out, bad


def capture(sticks, slot=10):
    """sticks: iterable of (sx,sy). Returns {(sx,sy): angle}, the exact mMainStickAngle read off
    a guaranteed facing-snap. Multiple filler passes so EVERY stick (incl. near-cardinal) snaps:
    pass 1 the gate-clamped opposite; retries rotate the filler 90/45deg to force a >135deg swing.
    Each angle is cross-checked: a stick captured in two passes must agree (else it's dropped)."""
    want = [s for s in dict.fromkeys((int(a), int(b)) for a, b in sticks)]
    if not want:
        return {}
    fillers = [
        lambda s: (max(1, min(255, 256 - s[0])), max(1, min(255, 256 - s[1]))),  # opposite
        lambda s: (128, 0),                                                       # full down
        lambda s: (128, 255),                                                     # full up
        lambda s: (255, 128),                                                     # full right
        lambda s: (0, 128),                                                       # full left
    ]
    got = {}
    todo = list(want)
    for fl in fillers:
        if not todo:
            break
        res, bad = _capture_pass(todo, fl, slot)
        for s, a in res.items():
            if s in got and ((got[s] - a + 0x8000) & 0xFFFF) - 0x8000 != 0:
                print(f"  WARNING inconsistent angle for {s}: {got[s]} vs {a}")
            got[s] = a
        todo = sorted(bad)
    # Sticks that never snap from any filler (their direction is too close to every filler):
    # read the angle via a GRADUAL chase instead -- hold the stick ~20 frames so facing converges
    # to m34E8 (cLib_addCalcAngleS settles), then angle = facing - 0x8000 - csangle.
    for s in list(todo):
        a = _capture_gradual(s, slot)
        if a is not None:
            got[s] = a; todo.remove(s)
    if todo:
        print(f"  WARNING {len(todo)} sticks could not be measured (no angle): {todo[:8]}")
    return got


def _capture_gradual(stick, slot=10, hold=24):
    """Hold one stick long enough for facing to gradually chase (no snap) all the way to m34E8,
    then read angle = facing - 0x8000 - csangle. Confirms convergence (facing stops moving)."""
    sx, sy = stick
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = dm.attach()
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
    h, m = dm.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", -300.0)
    prev_fac = None; stable = 0; last = None
    for _ in range(hold):
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": 128, "substickY": 0, "frames": 1})
        fac = dm.read_named(h, m, "facing"); cam = dm.read_named(h, m, "csangle")
        if prev_fac is not None and abs(_s16(fac - prev_fac)) <= 1:
            stable += 1
        else:
            stable = 0
        prev_fac = fac
        last = (fac - 0x8000 - cam) & 0xFFFF
    dm.control_pipe_quiet("clearinput")
    return last if stable >= 2 else None       # require facing to have settled


def sticks_from_csv(path):
    rows = list(csv.DictReader(open(path)))
    return [(int(r["sx"]), int(r["sy"])) for r in rows[1:] if r["sx"] != ""]


def main():
    args = sys.argv[1:]
    sticks = []
    if args and args[0] == "--sticks":
        for tok in args[1:]:
            a, b = tok.split(","); sticks.append((int(a), int(b)))
    else:
        for p in args:
            sticks += sticks_from_csv(p)
    if not sticks:
        print(__doc__); sys.exit(1)
    table = load_table()
    need = [s for s in dict.fromkeys(sticks) if s not in table]
    print(f"{len(set(sticks))} unique sticks; {len(need)} need live capture")
    if need:
        got = capture(need)
        table.update(got)
        save_table(table)
        print(f"captured {len(got)} cells -> {TABLE} (now {len(table)} total)")
    else:
        print("all cached already")


if __name__ == "__main__":
    main()
