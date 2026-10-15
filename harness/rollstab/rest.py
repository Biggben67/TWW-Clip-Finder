"""From-rest exact seeding + the one-live-run verification gate.

`rest_state(anchor)` builds a sim that is BIT-EXACT vs live FROM ROW 0 with NO mid-run
calibration -- verified 0-ULP through walk entry, cruise, bearing arcs, partial-magnitude dips,
the turn lean, and the roll (kaze r11, 2026-07-10). It needs the anchor's seed json `rest_*`
fields (mint.py captures them at the paused anchor):
  * rest_d_frame/rest_w_frame + rates  (the WAIT(4) blend's two J3DFrameCtrl phases),
  * rest_m359C / rest_m35B4            (the posMoveFromFootPos smoothing state at rest),
  * rest_t1 / rest_t2                  (the STORED delayed foot poses, mFootData 018/00C --
                                        they carry the pre-mint position's f32 rounding noise,
                                        which re-posing at a translated position cannot).
Critical-health anchors additionally use `low_life` + `rest_mode`: an in-progress mode-0
`ANM_WAITATOB` single is seeded directly, while a settled mode-2 WAITB/WALK blend uses its captured
phase and rate.
The model behind it (all decomp-grounded, see the package README):
  * procWait re-inits the WAITS/WALK blend EVERY idle frame (setBlendMoveAnime(-1) -> the f31
    frame round-trip) -- foot_speedf.seed_rest_blend + the rest-blend WAIT branch;
  * the draw poses at the END of the frame -- post-integration pos (setWorldMatrix) -- via the
    deferred-draw mode;
  * the base tilts by the MOVE turn lean shape_angle.z = m351C>>1 (setMoveSlantAngle);
  * a savestate-anchored run_dtm movie has 2 leading alignment rows the game never ran
    (REST_NOOPS).

STICK CALIBRATION (dtm_stick): dtm_make writes 255->254 / 0->1 into every DTM, so plans must be
built FROM the delivered bytes -- sim the calibrated stick, never the raw one.

CLI -- the per-anchor live gate (one clean-DTM run, then the offline row diff):
    python -m harness.rollstab.rest anchor=kaze_r11_rollstab_idle13@twwgz
        -> writes _generated/rollstab_calib.json, then verify_rest must print REST BIT-EXACT
"""
import os, sys, json, struct
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

from tww_sim.land.land import LandState
from tww_sim.land.plan_land import stick_for_bearing
from harness.rollstab import geometry as G

CALIB_PATH = os.path.join(_rb, '_generated', 'rollstab_calib.json')
NPREF = 10                     # straight prefix frames of the verification stream
NCRUISE = 18
REST_NOOPS = 2      # leading run_dtm rows the game never ran (savestate-anchored DTM alignment):
#                     live d_frame holds the REST value through sim rows [seed, 0] and first advances
#                     at row 1 (verified on idle13: d = 30.8, 30.8, 31.9, 33.0(entry) for rows 0..2).

# dtm_make's getMainStickValue calibration: every authored DTM delivers 255 as 254 and 0 as 1.
# The undelivered raw byte cost a 60-tread stick-angle error on the (73,255) arc (found live).
_DTM_CAL = {255: 254, 0: 1}


def dtm_stick(stk):
    """Map a planned stick to the bytes dtm_make will actually deliver. Plan/sim ONLY these."""
    return (_DTM_CAL.get(stk[0], stk[0]), _DTM_CAL.get(stk[1], stk[1]))


def sticks_of(anchor, seam=None):
    """(seed, straight, aim) for the verification/approach stream. `straight` aims at the anchor
    facing; `aim` aims at the seam's thrust facing F. `seam` (a SeamGeo) generalizes a NOVEL seam --
    default None uses the kaze `geometry.F` (byte-identical). For an anchor minted facing INTO its
    corner, straight ~= aim, so the straight walk alone already verifies the from-rest approach."""
    seed = G.load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    f0 = seed['shape_angle_y'] & 0xFFFF
    F = seam.F if seam is not None else G.F
    straight = dtm_stick(stick_for_bearing(f0, cs, 1.0))
    aim = dtm_stick(stick_for_bearing(F, cs, 1.0))
    return seed, straight, aim


