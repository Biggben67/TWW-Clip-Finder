"""Superswim adapter over the generic DTM writer (`tools/dtm_make.py`).

The cadence-correct DTM authoring (header clone, calibration, poll layout) lives in
`tools/dtm_make.build_dtm_from_sticks`. This module only translates the superswim action-list
seq vocabulary (ess/neu/chg) into the per-frame stick states that writer consumes, via
`run_tests.expand` + `run_tests.acts_to_seq`.

Usage: python make_dtm.py seq=cruise_pump300k_seq.txt [out=...] [template=cruise_pump300k_rec.dtm]
       [polls=4] [seed=1]
"""
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
from tww_sim.swim import actions as A
import dtm_make as M


def build_dtm(seqfile, out, template='cruise_pump300k_rec.dtm', polls=4, seed=1):
    """Author a clean DTM from a superswim action-list seq file. Returns an info dict."""
    acts = A.expand(open(seqfile).read())
    sticks = A.acts_to_seq(acts)
    info = M.build_dtm_from_sticks(sticks, out, template, polls, seed)
    info["acts"] = len(acts)
    return info


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    seqfile = o.get('seq', 'cruise_pump300k_seq.txt')
    template = o.get('template', 'cruise_pump300k_rec.dtm')
    out = o.get('out', seqfile.rsplit('.', 1)[0] + '_clean.dtm')
    polls = int(o.get('polls', '4'))
    seed = int(o.get('seed', '1'))

    info = build_dtm(seqfile, out, template, polls, seed)
    print(f"{seqfile}: {info['acts']} acts -> {out}")
    print(f"  {info['polls']} polls ({seed} seed + {info['frames']}x{polls}), "
          f"{info['rows']} rows, {info['bytes']} bytes")
    print(f"NEXT: copy {template}.sav -> {out}.sav, then "
          f"python ../tools/dtm_play.py dtm={out} game=<iso>")


if __name__ == "__main__":
    main()
