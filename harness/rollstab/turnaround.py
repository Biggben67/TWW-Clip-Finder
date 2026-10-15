"""turnaround.py -- the FOLLOW-ENABLED Tetra seam clip via the A+stick TURNAROUND ROLL (slot 7).

The session-22 push-aside clip ([[tetra-clip-solved-live]], `pushaside.py`) relied on Tetra being in a
GLITCHED no-follow state -- slow to set up, not the real tech. This module is the "kill the glitched
Tetra" successor: a NORMAL following Tetra (type-5), herded to / placed in the corner, plus a from-rest
walk + one-frame turnaround roll that plows her aside and steers the roll-stab `CUT_F` lunge through the
seam at the flooded-Hyrule (-1727,-990) corner. Dereck's slot-7 setup: Tetra following-enabled idle in
the corner, Link behind her facing away, sword OUT.

THE MECHANIC (all sim-validated, session 23):
- Hold **DOWN** (camera-relative; = Link's away-facing) for ~6 frames: speedF ramps to the 17.0 walk cap
  by ~frame 5, Tetra stays inside her 130/230 follow band so she never engages (`core.npc_zl1`).
- One frame **A + a diagonal stick** = the turnaround roll ([[turnaround-roll-tech]]): `_roll_init` snaps
  facing to the stick target (toward the corner) and enters FRONT_ROLL at nspeed 26 (the FULL ~49u lunge,
  because speedF was 17 at the A press -- the roll SPEED comes from the walk cap, NOT the stick magnitude,
  so the entry stick is free to AIM precisely). Facing away from Tetra dodges her talk cone (no talk).
- **NEUTRAL** through the roll (a pushed stick force-exits FRONT_ROLL early -- `land/procs/roll.py`).
- **UP+B** fires the in-line CUT_F out of the roll (a neutral B is a side slash -- dead-end #12).

THE HARD CONSTRAINT (session 23): the CUT lunge must aim THROUGH the fixed corner seam-gap -- a tight
angular window at facing **~40842** (224.35 deg). Outside it, `new` stays wall-pinned ~49u short and NO
Tetra push helps. The octagon stick VERTEX (a_sx,255) only reaches 40758/40913 (miss); a **DIAGONAL**
stick **(108,204) -> 40835** or **(108,203) -> 40849** hits the window under the slot-7 camera
(csangle 39981) with msd 1.0 -- no camera change needed.

DELIVERY = the session-22 recipe (`pushaside.py` truths #2/#3/#4). The genuine Tetra placement is f32
DUST sensitive to the roll ENTRY (a ~0.2u entry shift relocates the whole genuine region), and the
from-rest walk is not yet bit-exact, so: deliver the walk+turnaround DTM, MEASURE the real roll entry
(`entry` mode), fine-search Tetra placements at THAT entry (`search`), place her on a bit-confirmed spot,
deliver + per-frame diff (`diff`) -- NEVER guess inputs.

    python -m harness.rollstab.turnaround search        # offline: genuine Tetra placements at an entry
    python -m harness.rollstab.turnaround entry         # live: deliver walk+turnaround, read the roll entry
    python -m harness.rollstab.turnaround deliver        # live: full clip (Tetra placed + thrust)
    python -m harness.rollstab.turnaround diff          # live: per-frame Link+Tetra DTM-vs-sim diff

Live modes need Dolphin on slot 7. `search` is offline.
"""
import json
import math
import os
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

from tww_sim.core import mathlib as ML
from tww_sim.core.fp import f32, fmuls
from tww_sim.core.anim import body_cyl
from tww_sim.core.cc_push import push_shares, WEIGHT_LINK, WEIGHT_TETRA_V5
from tww_sim.core.npc_zl1 import Zl1FollowState, STT_IDLE
from tww_sim.land.land import LandState, WAIT, FRONT_ROLL, CUT_F, CUT_A
from tww_sim.land.walls import load_ordered_mesh, cull_walls, WALL_H, WALL_R, GRAVITY
from harness.rollstab.cc_stepper import (CcCoupledStepper, LINK_CO_R, LINK_CO_H,
                                         TETRA_CO_R, TETRA_CO_H)