def rest_state(anchor, walls=None, model_draw=None, dtm_seed=1, noops=None, floors=None):
    """The bit-exact-from-REST sim state -- NO live calibration run. Seeds the active WAIT pose
    (ordinary mode-2 blend, critical mode-2 WAITB blend, or mode-0 WAITATOB single), frame
    controllers, stored
    toe stream, and m359C/m35B4 from the anchor's seed json and models the alignment no-ops, so ANY
    input stream from row 0 --
    including start-crawl micro-moves during acceleration -- is simulable offline. Clone this for
    solver runs. foot_native=False: the rest blend/lean/deferred draw live on the Python foot.
    `walls` (Phase W): wall tris for the in-stepper CrrPos response (wallgate.py gates).
    `model_draw` (session 35): the mid-walk sword pull-out (LandState.model_draw). Defaults to
    `not sword_drawn` -- a SHEATHED anchor auto-enables it so a walk-up B edge draws the sword
    (setting `sword_drawn` at the draw-completion frame, satisfying the roll->CUT gate); a
    sword-drawn anchor never draws so it stays OFF (byte-identical). No B edge => no draw => the
    walk is byte-identical either way (session-34 handoff).
    `dtm_seed` (session 43): the make_dtm leading-neutral-poll count the stream will be DELIVERED
    with. The stored `rest_noops` bakes in the pipeline default seed=1; a different seed shifts the
    leading-poll layout, so the sim's leading no-op count = `rest_noops + (1 - dtm_seed)`. MEASURED,
    not guessed (session 43, capture_walkentry seed=0 vs the seed-1 golden, d_frame-aligned): seed=1
    => noops=1 (28/0 bit-exact, byte-identical to before), seed=0 => noops=2 (28/0 bit-exact -- the
    seed-0 delivery fix; FEWER leading neutral polls => the game's rest blend advances one MORE frame
    before the plan takes hold, so the sim needs one MORE leading no-op). `noops` overrides outright.
    `floors` (Phase G): the room's GroundCross mesh (a `*_floors.json` path or a Tri list) --
    pos_y follows the floor, the speedF slope scale + m35B8 run per frame; the GroundState is
    seeded from the anchor's rest_m35B8/rest_foot024/rest_foot001/rest_waist captures (mint
    captures them since Phase G; a flat anchor without them seeds the flat defaults)."""
    seed, straight, aim = sticks_of(anchor)
    # Sword state picks the walk/dash anim SET (WALKS/DASHS vs base WALK/DASH -- different legs; see
    # KB mechanics/walk-stab.md). From the anchor's captured equip; default True (roll-stab idle anchors).
    sword_drawn = bool(seed.get('sword_drawn', seed.get('equip_item', 0x103) == 0x103))
    if model_draw is None:
        model_draw = not sword_drawn
    gnd_seed = None
    if floors is not None:
        if isinstance(floors, str):
            from tww_sim.land.floors import load_floor_mesh
            floors = load_floor_mesh(floors)
        gnd_seed = dict(m35b8=seed.get('rest_m35B8', 0.0),
                        foot024=seed.get('rest_foot024'),
                        foot001=tuple(seed.get('rest_foot001', (5, 5))),
                        waist=seed.get('rest_waist'),
                        m35c4=seed.get('rest_m35C4', 0.0))
    low_life = bool(seed.get('low_life', int(seed.get('life', 255)) <= 6))
    s = LandState(pos_x=seed['link_x'], pos_z=seed['link_z'], pos_y=seed.get('link_y', 0.0),
                  facing=seed['shape_angle_y'] & 0xFFFF, travel=seed['travel_angle'] & 0xFFFF,
                  csangle=seed['csangle'] & 0xFFFF, state=seed['link_state'], nspeed=0.0,
                  speedF=0.0, idle_frame=seed['anim_frame'], use_anim=True, native=False,
                  foot_native=False, sword_drawn=sword_drawn, idle_anim='waits', walls=walls,
                  model_draw=model_draw, floors=floors, gnd_seed=gnd_seed, low_life=low_life)
    # NO _pending_morf arming (the walk-entry frame triggers the oldframe-morf itself; arming it
    # too made the sim morf AGAIN one frame later -- caught by verify_rest row 4).
    # rest_noops = the anchor's savestate capture-phase DTM alignment, derived per-anchor by
    # mint.capture_rest (1 = boundary/canonical, 2 = legacy mid-frame). Default 2 for old seeds (#30).
    # (1 - dtm_seed) shifts it for a non-default make_dtm leading-poll count (session 43 fix,
    # MEASURED live); `noops` overrides outright (measurement path).
    direct_live = bool(seed.get('direct_live'))
    if direct_live:
        # This seed is captured at the paused input boundary, with no savestate/DTM polls to model.
        noops = 0
    elif noops is None:
        noops = max(0, int(seed.get('rest_noops', REST_NOOPS)) + (1 - int(dtm_seed)))
    if low_life and int(seed.get('rest_mode', 2)) == 0:
        s._foot.seed_rest_single(
            d_frame=seed['rest_d_frame'], d_rate=seed['rest_d_rate'],
            m359C=seed['rest_m359C'], m35B4=seed.get('rest_m35B4', 0.0),
            noops=noops, t1=seed.get('rest_t1'), t2=seed.get('rest_t2'),
        )
    else:
        s._foot.seed_rest_blend(
            d_frame=seed['rest_d_frame'], w_frame=seed['rest_w_frame'],
            d_rate=seed['rest_d_rate'], w_rate=seed['rest_w_rate'],
            m359C=seed['rest_m359C'], m35B4=seed.get('rest_m35B4', 0.0),
            noops=noops, t1=seed.get('rest_t1'), t2=seed.get('rest_t2'),
            idle_anim='waitb' if low_life else 'waits',
        )
    if not direct_live:
        s.step(128, 128)       # DTM seed frame for savestate-backed anchors
    return s


