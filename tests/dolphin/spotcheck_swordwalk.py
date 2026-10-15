"""Live spot-check of the SWORD-DRAWN dash foot pose -- the Dolphin source-of-truth regression for
the DASHS fix. When the sword is equipped, getAnmData (d_a_player_main.cpp mSwordAnmIndexTable)
swaps ANM_DASH -> ANM_DASHS: the sword-drawn dash poses DIFFERENT leg rotations, so the foot toe
(and hence posMoveFromFootPos's f31_2, the dip-frame speedF) differs from the sheathed 'dash'. The
sim used 'dash' for both, so any partial-magnitude (m3598>0) frame off a sword-drawn dash cruise had
speedF off ~0.08u. It slipped through because pure dash-cruise toe is invisible to position (m3598=0
there): the from-rest on-axis suite only ever validated the WALK toe via speedF, never the dash toe.

Two checks against the LIVE game (bit-exact / 0 ULP):
  (A) DATA: the game's LOADED dashs keyframe rotation data (walked out of the resident
      J3DAnmTransform in RAM) == the sim's _generated/anim/link_anim_walk_dash.json['dashs']. Guards
      against a regenerate-from-wrong-arc or wrong-anim-name regression.
  (B) POSE: play a constant-stick sword-drawn dash cruise; reproduce the sim's sword-dash right-foot
      toe posed at each frame's LIVE frame-ctrl / pos / facing, and assert its X/Z (the f31_2 inputs)
      match the game's stored mFootData rtoe (0x3CF8 = posMoveFromFootPos's own output) bit-exact,
      with the 1-frame mFootData lag (live rtoe[k] == pose at frame k-1). Compared to the GAME's
      stored toe, not a Python re-derivation from anmMtx (that carries world-magnitude ~9100
      quantization). Wall-collision frames (per-frame advance below the cruise step) are excluded --
      out of scope (LandState has no DZB wall collision).

Independent of the calibration seed (compares the POSE, not the accumulated f31_2). The end-to-end
dip-speedF 0-ULP (which additionally needs an exact f31_2/m359C seed) is a separate frontier.

SETUP: Dolphin twwgz booted; the anchor kaze_r11_rollstab_idle2@twwgz (sword-out WAIT(4)) is minted.

Usage:  python tests/dolphin/spotcheck_swordwalk.py
"""
import os, sys, struct, json, math  # >>> repo bootstrap: locate tww_sim/ package + ../tools/
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
import harness.dtm.run_dtm as R
from tww_sim.core.anim import fk
from tww_sim.core.anim.foot_fk import FootFK

ANCHOR = "kaze_r11_rollstab_idle2@twwgz"
AIM = (77, 249)                 # decodes facing 33295 at this anchor's csangle; full magnitude (regime 3)
NCRUISE = 18                    # constant sword-dash cruise frames (pos_z ~1005 -> ~700; clear of the seam)
IDX_DASHS = 116                 # dRes_INDEX_LKANM_BCK_DASHS_e in this JP build (verified live)
CRUISE_STEP_MIN = 16.0          # per-frame advance below this => wall-slowed => excluded (cruise ~17)


def bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def _rd_mtx(h, m, addr):
    b = D.read_bytes(h, m, addr, 48)
    return [list(struct.unpack('>4f', b[i * 16:i * 16 + 16])) for i in range(3)]


def _ram_rot_track(h, m, anm_ptr, j, axis):
    """(count, [values]) of the rotation KeyTable for joint j / axis from a live J3DAnmTransformKey."""
    mRot = struct.unpack('>I', D.read_bytes(h, m, anm_ptr + 0x14, 4))[0]
    mTab = struct.unpack('>I', D.read_bytes(h, m, anm_ptr + 0x28, 4))[0]
    ent = mTab + (j * 3 + axis) * 0x12 + 6                       # rotation KeyTableBase (2nd of S/R/T)
    cnt = struct.unpack('>H', D.read_bytes(h, m, ent, 2))[0]
    off = struct.unpack('>H', D.read_bytes(h, m, ent + 2, 2))[0]
    tt = struct.unpack('>H', D.read_bytes(h, m, ent + 4, 2))[0]
    st = 3 if tt == 0 else 4
    vals = [struct.unpack('>h', D.read_bytes(h, m, mRot + (off + st * i + 1) * 2, 2))[0]
            for i in range(cnt)]
    return cnt, vals