from harness.rollstab import fast_shove as FS
from harness.rollstab import geometry_tetra as GT
from harness.rollstab import pushaside as PA   # reuse play/report + the (shared) live addresses

# --- slot-7 live setup (Dereck, session 23; read live via probe -- re-read before trusting) ---------
SLOT = 7
LINK_START = (-1601.9906005859375, 0.16326415538787842, -872.5116577148438)
LINK_FACING = 7213               # shape_angle.y (also travel); the away-from-Tetra facing
CSANGLE = 39981                  # dCam_getControledAngleY: stick-DOWN = walk NE away; stick-UP = SW
TETRA_START = (-1666.0159912109375, 0.16326923668384552, -940.255615234375)
TETRA_FACING = 7286
GROUND_Y = 0.1632676
S_VERTEX = (-1727.0, -990.0)

# The delivered stick schedule (raw controller bytes; the sim's INPUT_DELAY buffers them).
DOWN = (128, 0, 0, 0, 128, 128)             # walk away, build to the 17 cap
NEU = (128, 128, 0, 0, 128, 128)
TURN = (108, 204, 0x100, 0, 128, 128)       # A + diagonal stick -> facing ~40835 (in the seam-gap window)
UPB = (128, 255, 0x200, 0, 128, 128)        # forward CUT_F thrust out of the roll
N_WALK = 6                                  # DOWN frames (speedF caps at ~5; 6 keeps a follow-safe entry)
THRUST = 14                                 # sim schedule thrust step (its CUT lands +2 -> sim step 16)
B_STEP = 16                                 # DTM UP+B roll-index, live-calibrated: fires the CUT on the
#   sim-step-16 frame (b_step=15 fires it a frame early -> no lunge). +2 vs sim thrust; see README Status.
FAR = (-1670.0, -3000.0)                    # Tetra parking spot for the entry sim
_ROLL_POSE = (FRONT_ROLL, CUT_F, CUT_A)

ANCHOR = os.path.join(_rb, '_generated', 'turnaround_roll7.sav')
ENTRY_JSON = os.path.join(_rb, '_generated', 'turnaround_entry.json')   # entry mode -> search/deliver

_full = load_ordered_mesh(FS.WALLS_FIX)
WALLS = cull_walls(_full, -1770.0, -1020.0, -1500.0, -760.0, margin=250.0)
SUM_R = LINK_CO_R + TETRA_CO_R


def is_walkable(x, z):
    p = GT.p32(x, z)
    return GT.wA.pla.func(p) > 0 and GT.wB.pla.func(p) > 0


# --- the walk+turnaround entry (Python coupled stepper, Tetra parked far) --------------------------

def entry_from_walk(link0=LINK_START, facing0=LINK_FACING, csangle=CSANGLE, n_walk=N_WALK,
                    turn=TURN):
    """Sim the from-rest DOWN-walk + A+turnaround with Tetra parked FAR (no coupling). Return the roll
    ENTRY state at the FIRST FRONT_ROLL frame + the Link walk trajectory (for the follow-dist check)."""
    link = LandState(pos_x=link0[0], pos_z=link0[2], pos_y=link0[1], facing=facing0, travel=facing0,
                     csangle=csangle, state=WAIT, nspeed=0.0, speedF=0.0, use_anim=True,
                     native=False, sword_drawn=True, walls=WALLS)
    tetra = Zl1FollowState(x=FAR[0], y=GROUND_Y, z=FAR[1], angle_y=facing0, speedF=0.0, stt=STT_IDLE)
    drv = CcCoupledStepper(link, tetra, walls_tetra=WALLS, ground_y=GROUND_Y)
    traj = []
    for inp in ([DOWN] * n_walk) + [turn] + [NEU] * 6:
        drv.step(*inp)
        traj.append((link.pos_x, link.pos_z))
        if (link.state & 0xFF) == FRONT_ROLL:
            return dict(x=link.pos_x, z=link.pos_z, facing=link.facing, m351C=link.m351C & 0xFFFF,
                        nspeed=link.nspeed, y=link0[1], traj=traj)
    return None


