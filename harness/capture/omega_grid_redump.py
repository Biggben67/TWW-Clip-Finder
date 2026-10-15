"""omega_grid_redump.py — FULL 65536-cell (csx 0..255 x csy 0..255) omega grid dump, live.

The shipped omega_table_full.csv covers only csx 0..15 (deep negative-saturation); the 2-D
camera model (camera_arbitrary.CameraArbitrary) raises KeyError for off-grid (csx,csy) with
csy != 128. omega is the per-frame camera-rate command = steady d(cam_target)/frame while a
C-stick is held (main stick neutral so facing can't confound).

omega is STATE-DEPENDENT (the negative-saturation band drifts +/-1 as cam_yaw/cam_target
accumulate); omega_full_redump.py handles this with a fresh loadstate PER CELL (~2.8 s/cell ->
~50 h for 65536). This script adds a FAST method: reset cam_yaw/cam_target (and air/speed) to the
rest values via a memory WRITE per cell instead of a loadstate, so a cell is measured from the
same rest state without the 2.8 s load. `method=loadstate` keeps the gold per-cell load for
VALIDATION — run both on a sample and confirm bit-identical before trusting the fast path.

Per cell: reset -> hold (csx,csy) `settle` frames (ramp) -> read steady d(cam_target) over the
last two frames; VERIFY the two steady deltas agree (else re-try longer / flag).

PARALLEL: shard by csx range across N Dolphin instances (DOLPHIN_PID / pid=), merge afterward.
Resumable, flush every FLUSH cells.

Usage:
    DOLPHIN_PID=<pid> python omega_grid_redump.py csxlo=0 csxhi=42 out=oshard0.csv \
        [method=fast|loadstate] [settle=11] [slot=10]
    python omega_grid_redump.py merge out=omega_table_full.csv shard0=... shard1=... ...
"""
import os, sys, csv, struct, time

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm

GEN = os.path.join(_rb, "_generated")
FLUSH = 256
SETTLE = 11               # ramp frames before reading the steady omega (matches omega_capture HOLD)
LOCK_SPEED = -700.0


def _d16(a, b):
    x = (a - b) & 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _retry(fn, *a, **k):
    last = None
    for _ in range(40):
        try:
            return fn(*a, **k)
        except (OSError, ValueError) as e:
            last = e; time.sleep(0.1)
    raise last


def _pipe(op, extra=None):
    return _retry(dm.control_pipe_quiet, op, extra)


