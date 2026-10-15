"""Mint anchors for the roll-stab sandbox.

Translated anchors: load a base anchor with the emulator PAUSED FIRST (zero frames run, so the
idle anim state is preserved bit-for-bit -- letting the game run even ~2.5s between load and
pause advances the idle/fidget state and desyncs the anchor from its seed json; that bug cost the
idle4..idle11 chain), write link_x/z += delta, save as the new anchor, and copy the seed json
with the new position.

The seed json also carries the REST_* fields rest.rest_state seeds the from-rest-exact sim
with, all read from RAM at the paused anchor:
  * the WAIT(4) blend frame ctrls (d/w frame + rate, player +0x2F64/+0x2F78/+0x2F60/+0x2F74),
  * the posMoveFromFootPos smoothing state (m359C/m35B4, +0x34C4/+0x34DC),
  * the STORED delayed foot poses t2 (mFootData[i] 018/00C: rtoe +0x3CF8, ltoe +0x3E10, rheel
    +0x3CEC, lheel +0x3E04 on JP) and t1 (the same fields after ONE paused frame-advance -- the
    advanced frame's execute stores the pose the anchor's matrices held). These carry the BASE
    anchor's position rounding noise, which a translated anchor's re-posed stream cannot.

    python -m harness.rollstab.mint base=<anchor> name=<anchor> dx=0.0 dz=0.05
"""
import os, sys, json, time, struct
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

import dolphin_mem as D
from harness import dolphin_env as ENV
from harness.rollstab.geometry import ANCHOR_DIR
from tww_sim.core.fp import f32 as _f

_FOOT_OFF = dict(rtoe=0x3CF8, ltoe=0x3E10, rheel=0x3CEC, lheel=0x3E04)  # JP mFootData 018/00C
# Phase G rest seed offsets. JP = the decomp's US field-name offsets - 0xD8 (live-validated
# s65; full table in knowledge/history/seam-clip-dead-ends.md ledger #52).
_M35B8_OFF = 0x34E0
_M35C4_OFF = 0x34EC   # m35C4, the setStepsOffset walk base-Y lift (frozen during WAIT)
_CLMODEL_OFF = 0x254
_FOOT024_OFF = (0x3D04, 0x3E1C)   # mFootData[i].field_0x024 (frozen probe midpoint, cXyz)
_FOOT001_OFF = (0x3CE1, 0x3DF9)   # mFootData[i].field_0x001 (freeze countdown, u8)
_WAIST_JNT = 30


def _player(h, m):
    return struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]


def _f32_at(h, m, addr):
    return struct.unpack('>f', D.read_bytes(h, m, addr, 4))[0]


def _foot_tuple(h, m, Pp):
    out = []
    for key in ('rtoe', 'ltoe', 'rheel', 'lheel'):
        out += list(struct.unpack('>3f', D.read_bytes(h, m, Pp + _FOOT_OFF[key], 12)))
    return out


def _load_paused(path):
    D.control_pipe_quiet('pause')
    time.sleep(0.5)
    D.control_pipe_quiet('savestate', {'action': 'load', 'path': path.replace('\\', '/')})
    time.sleep(1.5)


def _waist_world(h, m, Pp):
    """The last drawn WAIST joint world translate (getAnmMtx(30) column 3) -- footBgCheck's r31
    input; floors-mode anchors seed it (a translated anchor's re-posed waist carries the wrong
    rounding noise, like rest_t1/t2)."""
    model = struct.unpack('>I', D.read_bytes(h, m, Pp + _CLMODEL_OFF, 4))[0]
    node_mtx = struct.unpack('>I', D.read_bytes(h, m, model + 0x8C, 4))[0]
    a = node_mtx + _WAIST_JNT * 0x30
    return [_f32_at(h, m, a + 0x0C), _f32_at(h, m, a + 0x1C), _f32_at(h, m, a + 0x2C)]


def capture_rest(src):
    """Read the rest_* seed fields from an anchor savestate (leaves the anchor re-loaded)."""
    _load_paused(src)
    h, m = D.attach()
    Pp = _player(h, m)
    rest = dict(rest_d_frame=_f32_at(h, m, Pp + 0x2F64),
                rest_w_frame=_f32_at(h, m, Pp + 0x2F78),
                rest_d_rate=_f32_at(h, m, Pp + 0x2F60),
                rest_w_rate=_f32_at(h, m, Pp + 0x2F74),
                rest_m359C=_f32_at(h, m, Pp + 0x34C4),
                rest_m35B4=_f32_at(h, m, Pp + 0x34DC),
                rest_t2=_foot_tuple(h, m, Pp),
                # Phase G ground rest state (harmless extras on a flat anchor)
                rest_m35B8=_f32_at(h, m, Pp + _M35B8_OFF),
                rest_m35C4=_f32_at(h, m, Pp + _M35C4_OFF),
                rest_foot024=[list(struct.unpack('>3f', D.read_bytes(h, m, Pp + o, 12)))
                              for o in _FOOT024_OFF],
                rest_foot001=[D.read_bytes(h, m, Pp + o, 1)[0] for o in _FOOT001_OFF],
                rest_waist=_waist_world(h, m, Pp))
    # ONE paused frame-advance stores the anchor's held pose into mFootData (t1). rest_noops =
    # advances-until-d-changes = the anchor's DTM-alignment / savestate capture phase (see #30).
    d0 = rest['rest_d_frame']
    noops = 0
    for _ in range(3):
        D.control_pipe_quiet('advance', {'frames': 1})
        time.sleep(0.3)
        noops += 1
        if _f32_at(h, m, Pp + 0x2F64) != d0:
            break
    rest['rest_noops'] = noops
    rest['rest_t1'] = _foot_tuple(h, m, Pp)
    _load_paused(src)          # restore: the advance must never leak into the minted anchor
    return rest


