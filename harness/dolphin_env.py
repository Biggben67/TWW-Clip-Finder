"""dolphin_env.py -- machine-specific Dolphin/ISO paths + one-call live warm-up.

Dolphin command reference: ../tools/DOLPHIN_CONTROL.md (dolphin_mem.py -- the single source of truth).

Two jobs so a live run is a single command with zero manual setup:

1. PATHS. The Dolphin binary, the ISO directory, and the cold-start slate vary per machine, so
   they are NOT committed. Each resolves as:  env var  ->  dolphin.local.json (repo root)  ->  a
   computed default (relative to the repo, for the exe/slate; the ISO dir has no safe default and
   must come from env/config). Copy dolphin.local.example.json -> dolphin.local.json and edit.

2. WARM-UP. `ensure_running(iso)` makes the runner self-sufficient: it checks the control pipe,
   and if nothing usable is up it enables "Pause at end of movie" (required for fast, exact DTM
   playback -- see below), launches the pipe-enabled Release build, waits for the pipe, and boots
   the iso. If a game is already running it is reused as-is.

Why PauseMovie matters: run_dtm's fast `exhaust` read lets the movie free-run and reads the end
state once playback stops. That is only exact if the emulator PAUSES at the last movie frame; with
"Pause at end of movie" off (the Dolphin default) it would free-run past the end and read a wrong,
over-decayed state. `ensure_pause_at_end` writes `[Movie] PauseMovie = True` to the (portable) ini
BEFORE launch, so the guarantee holds on any machine.
"""
from __future__ import annotations
import os, sys, json, time, subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)                       # tww_sim repo root
_SPEEDRUN = os.path.dirname(_ROOT)                   # speedrunning/
_CONFIG = os.path.join(_ROOT, "dolphin.local.json")  # gitignored; see dolphin.local.example.json

_DEFAULT_EXE = os.path.join(_SPEEDRUN, "Dolphin-Zelda-TAS-Edition", "Binary", "x64",
                            "Release", "Dolphin.exe")  # the pipe-enabled build (ControlPipe.cpp)
_DEFAULT_SLATE = os.path.join(_ROOT, "fixtures", "savestate", "superswim_coldstart_slate.s10")

_cfg_cache = None


def _config() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        try:
            with open(_CONFIG) as f:
                _cfg_cache = json.load(f)
        except (OSError, ValueError):
            _cfg_cache = {}
    return _cfg_cache


def _resolve(env_var: str, cfg_key: str, default):
    """env var -> dolphin.local.json[cfg_key] -> default."""
    return os.environ.get(env_var) or _config().get(cfg_key) or default


def dolphin_exe() -> str:
    return _resolve("DOLPHIN_EXE", "dolphin_exe", _DEFAULT_EXE)


def isos_dir() -> str:
    d = _resolve("TWW_ISOS_DIR", "isos_dir", None)
    if not d:
        raise SystemExit(
            f"No ISO directory configured. Set TWW_ISOS_DIR, or add \"isos_dir\" to {_CONFIG} "
            f"(copy dolphin.local.example.json).")
    return d


def slate() -> str:
    return _resolve("TWWGZ_SLATE", "slate", _DEFAULT_SLATE)


def iso_path(key: str = "twwgz") -> str:
    """Resolve <isos_dir>/<key>.iso (exact match, else <key>*.iso)."""
    import glob
    exact = os.path.join(isos_dir(), key + ".iso")
    if os.path.exists(exact):
        return exact.replace("\\", "/")
    hits = glob.glob(os.path.join(isos_dir(), key + "*.iso"))
    if not hits:
        raise SystemExit(f"no iso for key '{key}' in {isos_dir()}")
    return hits[0].replace("\\", "/")


def tww_extract_dir() -> str | None:
    """Optional path to an already-extracted disc root (the dir CONTAINING `files/`).
    env TWW_EXTRACT_DIR -> dolphin.local.json["tww_extract_dir"] -> None (fall back to the ISO)."""
    return _resolve("TWW_EXTRACT_DIR", "tww_extract_dir", None)


def game_file_bytes(disc_path: str, iso_key: str = "twwgz") -> bytes:
    """Return the raw bytes of a disc file (e.g. 'files/res/Object/LkAnm.arc') WITHOUT committing
    any copyrighted game data: read it from tww_extract_dir if configured, else pull it straight
    from the configured ISO in memory via the wwrando GCM reader. Lets tools parse game assets on
    demand from the user's own dump. `disc_path` is relative to the disc root, forward slashes."""
    ed = tww_extract_dir()
    if ed:
        p = os.path.join(ed, disc_path.replace("/", os.sep))
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
    # fall back to reading the single file out of the ISO
    wwrando = os.path.join(_SPEEDRUN, "ww_model_helpers", "wwrando")
    if wwrando not in sys.path:
        sys.path.insert(0, wwrando)
    from wwlib.gcm import GCM
    gcm = GCM(iso_path(iso_key))
    gcm.read_entire_disc()
    return gcm.read_file_data(disc_path).getvalue()


def object_arc_bytes(name: str, iso_key: str = "twwgz") -> bytes:
    """Raw bytes of files/res/Object/<name>.arc from the user's dump (extract dir or ISO)."""
    return game_file_bytes(f"files/res/Object/{name}.arc", iso_key)


