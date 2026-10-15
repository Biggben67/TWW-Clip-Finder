"""pushaside.py -- mint / author / deliver / diff the TETRA PUSH-ASIDE SEAM CLIP (the Phase-T clip).

The clip (session 22, LIVE bit-exact): Tetra stands at her spot from the START (``placed_step=0``, an
initial setup var -- **no mid-run write**); Link's roll PLOWS her aside; her CC push steers the roll-stab
``CUT_F`` lunge through the seam at the flooded-Hyrule (-1727,-990) corner. Delivered by a CLEAN DTM.

This module is the SHIPPED recipe. It exists because getting the clip out of the sim and into the game
cost four non-obvious delivery truths, each of which looked like "the sim is wrong" and was not. They are
ENCODED here -- do not re-derive them (see `knowledge/history/seam-clip-dead-ends.md` #21-24):

1. **Tetra's START must be on WALKABLE floor** (`in_front` of BOTH seam walls). The coupled sim clamps her
   to the flat ground plane everywhere and NEVER models her falling, so it will happily "stand" her behind
   a wall and report a genuine clip. Live she drops OOB, delivers **no push at all**, and the bare cut is
   wall-blocked. `assert_walkable()` guards this.
2. **The ROLL PHASE must hold a NEUTRAL stick, not UP.** A pushed stick (`msd > 0.05`) force-exits
   FRONT_ROLL the instant `roll_frame > ROLL_EARLY` (`land/procs/roll.py`), so the CUT can never fire OUT
   of the roll -- the B degrades to a plain MOVE-slash (proc 90 recoil, no lunge). Deliver the SIM's OWN
   schedule (`fast_shove.make_inputs`: NEUTRAL + one UP+B), NOT the capture fixture's UP-held sticks.
   Symptom of getting this wrong: proc 30 -> 6 instead of 30 -> 66.
3. **The B goes ONE STEP LATER in the DTM than in the sim.** The sim buffers B with a 2-step INPUT_DELAY
   (B at step 14 -> CUT at step 16); the clean DTM delivers it with 1. So B sits at sim-step 15 (`B_STEP`).
4. **Seed the sim at the DTM's ACTUAL roll entry**, not the capture fixture's. `dtm_make` calibrates
   sticks (255->254), so the delivered walk enters the roll ~0.004u away from the advancewith capture's
   entry -- and on f32 DUST that is block-vs-clip. Seeded at the real entry the engine is **0-ULP vs live
   on every frame for BOTH actors, including the cut**.

Method rule (worth more than the clip): when live disagrees with the sim, do NOT tweak inputs by
guesswork -- run `diff` below (it logs BOTH actors per frame) and the divergence frame names the bug.

    python -m harness.rollstab.pushaside mint                 # place Tetra + save the DTM anchor (live)
    python -m harness.rollstab.pushaside deliver              # author + play the clean DTM, print the clip
    python -m harness.rollstab.pushaside diff                 # per-frame Link+Tetra DTM-vs-sim diff
    python -m harness.rollstab.pushaside search               # re-solve placements at a given roll entry

Live steps need Dolphin (slot 6). `search` is offline.
"""
import json
import math
import os
import shutil
import struct
import sys
import time

# >>> repo bootstrap
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

from tww_sim.land.land import FRONT_ROLL
from harness.rollstab import fast_shove as FS
from harness.rollstab import geometry_tetra as GT
from harness.rollstab.cc_stepper import LINK_CO_R, TETRA_CO_R

# --- the shipped clip (session 22, live bit-exact) -------------------------------------------------
SLOT = 6
THRUST = 14                      # the sim schedule (make_inputs); its CUT lands on step 16
B_STEP = 15                      # truth #3: the DTM's B sits ONE STEP LATER than the sim's (step 14)
TETRA_XZ = (-1652.2239990234375, -939.447998046875)          # walkable, bit-confirmed genuine
ROLL_ENTRY = (-1513.3475341796875, -763.5128784179688)        # truth #4: the DTM's REAL entry
GROUND_Y = 0.1632676
ANCHOR = os.path.join(_rb, '_generated', 'pushaside_roll6.sav')
DTM_OUT = os.path.join(_rb, '_generated', 'pushaside.dtm')

# live addresses (slot 6; tetra_base confirmed type-5)
TETRA_BASE = 0x80ACD20C
T_POS, T_SPEEDF, T_TYPE = 0x1F8, 0x254, 0x84F
LINK_PTR = 0x803AD860
L_POS_X, L_POS_Z, L_SPEEDF, L_CURPROC = 0x120, 0x128, 0x17C, 0x3100
L_SHAPE_Y, L_SHAPE_Z = 0x136, 0x138        # shape_angle.y (facing), shape_angle.z (=m351C>>1)

