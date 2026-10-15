"""The CC-push COUPLED per-frame stepper -- Phase C's "wire the push into the stepper".

Runs Link (:class:`~tww_sim.land.land.LandState`) and Tetra
(:class:`~tww_sim.core.npc_zl1.Zl1FollowState`) together one game frame at a time, computing their
Co cylinder overlap each frame and feeding the resulting ``m_cc_move`` to BOTH on the following
frame -- the decomp-faithful frame order (all validated against ``d_a_player_main.cpp`` +
``d_cc_s.cpp`` + ``d_s_play.cpp``):

  * EXECUTE phase: each actor's ``posMove`` consumes the ``m_cc_move`` accumulated during the
    PREVIOUS frame's collision check. Link consumes it AFTER ``posMoveFromFootPos`` (the speedF/foot
    move) and BEFORE the m34C2 cut root-translate lunge and before ``dBgS_Acch::CrrPos`` (the wall
    pass). Tetra consumes hers in ``fopAcM_posMove`` before her ``mObjAcch.CrrPos``.
  * DRAW phase: ``dScnPly_Draw`` calls ``dComIfG_Ccsp()->Move()`` == ``dCcS`` overlap check over the
    end-of-frame (post-CrrPos, post-draw) cylinder registrations, so the overlap that feeds frame
    N+1's push is computed from frame N's SETTLED positions and DRAWN pose (Link's Co cylinder center
    is his animated root/neck midpoint at the drawn pose -- ``body_cyl.roll_co_center``). ``SetPosCorrect``
    (``cc_push.co_move_pair``) then accumulates the equal-and-opposite (same-rank 50/50) moves.

The WallCorrect wall-brace (`walls_tetra=`) is a real, live-gated MECHANIC: a wedged Tetra's own CC
recoil is canceled, so she holds instead of recoiling away each overlap frame. WHICH staging actually
clips is OPEN (session-19 correction): a corner-braced Tetra pushes the WRONG way (out of the seam),
and a stationary behind-Link Tetra gets PLOWED by Link's roll (README ## Status, dead-ends #15-17).
This stepper is the SUBSTRATE for testing any candidate staging via the dynamic coupled cut; it does
not itself assert a working staging.

Pure-sim / no calibration: the driver takes only the two seed states + input sequences; the live
Dolphin run is a VALIDATION gate (`ccgate.py`), never in a solve loop. Order note: within a frame
Link executes then Tetra (player-first); each push is from the prior frame's check, so this order
only affects Tetra's follow READ of Link's position (the "Tetra read-lag" open item) -- a wedged/near
Tetra follow no-ops so it is immaterial for the clip. Override `link_first=False` to flip it.
"""
import struct

from tww_sim.core.cc_push import (co_move_pair, WEIGHT_LINK, WEIGHT_TETRA_V5)
from tww_sim.core.anim import body_cyl

# Body Co cylinders that feed cM3d_Cross_CylCyl (d_a_player_main.cpp:9762/9780; Tetra live 2026-07-06).
# Duplicated intentionally-nowhere: canonical in reference/constants.md#collision-actor-co-push.
LINK_CO_R, LINK_CO_H = body_cyl.FRONT_ROLL_R, body_cyl.FRONT_ROLL_H   # 30, 81.25 (FRONT_ROLL)
TETRA_CO_R, TETRA_CO_H = 50.0, 140.0

# Link procs that use the FRONT_ROLL Co cylinder posed from rollf (roll + the roll-stab cut out of it).
from tww_sim.land.land import FRONT_ROLL, CUT_F, CUT_A
_ROLL_POSE_STATES = (FRONT_ROLL, CUT_F, CUT_A)


def link_co_center(link):
    """Link's body Co cylinder center (x, y, z) for the CURRENT frame's pose, the decomp
    ``daPy_lk_c::setCollision`` midpoint. During a FRONT_ROLL / roll-stab cut it is the animated
    root+neck midpoint from the rollf pose (``body_cyl.roll_co_center`` at ``roll_frame``), live-
    validated bit-exact; otherwise (walk/idle Co pose not ported) it falls back to the feet
    (``current.pos``), a first-order proxy that only matters if an overlap fires off a roll. y =
    ``current.pos.y`` (FRONT_ROLL cylinder vertical)."""
    if link.state in _ROLL_POSE_STATES and body_cyl.available():
        # shape_z = the draw-time body lean (m351C>>1, setWorldMatrix base z-tilt): a curved-approach
        # roll carries it, shifting the Co centre until it decays. See knowledge/mechanics/actor-push.md.
        cx, cz = body_cyl.roll_co_center(link.pos_x, link.pos_z, link.facing, link.roll_frame,
                                         shape_z=getattr(link, "_draw_lean", 0))
        return (cx, link.pos_y, cz)
    return (link.pos_x, link.pos_y, link.pos_z)


