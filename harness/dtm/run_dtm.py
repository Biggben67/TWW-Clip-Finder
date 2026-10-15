"""Generalized, pipe-artifact-free DTM runner.

Give it a per-frame INPUT sequence (raw sticks, or an ess/chg/neu action list) and an
optional EXPECTED endpoint; it handles the rest: author a clean-cadence DTM, copy the
savestate anchor, (re)launch Dolphin to a stopped game list, play the movie, read the
live endpoint, and compare. This is the trustworthy live check (movie playback flips
WantDeterminism on and polls at the game's natural cadence -- no advanceseq pipe jitter,
see pt-21 / KNOWLEDGE bug#2). Dolphin command reference: ../../tools/DOLPHIN_CONTROL.md.

Generalizes harness/validate/validate_dtm.py, which was hardwired to action-seq files, the
cold anchor, and a SwimState compare. Here:
  - inputs are universal per-frame sticks (action lists convert via actions.acts_to_seq),
  - the anchor / template / expected are all parameters,
  - boot is detected by an anchor-loaded readiness predicate (state-agnostic: swim slate 54/55,
    land idle 5, ...), NOT the movie playing flag (true from the playmovie call all through boot,
    so it can't tell us the anchor is in -- resuming before it wastes the input frames on a
    still-booting game), and
  - the end state is read once the movie exhausts and the emulator pauses at the last frame
    (PauseMovie, ensured by dolphin_env) -- exact and fast, no per-frame pipe stepping.

Works for ANY player state, one playback path with all the gotchas: pass a `ready` predicate and
put the state's fields in `expected`. swim_ready / land_ready are provided; land also reads/compares
pos_x/pos_z and the two-angle model (shape/travel). The swim defaults are unchanged.

Programmatic:
    from harness.dtm.run_dtm import run_dtm, sticks_from_actions, land_ready, land_walk_sticks
    end = run_dtm(sticks, expected={'v': -812.3, 'anim': 4.1, 'air': 870, 'state': 55},
                  game=ISO, anchor=ANCHOR)                                    # swim (default gate)
    end = run_dtm(land_walk_sticks(30, 15), expected={'pos_z': 1095.42, 'state': 5},
                  anchor="land_flatwalk@twwgz", ready=land_ready, watch=True)  # land, watchable

CLI:
    python run_dtm.py seq=plan3k_exact_seq.txt [game=<iso>] [anchor=<.sav>]
                      [expect_v=..] [expect_anim=..] [expect_air=..] [expect_state=..]
                      [tol=0.02] [norelaunch=0]
    python run_dtm.py ready=land [up=30] [neut=15] [anchor=land_flatwalk@twwgz]
                      [expect_pos_z=1095.42] [expect_state=5] [watch=1]
"""
import sys, os, time, math, json, shutil, subprocess, struct
# >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import glob
import dolphin_mem as D
from tww_sim.swim import actions as A
from tww_sim.swim import sim as S
import dtm_make as DM
from harness import dolphin_env as ENV

# --- environment (machine paths come from harness.dolphin_env: env -> dolphin.local.json) ------
# Test-owned anchors (not save slots): "<test>@<isokey>.sav"; isokey -> <isos_dir>/<key>.iso so
# the runner pulls the right image automatically. See tests/dolphin/anchors/README.md.
ANCHOR_DIR = os.path.join(_rb, "tests", "dolphin", "anchors")
_GEN = os.path.join(_rb, "_generated")
DEFAULT_TEMPLATE = os.path.join(_GEN, "cruise_pump300k_rec.dtm")  # iso-agnostic header clone
DEFAULT_ANCHOR = os.path.join(ANCHOR_DIR, "cruise_cold@twwgz.sav")  # cold start v0/state54
X0, Z0 = 42222.0, -158781.0          # slate origin (net is a sanity scalar only)
FACING_TOL_DEG = 2.0                 # default facing compare tolerance (game u16 -> deg)


def resolve_anchor(anchor):
    """Accept a bare anchor name or a path; return its absolute .sav path."""
    if os.path.isabs(anchor) or os.sep in anchor or '/' in anchor:
        return anchor
    cand = os.path.join(ANCHOR_DIR, anchor)
    return cand if cand.endswith('.sav') else cand + '.sav'