CUT_F_PROC, FALL_PROC = 66, 39
SUM_R = LINK_CO_R + TETRA_CO_R


# --- constraint guards (truth #1) ------------------------------------------------------------------

def is_walkable(x, z):
    """Tetra can only STAND in front of BOTH seam walls. Off it she falls OOB -> no push -> no clip.
    The sim cannot tell you this: it clamps her to flat ground everywhere and never models falling."""
    p = GT.p32(x, z)
    return GT.wA.pla.func(p) > 0 and GT.wB.pla.func(p) > 0


def _d2seg(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def walk_clear(x, z, fix=None, margin=10.0):
    """Tetra must sit clear of Link's pre-roll WALK path: the engine only models the ROLL, so a
    walk-phase CC contact would move her before the roll and desync sim from live."""
    fix = fix or FS.load_fixture()
    rows = fix['frames']
    e = next(i for i, r in enumerate(rows) if r['link']['proc'] == FRONT_ROLL)
    wp = [(r['link']['pos'][0], r['link']['pos'][2]) for r in rows[:e + 1]]
    return min(_d2seg(x, z, wp[i][0], wp[i][1], wp[i + 1][0], wp[i + 1][1])
               for i in range(len(wp) - 1)) > SUM_R + margin


def assert_walkable(x, z):
    if not is_walkable(x, z):
        p = GT.p32(x, z)
        raise SystemExit("Tetra start (%r, %r) is NOT on walkable floor (fA=%.2f fB=%.2f). She would "
                         "fall OOB and deliver NO push. See dead-end #21."
                         % (x, z, GT.wA.pla.func(p), GT.wB.pla.func(p)))


# --- the sim side ----------------------------------------------------------------------------------

def sim(tetra_xz=TETRA_XZ, entry=ROLL_ENTRY, thrust=THRUST):
    """Coupled-engine prediction, seeded at the DTM's REAL roll entry (truth #4).
    Returns (result_dict, per-step [(link_x, link_z, tet_x, tet_z)], schedule)."""
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    inputs = FS.make_inputs(thrust)
    ctx, sch = FS.build_ctx(fix, walls, inputs)
    res, steps = ctx.run_trace(tetra_xz[0], tetra_xz[1], 0, link_x0=entry[0], link_z0=entry[1])
    return res, steps, sch


# --- the DTM sticks (truths #2 and #3) -------------------------------------------------------------

def build_sticks(thrust=THRUST, b_step=B_STEP, tail=20):
    """The delivered stick stream.

    Walk phase = the fixture's captured walk (UP x14 + the A roll press at fixture frame 15).
    ROLL phase = the SIM's OWN schedule (`make_inputs`): **NEUTRAL** holds + one UP+B thrust (truth #2),
    with the B moved ONE STEP LATER than the sim's (truth #3).

    Frame mapping (measured, and the thing that makes the whole alignment work):
        sim step k  ==  live frame (roll_entry + 1 + k)  ==  sticks[16 + k]
    """
    fix = FS.load_fixture()
    rows = fix['frames']
    inputs = FS.make_inputs(thrust)
    NEU = dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0)
    sticks = []
    for r in rows[1:16]:                      # fixture frames 1..15: walk UP, A press at 15
        inp = r['inp']
        sticks.append(dict(stickX=int(inp['stickX']), stickY=int(inp['stickY']),
                           substickX=int(inp.get('substickX', 128)),
                           substickY=int(inp.get('substickY', 128)),
                           buttons=int(inp.get('buttons', 0))))
    sticks.append(dict(NEU))                  # sticks[15] -> the roll-entry row (sim seeds here)
    for inp in inputs:                        # sticks[16+k] -> sim step k
        sticks.append(dict(stickX=inp[0], stickY=inp[1], buttons=inp[2],
                           substickX=inp[4], substickY=inp[5]))
    for s in sticks[16:]:                     # strip the sim's B; re-place it one step later
        if s['buttons'] == 0x200:
            s['buttons'] = 0
            s['stickX'], s['stickY'] = 128, 128
    sticks[16 + b_step] = dict(stickX=128, stickY=255, substickX=128, substickY=128, buttons=0x200)
    sticks += [dict(NEU)] * tail
    return sticks


# --- live: mint the anchor -------------------------------------------------------------------------