class CcCoupledStepper:
    """Couple a Link ``LandState`` and a Tetra ``Zl1FollowState`` through the per-frame CC push.

    Seed both states, then :meth:`step` each frame with Link's controller input. Link MUST be on the
    Python path (constructed with ``walls=`` or ``native=False``) -- the CC push needs it. Tetra's
    ``walls_tetra`` mesh (her ordered room walls) runs her WallCorrect brace; ``ground_y`` clamps her
    to the flat corner floor (Phase G). ``link_w``/``tetra_w`` are the raw Co weights (rank split)."""

    def __init__(self, link, tetra, walls_tetra=None, ground_y=None,
                 link_w=WEIGHT_LINK, tetra_w=WEIGHT_TETRA_V5, link_first=True,
                 link_co_center_fn=link_co_center):
        self.link = link
        self.tetra = tetra
        self.walls_tetra = walls_tetra
        self.ground_y = ground_y
        self.link_w = link_w
        self.tetra_w = tetra_w
        self.link_first = link_first
        self._center = link_co_center_fn
        # Pending m_cc_move for the NEXT frame's posMove (accumulated by the prior frame's check).
        self._link_pending = None
        self._tetra_pending = (0.0, 0.0, 0.0)
        self.frame = 0

    def _cc_check(self):
        """dScnPly_Draw -> Ccsp()->Move(): overlap the end-of-frame cylinders, SetPosCorrect split."""
        lc = self._center(self.link)
        tc = self.tetra.pos                                  # Tetra Co center == current.pos (feet)
        link_mv, tetra_mv = co_move_pair(lc, LINK_CO_R, LINK_CO_H, tc, TETRA_CO_R, TETRA_CO_H,
                                         w1=self.link_w, w2=self.tetra_w)
        return lc, tc, link_mv, tetra_mv

    def step(self, sx, sy, buttons=0, triggerL=0, csx=128, csy=128):
        """Advance one coupled frame. Consumes the pushes from the prior frame's check, steps both
        actors (player-first by default), then runs the CC check for the next frame. Returns a dict:
        ``link``/``tetra`` = post-step (x, y, z); ``link_push``/``tetra_push`` = the m_cc_move each
        CONSUMED this frame; ``link_center``/``tetra_center`` = the Co centers the NEXT push was
        computed from; ``next_link_push``/``next_tetra_push`` = accumulated for the next frame;
        ``tag`` = Link's proc tag."""
        link_push = self._link_pending
        tetra_push = self._tetra_pending

        if self.link_first:
            self.link.set_cc_move(link_push)
            d, tag = self.link.step(sx, sy, buttons, triggerL, csx, csy)
            self.tetra.step((self.link.pos_x, self.link.pos_y, self.link.pos_z),
                            cc_move=tetra_push, ground_y=self.ground_y, walls=self.walls_tetra)
        else:
            self.tetra.step((self.link.pos_x, self.link.pos_y, self.link.pos_z),
                            cc_move=tetra_push, ground_y=self.ground_y, walls=self.walls_tetra)
            self.link.set_cc_move(link_push)
            d, tag = self.link.step(sx, sy, buttons, triggerL, csx, csy)

        lc, tc, next_link, next_tetra = self._cc_check()
        self._link_pending = next_link
        self._tetra_pending = next_tetra
        self.frame += 1
        return dict(
            link=(self.link.pos_x, self.link.pos_y, self.link.pos_z),
            tetra=self.tetra.pos,
            link_push=link_push, tetra_push=tetra_push,
            link_center=lc, tetra_center=tc,
            next_link_push=next_link, next_tetra_push=next_tetra,
            tag=tag, d=d)


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _row_step_args(row):
    """The step() args (sx, sy, buttons, triggerL, csx, csy) captured for a frame, or neutral-hold.
    The capture stores the raw controller input as ``row['inp']`` (stickX/stickY/substickX/substickY/
    buttons/triggerL); a legacy fixture without it replays as a neutral hold."""
    inp = row.get('inp')
    if inp is None:
        return (128, 128, 0, 0, 128, 128)
    return (int(inp['stickX']), int(inp['stickY']), int(inp.get('buttons', 0)),
            int(inp.get('triggerL', 0)), int(inp['substickX']), int(inp['substickY']))