def capture_full_seed(h, m):
    """Read the COMPLETE seed json (base state + rest_* fields) from the currently loaded paused
    anchor. Unlike `mint` (translate + inherit the base seed), this reads EVERY field from RAM, so
    it can mint an anchor whose equip/idle/facing differs from any existing base (e.g. a SHEATHED
    roll anchor -- session 36). Assumes the desired paused state is already live + saved to `dst`."""
    Pp = _player(h, m)
    seed = dict(link_x=D.read_named(h, m, 'link_x'), link_z=D.read_named(h, m, 'link_z'),
                link_y=_f32_at(h, m, Pp + 0x124),
                facing=D.read_named(h, m, 'facing') & 0xFFFF,
                shape_angle_y=D.read_named(h, m, 'shape_angle_y') & 0xFFFF,
                travel_angle=D.read_named(h, m, 'travel_angle') & 0xFFFF,
                csangle=D.read_named(h, m, 'csangle') & 0xFFFF,
                link_state=D.read_named(h, m, 'link_state'),
                anim_frame=_f32_at(h, m, Pp + 0x2F64),
                mEquipItem=struct.unpack('>H', D.read_bytes(h, m, Pp + 0x3488, 2))[0])
    seed['sword_drawn'] = (seed['mEquipItem'] == 0x103)
    seed['equip_item'] = seed['mEquipItem']
    return seed


def mint_current(name):
    """Mint the anchor from whatever Link is doing RIGHT NOW (the live, paused state) -- full-seed
    capture, no base inheritance. Set Link up live first (load + press A to sheathe, settle the
    idle, etc.), then call this. Saves the savestate, captures the complete seed json (incl. the
    rest_* fields via capture_rest), and leaves the anchor re-loaded."""
    dst = os.path.join(ANCHOR_DIR, name + '.sav')
    D.control_pipe_quiet('pause')
    time.sleep(0.4)
    D.control_pipe_quiet('savestate', {'action': 'save', 'path': dst.replace('\\', '/')})
    time.sleep(0.8)
    rest = capture_rest(dst)          # loads dst, reads rest_*, t1-advance, reloads dst (paused)
    h, m = D.attach()
    seed = capture_full_seed(h, m)
    seed.update(rest)
    json.dump(seed, open(os.path.join(ANCHOR_DIR, name + '.seed.json'), 'w'), indent=1)
    print('minted %s' % dst)
    print('  pos=(%.6f,%.6f,%.6f) facing=%d csangle=%d state=%d equip=0x%X anim=%.5f' % (
          seed['link_x'], seed['link_y'], seed['link_z'], seed['shape_angle_y'], seed['csangle'],
          seed['link_state'], seed['mEquipItem'], seed['anim_frame']))
    print('  rest d=%.6f w=%.6f d_rate=%.4f w_rate=%.4f m359C=%.6g' % (
          rest['rest_d_frame'], rest['rest_w_frame'], rest['rest_d_rate'], rest['rest_w_rate'],
          rest['rest_m359C']))
    return seed


def draw_base(base, name):
    """Make a sword-DRAWN base savestate from a SHEATHED one (ledger #55, session 67).

    A base whose rest is sheathed (equip 0x100, `sword_drawn` false) makes `mint_online`
    structurally unable to accept: the pure-sim baseline roll presses B mid-roll with no
    `draw_at`, the roll->CUT gate needs the sword out, so the baseline reports old=None on
    every iteration (the tell: old=None while spF_at_A == 17.0). Fix is mint-time setup, not
    solver surgery: one-time B-press draw + idle + the steady-WAITS probe, saved as a new
    `_drawn` base. Check `sword_drawn` in a novel base's seed BEFORE any mint_online loop."""
    ENV.ensure_running()
    src = os.path.join(ANCHOR_DIR, base + '.sav')
    _load_paused(src)
    h, m = D.attach()
    Pp = _player(h, m)
    D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                         'substickY': 0, 'buttons': 0x200, 'frames': 2})
    time.sleep(0.2)
    D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                         'substickY': 0, 'buttons': 0, 'frames': 120})
    time.sleep(0.5)
    # prove steady WAITS before saving (the mint_novel probe; ledger #47)
    for _probe in range(8):
        w0 = _f32_at(h, m, Pp + 0x2F78)
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                             'substickY': 0, 'buttons': 0, 'frames': 1})
        time.sleep(0.15)
        if _f32_at(h, m, Pp + 0x2F78) != w0:
            break
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                             'substickY': 0, 'buttons': 0, 'frames': 10})
        time.sleep(0.2)
    else:
        print('draw_base: WARNING idle never reached steady WAITS', flush=True)
    eq = struct.unpack('>H', D.read_bytes(h, m, Pp + 0x3488, 2))[0]
    st = D.read_named(h, m, 'link_state')
    print('draw_base: equip=0x%X state=%d anim=%.3f' % (eq, st, _f32_at(h, m, Pp + 0x2F64)),
          flush=True)
    if eq != 0x103 or st != 4:
        raise RuntimeError('draw_base: not a drawn steady idle (equip=0x%X state=%d) -- does '
                           'this save have the sword?' % (eq, st))
    dst = os.path.join(ANCHOR_DIR, name + '.sav')
    D.control_pipe_quiet('savestate', {'action': 'save', 'path': dst.replace('\\', '/')})
    time.sleep(1.0)
    print('saved %s (%d bytes)' % (dst, os.path.getsize(dst)), flush=True)
    return dst