def verify_rest(anchor, calib=None, seam=None, dtm_seed=1, floors=None, walls=None):
    """Offline gate: replay the calibration stream FROM REST and diff every row vs the live
    trace -- pos, d/w frames, m359C (+ pos_y when a Phase G floors mesh is in play). Returns
    nbad (0 == REST BIT-EXACT). `seam`/`dtm_seed` for a NOVEL seam (aim at seam.F) / a seed-0
    delivery; defaults byte-identical to the kaze path. `floors` = mesh path or Tri list.
    `walls` (session 72): the seam CrrPos tris for the in-stepper wall response -- REQUIRED for a
    short-corridor (walk-stab) anchor whose ~200u-out verification walk reaches the seam wall and
    SLIDES along it; without walls the wall-less sim walks THROUGH and the gate false-DIVERGEs at
    the wall frame. Byte-identical for a far (~580u) roll anchor: its 28-frame walk never nears a
    wall, so no wall_hit fires (verified). Pass `seam.TRIS`."""
    def bits(x):
        return struct.unpack('<I', struct.pack('<f', float(x)))[0]

    if calib is None:
        calib = json.load(open(CALIB_PATH))
        assert calib['anchor'] == anchor, (calib['anchor'], anchor)
    s = rest_state(anchor, dtm_seed=dtm_seed, floors=floors, walls=walls)
    _, straight, aim = sticks_of(anchor, seam=seam)
    stream = [straight] * NPREF + [aim] * NCRUISE
    nbad = 0
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy)
        if k >= len(calib['frames']):
            break
        lf = calib['frames'][k]
        st = s._foot.st
        ok = (bits(s.pos_x) == bits(lf['pos_x']) and bits(s.pos_z) == bits(lf['pos_z'])
              and bits(st.fc0.frame) == bits(lf['d_frame'])
              and bits(st.fc1.frame) == bits(lf['w_frame'])
              and bits(s._foot.prev_f312) == bits(lf['m359C']))
        ytag = ''
        if floors is not None and lf.get('pos_y') is not None:
            ok = ok and bits(s.pos_y) == bits(lf['pos_y'])
            ytag = ' y %.7f|%.7f' % (s.pos_y, lf['pos_y'])
        nbad += 0 if ok else 1
        print('  k=%-2d %s pos(%.7f,%.7f)|(%.7f,%.7f) d %.6f|%.6f w %.6f|%.6f m359C %.8f|%.8f%s' % (
              k, 'ok  ' if ok else 'DIFF', s.pos_x, s.pos_z, lf['pos_x'], lf['pos_z'],
              st.fc0.frame, lf['d_frame'], st.fc1.frame, lf['w_frame'],
              s._foot.prev_f312, lf['m359C'], ytag), flush=True)
    print('\n%s' % ('REST BIT-EXACT' if nbad == 0 else 'REST DIVERGED (%d)' % nbad))
    return nbad


