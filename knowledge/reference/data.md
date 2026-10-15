# Raw measurement data (live Dolphin, 2026-06-26)

**Answers:** What are the raw per-frame measurement tables behind the swim conclusions (ESS pump entry
tax, decay, displacement)? What was the capture setup?
**Status:** reference (live Dolphin, 2026-06-26).
**Source:** live Dolphin, flat-water slot-10 slate. Feeds the [swim mechanics](../mechanics/overview.md)
pages.

---

Raw tables behind the conclusions in the [knowledge base](../README.md), so a new session can
re-analyze WITHOUT re-running. All from the flat-water slot-10 slate (24763,1,
-197306). Stick held with substickY=0 (free-cam). ESS = (128,110), neutral =
(128,128). First frame after charge→hold is a −3 facing-flip transient.

## ESS pump — entry tax (per-frame speed decay, ESS held 7 frames out of neutral)
Setup: loadstate10; 4 ESS; 5 neutral; then ESS×7.
```
ess1: state=54 dSpeed=+2.0000   <- still swim-wait; pure-neutral decay (entry tax)
ess2: state=55 dSpeed=+0.1667   <- now move state; ESS -1/6 begins
ess3..7: state=55 dSpeed=+0.1667
```
Pure-neutral baseline & single-pump (both state 54→54): dSpeed=+2.0000, disp=273.99.
ESS-formula pred for that single frame=216.76 → single pump gives NEUTRAL behavior,
not ESS. Confirms 1-frame pump useless.

## ESS pump — anim across pump (K = neutral frames before a 1-frame pump)
Setup: loadstate10; 4 ESS; K neutral; read; 1 ESS; read.
```
K  anim_preNeut anim_b4pump anim_pump  pump_disp
2  8.4861       3.6743      4.5077     279.99
3  8.4861       4.5077      5.3438     277.99
4  8.4861       5.3438      6.1827     275.99
5  8.4861       6.1827      7.0243     273.99
6  8.4861       7.0243      7.8688     271.99
```
(anim advances ~0.83/frame in neutral AND on the single pump frame — neutral rate.)

## Neutral→ESS anim scramble (ess3 = first real state-55 ESS frame)
Setup: loadstate10; 4 ESS; K neutral; then ESS×3 (ess1=s54, ess2=transition, ess3=s55).
```
K  anim_lastNeut ess1(s54)  ess2(transition_raw)  ess3(s55 real)
2  3.67432       4.50766    3195.573              7.08130
3  4.50766       5.34377    3697.228              2.68237
4  5.34377       6.18266    4200.545              22.94434
5  6.18266       7.02432    4705.522              21.86768
6  7.02432       7.86877    5212.162              22.45215
7  7.86877       8.71599    5720.462              1.69824
8  8.71599       9.56599    6230.423              5.60449
9  9.56599       10.41877   6742.045              11.17236
```
transition_raw rises ~503/entry-frame = 0.84·(oldEnd·newEnd) → oldEnd·newEnd≈599.
Verified: ess3 = (transition_raw mod 23) + ESS_increment. CLOSED FORM:
anim_ESS_start = (swimwait_frame · 598 + ESS_increment) mod 23  [598 = 26·23].

## Animation lengths (wrap points)
End_swim (ANM_SWIMING): sustained ESS wraps at modulus **22.9965 ≈ 23**.
End_wait (ANM_SWIMWAIT): sustained neutral anim climbs to 25.34 then wraps at
**25.997 ≈ 26** (f25→f26: 25.3410 → 0.2438). Neutral anim rate rises 0.833→0.92
over 33 frames (swimTimerRate/air-driven).

## ESS exit speed (= release_ess_speed) — 2-increment phase offset
Setup: loadstate10; K ESS; then neutral (exit lands 2nd neutral frame).
spd_lastESS→spd_postExit, each exit dSpeed on the transition frame was the af_drag set:
```
K   anim_exit  spd_lastESS  spd_postExit
5   17.3700    -293.333     (-186 region; ESS decay shown as +0.1667 on n1)
```
Verified model (af_drag at anim_lastESS + 2·increment), measured vs predicted:
```
spd_n1   anim_n1  +2incr  afd_pred  measured  err
293.17   3.25     12.13   185.98    185.78    +0.20
293.00   12.13    21.01   288.70    288.61    +0.09
292.83   21.00    6.88    244.81    245.04    -0.23
292.67   6.87     15.75   239.81    239.59    +0.22
292.50   15.74    1.62    289.65    289.74    -0.09
292.33   1.60     10.48   191.64    192.03    -0.39
```
Tool uses anim_lastESS (no offset) → up to ~40% error when offset lands a mid-cos
frame (e.g. tool 260 vs game 186 in the 5-frame case).

## Stroboscopic + reboost (high-speed slate ~-783, air 597)
Sustained ESS, anim crawl (strobo): d_anim ~-0.23 to -0.29/frame (vs +8.8 low speed).
```
f anim     d_anim   |cos|   speed    incr
1 17.3699  -0.2335  0.7186  -785.67  22.7630
5 16.4006  -0.2476  0.6205  -785.00  22.7489
10 15.1098 -0.2652  0.4733  -784.17  22.7313
18 12.8616 -0.2933  0.1849  -782.83  22.7031
```
Reboost vs pure ESS over 30 frames (net displacement):
```
Pure ESS 30f:                 disp=15676.8  end_speed=-781.2
(8 ESS + 2 up/dn)×3 = 30f:     disp=13672.8  end_speed=-797.0
```
→ reboost WORSE in-band (charge frames ~no displacement). Niche = post-drift only.

## Decay-curve sweep (potential-speed decay vs stick, low-speed slate)
```
stickY  measured|decay|  predicted (|off|-15)/54·3
110     0.16667          0.16667
90      1.27777          1.27778
75      2.11111          2.11111
70      2.38889          2.38889
67      2.55556          2.55556
65      2.66667          2.66667
63      2.72223          2.77778 (-1 unit, PADClamp top-end)
60      2.88889          2.94444 (-1 unit)
59      2.94444          3.00000 (-1 unit)
58/40   3.00000          3.00000 (saturated)
128     2.00000          neutral path
```
Diagonal ESS: (111,111) & (145,111) → 0.15610 (cardinal 0.16667).

## True-displacement validation (cardinal ESS, ratio meas/pred ≈ 1.000)
```
f vel      anim    air  measured  predicted  ratio
1 -233.84  3.54    790  214.12    213.98     1.0007
2 -233.67  10.75   789  143.65    143.52     1.0009
3 -233.51  17.97   788  203.43    203.43     1.0000
4 -233.34  2.18    787  219.71    219.59     1.0005
```

## Arrow-swim: 45° instant-turnaround boundary (max 1-frame heading turn vs tilt β)
```
β    0    35    42    44    46   50   70
turn 180  147.5 138.6 136.5 7.8  7.5  6.6   <- snap dies between 44° and 46°
```
Arrow-charge tradeoff (alternate (Xbias,255)/(Xbias,0), 12 frames):
```
Xbias 128/135: -3.0/fr, ~0 disp (deadzone) | 160: -2.90/fr, 387 | 180: -2.52/fr, 845 | 200: +2.0/fr (LOSS), 2290
```