# --- the facing-override native schedule (fast_shove bakes facing into dx/dz/cutx/cutz/chx/chz) -----

def extract_schedule_at(entry, facing, m351C, link_y, inputs):
    """FS.extract_schedule, seeded at an EXPLICIT (entry, facing, m351C) rather than the fixture's.
    Verified bit-exact vs FS.extract_schedule when given the fixture entry/facing (session 23)."""
    link = LandState(pos_x=entry[0], pos_z=entry[1], pos_y=link_y, facing=facing, travel=facing,
                     state=FRONT_ROLL, nspeed=26.0, speedF=26.0, use_anim=True, native=False,
                     sword_drawn=True, walls=WALLS)
    link._roll_m3570 = False
    link.m351C = int(m351C) & 0xFFFF
    tetra = Zl1FollowState(x=FAR[0], y=GROUND_Y, z=f32(FS.FAR_TETRA_Z), angle_y=facing, speedF=0.0,
                           stt=STT_IDLE)
    drv = CcCoupledStepper(link, tetra, walls_tetra=WALLS, ground_y=GROUND_Y)
    dx, dz, cutx, cutz, is_pose, chx, chz = [], [], [], [], [], [], []
    cut_step = None
    nroot = None
    for k, inp in enumerate(inputs):
        drv.step(*inp)
        st = link.state & 0xFF
        d = link.speedF
        dx.append(fmuls(d, ML.cM_ssin_s16(link.travel)))
        dz.append(fmuls(d, ML.cM_scos_s16(link.travel)))
        if st in (CUT_F, CUT_A) and cut_step is None:
            cut_step = k
            m37 = link._cut_m3700_at(st, link.cut_frame)
            s_ = ML.cM_ssin_s16(link.facing)
            c_ = ML.cM_scos_s16(link.facing)
            cutx.append(f32(f32(m37[2] * s_) + f32(m37[0] * c_)))
            cutz.append(f32(f32(m37[2] * c_) - f32(m37[0] * s_)))
        else:
            cutx.append(0.0)
            cutz.append(0.0)
        pose = st in _ROLL_POSE and body_cyl.available()
        is_pose.append(1 if pose else 0)
        if pose:
            rc, nc = body_cyl.roll_co_chain_consts(link.facing, link.roll_frame,
                                                   shape_z=getattr(link, '_draw_lean', 0))
            nroot = len(rc)
            chx.append([c[0] for c in rc] + [c[0] for c in nc])
            chz.append([c[1] for c in rc] + [c[1] for c in nc])
        else:
            chx.append(None)
            chz.append(None)
        if cut_step is not None:
            break
    if cut_step is None:
        raise ValueError("schedule never reached a CUT (thrust too early/late for this entry)")
    nlvl = max(len(c) for c in chx if c is not None)
    chx = [c if c is not None else [0.0] * nlvl for c in chx]
    chz = [c if c is not None else [0.0] * nlvl for c in chz]
    return dict(dx=dx, dz=dz, cutx=cutx, cutz=cutz, is_pose=is_pose, chx=chx, chz=chz,
                nroot=nroot, cut_step=cut_step, link_x0=entry[0], link_z0=entry[1], link_y=link_y,
                tet_seed=(FAR[0], f32(GROUND_Y), f32(FS.FAR_TETRA_Z), int(facing) & 0xFFFF, 0.0,
                          STT_IDLE))