def iso_for_anchor(anchor):
    """Parse the '@<isokey>.sav' suffix and resolve <isos_dir>/<isokey>.iso via dolphin_env.

    The iso the anchor was captured on is baked into its filename, so the runner never has
    to be told which image to boot. Raises if the name lacks a key or the iso isn't found.
    """
    base = os.path.basename(anchor)
    if base.endswith('.dtm.sav'):
        base = base[:-len('.dtm.sav')]
    elif base.endswith('.sav'):
        base = base[:-len('.sav')]
    if '@' not in base:
        raise SystemExit(f"anchor '{base}' has no '@<isokey>' iso tag; "
                         f"name it e.g. mytest@twwgz.sav")
    return ENV.iso_path(base.rsplit('@', 1)[1])


# --- input adapters -------------------------------------------------------------------
def sticks_from_actions(acts):
    """ess/chg/neu action list -> per-frame stick dicts (chg alternates up/down)."""
    return A.acts_to_seq(acts)


def sticks_from_seq_file(path):
    return sticks_from_actions(A.expand(open(path).read()))


# Land walk: C-stick full DOWN every frame forces free cam; hold UP then neutral (accel -> cruise
# -> stop). Same inputs land_capture drives via advancewith, so a correct DTM playback matches it.
_CDOWN = {"substickX": 128, "substickY": 0}
_LAND_UP = {"stickX": 128, "stickY": 255, **_CDOWN}
_LAND_NEUT = {"stickX": 128, "stickY": 128, **_CDOWN}


def land_walk_sticks(up=30, neut=15):
    return [dict(_LAND_UP)] * up + [dict(_LAND_NEUT)] * neut


# --- Dolphin lifecycle ----------------------------------------------------------------
def _status():
    try:
        return json.loads(D.control_pipe_quiet("status"))
    except Exception:
        return {}


def relaunch(verbose=True):
    exe = ENV.dolphin_exe()
    subprocess.run(["taskkill", "/F", "/IM", "Dolphin.exe"], capture_output=True)
    time.sleep(1.5)
    ENV.ensure_pause_at_end(exe, verbose=verbose)   # exhaust reads require pausing at movie end
    subprocess.Popen([exe], cwd=os.path.dirname(exe))
    for _ in range(40):
        if _status().get("ok"):
            if verbose: print("Dolphin relaunched (stopped game list)")
            return
        time.sleep(1.0)
    raise SystemExit("Dolphin did not come up after relaunch")


# --- readiness predicates (confirm the anchor's OWN loaded state, not just any readable link_state
# -- that fires on a transient mid-boot pointer before the anchor is in, the play_sticks bug) ------
def swim_ready(min_air=800):
    """Swim anchor loaded: neutral/moving-in-water state AND air still near full (also proves we
    caught the movie early, before free-run drained air)."""
    return lambda v: v["link_state"] in (54, 55) and v["air"] >= min_air


def land_ready(v):
    """Land anchor loaded: Link in an on-ground idle action state (FREE_WAIT 5 or the post-walk
    WAIT 4 -- anchors minted after a walk-and-stop settle rest in 4)."""
    return v["link_state"] in (4, 5)


def _attach_ready(ready):
    """Return (h, mem1, vals) once MEM1 is mapped, the player object reads, and ready(vals) holds;
    else None. State-agnostic: `ready` decides which loaded state counts (swim slate, land idle,
    ...), but the attach + successful read still gate on the anchor actually being loaded, keeping
    the race-safety of the old swim-only gate."""
    try:
        # D.attach() prints "Could not locate emulated MEM1" + sys.exits while MEM1 is unmapped
        # mid-boot; that's expected on early poll attempts, so swallow its stdout + the exit.
        _saved = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        try:
            h, m = D.attach()
        finally:
            sys.stdout.close(); sys.stdout = _saved
    except BaseException:
        return None
    try:
        vals = {k: D.read_named(h, m, k) for k in ("link_state", "air")}
    except BaseException:
        return None
    try:
        ok = bool(ready(vals))
    except BaseException:
        ok = False
    return (h, m, vals) if ok else None


