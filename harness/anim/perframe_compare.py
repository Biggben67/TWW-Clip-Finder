"""Per-frame sim-vs-live comparison for a land tech, using a recorded live capture CSV.

The FAST first move when a land case is RED: before reaching for a live per-joint anmMtx
decomposition, seed a LandState from a `harness/capture/*.csv` live capture's frame-0 row, step the
exact input seq, and print the per-frame bit-diff of pos_x / pos_z / travel / speedF vs the CSV. This
localizes the divergence to a frame + a quantity (is `travel` off? `speedF`? just the accumulation?)
with ZERO Dolphin time -- the CSV already holds the live per-frame truth.

Proven this way (2026-07-05): `walk_y171` = an f64 HIO frame-rate constant (speedF), NOT a jnt0 Hermite;
`ebs`/`waitturn` = the worldBase inverse was `R^T` instead of the retail PSMTXInverse (cofactor + `fres`),
so the foot toe drifted <=127 ULP at non-axis facings (bit-exact at axis facings only). All land techs
are now 0 ULP; this tool is the fast first move if a NEW case goes RED. See
knowledge/history/resolved-bugs.md and the `land-bitperfect-frontier` Claude memory.

Usage:  python harness/anim/perframe_compare.py <case>
        cases: ebs | waitturn   (add more by extending CASES below)
"""
import csv
import os
import struct
import sys

# >>> repo bootstrap: find repo root (marker pyproject.toml) so this runs uninstalled from the root.
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "pyproject.toml")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)
# <<< repo bootstrap

from tww_sim.land.land import LandState  # noqa: E402

CAP = os.path.join(_d, "harness", "capture")

# case -> (capture CSV, input seq as (stickX, stickY, buttons, triggerL) per frame). The seqs mirror
# tests/dolphin/run_land_tests.py (seq_ebs / seq_waitturn); keep them in sync if those change.
CASES = {
    "ebs":      (os.path.join(CAP, "atn_ebs.csv"),
                 [(128, 255, 0, 0)] * 10 + [(128, 0, 0x40, 255)] + [(128, 110, 0, 0)] * 30),
    "waitturn": (os.path.join(CAP, "explore_waitturn.csv"),
                 [(128, 0, 0, 0)] * 20),
}


def bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def run(case):
    csv_path, seq = CASES[case]
    rows = list(csv.DictReader(open(csv_path)))
    seed = rows[0]
    s = LandState(pos_z=float(seed['pos_z']), facing=int(seed['travel_angle']),
                  travel=int(seed['travel_angle']), csangle=int(seed['csangle']),
                  state=int(seed['link_state']), nspeed=float(seed['potential_speed']),
                  idle_frame=float(seed['anim_frame']))
    print(f"# {case}: sim vs {os.path.basename(csv_path)}  (d* = sim_bits - live_bits, in ULP)")
    print(f"{'f':>3} {'st':>3} {'dpx':>5} {'dpz':>4} {'dspF':>5}  {'strav':>6} {'ltrav':>6}  "
          f"{'sim_pz':>10} {'live_pz':>10}")
    for i, (sx, sy, b, tl) in enumerate(seq):
        s.step(sx, sy, buttons=b, triggerL=tl)
        if i + 1 >= len(rows):
            break
        r = rows[i + 1]
        dpx = bits(s.pos_x) - bits(float(r['pos_x']))
        dpz = bits(s.pos_z) - bits(float(r['pos_z']))
        dspf = bits(s.speedF) - bits(float(r['true_speed']))
        flag = '' if (dpx == 0 and dpz == 0) else '  <<<'
        print(f"{i + 1:>3} {s.state:>3} {dpx:>5} {dpz:>4} {dspf:>5}  {int(s.travel):>6} "
              f"{int(r['travel_angle']):>6}  {bits(s.pos_z):>10x} {bits(float(r['pos_z'])):>10x}{flag}")


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "ebs"
    if case not in CASES:
        sys.exit(f"unknown case {case!r}; known: {', '.join(CASES)}")
    run(case)
