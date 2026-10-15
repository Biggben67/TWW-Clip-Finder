"""search_shove.py - the Phase-T Tetra-placement seam-clip search (the solver that found the clip).

Two stages on the native exact engine (:mod:`fast_shove` / ``tww_sim.core._shovec``, ~100k
coupled sims/sec):

1. **Coarse region sweep** (``coarse``): placement grid x thrust step x placement step. Session-20
   result reproduced: plow-mediated pushes never thread (large chaotic pushes knock ``old`` off the
   pin) -- 13M+ sims, 0 genuine.
2. **Polar micro-search** (``polar``): place Tetra at the LAST pre-cut step so ``old`` stays exactly
   on the wall pin and exactly ONE overlap check feeds the cut, then sweep her f32 placement on the
   pre-cut graze circle (angle x depth). 2026-07-11: 10 genuine coupled clips (3 thrust timings),
   all bit-confirmed vs the Python engine, one LIVE-reproduced
   (``fixtures/hyrule_tetra_clip_live.json``, 0-ULP on the placement + clip frames). **VALIDATION
   ONLY** (Dereck, session 21b): the mid-run placement is a hack -- it proves the engine, the graze
   push, and the acceptance end-to-end, but the ACCEPTED mechanism is the PUSH-ASIDE (Tetra standing
   from the start, plowed aside by the roll; ``placed_step=0`` + the ``link_x0/z0`` roll-timing knob).
   The coarse empty result covered ONE approach line/entry/angle only -- see dead-end #19's scope.

Usage (offline, no Dolphin):
    python -m harness.rollstab.search_shove polar          # the graze micro-search (validation)
    python -m harness.rollstab.search_shove coarse         # the region sweep (slow-ish, ~3 min)

Hits print with FULL float precision (a rounded placement is a different f32 -> a different push ->
no clip) and are re-confirmed through ``fast_shove.py_reference`` before being reported.
"""
import json
import math
import os
import sys
import time

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.fp import f32, fadds, fmuls
from harness.rollstab import fast_shove as FS
from harness.rollstab.cc_stepper import LINK_CO_R, TETRA_CO_R

SUM_R = LINK_CO_R + TETRA_CO_R
THRUSTS = (13, 14, 15)          # B-edge steps that dispatch a CUT out of this roll schedule
OUT = os.path.join(_rb, '_generated', 'shove_hits.json')


def precut_centre(ctx, sch):
    """Link's Co-centre on the last pre-cut step (pin pos + that step's FK chain consts)."""
    ps = sch['cut_step'] - 1
    _, tr = ctx.run_trace(-3000.0, -3000.0, 9999)      # bare: Tetra never placed
    lx, lz = tr[ps][0], tr[ps][1]

    def chain(vals, p):
        t = f32(p)
        for c in vals:
            t = fadds(c, t)
        return t
    nroot = sch['nroot']
    cx = fmuls(0.5, fadds(chain(sch['chx'][ps][:nroot], lx), chain(sch['chx'][ps][nroot:], lx)))
    cz = fmuls(0.5, fadds(chain(sch['chz'][ps][:nroot], lz), chain(sch['chz'][ps][nroot:], lz)))
    return ps, (lx, lz), (cx, cz)


def polar(thrusts=THRUSTS, a0=190.0, a1=285.0, astep=0.05, d0=0.7, d1=2.6, dstep=0.002,
          confirm=True, verbose=True):
    """The winning micro-search: last-pre-cut-step placement on the graze circle. Returns hits."""
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    all_hits = []
    for ts in thrusts:
        inputs = FS.make_inputs(ts)
        ctx, sch = FS.build_ctx(fix, walls, inputs)
        ps, pin, (cx, cz) = precut_centre(ctx, sch)
        t0 = time.time()
        hits = []
        total = 0
        a = a0
        while a < a1:
            pls, metas = [], []
            for ai in range(40):
                ang = a + ai * astep
                if ang >= a1:
                    break
                r_ = math.radians(ang)
                ux, uz = math.sin(r_), math.cos(r_)
                d = d0
                while d <= d1:
                    cd = SUM_R - d
                    pls.append((cx - cd * ux, cz - cd * uz))
                    metas.append((ang, d))
                    d += dstep
            if not pls:
                break
            rs = ctx.sweep_par(pls, ps)
            total += len(pls)
            for (m, p, r) in zip(metas, pls, rs):
                if r[0]:
                    hits.append(dict(thrust=ts, placed=ps, ang=m[0], depth=m[1], p=p,
                                     old=(r[1], r[2]), new=(r[3], r[4]), push=(r[5], r[6])))
            a += astep * 40
        if verbose:
            print("thrust %d (cut_step %d, placed %d): %d sims in %.0fs -> %d genuine"
                  % (ts, sch['cut_step'], ps, total, time.time() - t0, len(hits)), flush=True)
        if confirm:
            for h in hits:
                ref, _ = FS.py_reference(fix, walls, inputs, tuple(h['p']), h['placed'])
                h['confirmed'] = bool(ref['genuine'] and ref['old'] == h['old']
                                      and ref['new'] == h['new'] and ref['push'] == h['push'])
        for h in hits:
            if verbose:
                print("  *** GENUINE p=(%r, %r) old=%r new=%r push=%r confirmed=%s"
                      % (h['p'][0], h['p'][1], h['old'], h['new'], h['push'],
                         h.get('confirmed')), flush=True)
        all_hits.extend(hits)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(all_hits, open(OUT, 'w'), indent=1)
    if verbose:
        print("TOTAL genuine: %d -> %s" % (len(all_hits), OUT), flush=True)
    return all_hits


def coarse(thrusts=THRUSTS, x0=-1725.0, x1=-1600.0, z0=-1000.0, z1=-860.0, step=0.25,
           verbose=True):
    """The region x timing sweep (finds no plow-mediated clips; kept as the coverage record)."""
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    grid = []
    x = x0
    while x <= x1:
        z = z0
        while z <= z1:
            grid.append((x, z))
            z += step
        x += step
    hits = []
    for ts in thrusts:
        inputs = FS.make_inputs(ts)
        ctx, sch = FS.build_ctx(fix, walls, inputs)
        for ps in range(0, sch['cut_step']):
            t0 = time.time()
            rs = ctx.sweep_par(grid, ps)
            n_gen = sum(1 for r in rs if r[0])
            hits.extend([dict(thrust=ts, placed=ps, p=p, r=r) for (p, r) in zip(grid, rs) if r[0]])
            if verbose:
                print("thrust %2d placed %2d: %d sims, genuine=%d [%.1fs]"
                      % (ts, ps, len(grid), n_gen, time.time() - t0), flush=True)
    return hits


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'polar'
    if mode == 'polar':
        polar()
    elif mode == 'coarse':
        coarse()
    else:
        print(__doc__)
