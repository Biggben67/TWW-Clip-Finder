"""Read the committed dataset (results.jsonl) and print pattern-hunting rollups.

Dependency-free (no pandas). The dataset accumulates across sessions and code revs, so the
interesting questions are cross-record: how did search work evolve per case across git revs,
how do dips/frames/frontier scale with distance, which records are DTM-verified base truths.

    python tests/benchmark/analyze.py                 # summary of the latest record per case
    python tests/benchmark/analyze.py history=cold_pump_50k   # a case across all git revs
    python tests/benchmark/analyze.py verified=1      # only DTM-verified base truths
    python tests/benchmark/analyze.py reproduce=1     # replay latest records, check determinism
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, 'pyproject.toml')):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests.benchmark import record as R


def _dtm_flag(r):
    d = r.get('dtm')
    if not d:
        return '  '
    return 'DT' if d.get('verified') else 'dX'


def _latest_per_name(records):
    latest = {}
    for r in records:
        latest[r['name']] = r         # file is append-order = chronological
    return [latest[n] for n in sorted(latest)]


def summary(records):
    rows = _latest_per_name(records)
    print(f"=== latest record per case ({len(rows)} cases, {len(records)} total records) ===")
    print("  vf name                 frames  dips   nodes    exp/act  peak_v   end_v  wall")
    for r in rows:
        s, d = r['stats'], r['derived']
        print(f"  {_dtm_flag(r)} {r['name']:<20} {str(r['frames']):>6}  "
              f"{str(d.get('dips')):>3}  {s.get('nodes_expanded', 0):>9,}  "
              f"{str(d.get('expansions_per_action')):>7}  "
              f"{_f(d.get('peak_v')):>6}  {_f(d.get('end_v')):>6}  {r['wall_s']:>6.1f}s")
    print("\n  vf: DT=DTM base truth, dX=DTM failed, blank=sim-only (unverified)")


def _f(x):
    return f"{x:.0f}" if isinstance(x, (int, float)) else "-"


def history(records, name):
    rows = [r for r in records if r['name'] == name]
    if not rows:
        print(f"no records for {name}")
        return
    print(f"=== {name}: {len(rows)} record(s) across revs ===")
    print("  timestamp            git      frames  nodes      fmax   cap  vf")
    for r in rows:
        s = r['stats']
        print(f"  {r['timestamp']:<20} {(r.get('git_sha') or '?')[:7]}  "
              f"{str(r['frames']):>6}  {s.get('nodes_expanded', 0):>9,}  "
              f"{s.get('frontier_max', 0):>5}  {s.get('capped_layers', 0):>4}  {_dtm_flag(r)}")


def reproduce_check(records):
    rows = _latest_per_name(records)
    print(f"=== reproduce latest {len(rows)} record(s) on current code ===")
    bad = 0
    for r in rows:
        if r['frames'] is None:
            continue
        res = R.reproduce(r)
        ok = res['frames_match'] and res['seq_match']
        if not ok:
            bad += 1
        print(f"  {'ok' if ok else 'XX'} {r['name']:<20} "
              f"frames {res['frames_rec']}->{res['frames_now']} "
              f"seq_match={res['seq_match']}")
    print(f"\n{bad} mismatch(es)" + ("" if bad == 0 else " -- code changed the plan or record predates a fix"))


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    records = R.load_records()
    if not records:
        print("no records yet -- run run_benchmark.py")
        return
    if o.get('verified', '0') not in ('0', 'false', 'no'):
        records = [r for r in records if (r.get('dtm') or {}).get('verified')]
    if 'history' in o:
        history(records, o['history'])
    elif o.get('reproduce', '0') not in ('0', 'false', 'no'):
        reproduce_check(records)
    else:
        summary(records)


if __name__ == "__main__":
    main()