def mint(tetra_xz=TETRA_XZ, slot=SLOT, out=ANCHOR):
    """Load the slot, place Tetra at her exact f32 spot, save the DTM anchor. NO frame is advanced
    between load and save (letting the game run would desync the anchor)."""
    import dolphin_mem as dm
    assert_walkable(*tetra_xz)
    h, mem1 = dm.attach()

    def rf(a):
        return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]

    def wf(a, v):
        dm.write_bytes(h, mem1, a, struct.pack('>f', v))

    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    time.sleep(0.3)
    typ = struct.unpack('>b', dm.read_bytes(h, mem1, TETRA_BASE + T_TYPE, 1))[0]
    if typ != 5:
        raise SystemExit("not the type-5 Tetra at 0x%08X (got %d) -- wrong slot?" % (TETRA_BASE, typ))
    wf(TETRA_BASE + T_POS, tetra_xz[0])
    wf(TETRA_BASE + T_POS + 4, GROUND_Y)
    wf(TETRA_BASE + T_POS + 8, tetra_xz[1])
    wf(TETRA_BASE + T_SPEEDF, 0.0)
    ax, az = rf(TETRA_BASE + T_POS), rf(TETRA_BASE + T_POS + 8)
    if struct.pack('>f', ax) != struct.pack('>f', tetra_xz[0]) or \
       struct.pack('>f', az) != struct.pack('>f', tetra_xz[1]):
        raise SystemExit("Tetra placement did not land on the exact f32")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    dm.control_pipe_quiet("savestate", {"action": "save", "path": out})
    time.sleep(0.3)
    print("Tetra @ (%r, %r) [walkable]; anchor -> %s" % (ax, az, out))
    return out


# --- live: author + play + log BOTH actors ---------------------------------------------------------

def play(anchor=ANCHOR, sticks=None, nlog=40, relaunch_dolphin=True):
    """Author the clean DTM, play it, and single-step-log BOTH Link and Tetra per frame.

    NOTE on delivery: `run_dtm(log_frames=)` logs Link only, which is why this exists -- the Tetra
    column is what proves the plow. For a pure PASS/FAIL (no trace) prefer a FREE-RUN `run_dtm` call.
    """
    import dolphin_mem as D
    import dtm_make as DM
    from harness.dtm.run_dtm import relaunch, land_ready, _attach_ready, DEFAULT_TEMPLATE
    from harness import dolphin_env

    sticks = sticks if sticks is not None else build_sticks()
    DM.build_dtm_from_sticks(sticks, DTM_OUT, DEFAULT_TEMPLATE, 4, 1)
    shutil.copyfile(anchor, DTM_OUT + ".sav")
    shutil.copyfile(DTM_OUT, DTM_OUT + ".sav.dtm")
    if relaunch_dolphin:
        relaunch(True)
    D.control_pipe_quiet("playmovie", {"path": DTM_OUT.replace('\\', '/'),
                                       "game": dolphin_env.iso_path("twwgz")})
    t0 = time.time()
    slate = None
    while time.time() - t0 < 180 and not slate:
        slate = _attach_ready(land_ready)
        if not slate:
            time.sleep(0.2)
    if not slate:
        raise SystemExit("never reached the anchor-loaded gate")
    h, mem1, _ = slate
    D.control_pipe_quiet("pause")

    def rf(a):
        return struct.unpack('>f', D.read_bytes(h, mem1, a, 4))[0]

    def ri(a):
        return struct.unpack('>i', D.read_bytes(h, mem1, a, 4))[0]

    rows = []
    for i in range(nlog):
        P = struct.unpack('>I', D.read_bytes(h, mem1, LINK_PTR, 4))[0]
        rows.append(dict(f=i, proc=ri(P + L_CURPROC), lx=rf(P + L_POS_X), lz=rf(P + L_POS_Z),
                         spF=rf(P + L_SPEEDF), tx=rf(TETRA_BASE + T_POS),
                         tz=rf(TETRA_BASE + T_POS + 8),
                         lfac=struct.unpack('>H', D.read_bytes(h, mem1, P + L_SHAPE_Y, 2))[0],
                         lsz=struct.unpack('>h', D.read_bytes(h, mem1, P + L_SHAPE_Z, 2))[0]))
        D.control_pipe_quiet("advance", {"frames": 1})
    return rows


def report(rows, res):
    """Did it clip? The CUT_F endpoint must equal the sim's `new` bit-for-bit, and Link must then FALL
    (proc 39) -- i.e. he is THROUGH the seam."""
    cut = [r for r in rows if r['proc'] == CUT_F_PROC]
    if not cut:
        print("NO CLIP: the CUT_F never fired (proc 66 absent).")
        print("  -> if the roll went 30 -> 6 (MOVE), you delivered an UP stick through the roll "
              "(truth #2) or the B is on the wrong step (truth #3).")
        return False
    got = (cut[0]['lx'], cut[0]['lz'])
    exact = got == tuple(res['new'])
    fell = [r for r in rows if r['proc'] == FALL_PROC and r['f'] > cut[0]['f']]
    print("CUT_F  @ f%d  live new = (%r, %r)" % (cut[0]['f'], got[0], got[1]))
    print("            sim  new = (%r, %r)" % (res['new'][0], res['new'][1]))
    print("  bit-exact: %s   fell through the seam (proc 39): %s" % (exact, bool(fell)))
    if exact and fell:
        print("*** CLIP CONFIRMED LIVE ***")
    elif not exact:
        print("  -> `new` differs: the sim was almost certainly seeded at the WRONG roll entry "
              "(truth #4). Re-read the live entry and re-run `search`.")
    return bool(exact and fell)