def mint(base, name, dx, dz):
    ENV.ensure_running()
    src = os.path.join(ANCHOR_DIR, base + '.sav')
    rest = capture_rest(src)
    h, m = D.attach()
    x0 = D.read_named(h, m, 'link_x')
    z0 = D.read_named(h, m, 'link_z')
    nx, nz = _f(x0 + dx), _f(z0 + dz)
    D.cmd_writename('link_x', repr(nx))
    D.cmd_writename('link_z', repr(nz))
    print('pos (%.10f,%.10f) -> (%.10f,%.10f)' % (x0, z0, nx, nz))
    dst = os.path.join(ANCHOR_DIR, name + '.sav')
    D.control_pipe_quiet('savestate', {'action': 'save', 'path': dst.replace('\\', '/')})
    # seed json travels with the anchor
    seed_src = os.path.join(ANCHOR_DIR, base + '.seed.json')
    seed = json.load(open(seed_src))
    seed['link_x'], seed['link_z'] = float(nx), float(nz)
    seed.update(rest)
    json.dump(seed, open(os.path.join(ANCHOR_DIR, name + '.seed.json'), 'w'), indent=1)
    print('captured %s (rest d=%.10f w=%.10f m359C=%.10g)' % (
          dst, rest['rest_d_frame'], rest['rest_w_frame'], rest['rest_m359C']))


def _sdiff(a, b):
    d = (int(a) - int(b)) & 0xFFFF
    return d - 65536 if d > 32768 else d


def mint_novel(name, rest_x, rest_z, facing, target_csangle, floor_y, base='kaze_r11_rollstab_idle13@twwgz',
               settle_walk=42, settle_idle=20):
    """Mint a fresh anchor for a NOVEL seam with the camera BEHIND Link (session-50 procedure).

    Load `base`, `cmd_teleport` to (rest_x, floor_y, rest_z) facing `facing` (SAME floor Y => no
    sploosh), then get the camera behind Link and mint. The L (recenter) button is NOT wired to live
    input, so the camera is aimed by PANNING the free cam with the C-STICK; and because the free cam
    gets a one-time leash pull as Link speeds up, the camera is PRE-SETTLED by WALKING (C-down held)
    past that pull before minting -- else csangle drifts during the solver's approach and breaks REST
    bit-exactness. All of this is PRE-mint, so none of it lands in the delivered DTM (Dereck's ask).
    After minting, verify with `rest.main(anchor, seam=<SeamGeo>, dtm_seed=0)` -- a mint_current anchor
    needs seed=0 (noops=2) + C-down. Returns the seed dict."""
    from harness.rollstab.rest import dtm_stick
    from tww_sim.land.plan_land import stick_for_bearing
    import time
    ENV.ensure_running()
    src = os.path.join(ANCHOR_DIR, base + '.sav')
    _load_paused(src)
    h, m = D.attach()
    D.cmd_teleport(['x=%r' % rest_x, 'y=%r' % floor_y, 'z=%r' % rest_z, 'facing=%d' % (int(facing) & 0xFFFF), 'frames=2'])
    time.sleep(0.4)

    def cs():
        return D.read_named(h, m, 'csangle') & 0xFFFF
    # pan the free cam toward target_csangle (C-right raises csangle, C-left lowers), 1 frame at a time
    for _ in range(80):
        if abs(_sdiff(target_csangle, cs())) < 800:
            break
        sub = 255 if _sdiff(target_csangle, cs()) > 0 else 0
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': sub, 'substickY': 128, 'buttons': 0, 'frames': 1})
        time.sleep(0.03)
    # walk-settle toward `facing` (C-down) UNTIL csangle FREEZES -- a fixed frame count
    # under-settles at some seams and the cam creeps through the approach (dead-end ledger #42).
    chunk = 7
    walked, prev_cs = 0, None
    while walked < settle_walk:
        c0 = cs()
        if prev_cs is not None and c0 == prev_cs:
            break
        prev_cs = c0
        sx, sy = dtm_stick(stick_for_bearing(int(facing) & 0xFFFF, c0, 1.0))
        D.control_pipe_quiet('advancewith', {'stickX': sx, 'stickY': sy, 'substickX': 128, 'substickY': 0, 'buttons': 0, 'frames': chunk})
        walked += chunk
        time.sleep(0.1)
    time.sleep(0.2)
    # stop + idle (C-down) to a clean WAITS rest at the frozen camera
    D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128, 'substickY': 0, 'buttons': 0, 'frames': settle_idle})
    time.sleep(0.3)
    # ... and PROVE steady WAITS before minting: idle in chunks until a 1-frame advance moves the
    # w ctrl (frozen = stop-transition tail, never REST bit-exact -- dead-end ledger #47).
    Pp = _player(h, m)
    for _probe in range(8):
        w0 = _f32_at(h, m, Pp + 0x2F78)
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128, 'substickY': 0, 'buttons': 0, 'frames': 1})
        time.sleep(0.15)
        if _f32_at(h, m, Pp + 0x2F78) != w0:
            break
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128, 'substickY': 0, 'buttons': 0, 'frames': 10})
        time.sleep(0.2)
    else:
        print('mint_novel: WARNING idle never reached steady WAITS (w ctrl frozen after %d probes)'
              % 8, flush=True)
    # NOTE do NOT teleport-to-rest after the settle: a teleport resets the cam-Link leash and the
    # next from-rest walk re-pulls the cam, so the settle must END at the rest spot (ledger #42).
    print('pre-mint: csangle=%d (target %d) state=%d' % (cs(), int(target_csangle) & 0xFFFF, D.read_named(h, m, 'link_state')), flush=True)
    return mint_current(name)