def check_data(cap):
    """(A) game's loaded DASHS rotation data == the sim json['dashs'], for the leg joints."""
    if cap.get("dashs") is None:
        return ["DASHS anmTransform never observed live (MOVE1 != %d)" % IDX_DASHS]
    JSON = json.load(open(os.path.join(_rb, "_generated", "anim", "link_anim_walk_dash.json")))
    a = JSON["dashs"]
    h, m = cap["h"], cap["m"]
    bad = []
    for j in (34, 36, 37, 38, 39):
        for axis in range(3):
            rc, rv = _ram_rot_track(h, m, cap["dashs"], j, axis)
            jc, joff, jtt = a['joints'][j]['r'][axis]
            st = 3 if jtt == 0 else 4
            jv = [a['rot_data'][joff + st * i + 1] for i in range(jc)]
            if rc != jc or rv != jv:
                bad.append("dashs jnt%d ax%d: RAM(cnt=%d) != json(cnt=%d)" % (j, axis, rc, jc))
    return bad


def check_pose(rows):
    """(B) sword-dash RFOOT toe posed at frame k-1's live ctrl/pos/facing == live stored rtoe[k], X/Z.

    (excludes wall-slowed frames; only pure-DASHS cruise). Returns (bad_list, n_checked, max_ulp)."""
    anm, sk = fk.load()
    bad = []
    n = 0
    max_ulp = 0
    for k in range(1, len(rows)):
        prev, cur = rows[k - 1], rows[k]
        if prev["mv0"] != IDX_DASHS or prev["mv1"] != IDX_DASHS:
            continue                                            # pure DASHS cruise pose only
        adv = math.hypot(cur["pos_x"] - prev["pos_x"], cur["pos_z"] - prev["pos_z"])
        if adv < CRUISE_STEP_MIN:
            continue                                            # wall-slowed frame -> out of scope
        ff = FootFK(anm, sk, world=True); ff._engine = None     # fresh, stateless (morf off), Python FK
        ff.set_pos(prev["pos_x"], prev["pos_z"], facing=prev["facing"])
        feet = ff.step_feet('dashs', 'dashs', prev["pose0"], prev["pose1"], 1.0, i_morf=-1.0)
        sim = (feet[0], feet[1], feet[2])                       # sim right-toe (model space)
        live = cur["rtoe"]                                      # game stored mFootData rtoe (posMove output)
        dx = bits(sim[0]) - bits(live[0]); dz = bits(sim[2]) - bits(live[2])
        n += 1
        max_ulp = max(max_ulp, abs(dx), abs(dz))
        if dx != 0 or dz != 0:
            bad.append("f0=%.4f: sim X/Z=(%.6f,%.6f) live=(%.6f,%.6f) dULP=(%d,%d)" % (
                prev["pose0"], sim[0], sim[2], live[0], live[2], dx, dz))
    return bad, n, max_ulp