# Fields read at both frame-0 (start) and exhaustion (end). Base set works in every state; the
# land two-angle/pos fields are read via the same player chain and guarded (harmless in swim).
_BASE_READS = ("potential_speed", "true_speed", "anim_frame", "air", "link_state",
               "link_x", "link_z", "facing")
_LAND_READS = ("pos_x", "pos_y", "pos_z", "travel_angle", "shape_angle_y",
               "target_angle", "ground_angle")


def _read_end(h, m):
    end = {}
    for k in _BASE_READS:
        end[k] = D.read_named(h, m, k)
    for k in _LAND_READS:                      # same player chain; guard so swim never trips on them
        try:
            end[k] = D.read_named(h, m, k)
        except BaseException:
            end[k] = None
    end["facing_deg"] = end["facing"] * 360.0 / 65536.0
    if end.get("shape_angle_y") is not None:
        end["shape_deg"] = end["shape_angle_y"] * 360.0 / 65536.0
        end["travel_deg"] = end["travel_angle"] * 360.0 / 65536.0
    end["net"] = math.hypot(end["link_x"] - X0, end["link_z"] - Z0)
    return end


_PLAYER_PTR = 0x803AD860       # deref -> player object base (Pp); proc @+0x3100, speedF @+0x17C


def _read_frame(h, m):
    """Compact per-frame read for `log_frames` tracing: pos/facing/proc/speedF/nspeed/state. proc +
    speedF come off the player chain (deref 0x803AD860) like spotcheck_rollstab / dtm_run_local."""
    Pp = struct.unpack('>I', D.read_bytes(h, m, _PLAYER_PTR, 4))[0]
    return {
        "pos_x": D.read_named(h, m, "link_x"), "pos_z": D.read_named(h, m, "link_z"),
        "pos_y": D.read_named(h, m, "link_y"),      # fall/OOB detector (drops below the floor Y)
        "facing": D.read_named(h, m, "facing") & 0xFFFF,
        "travel_angle": D.read_named(h, m, "travel_angle") & 0xFFFF,   # current.angle.y (cut foot-term aim)
        "state": D.read_named(h, m, "link_state"),
        "proc": struct.unpack('>i', D.read_bytes(h, m, Pp + 0x3100, 4))[0],
        "speedF": struct.unpack('>f', D.read_bytes(h, m, Pp + 0x17C, 4))[0],
        "nspeed": D.read_named(h, m, "potential_speed"),
        "anim": D.read_named(h, m, "anim_frame"),
    }


def _log_playback(ready, log_frames, verbose):
    """Per-frame trace of a movie playback (the `log_frames` path). Fast-polls (no 1s sleep) for the
    anchor-loaded gate so it catches the movie near frame 0, PAUSES, then single-steps advance(1) +
    _read_frame for `log_frames` frames (or until playback stops). Returns the list of per-frame dicts.
    The caller should prepend a few idle frames so the state-gate window is wide enough to catch idle
    (otherwise the fast-poll may land a couple frames in -- fine when aligning at a landmark)."""
    t0 = time.time(); slate = None
    while time.time() - t0 < 60:               # tight poll: catch the loaded savestate ASAP
        slate = _attach_ready(ready)
        if slate:
            break
        time.sleep(0.02)
    if not slate:
        raise SystemExit("log_playback: never reached the anchor-loaded gate")
    D.control_pipe_quiet("pause")
    h, m, _ = slate
    if verbose:
        print(f"  logging {log_frames} frames from the loaded gate (paused, single-stepping)")
    frames = []
    for i in range(log_frames):
        frames.append(_read_frame(h, m))
        D.control_pipe_quiet("advance", {"frames": 1})
        if not _status().get("playing"):
            frames.append(_read_frame(h, m))
            break
    return frames