def mint_online(name, geo_path, d2s=580.0, base='kaze_r11_rollstab_idle13@twwgz',
                perp_tol=2.0, max_iter=3, settle_est=160.0, target_csangle=None,
                settle_walk=42):
    """Mint an ON-LINE pan-camera anchor for a novel seam, first-class (session-54 procedure,
    dead-ends #36/#37). The two constraints a novel-seam anchor must satisfy:
      * the camera must be FROZEN (the mint_novel C-stick pan arms the MANUAL cam; anywhere the
        auto-cam tracks Link's walk, an unpanned mint's csangle creeps and the constant-cs rest
        model can never be bit-exact -- #36);
      * the BASELINE ROLL `old` must sit ON the F-through-S line (within the arc reach ~+-9u;
        `mint_novel`'s settle walk drifts off the park bearing AND the resulting misaim's MOVE
        turn to F adds more perp during the approach -- ~12u at the 97m corner's 23-deg misaim --
        so an off-line anchor makes `solve_focused` find 0 hits with Phase-A best score == the
        residual offset -- #37).
    Parks on the seam's aim line at `d2s` (+`settle_est` for the settle walk), pan-mints, then
    measures the PURE-SIM baseline roll `old`'s perp from the minted seed (`solver.run(anchor, [])`
    -- the quantity the arc bracket must center on; the REST perp alone under-measures by the turn
    drift) and RE-PARKS by it with a SECANT gain (session 58: the perp response per unit shift is
    NOT 1:1 everywhere -- ~1.8 at a large settle misaim -- so the 1:1 step can oscillate; the gain
    is estimated from the previous iteration and clamped). NOTE `d2s` must stay ~580 (the solver's
    A_proj derivation and the spF-17 cap distance assume the proven rest envelope) and the seam
    needs park = d2s + settle travel (~1000u+) of clear corridor -- `seam_screen.py` measures it.
    The aim comes from the geo fixture (`aim_deg` if declared, else the interior bisector); the park
    facing = the aim (the anchor need NOT face F exactly -- the arc bracket absorbs the misaim's
    ANGLE, #37 corollary; it is the misaim's perp DRIFT this loop cancels).
    After minting, REST-verify: python -m harness.rollstab.rest anchor=<name> geo=<geo> seed=0."""
    from harness.rollstab.seamgeo import SeamGeo
    from tww_sim.core.mathlib import deg_to_s16
    import math
    geo = json.load(open(geo_path))
    aim_deg = geo.get('aim_deg', geo['bisector_deg'])
    ar = math.radians(float(aim_deg) % 360.0)
    dx, dz = math.sin(ar), math.cos(ar)
    Sx, Sz = geo['S'][0], geo['S'][2]
    facing = deg_to_s16(float(aim_deg) % 360.0)
    if target_csangle is None:
        target_csangle = facing
    park_x = Sx - (d2s + settle_est) * dx
    park_z = Sz - (d2s + settle_est) * dz
    seed = None
    prev_perp, prev_shift = None, None
    for it in range(max_iter):
        seed = mint_novel(name, park_x, park_z, facing, target_csangle, geo['link_y'], base=base,
                          settle_walk=settle_walk)
        seam = SeamGeo(geo, seed['csangle'])
        rest = (seed['link_x'], seed['link_z'])
        # the load-bearing perp = the PURE-SIM baseline roll old's (rest perp + the turn drift)
        import harness.rollstab.solver as _SV
        for _c in (_SV._BASE, _SV._BASE_WALLED):    # the seed on disk just changed: drop the
            for _k in [k for k in _c if k[0] == name]:  # cached rest states for this anchor
                del _c[_k]
        r0 = _SV.run(name, [], dtm_seed=0, seam=seam)
        old = r0.get('old') if (r0 and r0.get('fired')) else None
        perp = seam.perp(old) if old else seam.perp(rest)
        print('mint_online iter %d: old_perp=%.3f (rest_perp=%.3f) old=%s d2S(rest)=%.1f '
              'csangle=%d F=%d facing=%d' % (
              it, perp, seam.perp(rest), old, seam.d2S(rest),
              seed['csangle'], seam.F, seed['shape_angle_y']), flush=True)
        if old is None:
            # unfired baseline = rest outside the ~580u envelope (ledger #42); never accept on
            # the rest-perp fallback -- re-park on the along error and retry
            print('mint_online iter %d: baseline roll did NOT fire (d2S %.1f vs d2s %.1f) -- '
                  're-parking on along error' % (it, seam.d2S(rest), d2s), flush=True)
        elif abs(perp) <= perp_tol:
            print('mint_online: ON-LINE (baseline |old perp| %.3f <= %.1f)' % (abs(perp), perp_tol),
                  flush=True)
            return seed
        # re-park by a SECANT-gain step (clamped; 1:1 on the first iteration) -- the perp response
        # per unit shift is ~1.8 at a large settle misaim, so a 1:1 step oscillates (ledger #42).
        # A rest-perp fallback (old=None) measures a DIFFERENT quantity: drop the secant history.
        if old is None:
            prev_perp = prev_shift = None
        if prev_shift and prev_perp is not None:
            gain = (perp - prev_perp) / prev_shift
            gain = max(0.4, min(2.5, gain))
        else:
            gain = 1.0
        shift = -perp / gain
        prev_perp, prev_shift = perp, shift
        along_err = seam.along(rest) + d2s          # rest sits at along ~ -d2s on the aim line
        park_x += shift * seam.PX - along_err * seam.DIRX
        park_z += shift * seam.PZ - along_err * seam.DIRZ
    print('mint_online: WARNING still off-line after %d iters (perp=%.3f)' % (max_iter, perp), flush=True)
    return seed