def build_ctx_at(entry, facing, m351C, link_y, thrust=THRUST, margin=140.0):
    from tww_sim.core._shovec import ShoveCtx
    sch = extract_schedule_at(entry, facing, m351C, link_y, FS.make_inputs(thrust))
    sh = push_shares(WEIGHT_LINK, WEIGHT_TETRA_V5)
    ctx = ShoveCtx(WALLS, GT.TRIS, GT.wA.pla, GT.wB.pla, GT.LINK_Y,
                   ML._SIN_TABLE, ML._COS_TABLE, ML._ATN_TABLE,
                   sch['dx'], sch['dz'], sch['cutx'], sch['cutz'], sch['is_pose'],
                   sch['chx'], sch['chz'], sch['nroot'], sch['cut_step'],
                   sch['link_x0'], sch['link_z0'], sch['link_y'],
                   WALL_H, WALL_R, GRAVITY,
                   sch['tet_seed'], FS.TET_WH, FS.TET_R, GROUND_Y,
                   LINK_CO_R, LINK_CO_H, TETRA_CO_R, TETRA_CO_H,
                   sh[1], sh[0], margin=margin)
    return ctx, sch


def follow_safe(tetra_xz, walk_traj, link0):
    """dist(Link,Tetra) <= 230 over the whole walk (she never engages); no initial Co overlap."""
    tx, tz = tetra_xz
    if any(math.hypot(lx - tx, lz - tz) > 230.0 for (lx, lz) in walk_traj):
        return False
    return math.hypot(link0[0] - tx, link0[2] - tz) > SUM_R


# --- the placement search (native Tetra-f32 sweep at a GIVEN roll entry) ----------------------------

def search(entry, facing, m351C, link_y, link0=LINK_START, walk_traj=None,
           gx=(-1700, -1600), gz=(-1000, -900), step=0.008, thrust=THRUST, verbose=True):
    """Bit-confirmed genuine Tetra placements (placed_step=0) at a GIVEN roll entry+facing.
    Seed `entry`/`facing`/`m351C` from `entry` mode's measured live roll entry (the region is f32-dust
    sensitive to the entry -- see the module docstring). `walk_traj` gates the follow constraint."""
    ctx, sch = build_ctx_at(entry, facing, m351C, link_y, thrust)
    grid = []
    x = gx[0]
    while x <= gx[1]:
        z = gz[0]
        while z <= gz[1]:
            grid.append((x, z))
            z += step
        x += step
    rs = ctx.sweep_par([(p[0], p[1], entry[0], entry[1]) for p in grid], 0)
    hits = []
    for p, r in zip(grid, rs):
        if not r[0] or not is_walkable(p[0], p[1]):
            continue
        if walk_traj is not None and not follow_safe((p[0], p[1]), walk_traj, link0):
            continue
        _, tr = ctx.run_trace(p[0], p[1], 0, link_x0=entry[0], link_z0=entry[1])
        if not all(is_walkable(s[2], s[3]) for s in tr):
            continue
        hits.append(dict(tetra=[struct.unpack('<f', struct.pack('<f', p[0]))[0],
                                struct.unpack('<f', struct.pack('<f', p[1]))[0]],
                         old=[r[1], r[2]], new=[r[3], r[4]], push=[r[5], r[6]]))
    if verbose:
        print("%d sims @ entry (%r,%r) facing=%d -> %d walkable+follow-safe+genuine"
              % (len(grid), entry[0], entry[1], facing, len(hits)))
        for h in hits[:8]:
            print("  tetra=(%r,%r) new=(%.4f,%.4f)" % (h['tetra'][0], h['tetra'][1],
                                                       h['new'][0], h['new'][1]))
    out = os.path.join(_rb, '_generated', 'turnaround_hits.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(hits, open(out, 'w'), indent=1)
    return hits


# --- the delivered stick stream --------------------------------------------------------------------

def build_sticks(n_walk=N_WALK, turn=TURN, thrust=THRUST, b_step=None, roll_hold=20, tail=20):
    """Raw controller stream: DOWN*n_walk (walk away) + turnaround (A+diagonal) + NEUTRAL roll +
    UP+B thrust + neutral tail. `b_step` = the UP+B index into the roll (from the turnaround frame);
    None -> B_STEP (16), the live-calibrated value that fires the CUT on the sim-step-16 frame."""
    if b_step is None:
        b_step = B_STEP
    sticks = [dict(stickX=DOWN[0], stickY=DOWN[1], substickX=128, substickY=128, buttons=0)
              for _ in range(n_walk)]
    sticks.append(dict(stickX=turn[0], stickY=turn[1], substickX=128, substickY=128, buttons=0x100))
    roll = [dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0) for _ in range(roll_hold)]
    roll[b_step] = dict(stickX=128, stickY=255, substickX=128, substickY=128, buttons=0x200)
    sticks += roll
    sticks += [dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0) for _ in range(tail)]
    return sticks


