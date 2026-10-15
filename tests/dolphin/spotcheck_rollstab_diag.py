"""Live spot-check of the DIAGONAL roll stab -- roll STRAIGHT forward, then a slight up/left (or
up/right) thrust to steer the cut. Confirms the sim's steered CUT_F trajectory matches the game
BYTE-FOR-BYTE (0 ULP) from the lunge frame through the WAIT idle exit, across a range of aims.

Mechanism (decomp d_a_player_sword.inc procCutF + d_a_player_main.cpp posMove/changeCutProc, live
2026-07-07): the entry LUNGE (49.22u) always fires along the ROLL facing -- procCutF has not run on
the init frame, so shape_angle.y is unchanged. On the FIRST cut proc frame procCutF steps
cLib_addCalcAngleS(shape, m34D4, mTurn.f4=30, mTurn.f0=0x3CDF, mTurn.f2=0x1F40); the 0x1F40 min-step
dwarfs any in-range diff, so shape=travel SNAPS to the latched aim (m34D4 = the stick target m34E8
sampled at the thrust) in one frame and holds -- the whole ~40u cut tail rotates by the aim. The
stab dispatches CUT_F only while |aim - roll_facing| < 0x2000 (getDirectionFromAngle FORWARD); a
larger aim gives CUT_L / CUT_R instead. So the steer-able in-line thrust range is +-0x2000 (+-45deg).

OFF-AXIS STICKS MUST GO THROUGH A DTM (advancewith mis-injects near-full off-axis, the bug#2-family
artifact -- see the advancewith-offaxis-stick-artifact memory). We author a clean movie truncated at
each frame; the movie auto-plays to exhaustion and pauses at the last frame, so the exhaustion read
IS that frame's exact (full-precision) state. Sweeping the truncation reconstructs the trajectory.

SETUP: SAVESTATE SLOT 7 anchor = the large flat arena (captured as rollstab_arena@twwgz). Requires a
pipe-enabled Dolphin (harness.dolphin_env). Usage:  python spotcheck_rollstab_diag.py [aimX ...]
"""
import os, sys, struct, math, time, json, shutil
_rb = os.path.dirname(os.path.abspath(__file__))            # >>> repo bootstrap
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')           # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
import dtm_make as DM
from harness.dtm.run_dtm import relaunch, resolve_anchor, iso_for_anchor, DEFAULT_TEMPLATE, _GEN
from tww_sim.land.land import LandState, CUT_F, FRONT_ROLL

ANCHOR = "rollstab_arena@twwgz"
OFF = dict(pos_x=0x120, pos_z=0x128, shape_y=0x136, angle_y=0x12E, speedF=0x17C,
           nspeed=0x34E4, curproc=0x3100)
# frame map (DTM playback): unsheathe B@4, roll A@21, thrust@37, LUNGE (first CUT_F) at frame index 39
# -> truncation N = index+1, so lunge at N=40. Sweep a window that spans roll-tail .. WAIT+.
N_FROM, N_TO = 39, 52


def _build(aim_x, aim_y=255, truncate=None):
    """Roll straight up, diagonal (aim_x, aim_y) held from the thrust (index 37) through the tail."""
    C = dict(substickX=128, substickY=0)
    UP = dict(stickX=128, stickY=255, buttons=0, triggerL=0, **C)
    AIM = dict(stickX=aim_x, stickY=aim_y, buttons=0, triggerL=0, **C)
    B = {**UP, 'buttons': 0x200}
    A = {**UP, 'buttons': 0x100}
    AIMB = {**AIM, 'buttons': 0x200}
    seq = [UP]*4 + [B] + [UP]*16 + [A] + [UP]*15 + [AIMB] + [UP]*16
    for i in range(37, len(seq)):
        if seq[i]['buttons'] == 0: seq[i] = dict(AIM)
        elif seq[i]['buttons'] == 0x200: seq[i] = dict(AIMB)
    return seq[:truncate] if truncate is not None else seq


def _status():
    try: return json.loads(D.control_pipe_quiet("status"))
    except Exception: return {}


def _readrow(h, m):
    P = struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]
    rf = lambda o: struct.unpack('>f', D.read_bytes(h, m, P + o, 4))[0]
    ri = lambda o: struct.unpack('>i', D.read_bytes(h, m, P + o, 4))[0]
    ru = lambda o: struct.unpack('>H', D.read_bytes(h, m, P + o, 2))[0]
    return dict(proc=ri(OFF['curproc']), px=rf(OFF['pos_x']), pz=rf(OFF['pos_z']),
                shape=ru(OFF['shape_y']), cur=ru(OFF['angle_y']),
                speedF=rf(OFF['speedF']), nspeed=rf(OFF['nspeed']))