def mint_walkstab(name, geo_path, d2s=200.0, base='kaze_r11_walkstab@twwgz',
                  target_csangle=None, settle_walk=0):
    """Mint a from-rest WALK-stab anchor for a NOVEL seam (session 72) -- the walk-stab counterpart of
    mint_online, the piece the walk-stab tier lacked (ledger #58). Three differences from the roll mint:

      * The rest sits at a SUB-580u distance. A capped-walk cut reaches ~40u (speedF 17 + the 23.22
        CUT_F root translate), so the rest is only a short walk out -- and for seam_0352_0353 it must
        sit past the corridor CC actor, which is why the roll (which needs the ~506u A-press runway)
        cannot deliver that corner. But it must be FAR ENOUGH for the walk to reach the speedF-17 cap
        before the cut zone -- `check_runway` GUARDS this after minting (session-72 fix: an earlier
        mint over-settled to d2S ~58 with no runway and wasted a live REST-gate run). `d2s` defaults
        to 200 (parked DIRECTLY, no settle overshoot).
      * NO settle-walk. mint_novel's settle-walk (walk-until-cam-freezes) OVERSHOOTS here -- it
        travels ~240u toward S and curves off-line -- and a live probe showed the camera is already
        behind Link after the pan + a brief idle (csangle drifts only ~11 hw over the whole approach,
        an arm idle->walk transient, NOT a wall collision). So `settle_walk=0`: park AT d2s, pan the
        cam behind Link, idle to steady WAITS, mint. The rest stays put at d2s.
      * NO baseline-perp secant loop (a walk-stab has no baseline roll; the solver's grazing cruise +
        bearing arcs absorb residual misaim, ledger #58).

    Parks on the seam's aim line (`_aim_line`; bisector unless the geo declares `aim_deg`) at `d2s`,
    pans the free cam to `target_csangle` (default = the aim F), idles to a clean steady-WAITS rest --
    all PRE-mint, so none lands in the delivered DTM. `base` defaults to the item-held kaze walk-stab
    idle (sword sheathed -> the delivery's B edge draws it via the 4-frame put-away). After minting it
    RETARGETS walkstab.configure(name, geo) and runs the runway guard. Verify next with
    `rest.main(anchor, seam=<walkstab SeamGeo>, dtm_seed=0)` -> REST BIT-EXACT. Returns the seed dict."""
    import math
    geo = json.load(open(geo_path))
    F, dx, dz, Sx, Sz = _aim_line(geo)
    if target_csangle is None:
        target_csangle = F
    park_x = Sx - d2s * dx
    park_z = Sz - d2s * dz
    seed = mint_novel(name, park_x, park_z, F, int(target_csangle) & 0xFFFF, geo['link_y'],
                      base=base, settle_walk=settle_walk)
    # GUARD (session 72): retarget the tier to the fresh anchor + verify runway (check_runway) so a
    # too-close 'no speedF cap before the cut' mint is flagged HERE, not after a wasted live run.
    try:
        from harness.rollstab import walkstab as W
        W.configure(name, geo_path, name=name.split('@')[0].split('_')[-1])
        ok, msg, info = W.check_runway()
        if not ok:
            print('*** %s' % msg, flush=True)
    except Exception as e:
        print('mint_walkstab: runway guard skipped (%s)' % e, flush=True)
    return seed


