"""Live spot-check of a FULL front-end + cruise plan (charge/arrow -> reorient -> ESS).

Validates plan_with_frontend end-to-end (TODO #4): the reorient snap-chains, the ramped
arrow alpha-schedule, and the cruise hand-off, replayed live and compared per frame to
the planner/sim prediction. Progress is measured TOWARD the target (west on the slate =
-x), matching the cruise DP's forward = -x convention.

Flow: loadstate -> settle -> seed (v, air) -> hold ESS to steady state 55 -> read the
REAL (v, anim, air, facing) -> plan_with_frontend FROM THOSE REAL VALUES -> build the
live stick sequence (reorient-in chain + arrow ramp via arrow_sticks + reorient-out chain
+ cruise seq) -> replay, comparing v and progress-toward-target each frame.

Usage: python spotcheck_frontend.py [v=-150] [air=900] [dest=20000] [slot=10]
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
from tww_sim.swim import sim as S
from tww_sim.swim import plan as P

ESS = (128, 110)
NEU = (128, 128)
CHG_UP, CHG_DN = (128, 255), (128, 0)
SETTLE = 6


def adv(sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})


def wnamed(h, mem1, name, value):
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, mem1, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    D.write_bytes(h, mem1, addr, data)


def r(h, mem1, name):
    return D.read_named(h, mem1, name)


def build_sticks(plan, facing0, cam):
    """Translate a plan_with_frontend result into a live (sx,sy) sequence + per-frame tag.
    Mirrors frontend_prefix EXACTLY: reorient-OUT is computed from the actual post-arrow
    (tilted) facing via a throwaway ArrowState replay, not the nominal axis."""
    axis = (cam - 180.0 - 90.0) % 360.0
    cruise_f = (cam - 180.0) % 360.0
    chain_in = S.reorient_chain(facing0, axis, cam) or []
    seq = [(st, 'R-in') for st in chain_in]
    # replay in+arrow on a throwaway state to find the actual post-arrow facing
    st = S.ArrowState(facing_deg=facing0, cam_deg=cam)
    for sx, sy in chain_in:
        st.step(sx, sy)
    for i, a in enumerate(plan['schedule']):
        pair = S.arrow_sticks(a, drift_down=P.ARROW_DRIFT_DOWN)
        seq.append((pair[i % 2], f'arw{a:.0f}'))
        st.step(*pair[i % 2])
    settled = st._pending_facing if st._pending_facing is not None else st.facing
    for s2 in S.reorient_chain(settled, cruise_f, cam) or []:
        seq.append((s2, 'R-out'))
    seq.append((ESS, 'settle'))      # 1-frame-lag settle: final R-out snap lands -> cruise
    tog = 0
    for a in plan['cruise']['actions']:
        if a == 'ess':
            seq.append((ESS, 'ess'))
        elif a == 'neu':
            seq.append((NEU, 'neu'))
        else:
            seq.append((CHG_UP if tog == 0 else CHG_DN, 'chg')); tog ^= 1
    return seq


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    v = float(opts.get('v', '-150')); air_seed = int(opts.get('air', '900'))
    dest = float(opts.get('dest', '20000')); slot = int(opts.get('slot', '10'))

    D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})
    h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()
    wnamed(h, mem1, "air", air_seed); wnamed(h, mem1, "potential_speed", v)
    for _ in range(SETTLE):
        adv(*ESS)
    v0 = r(h, mem1, "potential_speed"); anim0 = r(h, mem1, "anim_frame")
    air0 = r(h, mem1, "air"); st0 = r(h, mem1, "link_state")
    facing0 = r(h, mem1, "facing") * 360.0 / 65536.0
    cam = r(h, mem1, "csangle") * 360.0 / 65536.0
    print(f"start: v={v0:.2f} anim={anim0:.3f} air={air0} state={st0} "
          f"facing={facing0:.0f} cam={cam:.0f}")

    plan = P.plan_with_frontend(dest, v0, anim0, air0, facing0=facing0,
                                target_bearing=180.0, cam_deg=cam, verbose=False)
    if plan is None:
        print("no plan"); D.cmd_control_pipe("clearinput"); return
    sch = plan['schedule']
    ramp = f"{sch[0]:.0f}->{sch[-1]:.0f}" if sch else "none"
    print(f"plan: total={plan['total']}  prefix {plan['prefix_frames']} "
          f"({plan['n_in']} R-in + {plan['n_arrow']} arrow ramp {ramp} "
          f"+ {plan['n_out']} R-out)  "
          f"cruise {plan['cruise_frames']}  pred progress {plan['progress']:.0f}")

    # replay, LOGGING FACING every frame so reorient snaps can be verified as INSTANT
    # turnarounds (|dface|>135 = SNAP) and not slow ~7deg/fr gradual turns.
    seq = build_sticks(plan, facing0, cam)
    x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
    prev_face = facing0
    print("\nf   stick      tag     facing  dface   kind   v_live   prog(W)  st")
    pref_n = plan['prefix_frames']
    for i, (stick, tag) in enumerate(seq, 1):
        adv(*stick)
        vl = r(h, mem1, "potential_speed")
        an = r(h, mem1, "anim_frame")
        face = r(h, mem1, "facing") * 360.0 / 65536.0
        dface = ((face - prev_face + 180.0) % 360.0) - 180.0
        kind = 'SNAP' if abs(dface) > 135.0 else ('turn' if abs(dface) > 1.0 else '-')
        x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z")
        prog = -(x - x0)                       # west = -x = toward target
        zoff = z - z0                          # cross-axis (N-S) excursion
        stt = r(h, mem1, "link_state")
        if i <= pref_n + 3 or i % 15 == 0 or i == len(seq):
            print(f"{i:<3} ({stick[0]:>3},{stick[1]:<3}) {tag:<6} {face:6.0f} "
                  f"{dface:+6.0f}  {kind:<4} {vl:8.1f} an={an:5.2f} {prog:8.0f} "
                  f"z{zoff:+6.0f} {stt}")
        prev_face = face
    xf = r(h, mem1, "link_x"); zf = r(h, mem1, "link_z")
    net_w = -(xf - x0)
    print(f"\nfinal progress toward target (W): live={net_w:.0f}  plan dest={dest:.0f}")
    print(f"prefix predicted progress={plan['progress']:.0f}; "
          f"end v predicted={plan['prefix_end'][0]:.1f}")
    D.cmd_control_pipe("clearinput")


if __name__ == "__main__":
    main()
