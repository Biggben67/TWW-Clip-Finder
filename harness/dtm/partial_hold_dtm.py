"""LIVE proof: do partial-depth holds inserted mid-charge behave as the sim predicts?

Two sequences, identical except the depth of a 4-frame consecutive HOLD block mid-build:
  A: 25x chg + 4x ess(128,110) + 10x chg
  B: 25x chg + 4x ess:77(128,77) + 10x chg
The sim predicts A and B DIVERGE (consecutive holds let the lagged hold gains land, so depth
matters). This authors a clean DTM for each, plays it on real Dolphin, and compares the live
endpoint to the sim prediction. If live matches sim -> the partial-hold-during-charge model is
correct. If live diverges -> the sim is missing a mechanic (user's hunch).

Usage: python partial_hold_dtm.py
"""
import sys, os
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S
from tww_sim.swim import actions as A
from harness.dtm.run_dtm import run_dtm, sticks_from_actions

COLD_ANIM = 0.06392288208007812


def seq(holdraw):
    hold = 'ess' if holdraw == 110 else f'ess:{holdraw}'
    return ['chg'] * 25 + [hold] * 4 + ['chg'] * 10


def predict(acts):
    s = S.SwimState(v=0.0, anim=COLD_ANIM, air=900); s.state = 54; s._entry_tax = False
    for a in acts:
        s.step(a)
    return s


def main():
    variants = [('110-holds (ESS)', 110), ('77-holds (partial)', 77)]
    preds = {}
    print("=== SIM predictions ===")
    for name, hr in variants:
        s = predict(seq(hr))
        preds[hr] = s
        print(f"  {name:20s}: v={s.v:.4f} anim={s.anim:.4f} air={s.air} st={s.state} -x={-s.x:.3f}")
    dv = abs(preds[110].v - preds[77].v)
    print(f"  sim says they DIVERGE by dv={dv:.4f}, danim={abs(preds[110].anim-preds[77].anim):.4f}\n")

    results = {}
    for i, (name, hr) in enumerate(variants):
        s = preds[hr]
        print(f"=== LIVE: {name} ===")
        end = run_dtm(sticks_from_actions(seq(hr)),
                      expected={'v': s.v, 'anim': s.anim, 'air': s.air, 'state': s.state},
                      relaunch_dolphin=True, read='step', tol=0.05)
        results[hr] = end

    print("\n=== VERDICT ===")
    lv110, lv77 = results[110]['potential_speed'], results[77]['potential_speed']
    la110, la77 = results[110]['anim_frame'], results[77]['anim_frame']
    print(f"  live 110: v={lv110:.4f} anim={la110:.4f}   live 77: v={lv77:.4f} anim={la77:.4f}")
    print(f"  live divergence: dv={abs(lv110-lv77):.4f}  danim={A.animdiff(la110,la77,23.0):.4f}")
    print(f"  sim  divergence: dv={dv:.4f}  danim={abs(preds[110].anim-preds[77].anim):.4f}")
    ok110 = results[110].get('compare', {}).get('ok')
    ok77 = results[77].get('compare', {}).get('ok')
    print(f"  sim-vs-live match: 110={'PASS' if ok110 else 'FAIL'}  77={'PASS' if ok77 else 'FAIL'}")


if __name__ == '__main__':
    main()
