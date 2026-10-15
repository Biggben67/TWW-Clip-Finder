"""Live spot-check of the ROLL STAB (sword thrust out of a roll) -- confirms the sim's CUT_F / CUT_A
trajectory matches the game BYTE-FOR-BYTE (0 ULP) from the cut-entry frame through the WAIT idle exit.

The roll stab is the seam-clip lunge: fire a sword cut out of a FRONT_ROLL and its first frame stacks the
animation joint-0 root translate (m3700, reset to 0 in procCut*_init, +23.220u at anim frame 4.0) onto the
carried roll speedF (26) -> a single-frame ~49.22u move. This drives it live from a large-arena savestate,
captures the per-frame pos, then re-runs LandState.enter_cut(cut) seeded at the LIVE cut-entry pos and
asserts pos_x/pos_z bit-exact for every cut frame. Because the roll pins speedF=26, the cut is
history-independent, so seeding at the entry isolates the cut model from the walk/accel approach.

  CUT_F = forward thrust:  hold up + B on the first frame the roll accepts it.
  CUT_A = vertical slash:  L (targeting) + B with a neutral stick, same timing.

SETUP (user-provided): Dolphin with twwgz booted; SAVESTATE SLOT 7 = the large safe roll-stab arena
(pos ~(0,0,764), facing +Z, sword obtainable). The FIRST B press UNSHEATHES the sword (a WAIT anim, no
slash); the NEXT B slashes -- so the sequence draws early, then thrusts out of the roll. kroll=15 (15 held
frames between the A roll and the B thrust) is the "first possible frame" that carries the full 26 -> 49.22.

Usage:  python spotcheck_rollstab.py            # both cuts
        python spotcheck_rollstab.py CUT_F      # one
"""
import os, sys, struct, math  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.land.land import LandState, CUT_F, CUT_A, FRONT_ROLL

SLOT = 7
# player pointer-chain field offsets (P = deref(0x803AD860); = class offset - 0xD8)
OFF = dict(pos_x=0x120, pos_z=0x128, shape_y=0x136, angle_y=0x12E, speedF=0x17C, nspeed=0x34E4,
           curproc=0x3100)
CUTPROC = {CUT_F: 0x42, CUT_A: 0x41}


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _drive(h, mem1, cut):
    """Drive the roll stab live from slot 7, return per-frame [(proc, pos_x, pos_z, shape, travel)]."""
    D.control_pipe_quiet("clearinput"); D.control_pipe_quiet("pause")
    D.control_pipe_quiet("savestate", {"action": "load", "slot": SLOT})
    P = struct.unpack('>I', D.read_bytes(h, mem1, 0x803AD860, 4))[0]
    rf = lambda o: struct.unpack('>f', D.read_bytes(h, mem1, P + o, 4))[0]
    ri = lambda o: struct.unpack('>i', D.read_bytes(h, mem1, P + o, 4))[0]
    ru16 = lambda o: struct.unpack('>H', D.read_bytes(h, mem1, P + o, 2))[0]
    UP = dict(stickX=128, stickY=255, substickX=128, substickY=0, buttons=0, triggerL=0, frames=1)
    B = {**UP, 'buttons': 0x200}
    A = {**UP, 'buttons': 0x100}
    if cut == CUT_F:
        THRUST = {**UP, 'buttons': 0x200}                                   # up + B
    else:
        THRUST = dict(stickX=128, stickY=128, substickX=128, substickY=0, buttons=0x40 | 0x200,
                      triggerL=255, frames=1)                               # L(target) + B, neutral stick
    seq = [UP] * 4 + [B] + [UP] * 16 + [A] + [UP] * 15 + [THRUST] + [UP] * 16
    rows = []
    for inp in seq:
        D.control_pipe_quiet("advancewith", inp)
        rows.append((ri(OFF['curproc']), rf(OFF['pos_x']), rf(OFF['pos_z']), ru16(OFF['shape_y']),
                     ru16(OFF['angle_y'])))
    return rows


def _check(cut, rows):
    tag = "CUT_F" if cut == CUT_F else "CUT_A"
    cp = CUTPROC[cut]
    idx = [i for i, r in enumerate(rows) if r[0] == cp]
    if not idx:
        print("FAIL %s: no cut frame reached live (proc %d) -- setup/timing off" % (tag, cp))
        return False
    first = idx[0]
    entry = rows[first - 1]                       # last roll frame = the seed
    s = LandState(pos_x=entry[1], pos_z=entry[2], facing=entry[3], travel=entry[4], state=FRONT_ROLL,
                  nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
    dx, dz = s.enter_cut(cut)
    disp = math.hypot(dx, dz)
    ok = True
    # entry frame (the lunge)
    lr = rows[first]
    e0 = bits(s.pos_x) - bits(lr[1]); e1 = bits(s.pos_z) - bits(lr[2])
    print("  f%d %s ENTRY  disp=%.4f  dpx=%+d dpz=%+d" % (first, tag, disp, e0, e1))
    ok &= (e0 == 0 and e1 == 0)
    # play the rest to WAIT
    i = first + 1
    while i < len(rows) and rows[i][0] == cp:
        s.step(128, 255)
        du = bits(s.pos_x) - bits(rows[i][1]); dv = bits(s.pos_z) - bits(rows[i][2])
        ok &= (du == 0 and dv == 0)
        if du or dv:
            print("  f%d %s  dpx=%+d dpz=%+d  <---" % (i, tag, du, dv))
        i += 1
    # the WAIT idle exit frame
    if i < len(rows):
        s.step(128, 255)
        du = bits(s.pos_x) - bits(rows[i][1]); dv = bits(s.pos_z) - bits(rows[i][2])
        ok &= (du == 0 and dv == 0)
    n = i - first
    print("%s %s: %d cut frames + WAIT, entry lunge %.4fu  (%s)" % (
        "PASS" if ok else "FAIL", tag, n, disp, "0 ULP" if ok else "MISMATCH"))
    return ok


def main():
    which = sys.argv[1].upper() if len(sys.argv) > 1 else None
    h, mem1 = D.attach()
    cuts = [CUT_F, CUT_A] if which is None else [CUT_F if which == "CUT_F" else CUT_A]
    allok = True
    for cut in cuts:
        rows = _drive(h, mem1, cut)
        allok &= _check(cut, rows)
    print("\n%s" % ("ALL PASS (0 ULP)" if allok else "FAILURES"))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
