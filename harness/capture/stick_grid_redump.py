"""stick_grid_redump.py — GOLD re-dump of the full 65536-cell main-stick grid, live.

WHY: the shipped superswim/tables/stick_angle_table.csv was produced by
tww-python-scripts/stick_angle_grid_dump.py with a 1-frame set/read pipeline. The game's
mMainStickAngle (0x80398314) and especially mStickDistance ([0x803BD910]+0x35B4) update with a
LONGER latency than that assumed, so some cells recorded a stale neighbour's value:
  - stick_dist: the WHOLE column is shifted ~2 rows (mStickDistance lagged ~2 frames);
  - angle: ~6% of off-axis cells are wrong (worst at exact-diagonal cells, e.g. (160,160)=24260
    shipped vs 24576 live, (160,112)=15162 vs 15771). angle is the ONE column the sim reads
    (tww_sim.swim.predict.stick_angle), so those errors cause a real sim-vs-live facing desync
    (confirmed via a clean-DTM negative-v test).

FIX (root cause): hold each stick for SETTLE frames so every field fully converges, and VERIFY
stability by reading on two consecutive settled frames — if they disagree the cell hasn't
settled and is flagged rather than silently recorded. Per-frame we re-lock air/pos/speed so Link
stays a valid in-place superswimmer over the whole sweep (no drown / void-out / pointer null).

Captures per cell: angle (u16), x, y, value (the MAIN_STICK_* controller fields), and stick_dist
(mStickDistance, the /54 swim-gain gate) — the full useful set, all settled-consistent.

PARALLEL (mirrors harness/capture/omega_full_redump.py): each Dolphin instance dumps a disjoint
sx range to its own shard CSV; set DOLPHIN_PID (or pass pid=) so pipe+memory target that instance.
Merge the shards afterward (merge sub-command). Resumable: skips cells already in the shard,
flushes every FLUSH cells.

Usage (one shard / instance):
    DOLPHIN_PID=<pid> python stick_grid_redump.py sxlo=0 sxhi=63 out=shard0.csv [settle=8]
Merge:
    python stick_grid_redump.py merge out=stick_angle_full.csv shard0=... shard1=... ...
"""
import os, sys, csv, struct, time

# >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm

# --- live addresses (from stick_angle_grid_dump.py, verified) --------------------------
A_ANGLE = 0x80398314        # u16 mMainStickAngle (== the `stickAngle` term in m34E8)
A_X     = 0x80398308        # f32 normalized X (octagonal-gated)
A_Y     = 0x8039830C        # f32 normalized Y
A_VALUE = 0x80398310        # f32 controller normalized magnitude
SD_BASE = 0x803BD910        # deref -> +0x35B4 = f32 mStickDistance (the /54 swim-gain gate)
SD_OFF  = 0x35B4

FIELDS = ["angle", "x", "y", "value", "stick_dist"]
DEFAULT_ANCHOR = os.path.join(_rb, "tests", "dolphin", "anchors", "negcharge@twwgz.sav")
FLUSH = 256
SETTLE = 8                  # settle frames per cell (>= the ~2-frame mStickDistance latency + margin)
LOCK_SPEED = -60.0          # small negative speed: keeps state swimming but bounds in-cell travel
                            # (settle runs unlocked in one advanceseq) so Link never voids out


def _retry(fn, *a, **k):
    """Retry pipe/memory calls through transient failures (per-instance pipe torn down during a
    savestate-load; player pointer chain momentarily null right after a reset)."""
    last = None
    for _ in range(40):
        try:
            return fn(*a, **k)
        except (OSError, ValueError) as e:
            last = e; time.sleep(0.1)
    raise last


def _pipe(op, extra=None):
    return _retry(dm.control_pipe_quiet, op, extra)


def _rd(h, m, addr, typ):
    fmt, sz = dm.FMT[typ]
    return struct.unpack(fmt, dm.read_bytes(h, m, addr, sz))[0]


def read_fields(h, m):
    sdp = _rd(h, m, SD_BASE, "u32")
    sd = _rd(h, m, sdp + SD_OFF, "f32") if 0x80000000 <= sdp < 0x81800000 else float("nan")
    return {
        "angle": _rd(h, m, A_ANGLE, "u16"),
        "x": _rd(h, m, A_X, "f32"),
        "y": _rd(h, m, A_Y, "f32"),
        "value": _rd(h, m, A_VALUE, "f32"),
        "stick_dist": sd,
    }


