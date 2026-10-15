"""omega_full_redump.py - regenerate omega_table_full.csv via the RAW-BYTE advancewith path.

The shipped omega_table_full.csv (csx 0..15 x csy 0..255 = 4096 cells) was dumped via the
in-Dolphin controller.set_gc_buttons (CALIBRATED) path with a 1-frame-latency attribution that
recorded the negative-saturation omega as -546 where the advancewith (raw-byte) path the
swim/tests/DTM actually use gives -547 (verified live: 1816 cells off by +1). This re-dumps the
SAME grid through advancewith so it matches the live omega the swim consumes.

METHOD (gold per-cell, resumable):
  - omega in the negative-saturation band is STATE-DEPENDENT by +/-1: a continuous neutral-settle
    sweep drifts -547 -> -546 as cam_target/cam_yaw accumulate. The value the SWIM actually
    experiences (and the fine omega_table.csv captured) is the one measured from the slot-10 REST
    state. So we loadstate per cell (like omega_capture.capture) -> gold-accurate, matches live.
  - per cell: load slot 10, one neutral settle frame, set swim state (air=900, speed=-700), hold
    the C-stick HOLD frames, read the steady d(cam_target)/frame (the exact omega from rest).
  - ~2.8 s/cell (loadstate dominated) -> 4096 cells ~ 3.2 h; run as resumable foreground chunks
    (maxcells=N). Flush every FLUSH cells so a killed run resumes (skips cells already in the CSV).

Usage:  python omega_full_redump.py [maxcells=N] [hold=11]
Re-run until it prints DONE (writes <repo>/superswim/tables/omega_table_full.csv).
"""
import os, sys, csv, struct, time

import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm

OUT = os.path.join(_rb, "tww_sim", "core", "tables", "omega_table_full.csv")
CSX_VALS = list(range(16))          # the shipped grid's csx axis (0..15)
CSY_VALS = list(range(256))
# parallel sharding: each Dolphin instance (DOLPHIN_PID) dumps a csx range to its own out= file;
# merge the shards into omega_table_full.csv afterward (merge_shards()).
FLUSH = 128


def _d16(a, b):
    x = (a - b) & 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _retry(fn, *a, **k):
    """Retry a dolphin_mem pipe/memory call through transient failures: the per-instance control
    pipe is briefly torn down during a savestate-load (CreateFileW error 2), and the camera pointer
    chain can momentarily read null right after a load. Retries with a short backoff."""
    import time as _t
    last = None
    for i in range(40):
        try:
            return fn(*a, **k)
        except (OSError, ValueError) as e:
            last = e
            _t.sleep(0.1)
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


def load_existing(path):
    t = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            t[(int(r["csx"]), int(r["csy"]))] = int(r["omega"])
    return t


def save(t, path):
    with open(path, "w", newline="") as f:
        f.write("csx,csy,omega\n")
        for (csx, csy), o in sorted(t.items()):
            f.write("%d,%d,%d\n" % (csx, csy, o))


def snake_cells(csxlo=0, csxhi=15):
    out = []
    for i, csx in enumerate(c for c in CSX_VALS if csxlo <= c <= csxhi):
        ys = CSY_VALS if (i % 2 == 0) else CSY_VALS[::-1]
        for csy in ys:
            out.append((csx, csy))
    return out


def merge_shards(shard_paths):
    """Merge shard CSVs into OUT (later shards win on overlap; all should be disjoint csx ranges)."""
    merged = {}
    for p in shard_paths:
        merged.update(load_existing(p))
    save(merged, OUT)
    print("merged %d cells from %d shards -> %s" % (len(merged), len(shard_paths), OUT))


def main():
    opts = dict(t.split("=") for t in sys.argv[1:] if "=" in t)
    if "merge" in sys.argv:
        merge_shards([opts[k] for k in sorted(opts) if k.startswith("shard")])
        return
    maxcells = int(opts.get("maxcells", "0"))
    hold = int(opts.get("hold", "11"))
    out = opts.get("out", OUT)
    csxlo = int(opts.get("csxlo", "0")); csxhi = int(opts.get("csxhi", "15"))

    table = load_existing(out)
    cells = snake_cells(csxlo, csxhi)
    todo = [c for c in cells if c not in table]
    print("full grid %d cells; %d already done; %d to dump (hold=%d)"
          % (len(cells), len(cells) - len(todo), len(todo), hold))
    if not todo:
        print("DONE: all %d cells present -> %s" % (len(table), out)); return

    if maxcells:
        todo = todo[:maxcells]

    t0 = time.time(); done = 0
    for (csx, csy) in todo:
        # gold per-cell: fresh loadstate so omega is measured from the slot-10 rest state, all
        # pipe/mem calls via _retry (concurrent instances briefly drop the pipe during a load).
        _pipe("savestate", {"action": "load", "slot": 10}); h, m = _retry(dm.attach)
        _pipe("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
        h, m = _retry(dm.attach)
        _retry(wnamed, h, m, "air", 900); _retry(wnamed, h, m, "potential_speed", -700.0)
        prev = _retry(dm.read_named, h, m, "cam_target"); last = 0
        for _ in range(hold):
            _pipe("advancewith", {"stickX": 128, "stickY": 128,
                                  "substickX": csx, "substickY": csy, "frames": 1})
            cur = _retry(dm.read_named, h, m, "cam_target")
            last = _d16(cur, prev); prev = cur
        table[(csx, csy)] = last
        done += 1
        if done % FLUSH == 0:
            save(table, out)
            rate = (time.time() - t0) / done
            print("[redump] %d/%d  (%.0f ms/cell, ~%.1f min left)"
                  % (done, len(todo), rate * 1000, rate * (len(todo) - done) / 60))
    save(table, out)
    dm.control_pipe_quiet("clearinput")
    remaining = [c for c in cells if c not in table]
    if remaining:
        print("flushed %d; %d cells still missing - re-run to continue" % (done, len(remaining)))
    else:
        print("DONE: all %d cells -> %s (%.0f ms/cell)"
              % (len(table), out, (time.time() - t0) / max(done, 1) * 1000))


if __name__ == "__main__":
    main()