def floor_probe(geo_path, dists, settle_frames=30, base='kaze_r11_rollstab_idle13@twwgz',
                fall_tol=60.0):
    """Live park-FLOOR probe (session 60, dead-end #43): does the aim line still have walkable
    FLOOR at each candidate park distance? `seam_screen.corridor` measures WALL clearance only --
    the 467-corner read 1020u "clear" over a pit edge, and a park past the floor edge
    teleport-slides off and falls OOB, so the mint is impossible there. Teleport to each d2S in
    `dists` along the aim line, idle `settle_frames`, and flag FLOOR if Link's Y held (within
    `fall_tol` of the seam's link_y). Returns {d: bool}. Run BEFORE cam screen + mint."""
    import math
    ENV.ensure_running()
    geo = json.load(open(geo_path))
    aim_deg = geo.get('aim_deg', geo['bisector_deg'])
    ar = math.radians(float(aim_deg) % 360.0)
    dx, dz = math.sin(ar), math.cos(ar)
    Sx, Sz = geo['S'][0], geo['S'][2]
    from tww_sim.core.mathlib import deg_to_s16
    F = deg_to_s16(float(aim_deg) % 360.0)
    src = os.path.join(ANCHOR_DIR, base + '.sav')
    h, m = D.attach()
    out = {}
    for d in dists:
        _load_paused(src)
        D.cmd_teleport(['x=%r' % (Sx - d * dx), 'y=%r' % geo['link_y'], 'z=%r' % (Sz - d * dz),
                        'facing=%d' % F, 'frames=2'])
        time.sleep(0.3)
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                             'substickY': 0, 'buttons': 0,
                                             'frames': settle_frames})
        time.sleep(0.4)
        Pp = _player(h, m)
        y = _f32_at(h, m, Pp + 0x124)
        out[d] = abs(y - geo['link_y']) <= fall_tol
        print('floor_probe d2S=%-6.0f y=%.2f (floor %.2f)  %s' % (
              d, y, geo['link_y'], 'FLOOR' if out[d] else 'OFF-FLOOR'), flush=True)
    return out


def _aim_line(geo):
    """(F, dx, dz, Sx, Sz) for a geo fixture's approach aim line (the interior bisector unless the
    fixture declares an `aim_deg`). Shared by every park-based live probe (floor/cam screens)."""
    import math
    from tww_sim.core.mathlib import deg_to_s16
    aim_deg = geo.get('aim_deg', geo['bisector_deg'])
    ar = math.radians(float(aim_deg) % 360.0)
    return (deg_to_s16(float(aim_deg) % 360.0), math.sin(ar), math.cos(ar), geo['S'][0], geo['S'][2])


def _park_pan_settle(h, m, geo, target, d2s, settle_est, base, F, dx, dz, Sx, Sz):
    """Replicate mint_novel's pre-mint camera setup at a candidate park, then leave Dolphin at the
    settled rest spot: teleport `base` to the aim-line park (d2s+settle_est out), pan the free cam
    to `target` csangle (C-stick), settle-walk (C-down, re-aim toward F) until csangle FREEZES, and
    idle to a clean rest. Returns (rest_cs, rest_d2S). Shared by cam_screen (legacy multi-target
    dev sweep) and cam_clean_screen (the session-69 csangle-invariance probe) so they park the cam
    identically -- the screen must measure the SAME frozen csangle the mint will land on."""
    from harness.rollstab.rest import dtm_stick
    from tww_sim.land.plan_land import stick_for_bearing
    import math
    park_x = Sx - (d2s + settle_est) * dx
    park_z = Sz - (d2s + settle_est) * dz
    _load_paused(os.path.join(ANCHOR_DIR, base + '.sav'))
    D.cmd_teleport(['x=%r' % park_x, 'y=%r' % geo['link_y'], 'z=%r' % park_z,
                    'facing=%d' % F, 'frames=2'])
    time.sleep(0.3)

    def cs():
        return D.read_named(h, m, 'csangle') & 0xFFFF

    for _ in range(80):                           # mint_novel's pan loop
        if abs(_sdiff(target, cs())) < 800:
            break
        sub = 255 if _sdiff(target, cs()) > 0 else 0
        D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': sub,
                                             'substickY': 128, 'buttons': 0, 'frames': 1})
        time.sleep(0.02)
    walked, prev = 0, None                        # settle-until-frozen (chunked, ledger #42)
    while walked < 42:
        c0 = cs()
        if prev is not None and c0 == prev:
            break
        prev = c0
        sx, sy = dtm_stick(stick_for_bearing(F, c0, 1.0))
        D.control_pipe_quiet('advancewith', {'stickX': sx, 'stickY': sy, 'substickX': 128,
                                             'substickY': 0, 'buttons': 0, 'frames': 7})
        walked += 7
        time.sleep(0.08)
    D.control_pipe_quiet('advancewith', {'stickX': 128, 'stickY': 128, 'substickX': 128,
                                         'substickY': 0, 'buttons': 0, 'frames': 20})
    time.sleep(0.3)
    x = D.read_named(h, m, 'link_x')
    z = D.read_named(h, m, 'link_z')
    return cs(), math.hypot(x - Sx, z - Sz)