# --- live plumbing (slot 7; reuses pushaside.play/report; the Tetra base is shared with slot 6) -----

# Move Link +D NE along his facing so the roll entry lands in the known-good genuine region (~-1514,
# -763); the as-is slot-7 entry is ~110u short = wall-pinned. Dereck OK'd moving Link (README Status).
LINK_MOVE_D = 110.0
_POS_OFFS = (0x10C, 0x120)                   # both player class-pos triples (clean zero-length sweep)
_DBG_XYZ = (0x803D78FC, 0x803D7900, 0x803D7904)


def moved_start(link0=LINK_START, facing=LINK_FACING, d=LINK_MOVE_D):
    """Link's start shifted +d along his facing (the away-from-Tetra heading), full f32."""
    s = ML.cM_ssin_s16(facing)
    c = ML.cM_scos_s16(facing)
    return (f32(link0[0] + f32(d * s)), link0[1], f32(link0[2] + f32(d * c)))


def sim_at(tetra_xz, entry, facing, m351C, link_y, thrust=THRUST):
    """Coupled-engine prediction (placed_step=0), seeded at an EXPLICIT roll entry+facing+m351C.
    Returns (result_dict, per-step [(link_x,link_z,tet_x,tet_z)], schedule)."""
    ctx, sch = build_ctx_at(entry, facing, m351C, link_y, thrust)
    res, steps = ctx.run_trace(tetra_xz[0], tetra_xz[1], 0, link_x0=entry[0], link_z0=entry[1])
    return res, steps, sch


def mint(tetra_xz=None, slot=SLOT, out=ANCHOR, park=False, move_link=True):
    """Load slot 7, (optionally) move Link +LINK_MOVE_D NE, place Tetra (or park her FAR for entry
    measurement), and save the DTM anchor. NO frame is advanced between load and save.

    Link is placed with the CLEAN-PLACEMENT trick (write BOTH class-pos triples +0x10c/+0x120 so the
    first DTM frame's CrrPos is a zero-length sweep -> no collision snap; cf. dolphin_mem teleport).
    Tetra's START must be walkable (pushaside truth #1: off it she falls OOB and delivers NO push)."""
    import dolphin_mem as dm
    tx, tz = (FAR[0], FAR[1]) if park else (tetra_xz[0], tetra_xz[1])
    if not park and not is_walkable(tx, tz):
        p = GT.p32(tx, tz)
        raise SystemExit("Tetra start (%r,%r) NOT walkable (fA=%.2f fB=%.2f) -> falls OOB, no push "
                         "(pushaside truth #1)." % (tx, tz, GT.wA.pla.func(p), GT.wB.pla.func(p)))
    h, mem1 = dm.attach()

    def wf(a, v):
        dm.write_bytes(h, mem1, a, struct.pack('>f', v))

    def rf(a):
        return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]

    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    time.sleep(0.3)
    typ = struct.unpack('>b', dm.read_bytes(h, mem1, PA.TETRA_BASE + PA.T_TYPE, 1))[0]
    if typ != 5:
        raise SystemExit("not the type-5 Tetra at 0x%08X (got %d) -- wrong slot?" % (PA.TETRA_BASE, typ))
    base = struct.unpack('>I', dm.read_bytes(h, mem1, PA.LINK_PTR, 4))[0]
    if move_link:
        ms = moved_start()
        for off in _POS_OFFS:
            for k in range(3):
                wf(base + off + 4 * k, ms[k])
        for k, a in enumerate(_DBG_XYZ):
            wf(a, ms[k])
    wf(PA.TETRA_BASE + PA.T_POS, tx)
    wf(PA.TETRA_BASE + PA.T_POS + 4, GROUND_Y)
    wf(PA.TETRA_BASE + PA.T_POS + 8, tz)
    wf(PA.TETRA_BASE + PA.T_SPEEDF, 0.0)
    if not park:                                              # placed spot must land on the exact f32
        ax, az = rf(PA.TETRA_BASE + PA.T_POS), rf(PA.TETRA_BASE + PA.T_POS + 8)
        if struct.pack('>f', ax) != struct.pack('>f', tx) or struct.pack('>f', az) != struct.pack('>f', tz):
            raise SystemExit("Tetra placement did not land on the exact f32 (%r,%r != %r,%r)"
                             % (ax, az, tx, tz))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    dm.control_pipe_quiet("savestate", {"action": "save", "path": out})
    time.sleep(0.3)
    lx, lz = rf(base + 0x120), rf(base + 0x128)
    print("Link @ (%r,%r) [moved=%s]; Tetra @ (%r,%r) [%s]; anchor -> %s"
          % (lx, lz, move_link, tx, tz, "parked" if park else "walkable", out))
    return out