# --- the engine -----------------------------------------------------------------------
def run_dtm(sticks, expected=None, *, game=None, anchor=DEFAULT_ANCHOR,
            template=DEFAULT_TEMPLATE, out=None, relaunch_dolphin=True,
            polls=4, seed=1, bootsecs=180, playsecs=360,
            min_air=800, tol=0.02, facing_tol=FACING_TOL_DEG, pos_tol=1.0,
            ready=None, watch=False, verbose=True, log_frames=None):
    """Author -> play -> read -> compare. Returns an endpoint dict (see module docstring).

    sticks   : list of {stickX, stickY, substickX?, substickY?} (one per game frame).
    expected : optional dict, any of {v, anim, air, state, facing, pos_x, pos_z, shape, travel}
               (angles in DEGREES); v/anim/state/air within tol, pos_x/pos_z within pos_tol,
               facing/shape/travel cyclically within facing_tol.
    game     : iso path; if None, derived from the anchor's '@<isokey>' tag.
    ready    : anchor-loaded readiness predicate over the read dict {link_state, air}. Default =
               swim_ready(min_air) (the original swim gate). Pass land_ready (or any predicate) to
               validate a non-swim state -- one playback path, all the gotchas, any player state.
    watch    : if True, pause a beat after the anchor loads and announce so a human can watch the
               (short) movie play on screen before resume. Verification is unaffected.
    The end state is read at movie exhaustion: the movie free-runs and is read once playback
    stops, which is exact because the emulator PAUSES at the last movie frame (PauseMovie, ensured
    by relaunch via dolphin_env). No per-frame pipe stepping -- that paid ControlPipe's per-frame
    DoFrameStep wait and ran ~100x slower.
    """
    if ready is None:
        ready = swim_ready(min_air)
    anchor = resolve_anchor(anchor)
    game = (game or iso_for_anchor(anchor)).replace('\\', '/')
    sticks = list(sticks)
    nframes = len(sticks)
    if out is None:
        out = os.path.join(_GEN, "run_dtm_tmp.dtm")
    info = DM.build_dtm_from_sticks(sticks, out, template, polls, seed)
    shutil.copyfile(anchor, out + ".sav")
    # Companion DTM beside the boot savestate: without it, State::Load ends a fromSaveState movie at
    # load for deep-session anchors (m_current_frame != 1). See memory superswim-land-dtm-playback.
    shutil.copyfile(out, out + ".sav.dtm")
    if verbose:
        print(f"authored {os.path.basename(out)}: {info['frames']} fr, "
              f"{info['rows']} rows; anchor={os.path.basename(anchor)}")

    if relaunch_dolphin:
        relaunch(verbose)
    D.control_pipe_quiet("playmovie", {"path": out.replace('\\', '/'), "game": game})
    if verbose: print(f"playmovie {os.path.basename(out)}")

    # PER-FRAME TRACE PATH: single-step + read each frame (diagnosing sim<->live divergence). Returns
    # the log in end["log"] and the final logged frame as the end read; skips the exhaust free-run.
    if log_frames:
        frames = _log_playback(ready, int(log_frames), verbose)
        D.control_pipe_quiet("pause")
        h, m = D.attach()
        end = _read_end(h, m)
        end.update(ended=True, armed=True, frames=nframes, advanced=None, start=None, log=frames)
        if verbose:
            print(f"  logged {len(frames)} frames (end proc=0x{frames[-1]['proc']:02x} "
                  f"pos=({frames[-1]['pos_x']:.2f},{frames[-1]['pos_z']:.2f}))")
        return end

    # boot: wait for the anchor-loaded readiness gate, NOT the playing flag (true all through boot,
    # so it can't tell the anchor is in; resuming early drives inputs on a dead game -- play_sticks bug).
    # SHORT-MOVIE HARDENING: a short movie can auto-play + exhaust before the 1s gate poll catches the
    # loaded state, so also watch the frame counter -- played-then-stopped -> read the end directly.
    t0 = time.time(); slate = None; saw_playing = False; frame_moved = False; last_frame = None
    boot_exhausted = False
    while time.time() - t0 < bootsecs:
        st = _status()
        if st.get("playing"):
            saw_playing = True
        fr = st.get("frame")
        if last_frame is not None and fr is not None and fr != last_frame:
            frame_moved = True
        last_frame = fr
        slate = _attach_ready(ready)
        if slate:
            if verbose: print(f"booted after {time.time()-t0:.1f}s (state={slate[2]['link_state']})")
            break
        if saw_playing and frame_moved and not st.get("playing"):
            boot_exhausted = True                # movie played+stopped before the gate caught it
            if verbose: print(f"movie auto-played+exhausted during boot ({time.time()-t0:.1f}s); "
                              f"reading end directly (gate missed -- short-movie path)")
            break
        time.sleep(1.0)
    if not slate and not boot_exhausted:
        raise SystemExit("never reached the anchor-loaded readiness gate (movie never played)")
    armed = bool(_status().get("playing")) or saw_playing

    ended = True
    if slate:
        # start-of-movie controllable values (frame 0, before any input) -- lets a caller seed
        # its prediction to the ACTUAL anchor instead of assuming a fixed cold-start seed.
        h0, m0, _ = slate
        start = {k: D.read_named(h0, m0, k) for k in
                 ("potential_speed", "anim_frame", "air", "link_state")}
        # Read at exhaustion: free-run, read once playback stops. The emulator PAUSES at the last movie
        # frame (PauseMovie, ensured by relaunch); no slow per-frame pipe stepping.
        if watch and verbose:
            print("  anchor loaded, paused at frame 0 -- RESUMING, watch Dolphin (short movie)")
            time.sleep(2.0)
        D.control_pipe_quiet("resume")
        t1 = time.time(); ended = False
        while time.time() - t1 < playsecs:
            if not _status().get("playing"):
                ended = True; break
            time.sleep(0.3)
    else:
        # short-movie path: the movie already exhausted during boot, so there is no frame-0 to read
        # and nothing to resume. Confirm it has settled (frame counter stable), then read the end.
        start = None
        t1 = time.time(); stable = 0; last_frame = None
        while time.time() - t1 < playsecs:
            fr = _status().get("frame")
            stable = stable + 1 if fr == last_frame else 0
            last_frame = fr
            if stable >= 4 and not _status().get("playing"):
                break
            time.sleep(0.3)
    D.control_pipe_quiet("pause")

    # PauseMovie can freeze before the final frame's air decrement commits, leaving the read one
    # air-tick early. One advance flushes that pending frame (air only) -> frame-accurate read.
    advanced = None
    if ended:
        try:
            D.control_pipe_quiet("advance", {"frames": 1})
            advanced = 1
        except BaseException:
            advanced = None

    h, m = D.attach()
    end = _read_end(h, m)
    end.update(ended=ended, armed=armed, frames=nframes, advanced=advanced, start=start)

    if expected:
        end["compare"] = _compare(end, expected, tol, facing_tol, pos_tol)
    if verbose:
        _print_end(end, expected)
    return end


