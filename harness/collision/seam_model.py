"""GanonL grand-staircase seam-clip model (offline, bit-exact vs console).

Wraps :mod:`tww_sim.core.collision` with the specific seam geometry from Ganon's Tower grand
staircase (GZLJ01, savestate that spawns Link at ~(-816.7, 5852.7, -37297.4)). The seam is the
vertical edge at x=-847.632, z=-37336.613 where two wall quads meet:

  * wall **A** (face normal heading ~+14 deg, ~+Z) split into an upper + lower triangle,
  * wall **B** (heading ~+57 deg) split into two triangles.

The dihedral is ~137 deg (a convex corner from Link's side). Each triangle stores its own
independently-normalised plane, so A-upper and A-lower differ in the last bits (0.24360720813 vs
0.24360716343) and the two B triangles differ too. That per-triangle plane difference is the root
cause: when Link's swept centre-line (LineCheck) passes near the seam, it is intersected with each
triangle's OWN plane, so the crossings land at slightly different points that each fall just OUTSIDE
their triangle -> all miss -> no wall detected -> Link passes through (a "clip"), provided the
one-frame displacement (>~36 u) also carries him past WallCorrect's static radius-35 cylinder.

The 4 wall triangles + their STORED plane normals/D below were captured live via a breakpoint on
``cM3d_Cross_LinTri`` (see ``ganonl_seam_capture.json``). Feeding these stored planes,
:func:`predict_clip` reproduces the game's per-triangle crossing points to f32 and every hit/miss
(24/24 live cases; 14024/14049 of the brute-force clip set offline, the residual being old_pos
approximation + dump noise, not model error). See ``knowledge/mechanics/seam-clip.md``.
"""
from tww_sim.core.collision import Tri, Plane, line_check, wall_correct, len2dsq
from tww_sim.core.fp import f32 as _f, fmuls

# The four wall triangles at the seam: verts (world xyz) + STORED plane (n, D) read from RAM
# (cBgW.pm_tri, stride 0x18). A = the ~+14deg wall (upper/lower), B = the ~+57deg wall (two tris).
_WALLS = [
    dict(name="A_upper",
         A=(-513.3269653320312, 5834.38037109375, -37420.58203125),
         B=(-513.326904296875,  7334.38134765625, -37420.58203125),
         C=(-847.6318969726562, 7334.38134765625, -37336.61328125),
         n=(0.24360720813274384, -9.912397125333428e-09, 0.9698740243911743), D=36418.30078125),
    dict(name="A_lower",
         A=(-513.3269653320312, 5834.38037109375, -37420.58203125),
         B=(-847.6318969726562, 7334.38134765625, -37336.61328125),
         C=(-847.6320190429688, 5834.38037109375, -37336.61328125),
         n=(0.24360716342926025, -2.0319117055578317e-08, 0.9698739647865295), D=36418.30078125),
    dict(name="B_1",
         A=(-847.6320190429688, 5834.38037109375, -37336.61328125),
         B=(-847.6318969726562, 7334.38134765625, -37336.61328125),
         C=(-1085.3291015625,   7334.38134765625, -36967.18359375),
         n=(0.8409644365310669, -6.843781363841117e-08, 0.5410904884338379), D=20915.314453125),
    dict(name="B_2",
         A=(-847.6320190429688, 5834.38037109375, -37336.61328125),
         B=(-1085.3291015625,   7334.38134765625, -36967.18359375),
         C=(-1085.3291015625,   5834.38037109375, -36967.18359375),
         n=(0.8409645557403564, -6.983156275452984e-10, 0.5410903096199036), D=20915.30859375),
]

SEAM_TRIS = [Tri(w["A"], w["B"], w["C"], plane=Plane(*w["n"], w["D"])) for w in _WALLS]
WALL_H = (30.1, 89.9, 125.0)   # player wall-cylinder heights (setBgCheckParam)
WALL_R = 35.0                  # player wall-cylinder radius (standing/walking)
LINK_Y = 5852.66               # Link floor height at this seam (savestate 1)


def settle_initial(initial, y=LINK_Y, frames=4):
    """Reproduce the standing 'settle' the game applies before a swept clip frame: WallCorrect
    nudges an initial that overlaps the wall cylinder off the wall front. Matches live to <1e-4 u.
    Feed the settled pos as old_pos, since that is what the game carries as pm_old_pos."""
    pos = (_f(initial[0]), _f(y), _f(initial[1]))
    for _ in range(frames):
        pos, _ = wall_correct(pos, 0.0, SEAM_TRIS, WALL_H, WALL_R)
    return (pos[0], pos[2])


def predict_clip(initial, end, y=LINK_Y, settle=False):
    """Model one swept frame from `initial` (x,z) to `end` (x,z). Returns (clipped, info).
    Clipped == collision leaves Link at `end` (drift < 1 u). Pass settle=True to first settle a raw
    brute-force initial into the old_pos the game would actually carry."""
    if settle:
        initial = settle_initial(initial, y)
    old = (_f(initial[0]), _f(y), _f(initial[1]))
    new = (_f(end[0]), _f(y), _f(end[1]))
    dxz2 = len2dsq(old[0], old[2], new[0], new[2])
    ran_line = dxz2 > fmuls(WALL_R, WALL_R)
    pos = new
    line_hit = False
    if ran_line:
        line_hit, pos = line_check(old, pos, SEAM_TRIS, WALL_H)
    pos, wall_hit = wall_correct(pos, 0.0, SEAM_TRIS, WALL_H, WALL_R)
    if wall_hit and ran_line:
        lh2, pos = line_check(old, pos, SEAM_TRIS, WALL_H)
        line_hit = line_hit or lh2
    drift = ((pos[0] - new[0]) ** 2 + (pos[2] - new[2]) ** 2) ** 0.5
    return drift < 1.0, dict(pos=pos, line_hit=line_hit, wall_hit=wall_hit,
                             ran_line=ran_line, drift=drift)


if __name__ == "__main__":
    c, info = predict_clip((-817.6296387, -37307.21875), (-855.1299438, -37343.96094))
    print("row1 clip?", c, info)
