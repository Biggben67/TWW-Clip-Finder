"""Ship gate + clean-DTM delivery for a solver hit.

Gate: replay the hit's LITERAL stream FROM REST (rest.rest_state -- bit-exact from row 0,
no live calibration) and assert: the CUT fires, old/new 0-ULP vs the hit, genuine_clip,
approach_clear, new behind BOTH wall planes, and a sliver z-margin (require pred_genuine to hold
at old_z +- MARGIN_Z; with the rest-exact model this is belt-and-braces, not a residual budget).

Deliver: author DTM = [seed] + stream + WATCH_TAIL neutral frames (~2s so the clip is visible),
play via run_dtm(log_frames=N) (clean DTM, NEVER advancewith), and confirm per-frame that the cut
threads the seam live with the end behind both planes.

    python -m harness.rollstab.deliver gate [hit=0]
    python -m harness.rollstab.deliver ship [hit=0] [norelaunch]
"""
import os, sys, json, math, struct
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

from tww_sim.land.land import FRONT_ROLL, CUT_F, CUT_A
from tww_sim.core.fp import f32 as _f
from harness.rollstab import geometry as G
from harness.rollstab import rest as C
from harness.rollstab.solver import HITS_PATH

PLAN_PATH = os.path.join(_rb, '_generated', 'rollstab_ship_plan.json')
WATCH_TAIL = 120
MARGIN_Z = 0.0002


def bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def replay(anchor, stream, dtm_seed=1):
    s = C.rest_state(anchor, dtm_seed=dtm_seed)
    rows = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        rows.append((s.state & 0xFF, s.pos_x, s.pos_z, s.facing & 0xFFFF))
    return rows


def _seam_for(anchor, geo=None, seam=None):
    """The acceptance geometry: an explicit SeamGeo, or one built from a geo-fixture path + the anchor
    camera yaw (a NOVEL seam), else the kaze `geometry` shim (default, byte-identical)."""
    if seam is not None:
        return seam
    if geo is None:
        return G
    from harness.rollstab.seamgeo import SeamGeo
    cs = G.load_seed(anchor)['csangle'] & 0xFFFF
    return SeamGeo(json.load(open(geo)), csangle=cs)


def gate(idx=0, geo=None, seam=None):
    hit = json.load(open(HITS_PATH))[idx]
    anchor = hit['anchor']
    dtm_seed = int(hit.get('dtm_seed', 1))       # the make_dtm leading-poll seed this hit solves on
    sm = _seam_for(anchor, geo=geo or hit.get('geo'), seam=seam)
    stream = [tuple(fr) for fr in hit['stream']]
    rows = replay(anchor, stream, dtm_seed=dtm_seed)
    ci = next((i for i, rr in enumerate(rows) if rr[0] in (CUT_F, CUT_A)), None)
    if ci is None or ci == 0:
        print('FAIL: CUT never fired')
        return None
    old = (rows[ci - 1][1], rows[ci - 1][2])
    new = (rows[ci][1], rows[ci][2])
    roll = [(rr[1], rr[2]) for rr in rows if rr[0] == FRONT_ROLL]
    dOLD = (bits(old[0]) - bits(hit['old'][0]), bits(old[1]) - bits(hit['old'][1]))
    dNEW = (bits(new[0]) - bits(hit['new'][0]), bits(new[1]) - bits(hit['new'][1]))
    gen = sm.genuine_clip(old, new)
    clear = gen and not any(sm.seg_blocked(roll[i], roll[i + 1]) for i in range(len(roll) - 1))
    behindA = sm.wA.pla.func((new[0], sm.LINK_Y, new[1])) < 0
    behindB = sm.wB.pla.func((new[0], sm.LINK_Y, new[1])) < 0
    robust = (sm.pred_genuine((old[0], _f(old[1] + MARGIN_Z)))
              and sm.pred_genuine((old[0], _f(old[1] - MARGIN_Z))))
    ok = dOLD == (0, 0) and dNEW == (0, 0) and gen and clear and behindA and behindB
    print('gate[%d] anchor=%s cut@%d old=(%.7f,%.7f) new=(%.7f,%.7f)' % (
          idx, anchor, ci, old[0], old[1], new[0], new[1]))
    print('  dOLD=%s dNEW=%s gen=%s clear=%s behindA=%s behindB=%s z-margin(%.4f)=%s' % (
          dOLD, dNEW, gen, clear, behindA, behindB, MARGIN_Z, robust))
    print('  %s' % ('PASS (ship)' + ('' if robust else '  [thin sliver: expect live risk]')
                    if ok else 'FAIL -- do NOT ship'))
    if not ok:
        return None
    sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=b)
              for (sx, sy, b) in stream]
    plan = dict(anchor=anchor, hit={k: v for k, v in hit.items() if k != 'stream'},
                stream=[list(x) for x in stream], sticks=sticks, old=list(old), new=list(new),
                cut_idx=ci, robust=bool(robust), dtm_seed=dtm_seed, geo=(geo or hit.get('geo')),
                rows=[[r[0], r[1], r[2], r[3]] for r in rows])
    json.dump(plan, open(PLAN_PATH, 'w'))
    print('  wrote %s' % PLAN_PATH)
    return plan