# --- entry: deliver the walk+turnaround, MEASURE the real live roll entry --------------------------

def entry(nlog=40, move_link=True):
    """Deliver DOWN*n_walk + turnaround (Tetra parked FAR), log Link, read the FIRST FRONT_ROLL frame.
    Writes ENTRY_JSON (x,z,facing,m351C,link_y) for `solve`/`deliver`. m351C = shape_angle.z<<1."""
    mint(park=True, move_link=move_link)
    rows = PA.play(anchor=ANCHOR, sticks=build_sticks())
    e = next((r for r in rows if r['proc'] == FRONT_ROLL), None)
    if e is None:
        raise SystemExit("no FRONT_ROLL in the delivered walk+turnaround (n_walk/thrust wrong?). "
                         "Procs seen: %s" % [r['proc'] for r in rows[:20]])
    meas = dict(x=e['lx'], z=e['lz'], facing=e['lfac'], m351C=(e['lsz'] << 1) & 0xFFFF,
                link_y=GROUND_Y, frame=e['f'])
    os.makedirs(os.path.dirname(ENTRY_JSON), exist_ok=True)
    json.dump(meas, open(ENTRY_JSON, 'w'), indent=1)
    se = entry_from_walk(link0=moved_start() if move_link else LINK_START)
    print("\nLIVE roll entry: f%d  pos=(%r,%r) facing=%d (%.3f deg) m351C=%d speedF=%.4f"
          % (e['f'], e['lx'], e['lz'], e['lfac'], e['lfac'] * 360 / 65536, meas['m351C'], e['spF']))
    if se is not None:
        print("SIM  roll entry:     pos=(%r,%r) facing=%d m351C=%d  (dpos=%.4fu, dfac=%d)"
              % (se['x'], se['z'], se['facing'], se['m351C'],
                 math.hypot(e['lx'] - se['x'], e['lz'] - se['z']), e['lfac'] - se['facing']))
    print("wrote %s -- now `solve` at this entry, then `deliver`." % ENTRY_JSON)
    return meas


def _load_entry():
    if not os.path.exists(ENTRY_JSON):
        raise SystemExit("no %s -- run `entry` first to measure the live roll entry." % ENTRY_JSON)
    return json.load(open(ENTRY_JSON))


# --- solve: fine-scan Tetra placements at the MEASURED live entry -----------------------------------