def wnamed(h, m, name, value):
    e = dm.NAMED_ADDRS[name]; addr = dm.resolve_chain(h, m, e["base"], e["offsets"])
    tp = e["type"]; fmt, sz = dm.FMT[tp]
    data = (struct.pack(fmt, float(value)) if tp in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    dm.write_bytes(h, m, addr, data)


def rname(h, m, name):
    return dm.read_named(h, m, name)


def load_slot(slot):
    _pipe("savestate", {"action": "load", "slot": int(slot)})
    time.sleep(0.3)


def read_rest(h, m):
    """Rest state to reset to each cell (fast method), captured once after a fresh load: cam
    accumulators + Link's position (so he stays home — a neutral-stick superswim at LOCK_SPEED
    still TRANSLATES, and without a per-cell pos reset he drifts into geometry / nulls the camera
    chain). Position does NOT affect omega (fast==gold confirmed it), so this is safe."""
    return {"cam_yaw": int(rname(h, m, "cam_yaw")), "cam_target": int(rname(h, m, "cam_target")),
            "pos": (rname(h, m, "link_x"), rname(h, m, "link_y"), rname(h, m, "link_z"))}


def prep_swim(h, m, rest):
    _retry(wnamed, h, m, "air", 900)
    _retry(wnamed, h, m, "potential_speed", LOCK_SPEED)
    for k, v in zip(("link_x", "link_y", "link_z"), rest["pos"]):
        _retry(wnamed, h, m, k, v)


def hold_read_omega(h, m, csx, csy, settle):
    """Hold C-stick (csx,csy) with neutral main stick; return (omega, stable).
    omega = steady d(cam_target); stable = the last two per-frame deltas agree."""
    # ramp in one batched call
    if settle > 2:
        _pipe("advanceseq", {"port": 0, "seq": [
            {"stickX": 128, "stickY": 128, "substickX": csx, "substickY": csy, "frames": settle - 2}]})
    p0 = int(_retry(rname, h, m, "cam_target"))
    _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickX": csx, "substickY": csy, "frames": 1})
    p1 = int(_retry(rname, h, m, "cam_target"))
    _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickX": csx, "substickY": csy, "frames": 1})
    p2 = int(_retry(rname, h, m, "cam_target"))
    d1, d2 = _d16(p1, p0), _d16(p2, p1)
    return d2, (d1 == d2)


def dump_cell(h, m, csx, csy, rest, method, settle):
    if method == "loadstate":
        load_slot(dump_cell.slot); h2, m2 = _retry(dm.attach)
        _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
        h, m = _retry(dm.attach)
        prep_swim(h, m, rest)
    else:  # fast: reset cam state + swim state + position via writes
        _retry(wnamed, h, m, "cam_yaw", rest["cam_yaw"])
        _retry(wnamed, h, m, "cam_target", rest["cam_target"])
        prep_swim(h, m, rest)
    om, stable = hold_read_omega(h, m, csx, csy, settle)
    if not stable:
        om, stable = hold_read_omega(h, m, csx, csy, settle * 2)
    return om, stable


def load_existing(path):
    t = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            t[(int(r["csx"]), int(r["csy"]))] = int(r["omega"])
    return t


def save(t, path):
    with open(path, "w", newline="") as f:
        f.write("csx,csy,omega\n")
        for (csx, csy) in sorted(t):
            f.write("%d,%d,%d\n" % (csx, csy, t[(csx, csy)]))


def snake(lo, hi):
    out = []
    for i, csx in enumerate(range(lo, hi + 1)):
        ys = range(256) if i % 2 == 0 else range(255, -1, -1)
        for csy in ys:
            out.append((csx, csy))
    return out


def merge(shards, out):
    m = {}
    for p in shards:
        m.update(load_existing(p))
    save(m, out)
    print("merged %d cells from %d shards -> %s" % (len(m), len(shards), out))


def main():
    o = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    if "merge" in sys.argv:
        merge([o[k] for k in sorted(o) if k.startswith("shard")],
              o.get("out", os.path.join(GEN, "omega_grid_full.csv")))
        return
    if "pid" in o:
        os.environ["DOLPHIN_PID"] = str(int(o["pid"]))
    lo = int(o.get("csxlo", "0")); hi = int(o.get("csxhi", "255"))
    method = o.get("method", "fast")
    settle = int(o.get("settle", str(SETTLE)))
    slot = int(o.get("slot", "10"))
    maxcells = int(o.get("maxcells", "0"))
    cells_arg = o.get("cells")     # optional explicit "csx:csy,csx:csy,..." for validation samples
    out = o.get("out", os.path.join(GEN, "omega_shard_%d_%d.csv" % (lo, hi)))
    os.makedirs(GEN, exist_ok=True)
    dump_cell.slot = slot

    load_slot(slot); h, m = _retry(dm.attach)
    _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
    h, m = _retry(dm.attach)
    rest = read_rest(h, m)      # capture clean slot-10 pos/cam BEFORE any swim drift
    prep_swim(h, m, rest)
    st = int(rname(h, m, "link_state"))
    print("omega dump csx=%d..%d method=%s settle=%d pid=%s slot=%d state=%d rest=%s"
          % (lo, hi, method, settle, os.environ.get("DOLPHIN_PID"), slot, st, rest))

    if cells_arg:
        cells = [(int(a), int(b)) for a, b in (c.split(":") for c in cells_arg.split(","))]
    else:
        cells = snake(lo, hi)
    table = load_existing(out)
    todo = [c for c in cells if c not in table]
    if maxcells:
        todo = todo[:maxcells]
    print("grid %d cells; %d done; %d to dump" % (len(cells), len(cells) - len(todo), len(todo)))

    unstable = []; recoveries = 0
    t0 = time.time(); done = 0
    for (csx, csy) in todo:
        try:
            om, stable = dump_cell(h, m, csx, csy, rest, method, settle)
        except (ValueError, OSError):
            # camera pointer chain went null (known over long in-place runs). Recover: neutral-
            # settle a few frames; if still null, full loadstate to re-anchor the camera object.
            recoveries += 1
            try:
                _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 3})
                h, m = _retry(dm.attach)
                _retry(rname, h, m, "cam_target")   # probe: raises if still null
            except (ValueError, OSError):
                load_slot(slot); h, m = _retry(dm.attach)
                _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
                h, m = _retry(dm.attach); prep_swim(h, m)
            om, stable = dump_cell(h, m, csx, csy, rest, method, settle)
        if not stable:
            unstable.append((csx, csy, om))
        table[(csx, csy)] = om
        done += 1
        if done % FLUSH == 0:
            save(table, out)
            rate = (time.time() - t0) / done
            print("[%s] %d/%d  %.0f ms/cell  ~%.1f min left  unstable=%d"
                  % (os.environ.get("DOLPHIN_PID"), done, len(todo), rate * 1000,
                     rate * (len(todo) - done) / 60, len(unstable)))
    save(table, out)
    _pipe("clearinput")
    print("DONE csx=%d..%d method=%s: %d cells, %d unstable, %d chain-null recoveries -> %s"
          % (lo, hi, method, len(table), len(unstable), recoveries, out))


if __name__ == "__main__":
    main()
