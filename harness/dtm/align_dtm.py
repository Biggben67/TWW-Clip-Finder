"""Offline: align a recorded *_rec.dtm's real-input rows to the intended seq, to
confirm the poll cadence (real rows per game frame) and LOCATE the slip the handoff
flagged (recorded ~706 frames vs 705 intended, first shift ~f337). No Dolphin needed.

Real rows = btn 0x403f (the held stick); blank rows = btn 0x4000 (all-zero). The game
polls the pad several times per logic frame; the dominant pattern is 4 real rows/frame
(runs of 8/12/... = consecutive frames sharing one stick). We greedily consume real
rows in groups of 4 and compare each group's stick to intended[f]; on a length that is
not a clean multiple of 4, or a value mismatch, we report it -- that is the slip.

Usage: python align_dtm.py [dtm=cruise_pump300k_rec.dtm] [seq=cruise_pump300k_seq.txt]
"""
import sys, struct
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import actions as A

CAL = {255: 254, 0: 1}            # getMainStickValue calibration seen in the recording
def cal(sy): return CAL.get(sy, sy)


def real_rows(dtm):
    data = open(dtm, 'rb').read()
    rows = data[256:]
    out = []
    for i in range(len(rows) // 8):
        btn, tl, tr, sx, sy, cx, cy = struct.unpack('<H6B', rows[i*8:(i+1)*8])
        if btn == 0x403f:
            out.append((sx, sy))
    return out


def rle(seq):
    runs = []
    for s in seq:
        if runs and runs[-1][0] == s:
            runs[-1][1] += 1
        else:
            runs.append([s, 1])
    return runs


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    dtm = o.get('dtm', 'cruise_pump300k_rec.dtm')
    seqf = o.get('seq', 'cruise_pump300k_seq.txt')

    reals = real_rows(dtm)
    acts = A.expand(open(seqf).read())
    intended = [(s['stickX'], cal(s['stickY'])) for s in A.acts_to_seq(acts)]

    print(f"{dtm}: {len(reals)} real rows   {seqf}: {len(intended)} intended frames")
    print(f"real-row RLE runs: {len(rle(reals))}   intended RLE runs: {len(rle(intended))}")

    # Compare run-by-run on RLE: intended frame-count per run vs recorded real-rows/4
    irle = rle(intended)
    rrle = rle(reals)
    print("\n-- RLE side-by-side (intended frames  |  recorded real rows, rows/4) --")
    print("  leading recorded run:", rrle[0], "(seed neutral)")
    # skip a leading length-1 neutral seed in the recording if intended doesn't start neutral
    roff = 0
    if rrle[0][0] == (128, 128) and irle[0][0] != (128, 128):
        roff = 1
        print("  -> dropping leading seed-neutral run from recorded")
    fi = 0  # intended frame index
    bad = 0
    for ri in range(roff, len(rrle)):
        rstick, rlen = rrle[ri]
        nf = rlen / 4.0
        # how many intended frames does this run cover?
        if fi >= len(irle):
            print(f"  EXTRA recorded run past intended end: {rstick} rows={rlen}")
            bad += 1
            continue
        istick, ilen = irle[fi]
        flag = ""
        if rstick != istick:
            flag = f"  <-- STICK MISMATCH (intended {istick})"
            bad += 1
        if abs(nf - ilen) > 1e-9:
            flag += f"  <-- COUNT MISMATCH (rows {rlen} = {nf} frames, intended {ilen})"
            bad += 1
        if flag or ri < roff + 6 or ri > len(rrle) - 6:
            print(f"  run {ri-roff:3d} f{fi:3d}: rec {rstick} rows={rlen}({nf:g}f)  "
                  f"int {istick} x{ilen}{flag}")
        fi += 1
    print(f"\nintended runs consumed: {fi}/{len(irle)}   mismatches: {bad}")


if __name__ == "__main__":
    main()
