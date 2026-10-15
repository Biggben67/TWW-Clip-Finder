"""Promote benchmark records to BASE TRUTH by clean-DTM verification.

The offline benchmark records what the SIM predicts. A base truth needs the live game to
agree: this module replays a recorded plan's seq through the pipe-artifact-free DTM runner
(harness/dtm/run_dtm.py -- movie playback, not the advanceseq pipe, so bug#2 jitter is
absent) and compares Dolphin's end-state at movie exhaustion to the sim's predicted
end-state. If they match within tolerance, the plan is verified and the record's `dtm`
block is filled with the live endpoint + deltas.

WHY end-state, not frames: frame count is inherent to the seq length (the movie is exactly
that many frames), so it can't disagree. What CAN disagree is the physics -- if the sim
mis-modelled the swim, the live v/anim/air/state (and forward progress) drift from the
prediction. A clean end-state match is the bit-exact claim (per SUPERSWIM bug#2 / the
locked-DTM rule): the recorded plan really does what the sim says, so `frames`/`seq` are
trustworthy base truths.

Requires a configured Dolphin (dolphin.local.json) + the cold anchor + iso. Each plan boots
TWW and plays the movie (~1-3 min/case). Run AFTER run_benchmark.py has recorded plans:

    python tests/benchmark/verify_dtm.py                 # verify every un-verified record
    python tests/benchmark/verify_dtm.py name=cold_pump_50k
    python tests/benchmark/verify_dtm.py tier=smoke tol=0.02

The seed anchor MUST match the plan's seed. These cold-start cases seed the cold anchor
(cruise_cold@twwgz.sav, v0/state54, logged mRate 0.5) -- the same seed cases.py uses. A
plan whose params don't match the anchor is refused (would be a seed mismatch -> the
phantom failures the HARD RULE warns about).
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, 'pyproject.toml')):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_TOOLS = os.path.join(os.path.dirname(_ROOT), 'tools')   # locate tools/ (dolphin_mem, dtm_make)
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.append(_TOOLS)

from tww_sim.swim import actions as A
from tests.benchmark import record as R

# The cold-start anchor these cases seed. Its logged mRate (0.5) must equal the case's
# cold_mrate, else the run is a seed mismatch (see module docstring / HARD RULE).
COLD_ANCHOR = "cruise_cold@twwgz.sav"
COLD_ANCHOR_MRATE = 0.5


def _anchor_for(params):
    """Pick the anchor matching a case's seed, or raise on an unsupported seed.
    Only the cold-start seed is wired today; extend here as anchors are minted."""
    if params.get('cold_start') and abs((params.get('cold_mrate') or -1) - COLD_ANCHOR_MRATE) < 1e-9:
        return COLD_ANCHOR
    raise ValueError(
        f"no anchor for seed (cold_start={params.get('cold_start')}, "
        f"cold_mrate={params.get('cold_mrate')}); would be a seed mismatch -- refusing")


def expected_from_record(rec):
    """Sim-predicted end-state + action list to feed the DTM. REPLAY the recorded seq
    (deterministic, no search) rather than re-running the planner -- re-planning at frontier
    8000 costs minutes per case and is redundant: the seq fully determines the trajectory.
    (facing not modelled by SwimState -> omitted from the compare.)"""
    from tww_sim.swim import actions as _A
    acts = _A.expand(rec['seq'])
    seed = R._seed_from_params(rec['params'])
    es = R.plan._trajectory(seed, acts)[-1]
    return ({'v': es.v, 'anim': es.anim, 'air': es.air, 'state': es.state},
            {'actions': acts})


def verify_record(rec, *, tol=0.02, relaunch=True, verbose=True):
    """Run one record's plan through run_dtm; return a `dtm` block dict (not persisted here).
    Import of run_dtm is deferred so the offline benchmark never needs Dolphin/tools on path."""
    from harness.dtm.run_dtm import run_dtm, sticks_from_actions
    params = rec['params']
    anchor = _anchor_for(params)
    expected, res = expected_from_record(rec)
    sticks = sticks_from_actions(res['actions'])
    end = run_dtm(sticks, expected, anchor=anchor, tol=tol,
                  relaunch_dolphin=relaunch, verbose=verbose)
    cmp = end.get('compare', {})
    return {
        'verified': bool(cmp.get('ok')),
        'anchor': anchor,
        'tol': tol,
        'expected': expected,
        'live': {
            'v': end.get('potential_speed'), 'anim': end.get('anim_frame'),
            'air': end.get('air'), 'state': end.get('link_state'),
            'facing_deg': end.get('facing_deg'), 'net': end.get('net'),
            'ended': end.get('ended'),
        },
        'deltas': {k: cmp[k] for k in ('dv', 'dan') if k in cmp},
        'air_ok': cmp.get('air_ok'), 'state_ok': cmp.get('state_ok'),
        'dolphin_exe': _dolphin_exe(),
        'timestamp': None,   # filled by caller (keeps wall-clock out of this module)
    }


def _dolphin_exe():
    try:
        from harness import dolphin_env as ENV
        return ENV.dolphin_exe()
    except Exception:
        return None


def _rewrite_dtm(records, path=R.RESULTS_PATH):
    """Persist updated `dtm` blocks. results.jsonl is append-only for NEW plans, but a
    verification enriches an EXISTING plan in place -- rewrite the file keyed by
    (name, git_sha, timestamp) so no record is duplicated or lost."""
    with open(path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def _select_targets(records, only_name, only_tier, force):
    """Latest record per name (base truth tracks current code) still needing verification."""
    latest = {}
    for r in records:
        latest[r['name']] = r
    targets = []
    for name, r in latest.items():
        if only_name and name != only_name:
            continue
        if only_tier and r.get('tier') != only_tier:
            continue
        if r.get('frames') is None:
            continue
        if r.get('dtm') and r['dtm'].get('verified') and not force:
            continue
        targets.append(r)
    return targets


def _kill_dolphin():
    import subprocess
    subprocess.run(["taskkill", "/F", "/IM", "Dolphin.exe"], capture_output=True)


def _persist_block(name, block):
    """Attach a dtm block to the latest record for `name` and rewrite results.jsonl."""
    records = R.load_records()
    for r in reversed(records):     # latest wins
        if r['name'] == name:
            r['dtm'] = block
            break
    _rewrite_dtm(records)


def _run_child(name):
    """In-process single-case verify + persist. Invoked as the child of the batch runner
    (child=1) so a hung Dolphin can be killed from the parent by wall-clock timeout -- the
    ONE guard that survives a blocking control-pipe read (no in-process except can)."""
    import datetime
    records = R.load_records()
    tgt = None
    for r in reversed(records):
        if r['name'] == name:
            tgt = r
            break
    if tgt is None:
        print(f"no record for {name}")
        return
    tol = float(dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t).get('tol', '0.02'))
    xfail = _is_xfail_live(name)
    print(f"[child] verifying {name} ({tgt['frames']} fr){' [xfail_live]' if xfail else ''} ...")
    try:
        # BaseException: run_dtm raises SystemExit on boot failure -- don't let it escape unlogged.
        block = verify_record(tgt, tol=tol, relaunch=True)
    except BaseException as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        block = {'verified': False, 'error': f"{type(e).__name__}: {e}"}
    block['timestamp'] = datetime.datetime.now().isoformat(timespec='seconds')
    block['xfail_live'] = xfail
    _persist_block(name, block)
    print(f"  -> {_status_label(block.get('verified'), xfail)}")


def _is_xfail_live(name):
    """A case flagged as a known live desync (cases.py) -- an EXPECTED DTM failure, tracked
    until fixed. Looked up from the case def (source of truth), not the older record."""
    from tests.benchmark import cases as C
    c = C.CASES_BY_NAME.get(name)
    return bool(c and c.get('xfail_live'))


def _status_label(verified, xfail):
    if xfail:
        # XPASS = the known desync now reproduces live -> the bug is fixed, clear the flag.
        return ("XPASS -- now verifies! clear xfail_live in cases.py + set known_best"
                if verified else "XFAIL (expected live desync)")
    return 'VERIFIED' if verified else 'NOT verified'


def main():
    import datetime
    import subprocess
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)

    if o.get('child') not in (None, '0', 'false', 'no'):
        _run_child(o['child'])           # child=<name>: do the actual verification in-process
        return

    tol = o.get('tol', '0.02')
    per_timeout = int(o.get('timeout', '300'))   # per-case wall-clock guard (boots seen up to ~123s)
    records = R.load_records()
    if not records:
        print("no records in results.jsonl -- run run_benchmark.py first")
        return
    targets = _select_targets(records, o.get('name'), o.get('tier'),
                              o.get('force', '0') not in ('0', 'false', 'no'))
    if not targets:
        print("nothing to verify (all target records already verified; use force=1 to redo)")
        return

    print(f"=== DTM-verifying {len(targets)} record(s), tol={tol}, "
          f"per-case timeout {per_timeout}s ===")
    # Each case in a FRESH child process with a wall-clock timeout: the only guard that survives a
    # hung Dolphin (blocking pipe read no in-process except can break). See README / _run_child.
    for i, r in enumerate(targets):
        name = r['name']
        print(f"\n[{i+1}/{len(targets)}] {name} ({r['frames']} fr) ...", flush=True)
        _kill_dolphin()
        cmd = [sys.executable, "-u", os.path.abspath(__file__), f"child={name}", f"tol={tol}"]
        try:
            subprocess.run(cmd, timeout=per_timeout)
        except subprocess.TimeoutExpired:
            _kill_dolphin()
            _persist_block(name, {
                'verified': False,
                'error': f"timeout after {per_timeout}s (Dolphin hang/slow boot)",
                'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
            })
            print(f"  -> TIMEOUT after {per_timeout}s (killed; recorded, continuing)")
    _kill_dolphin()

    records = R.load_records()
    verified = {r['name']: (r.get('dtm') or {}).get('verified') for r in records}
    n_ok = sum(1 for r in targets if verified.get(r['name']))
    print(f"\n{n_ok}/{len(targets)} verified as base truth. results.jsonl updated.")
    # xfail_live cases are EXPECTED to fail -> don't report them as problems; but a PASS is news.
    xpass = [r['name'] for r in targets if verified.get(r['name']) and _is_xfail_live(r['name'])]
    real_fail = [r['name'] for r in targets
                 if not verified.get(r['name']) and not _is_xfail_live(r['name'])]
    xfail = [r['name'] for r in targets
             if not verified.get(r['name']) and _is_xfail_live(r['name'])]
    if xfail:
        print(f"xfail_live (expected desync, tracked): {', '.join(xfail)}")
    if xpass:
        print(f"** XPASS: {', '.join(xpass)} now verify -- clear xfail_live + set known_best **")
    if real_fail:
        print(f"unverified (re-run individually): {', '.join(real_fail)}")


if __name__ == "__main__":
    main()
