"""fast_shove.py - build + gate the EXACT native coupled shove engine (Phase T placement search).

The session-20 blocker was coupled-sim speed (~1.3 s/sim, 99% in ``acch_crr_pos`` over all 3162
room tris). This module compiles ONE fixed Link input schedule (the slot-6 roll -> UP+B roll-stab)
into per-frame constants and hands them to :class:`tww_sim.core._shovec.ShoveCtx`, the native
coupled engine. Exactness (not a predictor) rests on three facts, each gated:

1. Link's per-frame world displacement is position/Tetra-INDEPENDENT for this schedule:
   FRONT_ROLL/CUT integrate ``pos += f32(speedF*sin/cos(travel))`` with schedule-fixed
   speedF/travel; the roll bonk is disabled (``m3570`` seeded False, the live-validated grind), so
   no proc transition reads a position-dependent flag. The pushes and walls act on ``pos`` only.
2. The animated Co-centre decomposes into position-independent per-level f32-add constants
   (:func:`tww_sim.core.anim.body_cyl.roll_co_chain_consts`) -- exact, not fitted.
3. Far wall tris are exact no-ops, so the static room cull + the in-engine per-frame AABB
   prefilter leave results bit-identical.

The gate (tests/test_shove_fast.py + :func:`gate_vs_reference`): the native engine's per-frame
positions and cut old/new/push/genuine must be BIT-IDENTICAL to the live-validated Python
``cc_stepper`` engine, on the roll6 fixture inputs and on placement grids.

Timing knobs (thrust step / placement step) are new SCHEDULES: synthesize inputs with
:func:`make_inputs`, build one ctx per thrust timing, sweep placements inside it.
"""
import os, sys, json

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core import mathlib as ML
from tww_sim.core.fp import f32, fmuls
from tww_sim.core.anim import body_cyl
from tww_sim.core.cc_push import push_shares, WEIGHT_LINK, WEIGHT_TETRA_V5
from tww_sim.core.npc_zl1 import Zl1FollowState, STT_IDLE, WALL_H as TET_WH, WALL_R as TET_R
from tww_sim.land.land import LandState, FRONT_ROLL, CUT_F, CUT_A
from tww_sim.land.walls import load_ordered_mesh, cull_walls, WALL_H, WALL_R, GRAVITY
from harness.rollstab.cc_stepper import (CcCoupledStepper, LINK_CO_R, LINK_CO_H,
                                         TETRA_CO_R, TETRA_CO_H)
from harness.rollstab import geometry_tetra as GT

FIXTURE = os.path.join(_rb, 'fixtures', 'hyrule_shove_roll6.json')
WALLS_FIX = os.path.join(_rb, 'fixtures', 'hyrule_tetra_walls_ordered.json')
NEUTRAL = (128, 128, 0, 0, 128, 128)
UP_B = (128, 255, 0x200, 0, 128, 128)
FAR_TETRA_Z = -3000.0            # parking spot: no overlap, matches the live capture

_ROLL_POSE = (FRONT_ROLL, CUT_F, CUT_A)


def load_fixture(path=FIXTURE):
    return json.load(open(path))


def fixture_inputs(fix):
    """The captured per-step controller inputs, from the roll-entry row on (couple_replay order)."""
    rows = fix['frames']
    entry = next(i for i, r in enumerate(rows) if r['link']['proc'] == FRONT_ROLL)
    out = []
    for r in rows[entry + 1:]:
        inp = r.get('inp')
        if inp is None:
            out.append(NEUTRAL)
        else:
            out.append((int(inp['stickX']), int(inp['stickY']), int(inp.get('buttons', 0)),
                        int(inp.get('triggerL', 0)), int(inp['substickX']), int(inp['substickY'])))
    return out


def make_inputs(thrust_step, nsteps=30):
    """Synthesized roll-stab inputs: neutral hold, one UP+B press at ``thrust_step`` (0-based step
    index over the roll). The UP stick makes the thrust an in-line CUT_F (a neutral B is a side
    slash -- dead-end #12); B must be a RISING edge, so exactly one pressed step."""
    return [UP_B if k == thrust_step else NEUTRAL for k in range(nsteps)]


def load_walls(fix, margin=250.0):
    """The statically-culled ordered wall mesh for this run region (gated == full mesh)."""
    walls = load_ordered_mesh(WALLS_FIX)
    rows = fix['frames']
    xs = [r['link']['pos'][0] for r in rows] + [r['tetra']['pos'][0] for r in rows]
    zs = [r['link']['pos'][2] for r in rows] + [r['tetra']['pos'][2] for r in rows]
    return cull_walls(walls, min(xs), min(zs), max(xs), max(zs), margin=margin)


def _seed_link(fix, walls):
    rows = fix['frames']
    entry = next(i for i, r in enumerate(rows) if r['link']['proc'] == FRONT_ROLL)
    e = rows[entry]
    link = LandState(pos_x=e['link']['pos'][0], pos_z=e['link']['pos'][2],
                     pos_y=e['link']['pos'][1], facing=e['link']['shape_y'],
                     travel=e['link']['angle_y'], state=FRONT_ROLL, nspeed=26.0, speedF=26.0,
                     use_anim=True, native=False, sword_drawn=True, walls=walls)
    link._roll_m3570 = False
    if e['link'].get('m351C') is not None:
        link.m351C = int(e['link']['m351C']) & 0xFFFF
    elif e['link'].get('shape_z') is not None:
        link.m351C = (int(e['link']['shape_z']) << 1) & 0xFFFF
    return link, e, entry


def _seed_tetra(e):
    ts = e['tetra']
    return Zl1FollowState(x=ts['pos'][0], y=ts['pos'][1], z=ts['pos'][2],
                          angle_y=ts['shape_y'], speedF=0.0, stt=STT_IDLE)


