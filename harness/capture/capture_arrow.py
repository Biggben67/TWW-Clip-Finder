"""Live capture of ARROW-SWIM charge on the current slot-10 slate.

Validates the decomp arrow/charge model (d_a_player_swim.inc setSpeedAndAngleSwim):
  m34E8 (world target) = stickAngle + 0x8000 + cameraAngle
  snap: |m34E8 - facing| > 0x6000 (135deg) -> facing := m34E8 instantly
  speed delta = mStickDistance * 3 * cos(facing_after - facing_before)
  move along facing, negative speed = backward.

Charge = alternate (Xbias,255)/(Xbias,0): Y full up/down, X biased to TILT the
alternation axis off straight-back by some beta -> arrow swimming. Xbias=128 is pure
back (baseline +3). As Xbias grows the snap rotation shrinks (less charge gain) and
Link drifts sideways toward the tilt; past ~45deg the snap dies (tip-over).

Per frame we record facing, potential_speed, x/z, state so we can check:
  (1) facing snap pattern, (2) speed delta vs 3*dist*cos(d_facing),
  (3) net drift direction/magnitude, (4) the tip-over Xbias.

Usage: python capture_arrow.py [xbias=128,145,160,180,195,205] [v=-300] [n=14]
                               [axis=y]   # y: alternate Y, bias X (E-W charge axis)
                                          # x: alternate X, bias Y (N-S charge axis ->
                                          #    90-deg-rotated arrow; drift runs E-W/west)
"""
import sys, struct, math
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D

NEU = (128, 128)

def adv(sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})

def wnamed(h, mem1, name, value):
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, mem1, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1:"B",2:"H",4:"I",8:"Q"}[sz],
                             int(value) & ((1 << (sz*8)) - 1)))
    D.write_bytes(h, mem1, addr, data)

def r(h, mem1, name):
    return D.read_named(h, mem1, name)

def to_deg(u16):
    return u16 * 360.0 / 65536.0

