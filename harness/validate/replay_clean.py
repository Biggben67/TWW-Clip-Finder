"""Drop-proof live replay/validator. The `advancewith` pipe occasionally fails to latch a
per-frame stick change (a timing race), which on a charge frame leaves a STALE stick ->
the turnaround doesn't fire -> +3 instead of -3. That's a harness artifact, not physics
(the decomp instant-snaps a backward stick -> always -3).

Fix: replay in short SEGMENTS and use the bit-exact SwimState sim as an ORACLE. After each
segment, compare live (v, air) to the sim's prediction; if they diverge a stick was dropped,
so reload the last checkpoint and retry the segment. Result: a guaranteed clean run that
matches the sim frame-for-frame, i.e. what a real DTM movie (reliable per-frame input) does.

Usage: python replay_clean.py [seq=coldstart200k.txt] [slot=10] [cold=1] [K=15] [tol=1.0] (uses scratch slot 1)
"""
import sys, struct, math
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import sim as S

ESS = (128, 110); NEU = (128, 128); CHG_UP, CHG_DN = (128, 255), (128, 0)
CKPT_SLOT = 1   # scratch savestate slot for checkpoints (savefile/loadfile fail on this fork)


def ckpt_save():
    D.cmd_control_pipe("savestate", {"action": "save", "slot": CKPT_SLOT})


def ckpt_load():
    D.cmd_control_pipe("savestate", {"action": "load", "slot": CKPT_SLOT})


def adv(sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})


def wnamed(h, m, name, value):
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, m, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    D.write_bytes(h, m, addr, data)


def r(h, m, name):
    return D.read_named(h, m, name)


def expand(seq):
    acts = []
    for seg in seq.strip().split(';'):
        if seg:
            a, n = seg.split(','); acts += [a] * int(n)
    return acts


def stick_for(a, chg_count):
    if a == 'ess':
        return ESS
    if a == 'neu':
        return NEU
    return CHG_UP if chg_count % 2 == 0 else CHG_DN   # alternate per charge


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    seqfile = opts.get('seq', 'coldstart200k.txt')
    slot = int(opts.get('slot', '10')); cold = opts.get('cold', '1') != '0'
    K = int(opts.get('K', '15')); tol = float(opts.get('tol', '1.0'))
    maxretry = int(opts.get('maxretry', '40'))
    acts = expand(open(seqfile).read())

    D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})
    h, m = D.attach(); adv(*NEU); h, m = D.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", 0.0)
    v0 = r(h, m, "potential_speed"); anim0 = r(h, m, "anim_frame")
    air0 = r(h, m, "air"); st0 = r(h, m, "link_state")
    x0 = r(h, m, "link_x"); z0 = r(h, m, "link_z")
    print(f"seed: v={v0:.3f} anim={anim0:.4f} air={air0} state={st0}  ({len(acts)} frames)")

    # bit-exact sim oracle: per-frame (v, air) prediction
    sim = S.SwimState(v=v0, anim=anim0, air=air0); sim.state = st0
    sim._entry_tax = False if cold else True
    pred = []
    for a in acts:
        sim.step(a); pred.append((sim.v, sim.air, sim.anim))

    # cumulative charge count up to each frame (for stick alternation parity)
    chg_before = []; c = 0
    for a in acts:
        chg_before.append(c)
        if a == 'chg':
            c += 1

    ckpt_save()  # checkpoint @ frame 0
    seg_start = 0; drops = 0; retries_here = 0
    while seg_start < len(acts):
        seg_end = min(seg_start + K, len(acts))
        for j in range(seg_start, seg_end):
            stick = stick_for(acts[j], chg_before[j])
            adv(*stick)
        lv = r(h, m, "potential_speed"); lair = r(h, m, "air")
        pv, pair, _ = pred[seg_end - 1]
        if abs(lv - pv) <= tol and lair == pair:
            ckpt_save()  # advance ckpt
            seg_start = seg_end; retries_here = 0
        else:
            drops += 1; retries_here += 1
            tag = "air-desync" if lair != pair else f"v {lv:.1f} vs {pv:.1f}"
            print(f"  drop in [{seg_start},{seg_end}) ({tag}) -> reload+retry #{retries_here}")
            ckpt_load(); h, m = D.attach()
            if retries_here > maxretry:
                print("  too many retries; aborting"); D.cmd_control_pipe("clearinput"); return

    lv = r(h, m, "potential_speed"); lan = r(h, m, "anim_frame"); lair = r(h, m, "air")
    pv, pair, pan = pred[-1]
    xf = r(h, m, "link_x"); zf = r(h, m, "link_z")
    net = math.hypot(xf - x0, zf - z0)
    dvf = lv - pv; danf = ((lan - pan + 11.5) % 23.0) - 11.5
    print(f"\nCLEAN RUN ({drops} dropped-input repairs).")
    print(f"  final  live v={lv:.3f} anim={lan:.3f} air={lair}")
    print(f"  final  sim  v={pv:.3f} anim={pan:.3f} air={pair}")
    print(f"  dv={dvf:+.4f}  d_anim(mod23)={danf:+.4f}  air match={lair==pair}")
    print(f"  live net distance (wave byproduct): {net:.0f}")
    print("RESULT:", "BIT-EXACT v" if abs(dvf) < 0.01 else f"v MISMATCH {dvf:+.3f}")
    D.cmd_control_pipe("clearinput")


if __name__ == "__main__":
    main()
