"""capture_walkentry.py -- jitter-proof, foot-pose-rich live capture of the from-rest walk-entry.

WHY THIS EXISTS (session 37, 2026-07-13): the sheathed roll-stab anchor is NOT `REST BIT-EXACT`,
and session 36 mis-blamed "one extra idle frame before WAIT->MOVE". A jitter-proof measurement
(this tool) proved that WRONG: aligning each live row by the DETERMINISTIC emulator frame counter
(game_frame = emu - F0, F0 = the savestate's stored frame), the sheathed and drawn idles BOTH
transition proc 4->6 at the same game_frame and walk-enter at the same game_frame -- diff 0. The
session-36 "extra frame" was purely `run_dtm`'s row-0 poll jitter (`_log_playback` fast-poll lands
+-1 idle frame in). The REAL residual is the walk-entry foot TOE-STREAM (`posMoveFromFootPos` /
`f312`): at the sheathed idle phase (d~52.8) the sim's first-walk-frame toe delta is ~0.034 while
live is ~0.060, and the decomp-faithful 0.05 speedF clamp (`_py_foot_compose`) then zeros the sim
but keeps live -- opposite sides of the razor. It is PHASE-driven (idle13 d~30.8 is bit-exact),
not sword/equip. Modelling the walk-entry foot poses to f32 is the frontier fix (dead-end #25/#28).

This capture gives that modelling work its ground truth: for each anchor it plays the SAME clean-DTM
verification stream `rest.py` uses (never advancewith -- the stream is off-axis, dead-end #1), tags
EVERY row with the emulator frame (so alignment is deterministic, immune to the poll jitter), and
logs the raw foot poses (mFootData rtoe/ltoe/rheel/lheel + plant), the toe stream (m359C), the blend
weight (m3598), the two frame ctrls, pos, and proc. Diff sim-vs-live on THESE, aligned by game_frame.

    python -m harness.rollstab.capture_walkentry                       # sheathed, print + save golden
    python -m harness.rollstab.capture_walkentry anchor=<key> out=<path>
    python -m harness.rollstab.capture_walkentry anchor=kaze_r11_rollstab_idle13@twwgz  # the bit-exact ref

Live-only (Dolphin). Relaunches Dolphin (PauseMovie) like `rest.py`.
"""
import json
import os
import struct
import subprocess
import sys

# >>> repo bootstrap
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

LINK_PTR = 0x803AD860
# pointer offsets into P = deref(0x803AD860); RAM = header class offset - 0xD8.
OFF = dict(
    heap0_idx=0x2F04, heap1_idx=0x2F14,   # m_anm_heap_under[0/1].mIdx (loaded bck: WAITS 0x126 / WALK(S))
    d_frame=0x2F64, w_frame=0x2F78,       # mFrameCtrlUnder[MOVE0/MOVE1].mFrame
    m3598=0x34C0, m359C=0x34C4,           # WAITS/WALK blend weight + posMoveFromFootPos toe stream
    rtoe=0x3CF8, rheel=0x3CEC, ltoe=0x3E10, lheel=0x3E04, plant=0x33E4,
)
DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'sheathed_walkentry_golden.json')


def _emu_frame():
    out = subprocess.run([sys.executable, os.path.join(_tb, 'dolphin_mem.py'), 'status'],
                         capture_output=True, text=True).stdout.strip()
    try:
        return json.loads(out).get('frame')
    except Exception:
        return None


def _read_f0(sav):
    """Load the savestate PAUSED and read its stored emulator frame (the deterministic F0)."""
    import dolphin_mem as D
    D.control_pipe_quiet('clearinput')
    D.control_pipe_quiet('pause')
    D.control_pipe_quiet('savestate', {'action': 'load', 'path': sav.replace('\\', '/')})
    return _emu_frame()


def capture(anchor='kaze_r11_rollstab_sheathed@twwgz', out=None, seed=1):
    from harness.dtm.run_dtm import run_dtm, land_ready, resolve_anchor
    import harness.dtm.run_dtm as RD
    import dolphin_mem as D
    from harness.rollstab import rest as R

    f0 = _read_f0(resolve_anchor(anchor))
    print("anchor=%s  F0=%s" % (anchor, f0))

    _orig = RD._read_frame

    def rich(h, m):
        d = _orig(h, m)
        p = struct.unpack('>I', D.read_bytes(h, m, LINK_PTR, 4))[0]

        def rf(o):
            return struct.unpack('>f', D.read_bytes(h, m, p + o, 4))[0]

        def ru(o, sz):
            return struct.unpack('>' + {1: 'B', 2: 'H', 4: 'I'}[sz], D.read_bytes(h, m, p + o, sz))[0]

        def vec(o):
            return [rf(o), rf(o + 4), rf(o + 8)]
        d['emu'] = _emu_frame()
        d['heap0'] = ru(OFF['heap0_idx'], 2)
        d['heap1'] = ru(OFF['heap1_idx'], 2)
        for k, o in (('d_frame', 'd_frame'), ('w_frame', 'w_frame'), ('m3598', 'm3598'),
                     ('m359C', 'm359C')):
            d[k] = rf(OFF[o])
        d['plant'] = ru(OFF['plant'], 1)
        for k in ('rtoe', 'rheel', 'ltoe', 'lheel'):
            d[k] = vec(OFF[k])
        return d
    RD._read_frame = rich

    _, straight, aim = R.sticks_of(anchor)
    stream = [straight] * R.NPREF + [aim] * R.NCRUISE
    sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=0)
              for (sx, sy) in stream] + [dict(stickX=128, stickY=128, substickX=128,
                                              substickY=128, buttons=0)] * 20
    end = run_dtm(sticks, anchor=anchor, ready=land_ready, relaunch_dolphin=True,
                  log_frames=len(stream) + 2, verbose=True, seed=seed)
    RD._read_frame = _orig

    rows = []
    for r in end['log']:
        gf = (r['emu'] - f0) if (r.get('emu') is not None and f0 is not None) else None
        rows.append(dict(game_frame=gf, proc=r['proc'], pos_x=r['pos_x'], pos_z=r['pos_z'],
                         d_frame=r['d_frame'], w_frame=r['w_frame'], m3598=r['m3598'],
                         m359C=r['m359C'], plant=r['plant'], heap0=r['heap0'], heap1=r['heap1'],
                         rtoe=r['rtoe'], rheel=r['rheel'], ltoe=r['ltoe'], lheel=r['lheel']))

    print(" gf  proc heap0 |   pos_z     dz   | d_frame  m3598  m359C  plant")
    prevz = None
    for r in rows[:14]:
        dz = 0.0 if prevz is None else abs(r['pos_z'] - prevz)
        print("%3s  0x%02X 0x%03X | %10.5f %7.4f | %7.3f %6.4f %6.4f  %d" % (
            r['game_frame'], r['proc'], r['heap0'], r['pos_z'], dz, r['d_frame'],
            r['m3598'], r['m359C'], r['plant']))
        prevz = r['pos_z']

    result = dict(anchor=anchor, F0=f0, NPREF=R.NPREF, NCRUISE=R.NCRUISE, seed=seed, rows=rows)
    if out:
        with open(out, 'w') as f:
            json.dump(result, f, indent=1)
        print("wrote", out)
    return result


if __name__ == '__main__':
    kw = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    o = kw.pop('out', DEFAULT_OUT)
    capture(anchor=kw.get('anchor', 'kaze_r11_rollstab_sheathed@twwgz'), out=(o or None),
            seed=int(kw.get('seed', 1)))
