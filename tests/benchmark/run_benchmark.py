"""Planner-quality + search-efficiency benchmark runner.

Re-plans a set of cases (cases.py) from the cold anchor, APPENDS a fully-reproducible
record per plan to the committed dataset (results.jsonl), prints a table, and (optionally)
gates on the known-best frame counts. This is the regression signal the fast pytest suite
lacks: pytest/golden REPLAY fixed seqs, so a planner change that emits a WORSE plan is
invisible to them; this RE-RUNS the planner and checks frames + search work.

Records are always appended (bigger dataset = more to mine later, per project direction),
even for cases with no known_best. Verdicts:
  PASS      frames == known_best
  IMPROVED  frames <  known_best  (update cases.py known_best -- a new base truth, once DTM-verified)
  REGRESS   frames >  known_best  (a planner regression; nonzero exit under assert=1)
  BASELINE  no known_best yet     (recorded; establishes the number)

Base truth: a record is only a base truth once DTM-verified (verify_dtm.py). This runner
records the SIM prediction; run verify_dtm.py afterward to promote to base truth.

Usage:
    python tests/benchmark/run_benchmark.py                    # smoke tier (fast)
    python tests/benchmark/run_benchmark.py tier=full          # the slow real dests (200k ~8min)
    python tests/benchmark/run_benchmark.py tier=smoke,full    # everything
    python tests/benchmark/run_benchmark.py name=cold_pump_50k # a single case
    python tests/benchmark/run_benchmark.py assert=1           # nonzero exit on any REGRESS
    python tests/benchmark/run_benchmark.py save=1             # also write _generated/<name>_seq.txt

Tiers are runtime buckets (which cases run), NOT recording differences -- every run appends
the same rich record. See cases.py for the tier assignment and known-best table.
"""
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, 'pyproject.toml')):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tww_sim.swim import optimize
from tests.benchmark import cases as C
from tests.benchmark import record as R

_GEN = os.path.join(_ROOT, "_generated", "benchmark")

_VERDICT_MARK = {'PASS': 'ok', 'IMPROVED': '**', 'REGRESS': 'XX',
                 'BASELINE': '--', 'NOREACH': '!!'}


def _save_seq(rec):
    os.makedirs(_GEN, exist_ok=True)
    path = os.path.join(_GEN, rec['name'] + "_seq.txt")
    es_lines = ""
    d = rec['derived']
    with open(path, 'w', encoding='utf-8') as f:
        f.write(rec['seq'] + "\n")
        f.write(f"# {rec['name']}: {rec['frames']} frames, reached {rec['reached']:.0f}\n")
        f.write(f"# end_v={d.get('end_v')} peak_v={d.get('peak_v')} "
                f"dips={d.get('dips')} chg={d.get('chg')} neu={d.get('neu')}\n")
        f.write(f"# params={rec['params']}\n")
    return path


def _print_row(rec):
    s = rec['stats']
    d = rec['derived']
    kb = rec['known_best']
    mark = _VERDICT_MARK.get(rec['verdict'], '??')
    kb_str = str(kb) if kb is not None else '   -'
    dl = rec['delta']
    dl_str = f"{dl:+d}" if dl is not None else '  '
    print(f"  [{mark}] {rec['name']:<20} {str(rec['frames']):>5} "
          f"(kb {kb_str:>4} {dl_str:>3})  dips={str(d.get('dips')):>3}  "
          f"nodes={s.get('nodes_expanded', 0):>9,}  "
          f"fmax={s.get('frontier_max', 0):>5}  cap={s.get('capped_layers', 0):>4}  "
          f"{rec['wall_s']:>6.1f}s")


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    do_assert = o.get('assert', '0') not in ('0', 'false', 'no')
    do_save = o.get('save', '0') not in ('0', 'false', 'no')

    if 'name' in o:
        sel = [C.CASES_BY_NAME[n] for n in o['name'].split(',') if n in C.CASES_BY_NAME]
        missing = [n for n in o['name'].split(',') if n not in C.CASES_BY_NAME]
        if missing:
            print(f"unknown case(s): {missing}; known: {list(C.CASES_BY_NAME)}")
    else:
        tiers = tuple(o.get('tier', 'smoke').split(','))
        bad = [t for t in tiers if t not in C.TIERS]
        if bad:
            print(f"unknown tier(s) {bad}; known: {C.TIERS}")
            sys.exit(2)
        sel = C.cases_for(tiers)

    if not sel:
        print("no cases selected")
        sys.exit(2)

    print(f"=== benchmark: {len(sel)} case(s) | git {R.git_sha() or '?'}"
          f"{' (dirty)' if R.git_dirty() else ''} ===")
    print("  [mk] name                 frames (kb  d)  dips        nodes  fmax   cap    wall")

    regressed = []
    for case in sel:
        result, wall = R.run_case(case)
        ts = datetime.datetime.now().isoformat(timespec='seconds')
        rec = R.build_record(case, result, wall, ts)
        R.append_record(rec)
        if do_save and rec['frames'] is not None:
            _save_seq(rec)
        _print_row(rec)
        if rec['verdict'] == 'REGRESS':
            regressed.append(rec)

    print(f"\nappended {len(sel)} record(s) -> {os.path.relpath(R.RESULTS_PATH, _ROOT)}")
    if regressed:
        print(f"REGRESSIONS: {', '.join(r['name'] for r in regressed)} "
              f"(frames worse than known_best)")
    print("next: DTM-verify to promote to base truth -> python tests/benchmark/verify_dtm.py")
    if do_assert and regressed:
        sys.exit(1)


if __name__ == "__main__":
    main()