def _play_read(seq, out, template, game, anchor, boot=180):
    DM.build_dtm_from_sticks(seq, out, template, 4, 1)
    shutil.copyfile(anchor, out + ".sav"); shutil.copyfile(out, out + ".sav.dtm")
    D.control_pipe_quiet("playmovie", {"path": out.replace('\\', '/'), "game": game})
    t0 = time.time()
    while time.time() - t0 < boot and not _status().get("playing"): time.sleep(0.3)
    t1 = time.time()
    while time.time() - t1 < boot:
        st = _status()
        if st.get("ok") and not st.get("playing") and st.get("frame", 0) > 5:
            try:
                sv = sys.stdout; sys.stdout = open(os.devnull, 'w')
                try: h, m = D.attach()
                finally: sys.stdout.close(); sys.stdout = sv
                return _readrow(h, m)
            except BaseException: pass
        time.sleep(0.4)
    raise SystemExit("play/read timed out")


def _capture(aim_x, do_relaunch, out, template, game, anchor):
    if do_relaunch: relaunch(verbose=True)
    return {n: _play_read(_build(aim_x, truncate=n), out, template, game, anchor)
            for n in range(N_FROM, N_TO + 1)}


def _bits(x): return struct.unpack("<I", struct.pack("<f", x))[0]


def check(aim_x, rows):
    """Seed enter_cut at the live entry (last roll frame) with aim = the live snapped shape, run the
    full cut, assert bit-exact pos_x/pos_z for every CUT frame + the WAIT exit."""
    idx = sorted(n for n, r in rows.items() if r['proc'] == CUT_F)
    if not idx:
        print("FAIL aimX=%d: no CUT_F frame -- aim out of the +-0x2000 range (flipped to CUT_L/R)?" % aim_x)
        return False
    lunge = idx[0]; entry = rows[lunge - 1]                 # last roll frame = seed
    aim = rows[lunge + 1]['shape'] if (lunge + 1) in rows else rows[lunge]['shape']
    s = LandState(pos_x=entry['px'], pos_z=entry['pz'], facing=entry['shape'], travel=entry['cur'],
                  state=FRONT_ROLL, nspeed=26.0, speedF=26.0, use_anim=False, native=False,
                  sword_drawn=True)
    dx, dz = s.enter_cut(CUT_F, aim=aim)
    ok = True; nchk = 0
    lr = rows[lunge]
    e0 = _bits(s.pos_x) - _bits(lr['px']); e1 = _bits(s.pos_z) - _bits(lr['pz'])
    ok &= (e0 == 0 and e1 == 0); nchk += 1
    tail_rot = ((aim - entry['shape'] + 32768) % 65536) - 32768
    if e0 or e1: print("  LUNGE dpx=%+d dpz=%+d <--" % (e0, e1))
    n = lunge + 1
    while n in rows and rows[n]['proc'] == CUT_F:
        s.step(128, 255)
        du = _bits(s.pos_x) - _bits(rows[n]['px']); dv = _bits(s.pos_z) - _bits(rows[n]['pz'])
        ok &= (du == 0 and dv == 0); nchk += 1
        if du or dv: print("  f%d dpx=%+d dpz=%+d  (sim sh=%d live sh=%d) <--" % (n, du, dv, s.facing, rows[n]['shape']))
        n += 1
    if n in rows and rows[n]['proc'] == 4:                  # WAIT exit
        s.step(128, 255)
        du = _bits(s.pos_x) - _bits(rows[n]['px']); dv = _bits(s.pos_z) - _bits(rows[n]['pz'])
        ok &= (du == 0 and dv == 0); nchk += 1
    print("%s aimX=%d: %d frames 0-ULP; lunge=%.4fu straight, tail rotated %+.2fdeg (aim s16=%d)" % (
        "PASS" if ok else "FAIL", aim_x, nchk, math.hypot(dx, dz), tail_rot * 360.0 / 65536.0, aim))
    return ok


def main():
    aims = [int(a) for a in sys.argv[1:]] or [110, 96, 64]     # up-left diagonals (X<128); mirror = 256-X
    anchor = resolve_anchor(ANCHOR); game = iso_for_anchor(anchor).replace('\\', '/')
    out = os.path.join(_GEN, "spotcheck_diag_tmp.dtm"); allok = True
    for i, ax in enumerate(aims):
        rows = _capture(ax, i == 0, out, DEFAULT_TEMPLATE, game, anchor)
        allok &= check(ax, rows)
    print("\n%s" % ("ALL PASS (0 ULP)" if allok else "FAILURES"))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
