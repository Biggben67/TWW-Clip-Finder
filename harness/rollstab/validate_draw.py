"""validate_draw.py - OFFLINE: replay the mid-walk-draw capture in a from-rest LandState and pin the
anim-set switch frame (f_draw) that reproduces the live walk 0-ULP.

Reads fixtures/walk_draw.json (harness.rollstab.capture_draw). Seeds a from-rest LandState from the
anchor's rest seed, replays the exact captured inputs (UP walk + UP+B draw), and for each candidate
switch frame S pokes FootSpeedF.draw_sword() before producing row S, then diffs pos_z per frame vs
live. Also runs the two baselines (never-draw sword=False; always-sword sword=True) to show the switch
model is DISCRIMINATED (both baselines drift where the model is exact). No Dolphin.

    python -m harness.rollstab.validate_draw
"""
import json
import os
import struct
import sys

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.land import LandState

FIX = os.path.join(_rb, 'fixtures', 'walk_draw.json')
UP = dict(stickX=128, stickY=255, buttons=0, triggerL=0, csx=128, csy=128)
DRAW = {**UP, 'buttons': 0x200}


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _seq(fix):
    """The driven input list (one dict/frame). Prefer the exact captured `inputs` (supports the decel
    tail); fall back to reconstructing the all-UP walk for older fixtures."""
    if fix.get('inputs'):
        return [dict(stickX=i['stickX'], stickY=i['stickY'], buttons=i['buttons'],
                     triggerL=i['triggerL'], csx=i['substickX'], csy=i['substickY'])
                for i in fix['inputs']]
    return [UP] * fix['cruise'] + [DRAW] + [UP] * fix['tail']


def _new_sim(fix, model_draw=False):
    s = fix['seed']
    return LandState(pos_z=s['pos_z'], pos_x=s.get('pos_x', 0.0), facing=int(s['shape_angle_y']),
                     travel=int(s['travel_angle']), csangle=int(s['csangle']),
                     state=int(s['link_state']), nspeed=s['potential_speed'],
                     idle_frame=s['anim_frame'], native=False, foot_native=False,
                     model_draw=model_draw)


def run_auto(fix):
    """End-to-end: model_draw=True, feed the RAW captured inputs (incl. the UP+B draw). The B rising
    edge auto-starts the draw and the anim set flips DRAW_DELAY acted-frames later -- no manual poke."""
    sim = _new_sim(fix, model_draw=True)
    rows = fix['rows']
    out = []
    for k, inp in enumerate(_seq(fix)):
        sim.step(inp['stickX'], inp['stickY'], buttons=inp['buttons'],
                 triggerL=inp['triggerL'], csx=inp['csx'], csy=inp['csy'])
        live = rows[k + 1]['pos'][2]
        out.append((k + 1, sim.pos_z, live, abs(_bits(sim.pos_z) - _bits(live))))
    return out


def run(fix, switch_at=None, always_sword=False):
    """Replay; poke draw_sword before producing row `switch_at` (row index into fix['rows']).
    Returns [(row_index, sim_posz, live_posz, ulp)] for the walk rows."""
    sim = _new_sim(fix)
    if always_sword:
        sim._foot.draw_sword()
    seq = _seq(fix)
    rows = fix['rows']
    out = []
    for k, inp in enumerate(seq):
        row_idx = k + 1                      # rows[0]=rest; stepping seq[k] produces rows[k+1]
        if switch_at is not None and row_idx == switch_at:
            sim._foot.draw_sword()
        sim.step(inp['stickX'], inp['stickY'], buttons=inp['buttons'],
                 triggerL=inp['triggerL'], csx=inp['csx'], csy=inp['csy'])
        live = rows[row_idx]['pos'][2]
        out.append((row_idx, sim.pos_z, live, abs(_bits(sim.pos_z) - _bits(live))))
    return out


def _summ(res):
    mx = max(r[3] for r in res)
    bad = [r[0] for r in res if r[3] != 0]
    return mx, bad


def main():
    with open(FIX) as f:
        fix = json.load(f)
    f_flip = fix['f_flip']
    print("fixture: anchor=%s  rest_equip=0x%X  f_flip(row)=%s  b_row=%s"
          % (fix['anchor'], fix['rest_equip'], f_flip, fix['b_row']))
    print("live walk: rows 1..%d ; m3598>0 (toe feeds speedF) on the accel frames only\n" % len(fix['rows'][1:]))

    print("=== baselines ===")
    for label, kw in (("sword=False (never draw)", dict()),
                      ("sword=True  (always drawn)", dict(always_sword=True))):
        res = run(fix, **kw)
        mx, bad = _summ(res)
        print("  %-28s max %2d ULP   mismatched rows: %s" % (label, mx, bad or "none"))

    print("\n=== switch-frame sweep (poke draw_sword before row S) ===")
    best = None
    for S in range(f_flip - 2, f_flip + 3):
        res = run(fix, switch_at=S)
        mx, bad = _summ(res)
        star = ""
        if mx == 0:
            star = "  <== 0-ULP (f_draw)"
            best = S
        print("  switch@row %2d   max %2d ULP   mismatched rows: %-12s%s" % (S, mx, str(bad or "none"), star))

    print("\n=== end-to-end auto (model_draw=True, raw B input, no manual poke) ===")
    ares = run_auto(fix)
    amx, abad = _summ(ares)
    print("  LandState(model_draw=True)   max %2d ULP   mismatched rows: %s" % (amx, abad or "none"))

    if best is not None:
        print("\nPER-FRAME (switch@row %d):" % best)
        print("  row |     sim_pos_z          live_pos_z       ULP")
        for row_idx, sp, lv, ulp in run(fix, switch_at=best):
            print("  %3d | %18.9f  %18.9f  %3d" % (row_idx, sp, lv, ulp))
        print("\nRESULT: from-rest walk with the anim-set switch@row %d is 0-ULP vs live; both baselines drift."
              % best)
    else:
        print("\nNo 0-ULP switch frame found -- investigate (baseline sword=False ULP on the pre-flip rows "
              "would indicate a from-rest seeding gap unrelated to the draw).")


if __name__ == '__main__':
    main()