def wnamed(h, m, name, value):
    e = dm.NAMED_ADDRS[name]; addr = dm.resolve_chain(h, m, e["base"], e["offsets"])
    tp = e["type"]; fmt, sz = dm.FMT[tp]
    data = (struct.pack(fmt, float(value)) if tp in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    dm.write_bytes(h, m, addr, data)


def read_pos(h, m):
    return tuple(_retry(dm.read_named, h, m, k) for k in ("link_x", "link_y", "link_z"))


def lock_slate(h, m, pos0):
    """Re-pin Link so he stays an in-place superswimmer: pos frozen (no travel/void), air full
    (no drown), speed negative (stays state 55 so mStickDistance keeps updating)."""
    _retry(wnamed, h, m, "air", 900)
    _retry(wnamed, h, m, "potential_speed", LOCK_SPEED)
    for k, v in zip(("link_x", "link_y", "link_z"), pos0):
        _retry(wnamed, h, m, k, v)


def hold(h, m, sx, sy, frames):
    """Hold one stick for `frames` in a SINGLE pipe call (one open) — the settle runs on the emu
    thread with no per-frame host round-trip. Position is re-pinned per cell (not per frame), so
    keep LOCK_SPEED small enough that `frames` of in-place swim can't cross a load zone."""
    _pipe("advanceseq", {"port": 0, "seq": [
        {"stickX": sx, "stickY": sy, "substickX": 128, "substickY": 0, "frames": frames}]})


def dump_cell(h, m, sx, sy, pos0, settle):
    """Reset the slate, hold (sx,sy) `settle` frames, read, then advance one MORE settled frame
    and re-read; return (fields, stable). stable == angle & stick_dist identical across the two
    settled reads (fully converged). On instability, caller re-tries with a longer settle."""
    lock_slate(h, m, pos0)
    hold(h, m, sx, sy, settle)
    a1 = _retry(read_fields, h, m)
    hold(h, m, sx, sy, 1)
    a2 = _retry(read_fields, h, m)
    stable = (a1["angle"] == a2["angle"]
              and (a1["stick_dist"] == a2["stick_dist"]
                   or (a1["stick_dist"] != a1["stick_dist"] and a2["stick_dist"] != a2["stick_dist"])))
    return a2, stable, a1


# --- csv io -----------------------------------------------------------------------------
def load_existing(path):
    t = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            t[(int(r["sx"]), int(r["sy"]))] = r
    return t


def save(t, path):
    with open(path, "w", newline="") as f:
        f.write("sx,sy,angle,x,y,value,stick_dist\n")
        for (sx, sy) in sorted(t):
            r = t[(sx, sy)]
            f.write("%d,%d,%d,%.7g,%.7g,%.7g,%.7g\n" %
                    (sx, sy, int(r["angle"]), float(r["x"]), float(r["y"]),
                     float(r["value"]), float(r["stick_dist"])))


def snake(sxlo, sxhi):
    out = []
    for i, sx in enumerate(range(sxlo, sxhi + 1)):
        ys = range(256) if i % 2 == 0 else range(255, -1, -1)
        for sy in ys:
            out.append((sx, sy))
    return out


def merge(shard_paths, out):
    merged = {}
    for p in shard_paths:
        merged.update(load_existing(p))
    save(merged, out)
    print("merged %d cells from %d shards -> %s" % (len(merged), len(shard_paths), out))


# --- main -------------------------------------------------------------------------------
def main():
    opts = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    if "merge" in sys.argv:
        shards = [opts[k] for k in sorted(opts) if k.startswith("shard")]
        merge(shards, opts.get("out", os.path.join(_rb, "tww_sim", "core", "tables", "stick_angle_full.csv")))
        return

    if "pid" in opts:
        os.environ["DOLPHIN_PID"] = str(int(opts["pid"]))
    sxlo = int(opts.get("sxlo", "0")); sxhi = int(opts.get("sxhi", "255"))
    settle = int(opts.get("settle", str(SETTLE)))
    maxcells = int(opts.get("maxcells", "0"))
    out = opts.get("out", os.path.join(_rb, "_generated", "stick_shard_%d_%d.csv" % (sxlo, sxhi)))
    unstable_path = out + ".unstable"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # anchor: load the negative-v superswim slate once so mStickDistance is live from frame 1
    anchor = opts.get("anchor", DEFAULT_ANCHOR)
    _pipe("pause")
    _pipe("savestate", {"action": "load", "path": anchor.replace("\\", "/")})
    time.sleep(1.0)
    h, m = _retry(dm.attach)
    hold(h, m, 128, 128, 2)                     # settle neutral; establish pos AFTER load
    pos0 = read_pos(h, m)
    st = _retry(dm.read_named, h, m, "link_state")
    print("shard sx=%d..%d settle=%d pid=%s slate: state=%d pos=%s"
          % (sxlo, sxhi, settle, os.environ.get("DOLPHIN_PID"), st, tuple("%.1f" % p for p in pos0)))

    table = load_existing(out)
    cells = snake(sxlo, sxhi)
    todo = [c for c in cells if c not in table]
    if maxcells:
        todo = todo[:maxcells]
    print("grid %d cells; %d done; %d to dump" % (len(cells), len(cells) - len(todo), len(todo)))

    unstable = []
    t0 = time.time(); done = 0
    for (sx, sy) in todo:
        fields, stable, a1 = dump_cell(h, m, sx, sy, pos0, settle)
        if not stable:                              # re-try with a longer settle before flagging
            fields, stable, a1 = dump_cell(h, m, sx, sy, pos0, settle * 3)
            if not stable:
                unstable.append((sx, sy, a1, fields))
        table[(sx, sy)] = fields
        done += 1
        if done % FLUSH == 0:
            save(table, out)
            if unstable:
                with open(unstable_path, "w") as f:
                    for (usx, usy, ua1, ua2) in unstable:
                        f.write("%d,%d %s vs %s\n" % (usx, usy, ua1, ua2))
            rate = (time.time() - t0) / done
            print("[%s] %d/%d  %.0f ms/cell  ~%.1f min left  unstable=%d"
                  % (os.environ.get("DOLPHIN_PID"), done, len(todo), rate * 1000,
                     rate * (len(todo) - done) / 60, len(unstable)))
    save(table, out)
    _pipe("clearinput")
    print("DONE shard sx=%d..%d: %d cells, %d unstable -> %s"
          % (sxlo, sxhi, len(table), len(unstable), out))
    if unstable:
        print("  UNSTABLE cells (need attention):", unstable[:20])


if __name__ == "__main__":
    main()