def cam_clean_screen(geo_path, target_csangle=None, d2s=580.0, settle_est=420.0, n=40,
                     base='kaze_r11_rollstab_idle13@twwgz', tol=0, armdrop=0.15, out=None):
    """The INVARIANT camera screen (session 69, ROADMAP Phase A exp.5, ledger #56) -- the
    principled replacement for cam_screen's empirical trial-pan hunt.

    Live RE proved csangle (mAngleY) is BIT-FROZEN in free space under a centered HORIZONTAL
    C-stick (no L); the only mover is `bumpCheck` camera-arm wall collision (a lateral eye push in
    a tight corridor). So the camera is screened by an INVARIANT, not by trial-and-error over pan
    tracks: park on the seam's aim line, freeze the cam at `target_csangle` (default = the aim F),
    then walk `n` frames DOWN the seam bearing with a FIXED stick (computed ONCE from the frozen
    csangle -- re-aiming each frame would chase a drift and confound the signal; cam_screen's flaw)
    and a centered horizontal C-stick, and assert csangle holds. CLEAN => the corridor keeps the
    arm off walls, so this park+csangle is mintable and the from-rest constant-csangle model stays
    bit-exact; DIRTY => `first_drift` names the frame/pos where the arm first hits a wall. Reads
    csangle + the eye/center arm via cam_clean.cam_geom and scores with cam_clean.evaluate (the
    same offline-gated verdict as the anchor-based probe). C-down (substickY=0) matches the
    delivered walk and is azimuth-neutral (verified live: it leaves csangle frozen in clean space).

    Returns cam_clean.evaluate()'s dict augmented with target/rest_cs/rest_d2S/rows. `out=<path>`
    dumps a golden JSON (meta + rows) for the offline regression."""
    from harness.rollstab import cam_clean
    from harness.rollstab.rest import dtm_stick
    from tww_sim.land.plan_land import stick_for_bearing
    ENV.ensure_running()
    geo = json.load(open(geo_path))
    F, dx, dz, Sx, Sz = _aim_line(geo)
    if target_csangle is None:
        target_csangle = F
    target_csangle &= 0xFFFF
    h, m = D.attach()
    rest_cs, rest_d2S = _park_pan_settle(h, m, geo, target_csangle, d2s, settle_est, base,
                                         F, dx, dz, Sx, Sz)
    # FIXED stick down the seam bearing at the now-frozen csangle: with a centered horizontal
    # C-stick the csangle azimuth is inert, so any drift below is bumpCheck (session-69 invariant).
    sx, sy = dtm_stick(stick_for_bearing(F, rest_cs, 1.0))
    cs0, c, e, arm0 = cam_clean.cam_geom(h, m)
    rows = [{"f": 0, "cs": cs0, "dcs": 0, "arm": round(arm0, 3),
             "lx": round(c[0], 2), "lz": round(c[2], 2)}]
    for i in range(1, n + 1):
        D.control_pipe_quiet('advancewith', {'stickX': sx, 'stickY': sy, 'substickX': 128,
                                             'substickY': 0, 'buttons': 0, 'frames': 1})
        time.sleep(0.04)
        cs, c, e, arm = cam_clean.cam_geom(h, m)
        rows.append({"f": i, "cs": cs, "dcs": cam_clean._sdiff(cs, cs0), "arm": round(arm, 3),
                     "lx": round(c[0], 2), "lz": round(c[2], 2)})
    res = cam_clean.evaluate(rows, tol=tol, armdrop=armdrop)
    res.update(target=target_csangle, rest_cs=rest_cs, rest_d2S=rest_d2S, rows=rows)
    if out:
        json.dump({"geo": os.path.basename(geo_path), "target": target_csangle, "base": base,
                   "d2s": d2s, "settle_est": settle_est, "n": n, "rows": rows},
                  open(out, 'w'), indent=1)
        print('  wrote golden %s' % out, flush=True)
    fd = res['first_drift']
    verdict = ('CLEAN' if res['clean'] else
               ('DIRTY @f%d pos=(%.1f,%.1f)' % (fd['f'], fd['lx'], fd['lz']) if fd else 'DIRTY'))
    print('cam_clean_screen target=%5d  rest_cs=%5d  rest_d2S=%.1f  max|drift|=%d hw  '
          'arm %.1f->%.1f  %s' % (target_csangle, rest_cs, rest_d2S, abs(res['max_dcs']),
          res['arm0'] or 0.0, res['min_arm'] or 0.0, verdict), flush=True)
    return res