def solve(gx=(-1656, -1642), gz=(-936, -912), step=0.008):
    """Bit-confirmed genuine Tetra placements at the MEASURED live entry (ENTRY_JSON). The region is
    f32-dust sensitive to the entry, so this MUST be re-run whenever the entry moves; if 0 hits,
    widen/shift the FINE grid (coarse scanning is useless -- no gradient)."""
    m = _load_entry()
    ms = moved_start()
    e = entry_from_walk(link0=ms)              # sim walk trajectory = follow-safety proxy
    hits = search((m['x'], m['z']), m['facing'], m['m351C'], m['link_y'], link0=ms,
                  walk_traj=(e['traj'] if e else None), gx=gx, gz=gz, step=step, verbose=True)
    if not hits:
        print("0 hits -- widen/shift the FINE grid (the region shifted with the entry).")
    return hits


# --- deliver / diff: place the chosen Tetra spot, run the full clip --------------------------------

def _chosen_tetra(tetra_xz):
    if tetra_xz is not None:
        return tetra_xz
    hits_path = os.path.join(_rb, '_generated', 'turnaround_hits.json')
    if not os.path.exists(hits_path):
        raise SystemExit("no tetra_xz given and no %s -- run `solve` first." % hits_path)
    hits = json.load(open(hits_path))
    if not hits:
        raise SystemExit("turnaround_hits.json is empty -- `solve` found no genuine placement.")
    return tuple(hits[0]['tetra'])


def deliver(tetra_xz=None, b_step=None, thrust=THRUST, move_link=True):
    """Place the chosen genuine Tetra spot, deliver the full clip DTM, print the clip verdict."""
    m = _load_entry()
    tetra_xz = _chosen_tetra(tetra_xz)
    res, _, _ = sim_at(tetra_xz, (m['x'], m['z']), m['facing'], m['m351C'], m['link_y'], thrust)
    print("sim: genuine=%s old=%r new=%r push=%r" % (res['genuine'], res['old'], res['new'],
                                                      res.get('push')))
    mint(tetra_xz, move_link=move_link)
    rows = PA.play(anchor=ANCHOR, sticks=build_sticks(thrust=thrust, b_step=b_step))
    return PA.report(rows, res)


def diff(tetra_xz=None, b_step=None, thrust=THRUST, nlog=40, move_link=True):
    """Per-frame DTM-vs-SIM diff for BOTH actors (the tool that cracks delivery -- NEVER guess inputs).
    The divergence frame names the bug; the alignment is sim step k == live frame (roll_entry+1+k)."""
    m = _load_entry()
    tetra_xz = _chosen_tetra(tetra_xz)
    res, steps, _ = sim_at(tetra_xz, (m['x'], m['z']), m['facing'], m['m351C'], m['link_y'], thrust)
    mint(tetra_xz, move_link=move_link)
    rows = PA.play(anchor=ANCHOR, sticks=build_sticks(thrust=thrust, b_step=b_step), nlog=nlog)
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
    PA.report(rows, res)
    return rows, res


# --- CLI ------------------------------------------------------------------------------------------

def _offline_search():
    """Offline PREVIEW at the moved SIM entry (the live entry will differ; use `entry`+`solve` for
    the real thing). Tight box near the known genuine region, within the 2-minute budget."""
    ms = moved_start()
    e = entry_from_walk(link0=ms)
    if e is None:
        raise SystemExit("no roll entry from the walk (n_walk too small?)")
    print("SIM roll entry (moved-start walk+turnaround): (%r, %r) facing=%d (%.3f deg) m351C=%d nspeed=%.2f"
          % (e['x'], e['z'], e['facing'], e['facing'] * 360 / 65536, e['m351C'], e['nspeed']))
    print("NOTE: the LIVE entry will differ (from-rest walk not bit-exact); use `entry`+`solve`.")
    return search((e['x'], e['z']), e['facing'], e['m351C'], e['y'], link0=ms, walk_traj=e['traj'],
                  gx=(-1660, -1644), gz=(-948, -932), step=0.008)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'search'
    if mode == 'search':
        _offline_search()
    elif mode == 'entry':
        entry()
    elif mode == 'solve':
        solve()
    elif mode == 'deliver':
        deliver()
    elif mode == 'diff':
        diff()
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
