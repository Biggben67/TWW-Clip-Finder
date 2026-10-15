"""capture_decode.py -- JITTER-IMMUNE live capture of the stick DECODE + two-angle state.

WHY THIS EXISTS (session 40, 2026-07-14): `run_dtm`'s log playback fast-polls and its per-frame read
lands +-1 frame off, so a per-frame read of a fast-changing value (a 1-frame fine's decoded target/msd,
the facing) can silently return the NEIGHBORING frame's value. That poll jitter has now misled the
roll-stab diagnosis in sessions 36, 37, 39 AND the session-40 intermediate (the "MOVE-turn shape
overshoot" of dead-end #31 was a jittered read of the aim frame). This tool removes the jitter two ways:
  1. **game_frame tagging** (like `capture_walkentry.py`): every row is tagged with the deterministic
     emulator frame (`game_frame = emu - F0`, F0 = the savestate's stored frame), so alignment is exact
     and a misaligned poll is DETECTABLE, not silent.
  2. **hold-to-measure** (`hold_decode`): a stick held CONSTANT for N frames decodes to the same value
     every frame, so any poll within the hold reads the true value regardless of jitter.

Use it for ANY per-frame live decode / facing / two-angle measurement in the roll-stab pipeline; do NOT
read those off a raw `run_dtm` log without game_frame tags.

JP RAM offsets (player = deref 0x803AD860; these are the JP GZLJ offsets = US class offset - 0xD8 for
the player-specific 0x34xx/0x35xx fields; the fopAc base fields use run_dtm's proven reads):
  target  m34E8        @ P+0x3410 (s16)   -- setStickData want-angle = m34DC + csangle
  m34DC                @ P+0x3404 (s16)   -- stick want-angle pre-csangle
  mStickDistance       @ P+0x34D8 (f32)   -- the decoded stick magnitude (msd)
  proc                 @ P+0x3100 (s32)   -- run_dtm reads this
  speedF               @ P+0x17C  (f32)   -- run_dtm reads this
  shape_angle.y/travel -- via run_dtm's named reads ('shape_angle_y' / 'travel_angle')

KEY FINDING this tool established (session 42, RAM-confirmed -- overturns the #33 "band walk-speed"
story): reading `g_mDoCPd_cpadInfo[0]` (the RAW SI-delivered pad, what the game ACTUALLY polls, added
here) proved the row-18 sheathed-clip miss is a **make_dtm DELIVERY DROP**, not a physics/decode gap.
The stick decode is faithful even for Y>=192 when isolated (`transient_probe`/`hold_decode`); but with
the pipeline default `make_dtm(polls=4, seed=1)`, a 1-frame partial fine CLUSTERED after other partials
is DROPPED -- the game polls its full neighbour instead (`cpad_val` reads the full value, not the fine).
`seed=0` restores delivery at the SAME timing (`polls=8` delivers but at 2x timing). Use `delivery_sweep`
to see which fines the game receives per (polls, seed) and to validate a make_dtm fix; the physics /
`main_stick_decode` are decomp-faithful and are NOT the gap.

    python -m harness.rollstab.capture_decode ship [hit=0]        # play a solver hit's stream, diff vs sim (+cpad)
    python -m harness.rollstab.capture_decode sweep [hit=0]       # (polls,seed) delivery sweep -- the make_dtm probe
    python -m harness.rollstab.capture_decode hold                # jitter-immune held-stick decode test
    python -m harness.rollstab.capture_decode probe               # DETERMINISTIC stopped-pos probe (1-frame safe)
    python -m harness.rollstab.capture_decode bandsweep           # per-frame band sweep (z-trajectory only)

Live-only (Dolphin). Relaunches Dolphin like rest.py / capture_walkentry.py.
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
OFF = dict(target=0x3410, m34dc=0x3404, mStickDistance=0x34D8)   # JP player-ptr offsets
# g_mDoCPd_cpadInfo[0] (JP static, 0x3c/entry): the RAW SI-delivered pad the game polled THIS frame,
# BEFORE setStickData latches it -- reads what the console RECEIVED, not what downstream speed implies.
CPAD = 0x80398308                       # &g_mDoCPd_cpadInfo[0]
CPAD_OFF = dict(px=0x00, py=0x04, value=0x08, angle=0x0C)   # interface_of_controller_pad layout


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


def capture(anchor, stream, tail=6, log_extra=2, polls=4, seed=1):
    """Play `stream` (list of (sx, sy, buttons)) from `anchor` via a clean DTM and return rows tagged
    with the deterministic game_frame plus the decode + two-angle state. Jitter-immune by game_frame.
    `stream` is DELIVERED as-is -- calibrate bytes with rest.dtm_stick BEFORE calling if planning.

    `polls`/`seed` = the make_dtm poll cadence (default 4/1 = the pipeline default). Session 42 found
    the DEFAULT `seed=1` DROPS a clustered 1-frame partial fine (the game receives its full neighbour
    instead -- read cpad_val to see it); `seed=0` restores delivery at the SAME timing. Sweep these
    with `delivery_sweep` to validate a make_dtm fix."""
    from harness.dtm.run_dtm import run_dtm, land_ready, resolve_anchor
    import harness.dtm.run_dtm as RD
    import dolphin_mem as D

    f0 = _read_f0(resolve_anchor(anchor))
    _orig = RD._read_frame

    def rich(h, m):
        d = _orig(h, m)
        p = struct.unpack('>I', D.read_bytes(h, m, LINK_PTR, 4))[0]
        d['emu'] = _emu_frame()
        d['target'] = struct.unpack('>h', D.read_bytes(h, m, p + OFF['target'], 2))[0] & 0xFFFF
        d['m34dc'] = struct.unpack('>h', D.read_bytes(h, m, p + OFF['m34dc'], 2))[0] & 0xFFFF
        d['msd'] = struct.unpack('>f', D.read_bytes(h, m, p + OFF['mStickDistance'], 4))[0]
        d['shape'] = D.read_named(h, m, 'shape_angle_y') & 0xFFFF
        d['travel'] = D.read_named(h, m, 'travel_angle') & 0xFFFF
        # RAW SI-delivered pad (g_mDoCPd_cpadInfo[0]) -- what the game actually polled this frame.
        d['cpad_val'] = struct.unpack('>f', D.read_bytes(h, m, CPAD + CPAD_OFF['value'], 4))[0]
        d['cpad_px'] = struct.unpack('>f', D.read_bytes(h, m, CPAD + CPAD_OFF['px'], 4))[0]
        d['cpad_py'] = struct.unpack('>f', D.read_bytes(h, m, CPAD + CPAD_OFF['py'], 4))[0]
        d['cpad_ang'] = struct.unpack('>h', D.read_bytes(h, m, CPAD + CPAD_OFF['angle'], 2))[0] & 0xFFFF
        return d
    RD._read_frame = rich
    try:
        sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=b)
                  for (sx, sy, b) in stream]
        sticks += [dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0)] * tail
        end = run_dtm(sticks, anchor=anchor, ready=land_ready, relaunch_dolphin=True,
                      log_frames=len(stream) + log_extra, verbose=False, polls=polls, seed=seed)
    finally:
        RD._read_frame = _orig
    rows = []
    for r in end['log']:
        gf = (r['emu'] - f0) if (r.get('emu') is not None and f0 is not None) else None
        rows.append(dict(game_frame=gf, proc=r['proc'], pos_x=r['pos_x'], pos_z=r['pos_z'],
                         pos_y=r.get('pos_y'), shape=r['shape'], travel=r['travel'], speedF=r['speedF'],
                         target=r['target'], m34dc=r['m34dc'], msd=round(r['msd'], 6),
                         cpad_val=round(r['cpad_val'], 6), cpad_px=round(r['cpad_px'], 4),
                         cpad_py=round(r['cpad_py'], 4), cpad_ang=r['cpad_ang']))
    return dict(anchor=anchor, F0=f0, rows=rows)


def delivery_sweep(anchor, stream, combos=((4, 1), (4, 0), (8, 1)), tail=40):
    """Author `stream` as a clean DTM at each (polls, seed) and report which distinctive PARTIAL-
    magnitude fines the game ACTUALLY receives (`g_mDoCPd_cpadInfo[0].mMainStickValue` != full),
    the roll-proc row (timing landmark), and whether Link goes OOB (proc 0x24 = the clip). THIS IS
    THE TOOL THAT FOUND THE make_dtm DELIVERY BUG (session 42): with the pipeline default
    `(polls=4, seed=1)` a clustered 1-frame partial fine is DROPPED (the game polls the full
    neighbour instead), so a from-rest hit that relies on that fine's speed dip does NOT reproduce
    live. `(4, 0)` restores delivery at the SAME roll-row (timing preserved); `(8, *)` delivers but
    at ~2x timing (each authored frame spans 2 game frames -> the plan's discrete B/A land wrong).
    A make_dtm fix is VALID when every authored partial fine appears AND the roll row is unchanged
    AND Link goes OOB. `stream` = a hit's DELIVERED (sx,sy,buttons) rows (e.g. solver.run(...)['stream']).
    Live-only; relaunches Dolphin per combo."""
    out = []
    for (polls, seed) in combos:
        res = capture(anchor, stream, tail=tail, log_extra=6, polls=polls, seed=seed)
        rows = res['rows']
        fines = sorted({round(r['cpad_val'], 4) for r in rows if 0.05 < r['cpad_val'] < 0.99})
        roll_row = next((i for i, r in enumerate(rows) if r['proc'] == 0x1e), None)
        oob = any(r['proc'] == 0x24 for r in rows)
        miny = min((r['pos_y'] for r in rows if r['pos_y'] is not None), default=None)
        rec = dict(polls=polls, seed=seed, fines_received=fines, roll_row=roll_row,
                   oob_clip=oob, min_pos_y=None if miny is None else round(miny, 3))
        out.append(rec)
        print("polls=%d seed=%d | fines_received=%s roll_row=%s OOB_CLIP=%s min_y=%s" % (
            polls, seed, fines, roll_row, oob, rec['min_pos_y']))
    o = os.path.join(_rb, '_generated', 'delivery_sweep.json')
    json.dump(out, open(o, 'w'), indent=1)
    print('wrote', o)
    return out


def hold_decode(anchor, test_sticks, hold=8):
    """Jitter-immune decode measurement: hold each stick CONSTANT for `hold` frames (walk to cruise
    first) and read live (m34dc, msd). A constant stick decodes the same every frame -> poll jitter
    cannot misalign it. Compares each to the closed-form `main_stick_decode`. This is how session 40
    proved the HELD decode is bit-exact live even in the (0.889,1.0) band (dead-end #32)."""
    from harness.rollstab import rest as C
    from tww_sim.core.mathlib import main_stick_decode
    _, straight, aim = C.sticks_of(anchor)
    stream = [straight + (0,)] * 10 + [aim + (0,)] * 6
    spans = []
    for t in test_sticks:
        spans.append((tuple(t), len(stream), len(stream) + hold))
        stream += [tuple(t) + (0,)] * hold + [aim + (0,)] * 4
    res = capture(anchor, stream)
    rows = res['rows']
    out = []
    for (t, a, b) in spans:
        cf_ang, cf_msd = main_stick_decode(*t)
        cf_m34dc = (cf_ang + 0x8000) & 0xFFFF
        vals = [(rows[k]['m34dc'], round(rows[k]['msd'], 4)) for k in range(a + 3, min(b + 3, len(rows)))]
        match = all(v == (cf_m34dc, round(cf_msd, 4)) for v in vals) if vals else None
        out.append(dict(stick=list(t), cf=(cf_m34dc, round(cf_msd, 4)), live=vals, match=match))
        print('stk %-9s sim(m34dc=%d,msd=%.4f) | live held: %s  %s' % (
            str(t), cf_m34dc, cf_msd, vals, 'MATCH' if match else 'DIFF'))
    return out


def transient_probe(anchor, tests=None, holds=(1,), cruise=10, stop=16):
    """DETERMINISTIC, jitter-immune measurement of a partial-magnitude stick's effect. For each test
    stick T and hold length h, deliver `[straight]*4 + [aim]*cruise (walk to cap) + [T]*h + [neut]*stop
    (decel to a DEAD STOP)` and read the STOPPED end position -- constant, so run_dtm's +-1 log offset
    CANNOT corrupt it (unlike a per-frame read; see the module docstring + [[run-dtm-1frame-jitter]]).
    Compares live to the SIM's replay of the same stream (the model under test): a bit-for-bit match
    means the sim is faithful for T; a delta is the modelling gap. This is how session 41 proved the
    band DECODE is faithful (overturning #32) and it is the tool for MODELLING the console's band
    WALK-SPEED (dead-end #33): sweep holds=(1,2,3,4) on a band stick at cap and the incremental stopped
    distance per added T-frame is the console's per-frame speed for that band magnitude.

    Returns per (T, h): live stopped pos, sim stopped pos, delta (0 => sim faithful)."""
    from tww_sim.core.mathlib import main_stick_decode
    from harness.rollstab import rest as C
    from harness.dtm.run_dtm import run_dtm, land_ready
    _, straight, aim = C.sticks_of(anchor)
    NEUT = (128, 128)
    if tests is None:
        tests = [(96, 192)]                                # the sheathed hit's culprit band fine
    out = []
    first = True
    for T in tests:
        Tc = C.dtm_stick(tuple(T))
        _, m = main_stick_decode(*Tc)
        for h in holds:
            pre = [straight + (0,)] * 4 + [aim + (0,)] * cruise
            stream = pre + [Tc + (0,)] * h + [NEUT + (0,)] * stop
            s = C.rest_state(anchor)                       # sim replay of the delivered stream
            for sx, sy, b in stream:
                s.step(sx, sy, buttons=b)
            sim = (s.pos_x, s.pos_z)
            end = run_dtm([dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=b)
                           for (sx, sy, b) in stream],
                          anchor=anchor, ready=land_ready, relaunch_dolphin=first, verbose=False)
            first = False
            live = (end['pos_x'], end['pos_z'])
            dz = live[1] - sim[1]
            faithful = _bits(live[0]) == _bits(sim[0]) and _bits(live[1]) == _bits(sim[1])
            out.append(dict(stick=list(Tc), msd=round(m, 4), h=h, live=list(live), sim=list(sim),
                            dz=round(dz, 6), faithful=faithful))
            print('T=%s msd=%.4f h=%d live=(%.6f,%.6f) sim=(%.6f,%.6f) dz=%+.6f %s' % (
                str(tuple(Tc)), m, h, live[0], live[1], sim[0], sim[1], dz,
                'FAITHFUL' if faithful else 'GAP'))
    o = os.path.join(_rb, '_generated', 'transient_probe.json')
    json.dump(out, open(o, 'w'), indent=1)
    print('wrote', o)
    return out


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def band_sweep(anchor, tests=None, holds=(1, 2, 3), pre_aim=3, post_aim=3):
    """Per-frame band-transient sweep -- deliver `[aim]*pre_aim + [T]*h + [aim]*post_aim` per test and
    save the FULL game_frame-tagged rows. WARNING: per-frame DECODE reads here are NOT reliable for a
    1-FRAME event -- run_dtm's stream->row offset is +-1 ambiguous (O=2 and O=3 both fit settled runs),
    and a 1-frame transient lives inside that window ([[run-dtm-1frame-jitter]], dead-end #33). For a
    1-frame effect use `transient_probe` (deterministic stopped position). This sweep is still useful
    for the ROBUST z-TRAJECTORY (positions are slowly-varying, +-1-immune) and for HELD (>=2f) decode.

    The game-side path (PADRead->PADClamp->CStick::update->CButton::update) is STATELESS (decomp,
    session 41), so the closed-form decode is faithful; the modelling gap is the band WALK-SPEED."""
    from harness.rollstab import rest as C
    from tww_sim.core.mathlib import main_stick_decode
    _, straight, aim = C.sticks_of(anchor)
    if tests is None:
        # ladder near the aim bearing, below-band -> deep-band (RAW vs PRIOR distinguishable);
        # (99,183)/(98,188) non-band controls, (96,192)=0.9605 the shipped hit's culprit fine.
        tests = [(99, 183), (98, 188), (99, 189), (99, 190), (97, 190),
                 (98, 192), (96, 192), (98, 193), (96, 193), (96, 194)]
    aim_ang, aim_msd = main_stick_decode(*aim)
    aim_m34dc = ((aim_ang if aim_ang is not None else 0) + 0x8000) & 0xFFFF
    stream = [straight + (0,)] * 10 + [aim + (0,)] * 6
    spans = []                                              # (T, h, start_idx, end_idx)
    for t in tests:
        for h in holds:
            stream += [aim + (0,)] * pre_aim
            spans.append((tuple(t), h, len(stream), len(stream) + h))
            stream += [tuple(t) + (0,)] * h
            stream += [aim + (0,)] * post_aim
    res = capture(anchor, stream, tail=4, log_extra=2)
    # Save FULL game_frame-tagged rows + the delivered stream: align OFFLINE by game_frame, NOT by
    # log-row index (run_dtm poll jitters +-1 -> a 1-frame transient misreads; see the module docstring).
    o = os.path.join(_rb, '_generated', 'band_sweep_decode.json')
    json.dump(dict(anchor=anchor, F0=res['F0'], aim=list(aim), aim_decode=[aim_m34dc, round(aim_msd, 4)],
                   stream=[list(x) for x in stream],
                   spans=[[list(t), h, a, b] for (t, h, a, b) in spans],
                   rows=[dict(gf=r['game_frame'], m34dc=r['m34dc'], msd=round(r['msd'], 4),
                              shape=r['shape'], speedF=round(r['speedF'], 3)) for r in res['rows']]),
              open(o, 'w'), indent=1)
    print('wrote %s (F0=%s, %d rows, aim decode m34dc=%d msd=%.4f)' % (
        o, res['F0'], len(res['rows']), aim_m34dc, aim_msd))
    return res


def ship(idx=0):
    """Play a solver hit's ship stream jitter-immune and diff vs the from-rest sim, aligned by
    game_frame -- the trustworthy per-frame delivery diff (do NOT use a raw run_dtm log for this)."""
    from harness.rollstab import rest as C
    from harness.rollstab.solver import HITS_PATH
    hit = json.load(open(HITS_PATH))[idx]
    anchor = hit['anchor']
    stream = [tuple(fr) for fr in hit['stream']]
    res = capture(anchor, stream)
    out = os.path.join(_rb, '_generated', 'capture_decode_ship.json')
    json.dump(res, open(out, 'w'), indent=1)
    # sim side
    s = C.rest_state(anchor)
    sim = []
    for (sx, sy, b) in stream:
        s.step(sx, sy, buttons=b)
        sim.append((s.state & 0xFF, s.facing & 0xFFFF, s.travel & 0xFFFF, round(s.speedF, 3),
                    s.target & 0xFFFF, round(s.msd, 4)))
    print('wrote %s (F0=%s)' % (out, res['F0']))
    print(' live rows (game_frame-tagged): idx gf proc shape travel tgt msd speedF -- diff vs sim by hand')
    for i, r in enumerate(res['rows']):
        print(' %2d gf=%3s 0x%02x shape=%d travel=%d tgt=%d msd=%.4f cpad_val=%.4f cpad=(%.2f,%.2f) spF=%.2f' % (
            i, r['game_frame'], r['proc'], r['shape'], r['travel'], r['target'], r['msd'],
            r['cpad_val'], r['cpad_px'], r['cpad_py'], r['speedF']))
    return res


def _sheathed_ship_stream():
    """Reconstruct the session-39 sheathed roll-stab hit's DELIVERED stream from the solver recipe
    (the durable source; mirrors tests/test_sheathed_roll_clip.py, so it works without the gitignored
    _generated/rollstab_hits.json)."""
    from harness.rollstab import solver as SV
    ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'
    MOVES = ((9, (73, 254), 2), (10, (99, 183)), (4, (96, 192)), (6, (98, 188)))
    START = ((77, 249), (98, 191))
    r = SV.run(ANCHOR, MOVES, A_proj=-500.0, start=START, draw_at=3)
    return ANCHOR, [tuple(x) for x in r['stream']]


if __name__ == '__main__':
    kw = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    if 'sweep' in sys.argv:
        # the make_dtm delivery probe (session 42): which (polls,seed) delivers every fine + clips OOB.
        anchor, stream = _sheathed_ship_stream()
        combos = ((4, 1), (4, 0), (8, 1))
        delivery_sweep(anchor, stream, combos=combos)
    elif 'hold' in sys.argv:
        A = kw.get('anchor', 'kaze_r11_rollstab_sheathed@twwgz')
        hold_decode(A, [(96, 192), (98, 191), (98, 196), (77, 249)])
    elif 'bandsweep' in sys.argv:
        A = kw.get('anchor', 'kaze_r11_rollstab_sheathed@twwgz')
        band_sweep(A)
    elif 'probe' in sys.argv:
        A = kw.get('anchor', 'kaze_r11_rollstab_sheathed@twwgz')
        transient_probe(A, holds=(1, 2, 3, 4))          # sweep hold length -> per-frame band speed
    else:
        ship(int(kw.get('hit', 0)))