def cam_screen(geo_path, targets=None, d2s=580.0, settle_est=420.0, nwalk=40,
               base='kaze_r11_rollstab_idle13@twwgz'):
    """LEGACY multi-target cam-trigger sweep (session 60), superseded by cam_clean_screen as the
    novel_deliver camera gate but kept as a diagnostic: for each candidate pan `target`, park the
    cam (`_park_pan_settle`) then walk the corridor `nwalk` frames RE-AIMING toward F and report any
    csangle deviation from the rest value. Some corridors carry a fixed ROAD-triggered cam band
    (kaze r11 seam824: csangle dips ~-300 s16 over d2S ~588..384) that fires only on some tracks.
    The re-aiming walk confounds a drift with the chase it induces -- cam_clean_screen's fixed-stick
    invariant probe is the principled replacement. Returns [(target, rest_cs, rest_d2S, deviations)]."""
    from harness.rollstab.rest import dtm_stick
    from tww_sim.land.plan_land import stick_for_bearing
    import math
    ENV.ensure_running()
    geo = json.load(open(geo_path))
    F, dx, dz, Sx, Sz = _aim_line(geo)
    if targets is None:
        targets = [(F + off) & 0xFFFF for off in (0, -8000, 8000, -16384, 16384)]
    h, m = D.attach()

    def cs():
        return D.read_named(h, m, 'csangle') & 0xFFFF

    out = []
    for target in targets:
        rest_cs, rest_d2S = _park_pan_settle(h, m, geo, target, d2s, settle_est, base,
                                             F, dx, dz, Sx, Sz)
        dev = []
        for _k in range(nwalk):                   # corridor walk: any csangle motion = trigger hit
            sx, sy = dtm_stick(stick_for_bearing(F, cs(), 1.0))
            D.control_pipe_quiet('advancewith', {'stickX': sx, 'stickY': sy, 'substickX': 128,
                                                 'substickY': 0, 'buttons': 0, 'frames': 1})
            time.sleep(0.04)
            x = D.read_named(h, m, 'link_x')
            z = D.read_named(h, m, 'link_z')
            c1 = cs()
            if c1 != rest_cs:
                dev.append((round(math.hypot(x - Sx, z - Sz)), c1))
        print('cam_screen target=%5d  rest_cs=%5d  rest_d2S=%.1f  frozen=%s  dev=%s' % (
              target, rest_cs, rest_d2S, 'YES' if not dev else 'no', dev[:8] or '-'), flush=True)
        out.append((target, rest_cs, rest_d2S, dev))
    return out


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    if 'floorprobe' in o:                 # park-floor probe along the aim line (ledger #43)
        floor_probe(o['floorprobe'],
                    [float(x) for x in o.get('dists', '1000,1100,1200').split(',')],
                    base=o.get('base', 'kaze_r11_rollstab_idle13@twwgz'))
    elif 'camclean' in o:                 # INVARIANT camera screen for a novel seam (session-69)
        cam_clean_screen(o['camclean'], d2s=float(o.get('d2s', 580.0)),
                         settle_est=float(o.get('settle_est', 420.0)), n=int(o.get('n', 40)),
                         target_csangle=(int(o['target_csangle'], 0) if 'target_csangle' in o else None),
                         out=o.get('out'),
                         base=o.get('base', 'kaze_r11_rollstab_idle13@twwgz'))
    elif 'camscreen' in o:                # legacy multi-target cam-trigger sweep (session-60)
        cam_screen(o['camscreen'], d2s=float(o.get('d2s', 580.0)),
                   settle_est=float(o.get('settle_est', 420.0)),
                   base=o.get('base', 'kaze_r11_rollstab_idle13@twwgz'))
    elif 'online' in o:                   # on-line pan mint for a NOVEL seam (session-54 procedure)
        mint_online(o['online'], o['geo'], d2s=float(o.get('d2s', 580.0)),
                    max_iter=int(o.get('max_iter', 3)),
                    settle_est=float(o.get('settle_est', 160.0)),
                    target_csangle=(int(o['target_csangle'], 0) if 'target_csangle' in o else None),
                    settle_walk=int(o.get('settle_walk', 42)),
                    base=o.get('base', 'kaze_r11_rollstab_idle13@twwgz'))
    elif 'walkstab' in o:                 # WALK-stab sub-580u pan mint for a NOVEL seam (session-72)
        mint_walkstab(o['walkstab'], o['geo'], d2s=float(o.get('d2s', 200.0)),
                      target_csangle=(int(o['target_csangle'], 0) if 'target_csangle' in o else None),
                      settle_walk=int(o.get('settle_walk', 0)),
                      base=o.get('base', 'kaze_r11_walkstab@twwgz'))
    elif 'novel' in o:                    # camera-behind mint for a NOVEL seam (session-50 procedure)
        mint_novel(o['novel'], float(o['x']), float(o['z']), int(o['facing'], 0),
                   int(o['csangle'], 0), float(o['y']), base=o.get('base', 'kaze_r11_rollstab_idle13@twwgz'))
    elif 'drawbase' in o:                 # sword-drawn base from a sheathed one (ledger #55)
        draw_base(o['drawbase'], o['name'])
    elif 'current' in o:                  # mint the live paused state as a fresh full-seed anchor
        ENV.ensure_running()
        mint_current(o['current'])
    else:
        mint(o['base'], o['name'], float(o.get('dx', 0.0)), float(o.get('dz', 0.0)))