def _compare(end, expected, tol, facing_tol, pos_tol=1.0):
    cyc = 26.0 if end["link_state"] == 54 else 23.0
    res = {"ok": True, "tol": tol}
    if "v" in expected:
        dv = end["potential_speed"] - expected["v"]
        res["dv"] = dv; res["ok"] &= abs(dv) <= max(tol, abs(expected["v"]) * 1e-4)
    if "anim" in expected:
        dan = A.animdiff(end["anim_frame"], expected["anim"], cyc)
        res["dan"] = dan; res["ok"] &= dan <= tol
    if "air" in expected:
        res["air_ok"] = (end["air"] == expected["air"]); res["ok"] &= res["air_ok"]
    if "state" in expected:
        res["state_ok"] = (end["link_state"] == expected["state"]); res["ok"] &= res["state_ok"]
    if "facing" in expected:
        dfac = abs(S.angdiff_deg(end["facing_deg"], expected["facing"]))
        res["dfac"] = dfac; res["ok"] &= dfac <= facing_tol
    # land two-angle + position (angles cyclic in deg; pos in world units)
    if "shape" in expected:
        dsh = abs(S.angdiff_deg(end["shape_deg"], expected["shape"]))
        res["dshape"] = dsh; res["ok"] &= dsh <= facing_tol
    if "travel" in expected:
        dtr = abs(S.angdiff_deg(end["travel_deg"], expected["travel"]))
        res["dtravel"] = dtr; res["ok"] &= dtr <= facing_tol
    if "pos_x" in expected:
        dpx = end["pos_x"] - expected["pos_x"]
        res["dpx"] = dpx; res["ok"] &= abs(dpx) <= pos_tol
    if "pos_z" in expected:
        dpz = end["pos_z"] - expected["pos_z"]
        res["dpz"] = dpz; res["ok"] &= abs(dpz) <= pos_tol
    return res