def write_golden(anchor, path, calib=None, seam=None, dtm_seed=1, geo=None,
                 floors=None):
    """Assemble the tracked REST golden (the `fixtures/seam*_rest_golden.json` schema the per-seam
    gates replay) from a verification calib -- the step every delivery used to hand-author from
    `_generated/rollstab_calib.json` (Phase-A touch-list item 4). Call ONLY after verify_rest
    printed REST BIT-EXACT: the golden is live-captured data and immutable once written."""
    if calib is None:
        calib = json.load(open(CALIB_PATH))
        assert calib['anchor'] == anchor, (calib['anchor'], anchor)
    _, straight, aim = sticks_of(anchor, seam=seam)
    gd = dict(anchor=anchor, seed=int(dtm_seed), geo=geo, floors=floors,
              straight=list(straight), aim=list(aim), NPREF=NPREF, NCRUISE=NCRUISE,
              frames=calib['frames'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(gd, open(path, 'w'), indent=1)
    print('rest golden -> %s (%d frames)' % (path, len(calib['frames'])), flush=True)


def _dedup_log(frames, rest_d):
    """Drop run_dtm DOUBLE-LOGGED rows from a verification capture (the known +-1-frame log
    jitter -- [[run-dtm 1-frame jitter]] -- first seen INSIDE the REST gate on the Hyrule stage,
    where a duplicated row shifted every later row and failed the index-aligned diff while the
    live physics matched kaze exactly; proven by logging the RAW PAD per row). Once d_frame has
    left the rest value, every real frame advances d/w/pos (procWait re-inits the blend each idle
    frame; the walk advances pos), so a byte-identical consecutive row is necessarily a log
    duplicate. Rows still AT rest_d are kept (legit alignment no-ops are covered by rest_noops)."""
    if not frames:
        return frames
    keys = ('pos_x', 'pos_z', 'facing', 'proc', 'd_frame', 'w_frame', 'm3598', 'm359C', 'm35B4')
    out = [frames[0]]
    for f in frames[1:]:
        prev = out[-1]
        if f.get('d_frame') != rest_d and all(f.get(k) == prev.get(k) for k in keys):
            continue
        out.append(f)
    return out


def main(anchor, seam=None, dtm_seed=1, golden=None, geo=None, floors=None, walls=None):
    """The per-anchor LIVE gate: one clean-DTM run of the verification stream, logging the anim
    fields per frame, then the offline from-rest diff. A new anchor must print REST BIT-EXACT
    before its solver hits are trusted. `seam` (a SeamGeo, or built from a `geo=` fixture) aims the
    cruise at a NOVEL seam's F; `dtm_seed` picks the make_dtm leading-poll layout (0 for the seed-0
    delivery a mint_current anchor needs -- noops = rest_noops + (1-dtm_seed)). `golden=` writes the
    tracked REST golden (schema of `fixtures/seam824_rest_golden.json`) on a BIT-EXACT pass --
    `geo` is the fixture path recorded inside it."""
    from harness.dtm.run_dtm import run_dtm, land_ready
    import harness.dtm.run_dtm as R
    import dolphin_mem as D
    _orig = R._read_frame

    def rich(h, m):
        d = _orig(h, m)
        Pp = struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]
        for kk, off in (('d_frame', 0x2F64), ('w_frame', 0x2F78), ('d_rate', 0x2F60),
                        ('m3598', 0x34C0), ('m359C', 0x34C4), ('m35B4', 0x34DC),
                        ('pos_y', 0x124), ('m35B8', 0x34E0)):
            d[kk] = struct.unpack('>f', D.read_bytes(h, m, Pp + off, 4))[0]
        d['csangle'] = D.read_named(h, m, 'csangle') & 0xFFFF
        return d
    R._read_frame = rich

    aseed, straight, aim = sticks_of(anchor, seam=seam)
    # csy=0 (C-down, free-cam pin) for a NOVEL mint_current anchor whose camera would else drift as Link
    # walks (session 50); csy=128 (neutral) is byte-identical to the legacy proven-anchor goldens.
    csy = 0 if (seam is not None or dtm_seed == 0) else 128
    stream = [straight] * NPREF + [aim] * NCRUISE
    sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=csy, buttons=0)
              for (sx, sy) in stream] + [dict(stickX=128, stickY=128, substickX=128,
                                              substickY=csy, buttons=0)] * 20
    end = run_dtm(sticks, anchor=anchor, ready=land_ready, relaunch_dolphin=True,
                  log_frames=len(stream) + 2, verbose=True, seed=dtm_seed)
    frames = _dedup_log(end['log'], aseed.get('rest_d_frame'))
    if len(frames) != len(end['log']):
        print('dedup: dropped %d double-logged row(s) (run_dtm log jitter)'
              % (len(end['log']) - len(frames)), flush=True)
    calib = dict(anchor=anchor, NPREF=NPREF,
                 frames=[dict(pos_x=f['pos_x'], pos_z=f['pos_z'],
                              facing=f['facing'] & 0xFFFF, proc=f['proc'],
                              d_frame=f.get('d_frame'), w_frame=f.get('w_frame'),
                              d_rate=f.get('d_rate'), m3598=f.get('m3598'),
                              m359C=f.get('m359C'), m35B4=f.get('m35B4'),
                              pos_y=f.get('pos_y'), m35B8=f.get('m35B8'),
                              csangle=f.get('csangle')) for f in frames])
    os.makedirs(os.path.dirname(CALIB_PATH), exist_ok=True)
    json.dump(calib, open(CALIB_PATH, 'w'))
    print('wrote %s (%d frames)' % (CALIB_PATH, len(frames)), flush=True)
    nbad = verify_rest(anchor, calib, seam=seam, dtm_seed=dtm_seed, floors=floors, walls=walls)
    if nbad == 0 and golden:
        write_golden(anchor, golden, calib=calib, seam=seam, dtm_seed=dtm_seed, geo=geo,
                     floors=floors if isinstance(floors, str) else None)
    return 0 if nbad == 0 else 1


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    _seam = None
    _walls = None
    if 'geo' in o:                    # NOVEL seam: build a SeamGeo from its geo fixture + anchor csangle
        from harness.rollstab.seamgeo import SeamGeo
        _a = o.get('anchor', 'kaze_r11_rollstab_idle2@twwgz')
        _seam = SeamGeo(json.load(open(o['geo'])), csangle=G.load_seed(_a)['csangle'] & 0xFFFF)
        # Auto-enable the seam walls in the gate (session 72): byte-identical for a far roll anchor,
        # REQUIRED for a short-corridor walk-stab whose walk slides the wall. `walls=0` disables.
        if o.get('walls', '1') != '0':
            _walls = _seam.TRIS
    sys.exit(main(o.get('anchor', 'kaze_r11_rollstab_idle2@twwgz'),
                  seam=_seam, dtm_seed=int(o.get('seed', 1)),
                  golden=o.get('golden'), geo=o.get('geo'), floors=o.get('floors'), walls=_walls))