def extract_schedule(fix, walls, inputs):
    """Run the BARE roll (Tetra parked far, never placed) once through the Python coupled stepper
    and read off the position-independent per-step Link tables. Returns a dict of parallel lists,
    truncated at (and including) the CUT entry step. Raises if the schedule never cuts."""
    link, e, _ = _seed_link(fix, walls)
    tetra = _seed_tetra(e)
    tetra.z = f32(FAR_TETRA_Z)
    drv = CcCoupledStepper(link, tetra, walls_tetra=walls, ground_y=fix['ground_y'])
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
            # the entry lunge m3700(CUT_START) rotated by facing, recomputed as state.py's CUT
            # pos-block did (link._cut_add is CLEARED after the pos block -- unreadable post-step)
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
        raise ValueError("schedule never reached a CUT -- no thrust in the inputs?")
    nlvl = max(len(c) for c in chx if c is not None)
    chx = [c if c is not None else [0.0] * nlvl for c in chx]
    chz = [c if c is not None else [0.0] * nlvl for c in chz]
    return dict(dx=dx, dz=dz, cutx=cutx, cutz=cutz, is_pose=is_pose,
                chx=chx, chz=chz, nroot=nroot, cut_step=cut_step,
                link_x0=e['link']['pos'][0], link_z0=e['link']['pos'][2],
                link_y=e['link']['pos'][1],
                tet_seed=(f32(e['tetra']['pos'][0]), f32(e['tetra']['pos'][1]), f32(FAR_TETRA_Z),
                          int(e['tetra']['shape_y']) & 0xFFFF, 0.0, STT_IDLE))


def build_ctx(fix=None, walls=None, inputs=None, margin=100.0):
    """Native ShoveCtx for one input schedule. Default: the roll6 fixture's captured inputs."""
    from tww_sim.core._shovec import ShoveCtx
    if fix is None:
        fix = load_fixture()
    if walls is None:
        walls = load_walls(fix)
    if inputs is None:
        inputs = fixture_inputs(fix)
    sch = extract_schedule(fix, walls, inputs)
    shares = push_shares(WEIGHT_LINK, WEIGHT_TETRA_V5)      # (obj2Weight, obj1Weight) in decomp naming
    return ShoveCtx(walls, GT.TRIS, GT.wA.pla, GT.wB.pla, GT.LINK_Y,
                    ML._SIN_TABLE, ML._COS_TABLE, ML._ATN_TABLE,
                    sch['dx'], sch['dz'], sch['cutx'], sch['cutz'], sch['is_pose'],
                    sch['chx'], sch['chz'], sch['nroot'], sch['cut_step'],
                    sch['link_x0'], sch['link_z0'], sch['link_y'],
                    WALL_H, WALL_R, GRAVITY,
                    sch['tet_seed'], TET_WH, TET_R, fix['ground_y'],
                    LINK_CO_R, LINK_CO_H, TETRA_CO_R, TETRA_CO_H,
                    shares[1], shares[0],       # share1 = tetra factor, share2 = link factor
                    margin=margin), sch


def py_reference(fix, walls, inputs, placement, placed_step, link_entry=None):
    """The Python coupled engine (the live-validated substrate) run EXACTLY like ShoveCtx._run:
    seed at roll entry (``link_entry`` overrides the entry (x, z) -- the roll-timing/offset search
    knob), Tetra parked far, (re-)placed at ``placed_step`` (0 == an initial condition), step
    ``inputs``, stop at the CUT entry. Returns (result_dict, per-step list). The gate's ground truth."""
    link, e, _ = _seed_link(fix, walls)
    if link_entry is not None:
        link.pos_x, link.pos_z = f32(link_entry[0]), f32(link_entry[1])
    tetra = _seed_tetra(e)
    tetra.z = f32(FAR_TETRA_Z)
    drv = CcCoupledStepper(link, tetra, walls_tetra=walls, ground_y=fix['ground_y'])
    steps = []
    cut = None
    for k, inp in enumerate(inputs):
        if k == placed_step:
            drv.tetra.x, drv.tetra.z = f32(placement[0]), f32(placement[1])
            drv.tetra.y = f32(fix['ground_y'])
            drv.tetra.speedF = f32(0.0)
            drv.tetra.stt = STT_IDLE
            drv._tetra_pending = (0.0, 0.0, 0.0)
            drv._link_pending = None
        pre = (link.pos_x, link.pos_z)
        d = drv.step(*inp)
        steps.append((link.pos_x, link.pos_z, tetra.x, tetra.z))
        if (link.state & 0xFF) in (CUT_F, CUT_A):
            push = (d['link_push'][0], d['link_push'][2]) if d['link_push'] else (0.0, 0.0)
            new = (link.pos_x, link.pos_z)
            cut = dict(old=pre, new=new, push=push,
                       genuine=GT.genuine_clip(pre, new), tetra=(tetra.x, tetra.z))
            break
    return cut, steps


def gate_vs_reference(ctx, fix, walls, inputs, placements, placed_step):
    """Bit-identity gate: native vs Python engine on each placement. Returns list of mismatches
    (empty == PASS): (placement, field, native_value, python_value)."""
    bad = []
    for p in placements:
        res, tr = ctx.run_trace(p[0], p[1], placed_step)
        ref, rtr = py_reference(fix, walls, inputs, p, placed_step)
        if ref is None:
            bad.append((p, 'no-cut-in-reference', None, None))
            continue
        for k, (a, b) in enumerate(zip(tr, rtr)):
            if a != b:
                bad.append((p, 'step%d' % k, a, b))
                break
        for f in ('old', 'new', 'push', 'genuine'):
            if res[f] != ref[f]:
                bad.append((p, f, res[f], ref[f]))
    return bad