def diff(tetra_xz=TETRA_XZ, entry=ROLL_ENTRY, nlog=40):
    """The tool that cracked this: per-frame DTM-vs-SIM diff for BOTH actors. The divergence frame
    names the bug. NEVER guess inputs -- run this."""
    res, steps, _ = sim(tetra_xz, entry)
    rows = play(nlog=nlog)
    e = next((r['f'] for r in rows if r['proc'] == FRONT_ROLL), None)
    print("\nsim genuine=%s old=%r new=%r" % (res['genuine'], res['old'], res['new']))
    print("live roll entry frame: %s   (alignment: sim step k == live frame entry+1+k)\n" % e)
    print(" f  proc  LINK live (x,z)             TETRA live (x,z)          |  k   dLink    dTetra")
    for r in rows:
        k = (r['f'] - e - 1) if e is not None else None
        s = steps[k] if (k is not None and 0 <= k < len(steps)) else None
        if s:
            dl = math.hypot(r['lx'] - s[0], r['lz'] - s[1])
            dt = math.hypot(r['tx'] - s[2], r['tz'] - s[3])
            print("%2d  %3d  (%11.4f,%11.4f) (%11.4f,%11.4f) | k%-2d %8.5f %8.5f %s"
                  % (r['f'], r['proc'], r['lx'], r['lz'], r['tx'], r['tz'], k, dl, dt,
                     "<== DIVERGE" if (dl > 1e-4 or dt > 1e-4) else ""))
        else:
            print("%2d  %3d  (%11.4f,%11.4f) (%11.4f,%11.4f) |"
                  % (r['f'], r['proc'], r['lx'], r['lz'], r['tx'], r['tz']))
    report(rows, res)
    return rows, res


# --- offline: re-solve placements at a given roll entry ---------------------------------------------

def search(entry=ROLL_ENTRY, x0=-1662.0, x1=-1642.0, z0=-946.0, z1=-928.0, step=0.008,
           thrust=THRUST, verbose=True):
    """Walkable + walk-clear + bit-confirmed genuine Tetra placements AT A GIVEN ROLL ENTRY.

    Re-run this whenever the delivered walk changes (a different anchor / stick stream moves the roll
    entry, and on f32 dust a ~0.004u entry shift is block-vs-clip -- truth #4)."""
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    inputs = FS.make_inputs(thrust)
    ctx, _ = FS.build_ctx(fix, walls, inputs)
    grid = []
    x = x0
    while x <= x1:
        z = z0
        while z <= z1:
            if is_walkable(x, z):
                grid.append((x, z))
            z += step
        x += step
    rs = ctx.sweep_par([(p[0], p[1], entry[0], entry[1]) for p in grid], 0)
    hits = []
    for p, r in zip(grid, rs):
        if not r[0]:
            continue
        _, tr = ctx.run_trace(p[0], p[1], 0, link_x0=entry[0], link_z0=entry[1])
        if not all(is_walkable(s[2], s[3]) for s in tr):      # her PLOW path must stay on floor too
            continue
        if not walk_clear(p[0], p[1], fix):
            continue
        ref, _ = FS.py_reference(fix, walls, inputs, p, 0, link_entry=entry)
        if not (ref['genuine'] and ref['new'] == (r[3], r[4])):
            continue
        fx = struct.unpack('<f', struct.pack('<f', p[0]))[0]
        fz = struct.unpack('<f', struct.pack('<f', p[1]))[0]
        hits.append(dict(tetra=[fx, fz], old=[r[1], r[2]], new=[r[3], r[4]]))
    if verbose:
        print("%d sims @ entry (%r, %r) -> %d walkable+clear+bit-confirmed genuine"
              % (len(grid), entry[0], entry[1], len(hits)))
        for h in hits[:10]:
            print("  tetra=(%r, %r) new=(%.4f, %.4f)" % (h['tetra'][0], h['tetra'][1],
                                                         h['new'][0], h['new'][1]))
    out = os.path.join(_rb, '_generated', 'pushaside_hits.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(hits, open(out, 'w'), indent=1)
    return hits


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'diff'
    if mode == 'mint':
        mint()
    elif mode == 'deliver':
        res, _, _ = sim()
        report(play(), res)
    elif mode == 'diff':
        diff()
    elif mode == 'search':
        search()
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
