"""Is a NON-vertical seam clippable? Tilt the GanonL seam about a horizontal axis (walls lean,
ny != 0, seam stays a shared edge) and search for clip solutions per tilt angle.

Result (see knowledge/mechanics/seam-clip.md): a vertical seam yields many clips; ANY tilt >=0.01deg
(ny >= 0.0002, well below the 0.008 Y-projection threshold) drops it to ZERO. With a SINGLE cylinder
height a tilted seam still clips -> the per-triangle-plane gap itself is not tilt-dependent; it is
LineCheck's THREE fixed cylinder heights (a tilted seam's gap sits at a different XZ at each height,
spread far wider than the ~0.01u gap) that forces verticality.

Uses recomputed (calc_pla) planes at all angles (no stored planes for a theoretical wall), so this
answers existence / relative clippability, not exact console boundaries.

    python -m harness.collision.tilt_experiment
"""
import math

from tww_sim.core.collision import Tri, crr_pos_walls

SEAM_BOT = (-847.6320190429688, 5834.38037109375, -37336.61328125)
WALLS = [
    ((-513.3269653320312, 5834.38037109375, -37420.58203125),
     (-513.326904296875,  7334.38134765625, -37420.58203125),
     (-847.6318969726562, 7334.38134765625, -37336.61328125)),
    ((-513.3269653320312, 5834.38037109375, -37420.58203125),
     (-847.6318969726562, 7334.38134765625, -37336.61328125),
     (-847.6320190429688, 5834.38037109375, -37336.61328125)),
    ((-847.6320190429688, 5834.38037109375, -37336.61328125),
     (-847.6318969726562, 7334.38134765625, -37336.61328125),
     (-1085.3291015625,   7334.38134765625, -36967.18359375)),
    ((-847.6320190429688, 5834.38037109375, -37336.61328125),
     (-1085.3291015625,   7334.38134765625, -36967.18359375),
     (-1085.3291015625,   5834.38037109375, -36967.18359375)),
]
LINK_Y = 5852.66
SEAM_XZ = (-847.632, -37336.613)


def _rot_x(v, th, c):
    x, y, z = v; _, cy, cz = c
    dy, dz = y - cy, z - cz
    return (x, cy + dy*math.cos(th) - dz*math.sin(th), cz + dy*math.sin(th) + dz*math.cos(th))


def build(theta_deg):
    th = math.radians(theta_deg)
    return [Tri(_rot_x(A, th, SEAM_BOT), _rot_x(B, th, SEAM_BOT), _rot_x(C, th, SEAM_BOT))
            for A, B, C in WALLS]


def search(tris, wall_h=(30.1, 89.9, 125.0)):
    """Sweep initials in front of the wall + aim/dist through the seam; count clip solutions."""
    clips = total = 0
    for ix in (-818.5, -817.6, -816.7, -815.8, -814.9):
        for iz in (-37308.5, -37307.2, -37306.0):
            base = math.atan2(SEAM_XZ[0]-ix, SEAM_XZ[1]-iz)
            for da in (d*0.1 for d in range(-25, 26)):
                ang = base + math.radians(da)
                sdx, sdz = math.sin(ang), math.cos(ang)
                for k in range(29):
                    D = 42 + 0.5*k
                    end = (ix + D*sdx, iz + D*sdz)
                    total += 1
                    pos, _ = crr_pos_walls((ix, LINK_Y, iz), (end[0], LINK_Y, end[1]), tris, wall_h=wall_h)
                    if ((pos[0]-end[0])**2 + (pos[2]-end[1])**2) ** 0.5 < 1.0:
                        clips += 1
    return clips, total


if __name__ == "__main__":
    print("tilt sweep (all three cylinder heights):")
    for theta in (0.0, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0, -0.5, -1.0):
        tris = build(theta)
        c, t = search(tris)
        print(f"  theta={theta:+5.2f}  ny={[round(x.pla.ny,5) for x in tris]}  clips={c}/{t}")
    print("mechanism check at theta=0.5 (single vs three heights):")
    tris = build(0.5)
    for wh in ((125.0,), (30.1, 89.9, 125.0)):
        c, t = search(tris, wall_h=wh)
        print(f"  wall_h={wh}  clips={c}/{t}")
