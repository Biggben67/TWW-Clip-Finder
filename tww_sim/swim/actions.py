"""Action-sequence helpers shared by the sim, planner, tests, and harness.

An *action* is one of ``ess`` / ``neu`` / ``chg`` (one game frame each). A *seq string* is the
compact run-length form ``"ess,200;chg,2;neu,50"``. These helpers convert between actions, seq
strings, and the per-frame stick element list consumed by ``dolphin_mem.advanceseq`` /
``swim.sim``. Kept Dolphin-free so the core package has no live dependency.

Previously these lived inside ``run_tests.py``; they were extracted here because ~30 scripts
import them. ``run_tests.py`` now re-imports from this module.
"""

# Main-stick coords per action (stickX, stickY). chg alternates up/down by charge parity.
ESS = (128, 110)
NEU = (128, 128)
CHG_UP, CHG_DN = (128, 255), (128, 0)


def expand(seq):
    """Expand a run-length seq string ``"ess,200;chg,2"`` into a flat action list."""
    acts = []
    for seg in seq.strip().split(';'):
        if seg:
            a, n = seg.split(','); acts += [a] * int(n)
    return acts


def acts_to_seq(acts):
    """Map an action list to the flat ``advanceseq`` element list. The chg stick alternates
    up/down each charge frame (parity of charge-count-so-far) — the same rule verify_state.py
    uses, so a live replay is bit-identical to the per-frame validator."""
    out, chg = [], 0
    for a in acts:
        if a == 'ess':
            sx, sy = ESS
        elif a.startswith('ess:'):                  # partial on-axis hold (128, rawY)
            sx, sy = 128, int(a[4:])
        elif a == 'neu':
            sx, sy = NEU
        elif a == 'chg':
            chg += 1
            sx, sy = CHG_UP if chg % 2 == 1 else CHG_DN
        elif a.startswith('chg:'):                  # partial charge: up stroke (128,rawY),
            chg += 1                                 # down stroke mirrored about 128 (matches
            up = int(a[4:])                          # SwimState._chg_stick(up_raw))
            sx, sy = (128, up) if chg % 2 == 1 else (128, 256 - up)
        else:
            raise ValueError(f"unknown action {a!r} in seq")
        out.append({"stickX": sx, "stickY": sy, "substickY": 0, "frames": 1})
    return out


def animdiff(a, b, n):
    """Shortest cyclic distance between two anim-frame values on a period-``n`` controller."""
    d = (a - b) % n
    return min(d, n - d)
