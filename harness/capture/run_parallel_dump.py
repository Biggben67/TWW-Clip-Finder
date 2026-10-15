"""run_parallel_dump.py — orchestrate the full 65536-cell stick-grid dump across N Dolphin
instances (mirrors the omega C-stick parallel method: shard by axis range, PID-targeted).

Kills all Dolphin, launches N fresh instances, boots the iso in each, then spawns one
stick_grid_redump.py shard per instance (disjoint sx ranges) and merges the shards.

Usage:
    python run_parallel_dump.py [instances=4] [settle=4] [maxcells=0] [nokill=0]
maxcells>0 dumps only the first maxcells of EACH shard (for a quick launch/boot smoke test).
"""
import os, sys, time, subprocess, json

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm

EXE = os.environ.get("DOLPHIN_EXE", os.path.join(
    os.path.dirname(_rb), "Dolphin-Zelda-TAS-Edition", "Binary", "x64", "Release", "Dolphin.exe"))
ISO = os.environ.get("TWW_ISO", "").replace("\\", "/")   # set TWW_ISO for your machine
if not ISO:
    raise SystemExit("set TWW_ISO to your Wind Waker image (see dolphin.local.example.json)")
GEN = os.path.join(_rb, "_generated")
CAP = os.path.join(_rb, "harness", "capture")


def pipe_ok(pid):
    try:
        dm._PID_OVERRIDE = pid
        return json.loads(dm.control_pipe_quiet("status")).get("ok", False)
    except Exception:
        return False
    finally:
        dm._PID_OVERRIDE = None


def launch_instances(n):
    """Launch n Dolphins one at a time; return the list of pipe-responsive PIDs."""
    pids = []
    for i in range(n):
        before = set(dm.list_dolphin_pids())
        subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
        # wait for a NEW pipe-responsive Dolphin PID to appear
        t0 = time.time(); new = None
        while time.time() - t0 < 40:
            cand = [p for p in dm.list_dolphin_pids() if p not in before and p not in pids]
            new = next((p for p in cand if pipe_ok(p)), None)
            if new:
                break
            time.sleep(1.0)
        if not new:
            raise SystemExit(f"instance {i} did not come up with a live pipe")
        pids.append(new)
        print(f"  instance {i}: pid={new}")
    return pids


def boot(pid):
    dm._PID_OVERRIDE = pid
    try:
        dm.control_pipe_quiet("boot", {"path": ISO})
        t0 = time.time()
        while time.time() - t0 < 120:
            if '"state":"running"' in dm.control_pipe_quiet("status"):
                return True
            time.sleep(1.0)
        return False
    finally:
        dm._PID_OVERRIDE = None


def shard_ranges(n):
    """Split sx 0..255 into n contiguous ranges."""
    edges = [round(i * 256 / n) for i in range(n + 1)]
    return [(edges[i], edges[i + 1] - 1) for i in range(n)]


# kind -> (dumper script, shard-arg prefix, shard-file prefix, merged file, extra pass-through keys)
KINDS = {
    "stick": ("stick_grid_redump.py", "sx", "stick_shard", "stick_angle_full.csv", ["settle"]),
    "omega": ("omega_grid_redump.py", "csx", "omega_shard", "omega_grid_full.csv",
              ["settle", "method", "slot"]),
}


def main():
    o = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    n = int(o.get("instances", "4"))
    maxcells = int(o.get("maxcells", "0"))
    kind = o.get("kind", "stick")
    dumper_name, axis, shard_prefix, merged_name, passthru = KINDS[kind]
    dumper = os.path.join(CAP, dumper_name)
    extra = [f"{k}={o[k]}" for k in passthru if k in o]
    os.makedirs(GEN, exist_ok=True)

    if o.get("nokill", "0") not in ("1", "true"):
        subprocess.run(["taskkill", "/F", "/IM", "Dolphin.exe"], capture_output=True)
        time.sleep(2.0)

    print(f"launching {n} Dolphin instances ...")
    pids = launch_instances(n)
    print(f"booting {ISO} in each ...")
    for pid in pids:
        if not boot(pid):
            raise SystemExit(f"pid {pid} never reached running")
        print(f"  pid {pid}: running")

    ranges = shard_ranges(n)
    procs = []
    for pid, (lo, hi) in zip(pids, ranges):
        out = os.path.join(GEN, f"{shard_prefix}_{lo}_{hi}.csv")
        args = [sys.executable, dumper, f"{axis}lo={lo}", f"{axis}hi={hi}", f"out={out}",
                f"pid={pid}"] + extra
        if maxcells:
            args.append(f"maxcells={maxcells}")
        logf = open(os.path.join(GEN, f"{shard_prefix}_{lo}_{hi}.log"), "w")
        print(f"  shard {axis} {lo}..{hi} -> pid {pid} ({os.path.basename(out)})")
        procs.append((subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT), out))

    print(f"dumping (see _generated/{shard_prefix}_*.log for progress) ...")
    rc = [p.wait() for (p, _) in procs]
    print("shard exit codes:", rc)

    shards = [out for (_, out) in procs]
    # merge to _generated (RAW dump); copy into superswim/tables/ only after the integrity check passes.
    merged = os.path.join(GEN, merged_name)
    subprocess.run([sys.executable, dumper, "merge", f"out={merged}"]
                   + [f"shard{i}={s}" for i, s in enumerate(shards)])
    print("MERGED ->", merged)


if __name__ == "__main__":
    main()