def _print_end(end, expected):
    posbit = ""
    if end.get("pos_z") is not None:
        posbit = (f" pos=({end['pos_x']:.1f},{end['pos_z']:.1f}) "
                  f"shape={end['shape_deg']:.1f} travel={end['travel_deg']:.1f}")
    print(f"  LIVE: v={end['potential_speed']:.3f} anim={end['anim_frame']:.4f} "
          f"air={end['air']} st={end['link_state']} face={end['facing_deg']:.1f} "
          f"net={end['net']:.0f}{posbit} armed={end['armed']} advanced={end['advanced']}"
          + ("" if end["ended"] else " [TIMEOUT]"))
    c = end.get("compare")
    if c:
        bits = []
        if "dv" in c: bits.append(f"dv={c['dv']:+.3f}")
        if "dan" in c: bits.append(f"dan={c['dan']:.3f}")
        if "air_ok" in c: bits.append(f"air={'ok' if c['air_ok'] else 'X'}")
        if "state_ok" in c: bits.append(f"state={'ok' if c['state_ok'] else 'X'}")
        if "dfac" in c: bits.append(f"dface={c['dfac']:.2f}deg")
        if "dshape" in c: bits.append(f"dshape={c['dshape']:.2f}deg")
        if "dtravel" in c: bits.append(f"dtravel={c['dtravel']:.2f}deg")
        if "dpx" in c: bits.append(f"dpx={c['dpx']:+.2f}")
        if "dpz" in c: bits.append(f"dpz={c['dpz']:+.2f}")
        print(("  PASS " if c["ok"] else "  FAIL ") + " ".join(bits))


# --- CLI ------------------------------------------------------------------------------
def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    # ready predicate: land -> land_ready (state 5); default swim gate otherwise.
    land = o.get('ready') == 'land' or 'up' in o or 'neut' in o
    ready = land_ready if land else None
    default_anchor = "land_flatwalk@twwgz" if land else DEFAULT_ANCHOR

    if 'seq' in o:
        seqpath = o['seq'] if os.path.exists(o['seq']) else os.path.join(
            _rb, 'fixtures', o['seq'])
        sticks = sticks_from_seq_file(seqpath)
        label = os.path.basename(seqpath)
    elif 'sticks' in o:
        sticks = DM.parse_seq(open(o['sticks']).read()); label = o['sticks']
    elif land:                                  # land walk: up=/neut= build the burst directly
        up, neut = int(o.get('up', 30)), int(o.get('neut', 15))
        sticks = land_walk_sticks(up, neut); label = f"land_walk ({up} up + {neut} neut)"
    else:
        raise SystemExit("pass seq=<action file>, sticks=<raw csv file>, or ready=land [up= neut=]")

    expected = {}
    if 'expect_v' in o: expected['v'] = float(o['expect_v'])
    if 'expect_anim' in o: expected['anim'] = float(o['expect_anim'])
    if 'expect_air' in o: expected['air'] = int(o['expect_air'])
    if 'expect_state' in o: expected['state'] = int(o['expect_state'])
    if 'expect_facing' in o: expected['facing'] = float(o['expect_facing'])
    if 'expect_shape' in o: expected['shape'] = float(o['expect_shape'])
    if 'expect_travel' in o: expected['travel'] = float(o['expect_travel'])
    if 'expect_pos_x' in o: expected['pos_x'] = float(o['expect_pos_x'])
    if 'expect_pos_z' in o: expected['pos_z'] = float(o['expect_pos_z'])

    print(f"=== run_dtm: {label} ({len(sticks)} frames) ===")
    run_dtm(sticks, expected or None,
            game=o.get('game'),                 # default: derived from anchor's @isokey tag
            anchor=o.get('anchor', default_anchor),
            template=o.get('template', DEFAULT_TEMPLATE),
            tol=float(o.get('tol', '0.02')),
            pos_tol=float(o.get('pos_tol', '1.0')),
            ready=ready,
            watch=o.get('watch', '0') in ('1', 'true', 'yes'),
            relaunch_dolphin=o.get('norelaunch', '0') not in ('1', 'true', 'yes'),
            bootsecs=int(o.get('bootsecs', '180')))


if __name__ == "__main__":
    main()