def ship(idx=0, norelaunch=False, geo=None, seam=None, golden=None):
    from harness.dtm.run_dtm import run_dtm, land_ready
    plan = gate(idx, geo=geo, seam=seam)
    if plan is None:
        return 1
    sm = _seam_for(plan['anchor'], geo=plan.get('geo'), seam=seam)
    # C-down (substickY=0) = the free-cam pin for a novel/seed-0 anchor (else the auto-cam swings csangle
    # off the frozen sim value); csy=128 byte-identical for proven anchors. Same rule as rest.main.
    csy = 0 if (plan.get('geo') or seam is not None or int(plan.get('dtm_seed', 1)) == 0) else 128
    sticks = [dict(sk, substickY=csy) for sk in plan['sticks']]
    sticks += [dict(stickX=128, stickY=128, substickX=128, substickY=csy, buttons=0)] * WATCH_TAIL
    log_n = plan['cut_idx'] + 14
    end = run_dtm(sticks, anchor=plan['anchor'], ready=land_ready,
                  relaunch_dolphin=not norelaunch, log_frames=log_n, verbose=True,
                  seed=int(plan.get('dtm_seed', 1)))
    frames = end['log']
    live_cut = next((i for i, f in enumerate(frames) if f['proc'] in (0x42, 0x41)), None)
    for i, f in enumerate(frames):
        if live_cut is not None and abs(i - live_cut) <= 3:
            tag = '  <== old' if i == live_cut - 1 else ('  <== CUT' if i == live_cut else '')
            print('  f%3d proc=0x%02x pos=(%.6f,%.6f)%s' % (i, f['proc'], f['pos_x'],
                                                            f['pos_z'], tag), flush=True)
    if live_cut is None:
        print('FAIL: no CUT frame in the live log')
        return 1
    lo = (frames[live_cut - 1]['pos_x'], frames[live_cut - 1]['pos_z'])
    ln = (frames[live_cut]['pos_x'], frames[live_cut]['pos_z'])
    threads = sm.genuine_clip(lo, ln)
    behindA = sm.wA.pla.func((ln[0], sm.LINK_Y, ln[1])) < 0
    behindB = sm.wB.pla.func((ln[0], sm.LINK_Y, ln[1])) < 0
    d = (lo[0] - plan['old'][0], lo[1] - plan['old'][1])
    ok = threads and behindA and behindB
    print('LIVE old=(%.7f,%.7f) new=(%.7f,%.7f) drift-vs-sim d(old)=(%.6f,%.6f)' % (
          lo[0], lo[1], ln[0], ln[1], d[0], d[1]))
    print('%s: threads=%s behindA=%s behindB=%s' % (
          'CLIP CONFIRMED' if ok else 'CHECK', threads, behindA, behindB))
    if ok and golden:
        # Live-data-backed immutable golden (SESSION_PROMPT): `stream`/`sim_*` = the from-rest prediction,
        # `live_*` = the clean-DTM frames; the gate asserts sim==live 0-ULP. NEVER edit to make the sim pass.
        gd = dict(anchor=plan['anchor'], geo=plan.get('geo'), dtm_seed=int(plan.get('dtm_seed', 1)),
                  hit=plan['hit'], stream=[list(x) for x in plan['stream']],
                  sim_old=list(plan['old']), sim_new=list(plan['new']),
                  cut_idx=plan['cut_idx'], live_cut_frame=live_cut,
                  live_old=list(lo), live_new=list(ln),
                  threads=bool(threads), behindA=bool(behindA), behindB=bool(behindB),
                  live=[dict(proc=f['proc'] & 0xFF, pos_x=f['pos_x'], pos_z=f['pos_z'],
                             pos_y=f.get('pos_y', 0.0), facing=f['facing'] & 0xFFFF)
                        for f in frames])
        os.makedirs(os.path.dirname(golden), exist_ok=True)
        json.dump(gd, open(golden, 'w'), indent=1)
        print('  live golden -> %s' % golden)
    return 0 if ok else 1


if __name__ == '__main__':
    idx = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('hit=')), 0)
    geo = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('geo=')), None)
    golden = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('golden=')), None)
    if 'ship' in sys.argv:
        sys.exit(ship(idx, norelaunch=('norelaunch' in sys.argv), geo=geo, golden=golden))
    sys.exit(0 if gate(idx, geo=geo) else 1)