def couple_replay(rows, tetra_placed_at, tetra_placed_xz, walls, ground_y,
                  front_roll_proc=30, seed_m3570=False, sword_drawn=False):
    """Replay a captured Link-roll + Tetra Co-push OFFLINE (no Dolphin) and diff the coupled sim
    against the logged live positions, frame by frame. Shared by the live capture
    (`capture_cc_push`) and the offline gate (`tests/test_cc_gate`).

    ``rows`` = the captured per-frame log (each ``{f, link:{proc,pos,shape_y,angle_y,...},
    tetra:{pos,shape_y,...}}``, optionally ``inp`` = the frame's raw controller input); ``tetra_placed_at``
    = the ROW index the corner Tetra first appears (she is (re)seeded there at ``tetra_placed_xz`` with
    speedF 0, matching the live teleport); ``walls`` = the room's ordered wall mesh (both actors' CrrPos);
    ``ground_y`` = the flat floor.

    Seeds the coupled sim at the live roll-entry frame (first ``front_roll_proc``), FRONT_ROLL with
    speedF pinned (isolating the roll+push from the walk-up + camera, per spotcheck_rollstab). Replays
    each frame's CAPTURED controller input (``row['inp']``) so a roll-stab (a B-thrust out of the roll ->
    CUT_F) fires at the same frame it did live -- the clip frame that stacks the CC push + the m34C2 cut
    lunge + the CrrPos wall pass; ``sword_drawn`` must be True for that roll->CUT dispatch (the sword is
    drawn during the walk-up, before roll entry). A legacy fixture (no per-frame ``inp``) replays as a
    neutral hold. Returns a list of per-frame dicts: ``f``, ``proc``, sim/live Link & Tetra positions, and
    the sim-minus-live ULP diffs ``dlx/dlz/dtx/dtz`` (0 == bit-exact)."""
    from tww_sim.land.land import LandState
    from tww_sim.core.npc_zl1 import Zl1FollowState, STT_IDLE
    from tww_sim.core.fp import f32

    entry = next(i for i, r in enumerate(rows) if r['link']['proc'] == front_roll_proc)
    e = rows[entry]
    link = LandState(pos_x=e['link']['pos'][0], pos_z=e['link']['pos'][2], pos_y=e['link']['pos'][1],
                     facing=e['link']['shape_y'], travel=e['link']['angle_y'], state=front_roll_proc,
                     nspeed=26.0, speedF=26.0, use_anim=True, native=False, sword_drawn=sword_drawn,
                     walls=walls)
    link._roll_m3570 = seed_m3570        # seeded mid-roll: live grinds (no bonk) => m3570 False
    # Seed the turn-lean from the live roll-entry value (part of the seed, not calibration): its
    # shape_z tilts the drawn Co centre. Prefer exact m351C; fall back to shape_z<<1 (loses the LSB).
    if e['link'].get('m351C') is not None:
        link.m351C = int(e['link']['m351C']) & 0xFFFF
    elif e['link'].get('shape_z') is not None:
        link.m351C = (int(e['link']['shape_z']) << 1) & 0xFFFF
    ts = e['tetra']
    tetra = Zl1FollowState(x=ts['pos'][0], y=ts['pos'][1], z=ts['pos'][2], angle_y=ts['shape_y'],
                           speedF=0.0, stt=STT_IDLE)
    drv = CcCoupledStepper(link, tetra, walls_tetra=walls, ground_y=ground_y)

    out = []
    for i in range(entry + 1, len(rows)):
        if tetra_placed_at is not None and i == tetra_placed_at:
            drv.tetra.x, drv.tetra.z = f32(tetra_placed_xz[0]), f32(tetra_placed_xz[1])
            drv.tetra.y = f32(ground_y)
            drv.tetra.speedF = f32(0.0)
            drv.tetra.stt = STT_IDLE
            drv._tetra_pending = (0.0, 0.0, 0.0)
            drv._link_pending = None
        drv.step(*_row_step_args(rows[i]))
        lv = rows[i]
        out.append(dict(
            f=lv['f'], proc=lv['link']['proc'],
            sim_link=(drv.link.pos_x, drv.link.pos_z), sim_tetra=(drv.tetra.x, drv.tetra.z),
            live_link=(lv['link']['pos'][0], lv['link']['pos'][2]),
            live_tetra=(lv['tetra']['pos'][0], lv['tetra']['pos'][2]),
            placed=(i == tetra_placed_at),
            dlx=_bits(drv.link.pos_x) - _bits(lv['link']['pos'][0]),
            dlz=_bits(drv.link.pos_z) - _bits(lv['link']['pos'][2]),
            dtx=_bits(drv.tetra.x) - _bits(lv['tetra']['pos'][0]),
            dtz=_bits(drv.tetra.z) - _bits(lv['tetra']['pos'][2])))
    return out