# --- "Pause at end of movie" (required for exact `exhaust` DTM reads) ------------------
def _user_dir(exe: str) -> str:
    d = os.path.dirname(exe)
    if os.path.exists(os.path.join(d, "portable.txt")):   # portable build: User/ next to the exe
        return os.path.join(d, "User")
    return os.path.join(os.environ.get("APPDATA", ""), "Dolphin Emulator")


def ensure_pause_at_end(exe: str | None = None, verbose: bool = True) -> None:
    """Set [Movie] PauseMovie = True in Dolphin.ini (default is False). Call BEFORE launch --
    Dolphin rewrites its ini on exit, so editing a running instance's ini is futile."""
    ini = os.path.join(_user_dir(exe or dolphin_exe()), "Config", "Dolphin.ini")
    try:
        lines = open(ini, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    out, in_movie, done = [], False, False
    for ln in lines:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            if in_movie and not done:        # leaving [Movie] without having seen the key
                out.append("PauseMovie = True"); done = True
            in_movie = (s == "[Movie]")
        elif in_movie and s.lower().startswith("pausemovie"):
            ln = "PauseMovie = True"; done = True
        out.append(ln)
    if not done:
        if not any(l.strip() == "[Movie]" for l in out):
            out.append("[Movie]")
        out.append("PauseMovie = True")
    os.makedirs(os.path.dirname(ini), exist_ok=True)
    open(ini, "w", encoding="utf-8").write("\n".join(out) + "\n")
    if verbose:
        print("ensured [Movie] PauseMovie = True")


# --- warm-up ---------------------------------------------------------------------------
def _status(D):
    """Pipe status dict, or None if the pipe isn't reachable (or the instance is ambiguous)."""
    try:
        return json.loads(D.control_pipe_quiet("status"))
    except BaseException:
        return None


def _slate_loadable(D, ready_slate: str) -> bool:
    """True once the slate loads AND its game state reads back -- i.e. the game engine is live.
    Right after boot the console sits at the logo/health screen where the player object doesn't
    exist yet (pointer 0x803ad860 is null) and a loadstate won't take; this gates on real
    readiness so advanceseq/loadstate callers don't hit a null-pointer read."""
    try:
        # action "load" + path (the pipe matches the quoted token "load"; "loadfile" would miss it)
        D.control_pipe_quiet("savestate", {"action": "load", "path": ready_slate.replace("\\", "/")})
        _saved, sys.stdout = sys.stdout, open(os.devnull, "w")   # D.attach() is chatty pre-MEM1
        try:
            h, m = D.attach()
        finally:
            sys.stdout.close(); sys.stdout = _saved
        return D.read_named(h, m, "link_state") in (54, 55)
    except BaseException:
        return False


def _boot(D, iso: str, timeout: float, verbose: bool, ready_slate: str | None = None):
    D.control_pipe_quiet("boot", {"path": iso.replace("\\", "/")})
    t0 = time.time()
    running = False
    while time.time() - t0 < timeout:
        if not running:
            running = bool((_status(D) or {}).get("state") == "running")
        elif ready_slate is None or _slate_loadable(D, ready_slate):
            if verbose:
                print(f"booted {os.path.basename(iso)} ({time.time()-t0:.0f}s)")
            return
        time.sleep(1.0)
    raise SystemExit(f"boot of {iso} never became {'loadable' if ready_slate else 'running'}")


def ensure_running(iso: str | None = None, *, iso_key: str = "twwgz", ready_slate: str | None = None,
                   verbose: bool = True, launch_timeout: float = 60, boot_timeout: float = 180):
    """Guarantee a pipe-reachable Dolphin with the game loaded. Reuses an existing running
    instance; otherwise enables PauseMovie, launches the Release build, and boots `iso`. When a
    boot happens and `ready_slate` is given, waits until that slate actually loads (game engine
    live) so a loadstate/advanceseq caller won't read a null pointer. Returns the iso path used.
    Idempotent -- safe to call at the top of every live run."""
    import dolphin_mem as D
    iso = (iso or iso_path(iso_key)).replace("\\", "/")

    if D.list_dolphin_pids():
        st = _status(D)
        if st is not None:                       # pipe is up -> reuse this instance
            if st.get("state") != "running":
                _boot(D, iso, boot_timeout, verbose, ready_slate)
            elif verbose:
                print("reusing running Dolphin")
            return iso
        raise SystemExit(
            "A Dolphin is running but its control pipe isn't responding -- it is probably a build "
            "without ControlPipe. Close it and re-run; the runner will launch the Release build.")

    # Nothing up: set the movie-pause guarantee, launch the pipe-enabled build, wait, boot.
    ensure_pause_at_end(verbose=verbose)
    exe = dolphin_exe()
    if not os.path.exists(exe):
        raise SystemExit(f"Dolphin.exe not found: {exe}\nSet DOLPHIN_EXE or dolphin_exe in {_CONFIG}.")
    if verbose:
        print(f"launching {exe}")
    subprocess.Popen([exe], cwd=os.path.dirname(exe))
    t0 = time.time()
    while time.time() - t0 < launch_timeout:
        if D.list_dolphin_pids() and _status(D) is not None:
            break
        time.sleep(1.0)
    else:
        raise SystemExit("Dolphin launched but its control pipe never came up")
    _boot(D, iso, boot_timeout, verbose, ready_slate)
    return iso
