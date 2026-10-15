"""ONE-TIME live capture: per-frame land-tech goldens for the OFFLINE regression gate.

Dereck's post-s66 steer: record each frame's live game state to a flat file ONCE, then all
future land-tech comparisons are offline sim-vs-recording (tests/test_land_goldens.py) --
no flaky live-playback layer in the standing gate. run_land_tests.py remains the live
re-capture / diagnosis tool; THIS script mints the recordings it compares against.

Per case (the 14 SIM-vs-LIVE cases from run_land_tests.CASES + TURN_CASES, including the
wiggle-EBS-into-roll chain, which replaced the retired flaky DTM-playback path):
  1. load the land_flatwalk anchor, read the frame-0 seed (the deterministic rest state);
  2. CHUNKED capture: advanceseq ONE element at a time, reading every READS field per frame;
  3. delivery cross-check: re-run the WHOLE seq as one advanceseq (the proven one-shot
     delivery) and require the end rows bit-identical -- if chunking perturbed delivery
     (bug#2 class), fall back to PREFIX-REPLAY (loadstate + advanceseq(seq[:k]) per row k:
     each row then comes from a clean one-shot, guaranteed faithful, just O(n^2) frames);
  4. known-good gate: run the OFFLINE sim over the seq and apply the SAME locked checks the
     live test asserts (sim_checks + the tech extra checks + the 0-ULP pos_z gate) against
     the recorded end row. A golden is only written when every check passes -- a recording
     that fails the locked expectations is a finding, never a fixture.

Goldens land in fixtures/land_goldens/<case>_golden.json:
  {case, anchor, note, capture ('chunked'|'prefix'), seq, seed, frames, assert_pos_x}
`assert_pos_x` is measured at capture time (True iff the sim matched live pos_x 0-ULP on
every frame) so the offline gate can assert exactly what is known-exact, no more, no less.

These recordings are LIVE goldens: locked-test rules apply (tests/dolphin/README.md) --
never edit one to make the sim pass. Re-record only after a DELIBERATE anchor/tech change.

Requires Dolphin running with twwgz booted (harness.dolphin_env.ensure_running).
Usage:
  python tests/dolphin/record_land_goldens.py             # capture + validate + write all
  python tests/dolphin/record_land_goldens.py only=<case> # one case
  python tests/dolphin/record_land_goldens.py dry=1       # capture + validate, write nothing
"""
import json
import os
import sys

_rb = os.path.dirname(os.path.abspath(__file__))  # >>> repo bootstrap: tww_sim/ + ../tools/
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

import dolphin_mem as D
from harness.dtm.run_dtm import resolve_anchor
from tww_sim.land.land import LandState

from run_land_tests import (ANCHOR, CASES, TURN_CASES, READS, f32_bits,
                            posz_status, sim_checks, deg, sdiff_deg)

GOLD_DIR = os.path.join(_rb, 'fixtures', 'land_goldens')
FLOATS = {"potential_speed", "true_speed", "pos_x", "pos_z", "anim_frame"}
INTS = {"link_state", "shape_angle_y", "travel_angle", "csangle"}


def read_row(h, m):
    return {k: D.read_named(h, m, k) for k in READS}


def rows_equal(a, b):
    """Bit-exact row equality: floats by f32 bits, ints by value."""
    for k in READS:
        if k in FLOATS:
            if f32_bits(a[k]) != f32_bits(b[k]):
                return False
        elif int(a[k]) != int(b[k]):
            return False
    return True


def load_anchor():
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace('\\', '/')})
    return D.attach()


def capture_chunked(seq):
    """Frame-0 seed + one advanceseq call per element, reading every frame."""
    h, m = load_anchor()
    seed = read_row(h, m)
    frames = []
    for el in seq:
        for _ in range(el.get("frames", 1)):
            one = dict(el)
            one["frames"] = 1
            D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [one]})
            h, m = D.attach()
            frames.append(read_row(h, m))
    return seed, frames


def capture_oneshot_end(seq):
    """The proven delivery: the whole seq in ONE advanceseq; returns the end row only."""
    load_anchor()
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    h, m = D.attach()
    return read_row(h, m)


def capture_prefix(seq):
    """Guaranteed-faithful per-frame capture: row k = clean one-shot advanceseq(seq[:k])."""
    flat = []
    for el in seq:
        for _ in range(el.get("frames", 1)):
            one = dict(el)
            one["frames"] = 1
            flat.append(one)
    h, m = load_anchor()
    seed = read_row(h, m)
    frames = []
    for k in range(1, len(flat) + 1):
        load_anchor()
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": flat[:k]})
        h, m = D.attach()
        frames.append(read_row(h, m))
    return seed, frames