def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    xbiases = [int(x) for x in opts.get('xbias', '128,145,160,180,195,205').split(',')]
    v = float(opts.get('v', '-300')); n = int(opts.get('n', '14'))
    axis = opts.get('axis', 'y')   # 'y': alternate Y/bias X ; 'x': alternate X/bias Y

    # probe=SX,SY;SX,SY;... : from a common state-55 east-facing start (3 back-charge
    # frames), fire EACH candidate stick for k frames (fresh reload each) and report the
    # resulting facing + d_pot -> maps which gate snaps Link where (find N-S-axis snaps).
    if 'probe' in opts:
        cands = [tuple(int(t) for t in p.split(',')) for p in opts['probe'].split(';') if p]
        k = int(opts.get('k', '1'))
        PREP = [(128, 255), (128, 0), (128, 255)]   # -> state 55, facing east (16384)
        print(f"# PROBE k={k}  start=state55 facing east(16384) after 3 back-charge frames")
        print("stick       snap_facing(deg)   d_face   pot      kept?")
        for (sx, sy) in cands:
            D.cmd_control_pipe("savestate", {"action": "load", "slot": 10})
            h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()
            wnamed(h, mem1, "air", 900); wnamed(h, mem1, "potential_speed", v)
            for (px, py) in PREP:
                adv(px, py)
            f_before = r(h, mem1, "facing"); p_before = r(h, mem1, "potential_speed")
            for _ in range(k):
                adv(sx, sy)
            face = r(h, mem1, "facing"); pot = r(h, mem1, "potential_speed")
            dfc = ((face - f_before + 32768) % 65536) - 32768
            print(f"({sx:>3},{sy:<3})  {face:6d}({to_deg(face):5.0f})    {to_deg(dfc):+6.0f}  "
                  f"{pot:8.2f}  {'CHARGE' if pot < p_before else 'lost'}")
        D.cmd_control_pipe("clearinput")
        return

    # seq=SX,SY;SX,SY;... : apply an explicit per-frame stick sequence and report
    # facing/pot/move each frame. For testing instant-turnaround rotations (gate snaps),
    # e.g. East-facing -> NW gate (0,255) -> E gate (255,128) -> ... to net-rotate North.
    if 'seq' in opts:
        slot = int(opts.get('slot', '10'))
        steps = [tuple(int(t) for t in p.split(',')) for p in opts['seq'].split(';') if p]
        D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})
        h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()
        wnamed(h, mem1, "air", 900); wnamed(h, mem1, "potential_speed", v)
        cam = r(h, mem1, "csangle"); x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
        print(f"# SEQ v={r(h,mem1,'potential_speed'):.1f} cam={cam}({to_deg(cam):.0f}d) "
              f"face0={r(h,mem1,'facing')}({to_deg(r(h,mem1,'facing')):.0f}d)")
        print("f  stick      facing(deg)  dface  pot      d_pot  dx     dz   moveBrg state")
        pf = r(h, mem1, "facing"); pp = r(h, mem1, "potential_speed"); px, pz = x0, z0
        for i, (sx, sy) in enumerate(steps):
            adv(sx, sy)
            face = r(h, mem1, "facing"); pot = r(h, mem1, "potential_speed")
            x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z"); st = r(h, mem1, "link_state")
            dface = ((face - pf + 32768) % 65536) - 32768
            dx, dz = x - px, z - pz
            mb = math.degrees(math.atan2(dz, dx)) % 360 if (dx or dz) else 0
            net = math.hypot(x - x0, z - z0)
            nb = math.degrees(math.atan2(z - z0, x - x0)) % 360 if net else 0
            show = int(opts.get('every', '1'))
            if show and (i + 1) % show == 0:
                print(f"{i+1:<3}({sx:>3},{sy:<3}) {face:6d}({to_deg(face):5.0f}) {to_deg(dface):+6.0f} "
                      f"{pot:8.2f} {pot-pp:+6.2f} {dx:+6.0f} {dz:+6.0f} net={net:7.0f}@{nb:3.0f}  {st}")
            pf, pp, px, pz = face, pot, x, z
        netx, netz = x - x0, z - z0
        net = math.hypot(netx, netz); nb = math.degrees(math.atan2(netz, netx)) % 360
        # west = bearing 180 (dx<0). Report net heading + how purely west it is.
        print(f"\nSUMMARY {len(steps)} frames: net={net:.0f} bearing={nb:.0f}deg "
              f"(dx={netx:+.0f} dz={netz:+.0f})  endpot={pot:.1f}  "
              f"{'WEST-ward' if netx < 0 else 'EAST-ward'} "
              f"({'mostly west, |dx|>|dz|' if abs(netx) > abs(netz) else 'drift < charge-osc'})")
        D.cmd_control_pipe("clearinput")
        return

    # hold=SX,SY : hold a steady stick and watch Link's facing rotate (turn mapping).
    if 'hold' in opts:
        sx, sy = (int(t) for t in opts['hold'].split(','))
        D.cmd_control_pipe("savestate", {"action": "load", "slot": 10})
        h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()
        wnamed(h, mem1, "air", 900); wnamed(h, mem1, "potential_speed", v)
        cam = r(h, mem1, "csangle"); x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
        print(f"# HOLD stick=({sx},{sy}) v={r(h,mem1,'potential_speed'):.1f} "
              f"cam={cam}({to_deg(cam):.0f}d)")
        print("f  facing(deg)  pot      dx     dz   moveBrg state")
        px, pz = x0, z0
        for i in range(n):
            adv(sx, sy)
            face = r(h, mem1, "facing"); pot = r(h, mem1, "potential_speed")
            x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z"); st = r(h, mem1, "link_state")
            dx, dz = x - px, z - pz
            mb = math.degrees(math.atan2(dz, dx)) % 360 if (dx or dz) else 0
            print(f"{i+1:<2} {face}({to_deg(face):5.0f})  {pot:8.2f} {dx:+6.0f} {dz:+6.0f} "
                  f"{mb:5.0f}   {st}")
            px, pz = x, z
        D.cmd_control_pipe("clearinput")
        return

    for xb in xbiases:
        D.cmd_control_pipe("savestate", {"action": "load", "slot": 10})
        h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()
        wnamed(h, mem1, "air", 900); wnamed(h, mem1, "potential_speed", v)
        # optional pre-rotation: hold a steady turn-stick to reorient Link before
        # the arrow alternation (e.g. rot=255,128,14 turns east->north for a west arrow).
        if 'rot' in opts:
            rsx, rsy, rn = (int(t) for t in opts['rot'].split(','))
            for _ in range(rn):
                adv(rsx, rsy)
            print(f"  (pre-rotated {rn}f @({rsx},{rsy}) -> facing="
                  f"{r(h,mem1,'facing')}({to_deg(r(h,mem1,'facing')):.0f}d) "
                  f"pot={r(h,mem1,'potential_speed'):.1f})")
        cam = r(h, mem1, "csangle"); face0 = r(h, mem1, "facing")
        x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
        print(f"\n# axis={axis} BIAS={xb} (off={xb-128:+d})  seed v={r(h,mem1,'potential_speed'):.1f} "
              f"air={r(h,mem1,'air')} cam={cam}({to_deg(cam):.0f}d) face0={face0}({to_deg(face0):.0f}d)")
        print("f  stick      facing   dface  pot      d_pot   dx      dz    moveBrg net  netBrg")
        prev_face = face0; prev_pot = v
        px, pz = x0, z0
        for i in range(n):
            alt = 255 if i % 2 == 0 else 0          # full-deflection alternation
            if axis == 'x':
                sx, sy = alt, xb                    # alternate X, bias Y (N-S charge)
            else:
                sx, sy = xb, alt                    # alternate Y, bias X (E-W charge)
            adv(sx, sy)
            face = r(h, mem1, "facing"); pot = r(h, mem1, "potential_speed")
            x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z")
            st = r(h, mem1, "link_state")
            dface = ((face - prev_face + 32768) % 65536) - 32768   # signed s16 delta
            dx, dz = x - px, z - pz
            net = math.hypot(x - x0, z - z0)
            move_brg = math.degrees(math.atan2(dz, dx)) % 360      # this-frame move bearing
            net_brg = math.degrees(math.atan2(z - z0, x - x0)) % 360  # cumulative drift bearing
            print(f"{i+1:<2} ({xb},{sy:<3}) {face:6d}  {to_deg(dface):+6.0f}  {pot:8.2f} "
                  f"{pot-prev_pot:+7.2f} {dx:+7.0f} {dz:+6.0f} {move_brg:5.0f}  {net:6.0f} {net_brg:5.0f}")
            prev_face, prev_pot = face, pot
            px, pz = x, z
    D.cmd_control_pipe("clearinput")

if __name__ == "__main__":
    main()