def check_selection():
    """(C) the anim SELECTION regression (the original bug form): UnderAnimState must pick ANM_DASHS
    for the DASH slot when the sword is equipped, and plain 'dash' when it is not. Offline; catches a
    revert of the getAnmData sword-table port even if the DASHS data + FK stay correct."""
    from tww_sim.core.anim.anim_state import UnderAnimState
    bad = []
    sw = UnderAnimState(move0_anim='dashs', move0_frame=10.0, m34C3=1, sword=True)
    st = sw.step(17.0)                                  # regime 3 (DASH cruise): MOVE0 == MOVE1 == dash slot
    if st['move0'] != 'dashs' or st['move1'] != 'dashs':
        bad.append("sword=True regime3 -> move0/move1=%s/%s (expected dashs/dashs)"
                   % (st['move0'], st['move1']))
    sh = UnderAnimState(move0_anim='dash', move0_frame=10.0, m34C3=1, sword=False)
    st = sh.step(17.0)
    if st['move0'] != 'dash' or st['move1'] != 'dash':
        bad.append("sword=False regime3 -> move0/move1=%s/%s (expected dash/dash)"
                   % (st['move0'], st['move1']))
    # regime 2 (WALK<->DASH blend): MOVE1 is the dash slot
    sw2 = UnderAnimState(move0_anim='dashs', move0_frame=10.0, m34C3=1, sword=True)
    st = sw2.step(12.75)                                # f30 = 12.75/17 = 0.75 -> regime 2
    if st['move1'] != 'dashs':
        bad.append("sword=True regime2 -> move1=%s (expected dashs)" % st['move1'])
    return bad


def capture():
    cap = {}
    rows = []
    _orig = R._read_frame

    def rich(h, m):
        d = _orig(h, m)
        Pp = struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]
        clm = struct.unpack('>I', D.read_bytes(h, m, Pp + 0x254, 4))[0]
        node = struct.unpack('>I', D.read_bytes(h, m, clm + 0x8C, 4))[0]
        a1 = struct.unpack('>I', D.read_bytes(h, m, Pp + 0x2EE8, 4))[0]   # MOVE1 anmTransform*
        mv0 = struct.unpack('>H', D.read_bytes(h, m, Pp + 0x2F04, 2))[0]
        mv1 = struct.unpack('>H', D.read_bytes(h, m, Pp + 0x2F14, 2))[0]
        a0 = struct.unpack('>I', D.read_bytes(h, m, Pp + 0x2EE0, 4))[0]
        d["_row"] = dict(
            pose0=struct.unpack('>f', D.read_bytes(h, m, a0 + 0x8, 4))[0],
            pose1=struct.unpack('>f', D.read_bytes(h, m, a1 + 0x8, 4))[0],
            mv0=mv0, mv1=mv1, pos_x=d["pos_x"], pos_z=d["pos_z"], facing=d["facing"] & 0xFFFF,
            rtoe=struct.unpack('>3f', D.read_bytes(h, m, Pp + 0x3CF8, 12)))
        if "h" not in cap:
            cap["h"] = h; cap["m"] = m
        if mv1 == IDX_DASHS and "dashs" not in cap:
            cap["dashs"] = a1
        return d
    R._read_frame = rich
    sticks = [dict(stickX=AIM[0], stickY=AIM[1], substickX=128, substickY=128, buttons=0)] * NCRUISE
    end = R.run_dtm(sticks, anchor=ANCHOR, ready=R.land_ready, relaunch_dolphin=True,
                    log_frames=NCRUISE, verbose=True)
    R._read_frame = _orig
    for f in end["log"]:
        if "_row" in f:
            rows.append(f["_row"])
    return cap, rows


def main():
    sel_bad = check_selection()                         # (C) offline; no Dolphin needed
    cap, rows = capture()
    data_bad = check_data(cap)
    pose_bad, n, max_ulp = check_pose(rows)
    print("\n(A) DATA (game loaded dashs == sim json['dashs']): %s" % ("OK" if not data_bad else "FAIL"))
    for b in data_bad[:10]:
        print("    " + b)
    print("(B) POSE (sword-dash RFOOT toe X/Z == live stored rtoe, 0 ULP over %d cruise frames, "
          "max dULP=%d): %s" % (n, max_ulp, "OK" if not pose_bad else "FAIL"))
    for b in pose_bad[:10]:
        print("    " + b)
    print("(C) SELECTION (UnderAnimState picks dashs when sword, dash when not): %s"
          % ("OK" if not sel_bad else "FAIL"))
    for b in sel_bad[:10]:
        print("    " + b)
    ok = not data_bad and not pose_bad and not sel_bad and n > 0
    print("\n%s" % ("PASS -- sword-dash foot pose is bit-exact vs Dolphin" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
