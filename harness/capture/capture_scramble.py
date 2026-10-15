"""Live re-measurement on the CURRENT slot-10 slate (2026-06-26 rebuild).
Resolves the neutral_anim_rate conflict (sim 0.49 vs old-slate data 0.84) and
re-measures the pump anim-scramble (oldFrame, ess3) with FULL float precision
(the `seq` helper's :.4g rounding destroys the x598-sensitive digits).

Usage: python capture_scramble.py <neutral|pump> <speed> [tag]
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

def loadstate(slot):
    D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})

def adv(h, mem1, sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})

def wnamed(h, mem1, name, value):
    e = D.NAMED_ADDRS[name]
    addr = D.resolve_chain(h, mem1, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    if t in ("f32", "f64"):
        data = struct.pack(fmt, float(value))
    else:
        data = struct.pack(">" + {1:"B",2:"H",4:"I",8:"Q"}[sz],
                           int(value) & ((1 << (sz*8)) - 1))
    D.write_bytes(h, mem1, addr, data)

def r(h, mem1, name):
    return D.read_named(h, mem1, name)

def seed(h, mem1, speed):
    """loadstate -> settle 1 -> re-attach happens by caller -> write -> readback verify."""
    wnamed(h, mem1, "air", 900)
    wnamed(h, mem1, "potential_speed", speed)
    # read-back verify (writes can race right after loadstate)
    return r(h, mem1, "potential_speed"), r(h, mem1, "air"), r(h, mem1, "link_state")

ESS = (128, 110)
NEU = (128, 128)

def test_neutral(speed, tag):
    loadstate(10)
    h, mem1 = D.attach()
    adv(h, mem1, *NEU)                 # settle 1 frame in neutral
    h, mem1 = D.attach()              # re-attach after loadstate
    pv, av, st = seed(h, mem1, speed)
    print(f"# NEUTRAL tag={tag} seed pot={pv:.1f} air={av} state={st}")
    print("f\tanim\tair\tpot\tstate\td_anim(mod26)")
    prev = None
    for i in range(40):
        adv(h, mem1, *NEU)
        a = r(h, mem1, "anim_frame"); air = r(h, mem1, "air")
        pot = r(h, mem1, "potential_speed"); state = r(h, mem1, "link_state")
        d = "" if prev is None else f"{D.__dict__.get('nfmod', nfmod)(a - prev, 26.0):.5f}"
        print(f"{i+1}\t{a:.6f}\t{air}\t{pot:.2f}\t{state}\t{d}")
        prev = a

def nfmod(a, n):
    return a - math.floor(a / n) * n

def test_pump(speed, tag):
    print(f"# PUMP K-sweep tag={tag} speed={speed}")
    print("K\tanim_lastNeut\tess1_s54\tess2_transition_raw\tess3_s55\tpre_state")
    for K in range(2, 10):
        loadstate(10)
        h, mem1 = D.attach()
        adv(h, mem1, *NEU)
        h, mem1 = D.attach()
        seed(h, mem1, speed)
        # 4 ESS
        for _ in range(4):
            adv(h, mem1, *ESS)
        # K neutral
        for _ in range(K):
            adv(h, mem1, *NEU)
        anim_lastNeut = r(h, mem1, "anim_frame")
        # then ESS x3: ess1=s54, ess2=transition, ess3=s55 real
        adv(h, mem1, *ESS); ess1 = r(h, mem1, "anim_frame"); s1 = r(h, mem1, "link_state")
        adv(h, mem1, *ESS); ess2 = r(h, mem1, "anim_frame")
        adv(h, mem1, *ESS); ess3 = r(h, mem1, "anim_frame")
        print(f"{K}\t{anim_lastNeut:.5f}\t{ess1:.5f}\t{ess2:.5f}\t{ess3:.5f}\t{s1}")

if __name__ == "__main__":
    mode = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else -280.0
    tag = sys.argv[3] if len(sys.argv) > 3 else "1"
    if mode == "neutral":
        test_neutral(speed, tag)
    elif mode == "pump":
        test_pump(speed, tag)
    D.cmd_control_pipe("clearinput")