def sim_over(seed, seq):
    """The offline sim, seeded exactly as run_land_tests.replay_sim_vs_live seeds it."""
    sim = LandState(pos_z=seed["pos_z"], facing=int(seed["shape_angle_y"]),
                    travel=int(seed["travel_angle"]), csangle=int(seed["csangle"]),
                    state=int(seed["link_state"]), nspeed=seed["potential_speed"],
                    idle_frame=seed["anim_frame"])
    per_frame = []
    for el in seq:
        for _ in range(el.get("frames", 1)):
            sim.step(el["stickX"], el["stickY"],
                     buttons=el.get("buttons", 0), triggerL=el.get("triggerL", 0))
            per_frame.append({"state": sim.state, "nspeed": sim.nspeed,
                              "facing": int(sim.facing) & 0xFFFF,
                              "travel": int(sim.travel) & 0xFFFF,
                              "pos_x": sim.pos_x, "pos_z": sim.pos_z})
    return sim, per_frame


def perframe_report(per_frame, frames):
    """First per-frame sim-vs-recording mismatch per field (None = exact on every frame)."""
    first = {}
    for i, (s, l) in enumerate(zip(per_frame, frames)):
        pairs = [("state", s["state"] == int(l["link_state"])),
                 ("nspeed", f32_bits(s["nspeed"]) == f32_bits(l["potential_speed"])),
                 ("facing", s["facing"] == int(l["shape_angle_y"]) & 0xFFFF),
                 ("travel", s["travel"] == int(l["travel_angle"]) & 0xFFFF),
                 ("pos_x", f32_bits(s["pos_x"]) == f32_bits(l["pos_x"])),
                 ("pos_z", f32_bits(s["pos_z"]) == f32_bits(l["pos_z"]))]
        for k, ok in pairs:
            if not ok and k not in first:
                first[k] = i
    return first


def flatten(seq):
    out = []
    for el in seq:
        for _ in range(el.get("frames", 1)):
            one = dict(el)
            one["frames"] = 1
            out.append(one)
    return out


def record_case(label, seqfn, note, checkfn, is_turn, dry):
    seq = seqfn()
    seed, frames = capture_chunked(seq)
    end = capture_oneshot_end(seq)
    capture = "chunked"
    if not rows_equal(end, frames[-1]):
        print(f"  [{label}] chunked delivery != one-shot -- falling back to prefix-replay")
        seed, frames = capture_prefix(seq)
        capture = "prefix"
        if not rows_equal(end, frames[-1]):
            print(f"FAIL {label}: prefix-replay end row still != one-shot end -- NOT deterministic?")
            return False

    live = frames[-1]
    sim, per_frame = sim_over(seed, seq)
    checks = sim_checks(sim, live, note)
    if is_turn:
        checks += checkfn(sim, live)
    elif checkfn is not None:
        e = {"link_state": int(live["link_state"]), "v": abs(live["potential_speed"]),
             "facing": deg(live["shape_angle_y"]), "travel": deg(live["travel_angle"]),
             "face_trav": abs(sdiff_deg(live["shape_angle_y"], live["travel_angle"]))}
        checks += checkfn(e)
    pos = posz_status(sim, live, label)
    ok = all(c[0] for c in checks) and (pos is None or pos[0] == "ok")
    if not ok:
        print(f"FAIL {label}: recording does not meet the locked live expectations -- golden NOT written")
        for passed, desc in checks:
            if not passed:
                print(f"     X  {desc}")
        if pos is not None and pos[0] != "ok":
            print(f"     X  {pos[1]}")
        return False

    first = perframe_report(per_frame, frames)
    core = {k: v for k, v in first.items() if k != "pos_x"}
    if core:
        print(f"FAIL {label}: end-state exact but PER-FRAME mismatch {core} -- golden NOT written "
              f"(a mid-run divergence that re-converges is a finding)")
        return False
    assert_pos_x = "pos_x" not in first
    golden = {"case": label, "anchor": "land_flatwalk@twwgz", "note": note,
              "capture": capture, "assert_pos_x": assert_pos_x,
              "seq": flatten(seq), "seed": seed, "frames": frames}
    tag = f"({capture}, {len(frames)} frames, pos_x {'exact' if assert_pos_x else 'NOT asserted'})"
    if dry:
        print(f"PASS {label} {tag} -- dry run, not written")
        return True
    os.makedirs(GOLD_DIR, exist_ok=True)
    path = os.path.join(GOLD_DIR, f"{label}_golden.json")
    with open(path, "w") as f:
        json.dump(golden, f)
    print(f"PASS {label} {tag} -> {os.path.relpath(path, _rb)}")
    return True


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    only = o.get('only')
    dry = o.get('dry', '0') in ('1', 'true', 'yes')
    from harness.dolphin_env import ensure_running
    ensure_running()
    n_ok = n_fail = 0
    for label, seqfn, note, extra in CASES:
        if only and only != label:
            continue
        okk = record_case(label, seqfn, note, extra, is_turn=False, dry=dry)
        n_ok, n_fail = n_ok + okk, n_fail + (not okk)
    for label, seqfn, note, check in TURN_CASES:
        if only and only != label:
            continue
        okk = record_case(label, seqfn, note, check, is_turn=True, dry=dry)
        n_ok, n_fail = n_ok + okk, n_fail + (not okk)
    print(f"\n{n_ok} recorded, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
