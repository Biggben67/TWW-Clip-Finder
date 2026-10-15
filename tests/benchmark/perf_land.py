#!/usr/bin/env python3
"""perf_land.py - PERFORMANCE benchmark for the land-walk sim (tww_sim.land.LandState).

Unlike run_benchmark.py (planner *quality*), this measures raw *throughput* of the per-frame
forward model: LandState.step with the anim engine active (the real hot path -- the ported J3D
foot-FK / quaternion / Hermite chain runs every MOVE/ATN/turn frame). It is the signal for the
Cythonization / micro-opt work.

It also carries a built-in CORRECTNESS FINGERPRINT: the exact f32 byte-pattern checksum of the
whole stepped trajectory (pos_x, pos_z, speedF, nspeed). Any optimization that is not bit-exact
changes the fingerprint and the benchmark fails loudly -- a fast local guard to run alongside the
0-ULP pytest golden suite.

Usage:
    python tests/benchmark/perf_land.py                # time the default workload
    python tests/benchmark/perf_land.py reps=20        # more timing reps (tighter min)
    python tests/benchmark/perf_land.py frames=4000     # longer trajectory
    python tests/benchmark/perf_land.py profile=1       # cProfile the hot path, print top 30
    python tests/benchmark/perf_land.py fingerprint=1   # just print the correctness fingerprint
"""
import os
import struct
import sys
import time

# >>> repo bootstrap
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, 'pyproject.toml')):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# <<< repo bootstrap

from tww_sim.land.land import LandState
from tww_sim.core.anim.foot_speedf import FootSpeedF

SEED_POS_Z = 764.0791015625


def build_workload(frames):
    """A representative land-walk stick stream that exercises the full anim hot path:
    stand->walk accel, sustained cruise (walk<->dash blend), a gentle curve, a hard reversal
    (WAIT_TURN / MOVE_TURN / SLIP procs), a forward roll, then release-to-stop. Repeats to `frames`.
    Returns a list of (sx, sy, buttons, triggerL, csx, csy)."""
    seq = []
    # stand->walk->cruise straight (full up)
    seq += [(128, 255, 0, 0, 128, 128)] * 40
    # gentle curve right (off-axis stick, sustained turn -> continuous travel/facing chase)
    seq += [(190, 245, 0, 0, 128, 128)] * 30
    # cruise straight again
    seq += [(128, 255, 0, 0, 128, 128)] * 20
    # hard reversal (stick flips down -> SLIP / MOVE_TURN at speed)
    seq += [(128, 1, 0, 0, 128, 128)] * 25
    # forward roll (A press while moving) then hold
    seq += [(128, 255, 0x100, 0, 128, 128)] + [(128, 255, 0, 0, 128, 128)] * 25
    # release to a full stop
    seq += [(128, 128, 0, 0, 128, 128)] * 20
    # tile up to the requested length
    out = []
    while len(out) < frames:
        out += seq
    return out[:frames]


def run_trajectory(workload):
    """Step the whole workload from the rest anchor; return the per-frame (pos_x, pos_z, speedF,
    nspeed) tuples. Fresh LandState each call (the anim engine is stateful)."""
    s = LandState(pos_z=SEED_POS_Z, use_anim=True)
    out = []
    step = s.step
    for (sx, sy, btn, tl, cx, cy) in workload:
        step(sx, sy, btn, tl, cx, cy)
        out.append((s.pos_x, s.pos_z, s.speedF, s.nspeed))
    return out


def _f32b(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def fingerprint(traj):
    """A stable, bit-exact fold of the whole trajectory's f32 fields -> a single hex digest.
    Two runs with byte-identical physics produce the same digest; a 1-ULP drift changes it."""
    h = 1469598103934665603  # FNV-1a 64
    for row in traj:
        for v in row:
            b = _f32b(v)
            for shift in (0, 8, 16, 24):
                h = ((h ^ ((b >> shift) & 0xFF)) * 1099511627853) & 0xFFFFFFFFFFFFFFFF
    return "%016x" % h


def time_run(workload, reps):
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        run_trajectory(workload)
        dt = time.perf_counter() - t0
        best = min(best, dt)
    return best


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    frames = int(o.get('frames', 2000))
    reps = int(o.get('reps', 8))

    if not FootSpeedF.available():
        print("WARNING: anim data absent -> falling back to the calibrated stand-in.")
        print("         The hot path is NOT exercised; numbers are not comparable.")

    workload = build_workload(frames)

    if o.get('fingerprint') not in (None, '0', 'false'):
        print(fingerprint(run_trajectory(workload)))
        return

    if o.get('profile') not in (None, '0', 'false'):
        import cProfile
        import pstats
        pr = cProfile.Profile()
        pr.enable()
        run_trajectory(workload)
        pr.disable()
        st = pstats.Stats(pr)
        st.sort_stats('tottime')
        st.print_stats(30)
        return

    # warm the caches once (calc_transform memoizes per-anm), then time.
    fp = fingerprint(run_trajectory(workload))
    best = time_run(workload, reps)

    per_frame_us = best / frames * 1e6
    print(f"=== land-sim perf | {frames} frames x {reps} reps (min) ===")
    print(f"  wall (min):   {best*1e3:8.2f} ms")
    print(f"  per frame:    {per_frame_us:8.3f} us")
    print(f"  throughput:   {frames/best:10.0f} frames/s")
    print(f"  fingerprint:  {fp}")


if __name__ == "__main__":
    main()
