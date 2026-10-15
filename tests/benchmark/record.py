"""Benchmark record schema: one self-contained, reproducible swim-plan result.

A record is the atomic unit of the committed dataset (results.jsonl). It carries
EVERYTHING needed to reproduce the plan and to mine it later:

  provenance  schema_version, name, tier, git_sha, git_dirty, timestamp, env
  recipe      planner (fn name) + params (the COMPLETE kwargs) -> deterministic replay
  outcome     frames, reached, seq (RLE action string -- the reproducible action list)
  stats       plan.result['stats'] (nodes_expanded etc. -- search-work metrics)
  derived     dips, pumps, chg/neu/ess counts, peak_v, end_v, expansions_per_frame, wall_s
  gate        known_best, delta, verdict (PASS/REGRESS/IMPROVED/BASELINE)
  dtm         live clean-DTM verification block (null until verified) -- see verify_dtm.py

Because the planner has no RNG, params fully determine the plan on a given code rev;
`reproduce()` replays and checks. A base truth is a record whose `dtm.verified` is True
(the sim's predicted end-state matched Dolphin at movie exhaustion).

Pure-offline except git/env probing. 3.7-compatible.
"""
import json
import os
import platform
import subprocess
import sys

# >>> repo bootstrap: locate tww_sim/ package
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, 'pyproject.toml')):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tww_sim.swim import plan, optimize

SCHEMA_VERSION = 3
RESULTS_PATH = os.path.join(_HERE, "results.jsonl")


# --- provenance ----------------------------------------------------------------------
def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=_ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def git_sha():
    return _git("rev-parse", "HEAD")


def git_dirty():
    out = _git("status", "--porcelain")
    return bool(out) if out is not None else None


def env_info():
    return {"python": platform.python_version(), "platform": platform.platform()}


# --- derived features (replay the plan on the planner's own seed) ---------------------
def _seed_from_params(params):
    """Rebuild the exact DP seed the planner used, so derived physics (peak_v) are faithful
    to the cold-start scramble. Mirrors plan.plan_min_frames' seed construction."""
    return plan._seed_for(
        params.get('v', -1630.0), params.get('anim', 18.148), params.get('air', 900),
        params.get('entry_tax', not params.get('cold_start', False)),
        params.get('cold_start', False), params.get('cold_mrate'))


def _dips(actions):
    """A dip/pump = a 'neu' immediately followed by a non-neu re-entry (neutral tap then
    resume swim). At cruise these are the drag-free neutral dips; in build they're pumps."""
    return sum(1 for i in range(len(actions) - 1)
               if actions[i] == 'neu' and actions[i + 1] != 'neu')


def derived_features(params, actions, end_state):
    d = {
        'n_actions': len(actions),
        'chg': actions.count('chg'),
        'neu': actions.count('neu'),
        'ess': sum(1 for a in actions if a not in ('chg', 'neu')),
        'dips': _dips(actions),
        'end_v': (abs(end_state.v) if end_state is not None else None),
        'peak_v': None,
        # AIR FEASIBILITY: the sim doesn't enforce air=0, so a long plan can "reach" with end_air
        # NEGATIVE = physically impossible (Link surfaces at air 0). end_air<0 => bogus. See README.
        'end_air': (end_state.air if end_state is not None else None),
        'air_feasible': (None if end_state is None else end_state.air >= 0),
        # SUB-FRAME arrival margin (min-frames optimizer signal): where in the final frame dest was
        # crossed. arrival_subframe ~0 = barely earned the last frame (shave candidate). See README.
        'overshoot': None,        # reached - dest (units past the target on the final frame)
        'last_step': None,        # |displacement| on the final frame
        'arrival_subframe': None, # fraction of the final frame at which -x reached dest, in [0,1]
    }
    try:
        seed = _seed_from_params(params)
        states = plan._trajectory(seed, actions)
        d['peak_v'] = max(abs(s.v) for s in states)
        dest = params.get('dest')
        if actions and dest is not None:
            prog = [-s.x for s in states]        # forward progress after each frame (prog[0]=seed)
            reached = prog[-1]
            before_last = prog[-2]
            last_step = reached - before_last
            d['overshoot'] = reached - dest
            d['last_step'] = last_step
            if last_step > 0:
                # linear-in-frame crossing fraction (physics is ~constant-v within a frame)
                d['arrival_subframe'] = max(0.0, min(1.0, (dest - before_last) / last_step))
    except Exception as e:
        d['peak_v_error'] = f"{type(e).__name__}: {e}"
    if actions:
        d['expansions_per_action'] = None   # filled by build_record once stats known
    return d


# --- gate --------------------------------------------------------------------------
def verdict(frames, known_best):
    if known_best is None:
        return 'BASELINE'
    if frames is None:
        return 'NOREACH'
    if frames < known_best:
        return 'IMPROVED'
    if frames > known_best:
        return 'REGRESS'
    return 'PASS'


# --- build / io --------------------------------------------------------------------
def build_record(case, result, wall_s, timestamp):
    """Assemble a record dict from a case def + a planner result dict.

    timestamp: ISO string supplied by the caller (kept out of here so the module has no
    hidden wall-clock dependency)."""
    params = case['params']
    actions = result.get('actions') or []
    stats = result.get('stats', {})
    frames = result.get('frames')
    kb = case.get('known_best')
    der = derived_features(params, actions, result.get('end_state'))
    if frames:
        der['expansions_per_action'] = round(stats.get('nodes_expanded', 0) / frames, 1)
    return {
        'schema_version': SCHEMA_VERSION,
        'name': case['name'],
        'tier': case['tier'],
        'timestamp': timestamp,
        'git_sha': git_sha(),
        'git_dirty': git_dirty(),
        'env': env_info(),
        'planner': case['planner'],
        'params': params,
        'frames': frames,
        'reached': result.get('reached'),
        'seq': optimize.seq_string(actions) if actions else '',
        'stats': stats,
        'derived': der,
        'known_best': kb,
        'delta': (None if (frames is None or kb is None) else frames - kb),
        'verdict': verdict(frames, kb),
        'wall_s': round(wall_s, 2),
        'dtm': None,                    # populated by verify_dtm.verify_record
    }


def run_case(case):
    """Run a case's planner and return (result_dict, wall_s). Uses time only here."""
    import time
    fn = getattr(plan, case['planner'])
    t0 = time.time()
    result = fn(**case['params'])
    return result, time.time() - t0


def reproduce(record):
    """Replay a record's recipe on the CURRENT code. Returns dict with match booleans.

    A frames/seq mismatch means either the code changed the plan (check git_sha) or the
    record predates a determinism fix -- a signal, surfaced, never silently reconciled."""
    fn = getattr(plan, record['planner'])
    result = fn(**record['params'])
    seq = optimize.seq_string(result.get('actions') or [])
    return {
        'name': record['name'],
        'frames_match': result.get('frames') == record['frames'],
        'seq_match': seq == record['seq'],
        'frames_now': result.get('frames'),
        'frames_rec': record['frames'],
        'git_sha_rec': record.get('git_sha'),
        'git_sha_now': git_sha(),
    }


def append_record(rec, path=RESULTS_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def load_records(path=RESULTS_PATH):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
