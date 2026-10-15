"""land_capture.py — drive a land-movement input burst on the LIVE game from a test-owned
anchor and log the two-angle model (travel vs facing vs target) + speed per frame to CSV.

First land-milestone validator (flat, wall-free room). Free-cam: C-stick is held FULL DOWN
(substickY=0) every frame so the auto-camera can't flip. Default burst = hold UP (forward)
for `up` frames, then release to neutral and log the decel until Link is at a standstill.

Attaches ONCE and reads memory natively each frame (fast). Non-dense inputs (a steady hold,
then neutral) so per-frame advancewith is race-safe (the pt-21 pipe jitter only hits dense
back-to-back charge alternation).

Usage:
  python land_capture.py [anchor=land_flatwalk@twwgz] [up=30] [out=land_walk.csv] [maxsettle=50]
  python land_capture.py seq=<file> [anchor=...] [out=...]     # arbitrary per-frame sequence

seq file lines (phase-labeled; ';'/'#' comments ok):
  phase,stickX,stickY[,substickX=128][,substickY=0][,count=1][,buttons=0][,triggerL=0]
  buttons = GC PAD_BUTTON mask (hex ok, e.g. 0x40=L, 0x100=A); triggerL 0..255 (analog L).

The tech-defining trio to watch: target_angle (stick+camera WANT) vs travel_angle (velocity
ACTUALLY points) vs shape_angle_y (body VISUALLY points). They diverge on turns/reversals.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
_rb = os.path.dirname(os.path.abspath(__file__))  # >>> repo bootstrap: locate tww_sim/ + ../tools/
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm
from harness.dtm.run_dtm import resolve_anchor

# Angle fields (u16 heading) + speed/pos. Trio = target/travel/shape.
READS = ["target_angle", "travel_angle", "shape_angle_y", "facing", "csangle",
         "potential_speed", "true_speed", "max_normal_speed", "msd", "link_state",
         "ground_angle", "pos_x", "pos_z", "anim_frame",
         # Walk-position (posMoveFromFootPos) internals: the MOVE0/MOVE1 anim controllers, the
         # WALK<->DASH blend (m3598), and the planted-foot XZ delta f31_2 (m359C, one frame late).
         "fc_rate", "move1_frame", "move1_rate", "blend_move", "foot_delta_prev", "msd_prev"]

# buttons:0 EXPLICITLY every frame -- the override persists (advancewith doesn't clear it), so a
# stale A/Start would inject a phantom roll/menu; press a button only when a step needs it.
CDOWN = {"substickX": 128, "substickY": 0, "buttons": 0}  # C-stick full down = forced free cam
UP    = {"stickX": 128, "stickY": 255, **CDOWN}
NEUT  = {"stickX": 128, "stickY": 128, **CDOWN}


def deg(a):
    return (a * 360.0 / 65536.0)


def parse_land_seq(path):
    """Land seq file -> [(phase, input_dict)]. See module docstring for the line format."""
    frames = []
    for ln in open(path):
        ln = ln.split('#', 1)[0].split(';', 1)[0].strip()
        if not ln:
            continue
        p = [x.strip() for x in ln.split(',')]
        phase, sx, sy = p[0], int(p[1], 0), int(p[2], 0)
        csx = int(p[3], 0) if len(p) > 3 else 128
        csy = int(p[4], 0) if len(p) > 4 else 0
        cnt = int(p[5], 0) if len(p) > 5 else 1
        btn = int(p[6], 0) if len(p) > 6 else 0
        trigL = int(p[7], 0) if len(p) > 7 else 0
        for _ in range(cnt):
            frames.append((phase, {"stickX": sx, "stickY": sy, "substickX": csx,
                                   "substickY": csy, "buttons": btn, "triggerL": trigL}))
    return frames


def main():
    o = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    anchor = o.get("anchor", "land_flatwalk@twwgz")
    up = int(o.get("up", 30))
    maxsettle = int(o.get("maxsettle", 50))
    out = o.get("out", "land_walk.csv")
    sav = resolve_anchor(anchor)

    # Clear the stale input override first (a leftover A/Start would corrupt the capture), then
    # load the anchor FILE (slot-independent), pausing first like loadstate does.
    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})

    h, mem1 = dm.attach()

    def snap():
        return {nm: dm.read_named(h, mem1, nm) for nm in READS}

    rows = []
    prev = snap()
    rows.append({"f": 0, "phase": "rest", **prev})

    def step(inp, phase, i):
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        cur = snap()
        rows.append({"f": i, "phase": phase, **cur})
        return cur

    i = 0
    if "seq" in o:
        for phase, inp in parse_land_seq(o["seq"]):
            i += 1
            step(inp, phase, i)
    else:
        for _ in range(up):
            i += 1
            step(UP, "up", i)
        # release: feed neutral until standstill (speed ~0 for 3 consecutive) or maxsettle
        still = 0
        for _ in range(maxsettle):
            i += 1
            cur = step(NEUT, "neutral", i)
            if abs(cur["potential_speed"]) < 0.05 and abs(cur["true_speed"]) < 0.05:
                still += 1
                if still >= 3:
                    break
            else:
                still = 0

    cols = ["f", "phase", *READS]
    with open(os.path.join(HERE, out), "w", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"wrote {out}: {len(rows)} rows (up={up})\n")

    # link_state is printed every frame: an UNEXPECTED state (e.g. a roll/attack from a stray
    # button press) is the fastest tell that the input isn't the clean walk you think it is.
    print(" f  phase   | st |  pot    true  |  m0fr  m0rt   m1fr  m1rt | blend  fdelta |  pos_z")
    for r in rows:
        print(f"{r['f']:>2}  {r['phase']:<7} | {r['link_state']:>2} | "
              f"{r['potential_speed']:6.2f} {r['true_speed']:6.2f} | "
              f"{r['anim_frame']:5.2f} {r['fc_rate']:5.2f}  {r['move1_frame']:5.2f} {r['move1_rate']:5.2f} | "
              f"{r['blend_move']:5.3f} {r['foot_delta_prev']:6.3f} | {r['pos_z']:9.3f}")


if __name__ == "__main__":
    main()
