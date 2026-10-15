"""Derive the Tetra-corner seam geometry fixture (rollstab convention) from the LIVE golden.

Offline + reproducible (no Dolphin): reads the live-confirmed RAM capture
`tests/golden/hyrule_seam_1727_ram.json` (the flooded-Hyrule (-1727,-990) Tetra corner, savestate
slot 3) and writes `fixtures/hyrule_tetra_geo.json` in the SAME schema as `kaze_r11_geo.json`, so the
Tetra acceptance module (`geometry_tetra.py`) loads it exactly like the kaze module loads its corner.

The golden's tris follow the tetra_clip convention (`tris[1]`=wall-A seam tri, `tris[2]`=wall-B seam
tri); planes are stored bit-exact (decoded from the RAM hex, which round-trips through JSON). The
seam vertex S (idx 2576) is shared by both incident walls; `link_y` is its floor Y (= the Phase-G
flat floor 0.16327). Also records the AUTHORITATIVE clip target (settled `old`, f32 `new`) so the
acceptance module can assert the live-anchored facts.

    python -m harness.rollstab.make_tetra_geo        # regenerate fixtures/hyrule_tetra_geo.json
"""
import os, sys, json, math, struct
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

GOLDEN = os.path.join(_rb, 'tests', 'golden', 'hyrule_seam_1727_ram.json')
OUT = os.path.join(_rb, 'fixtures', 'hyrule_tetra_geo.json')


def _fh(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def _tri(t):
    return dict(poly=t["poly"], v=[[_fh(x) for x in vv] for vv in t["v"]],
                n=[_fh(x) for x in t["n"]], d=_fh(t["D"]))


def build():
    g = json.load(open(GOLDEN))
    tris = [_tri(t) for t in g["tris"]]
    S = [_fh(x) for x in g["seam_v_hex"]]              # seam vertex (2576), Y = floor
    link_y = S[1]
    old = [_fh(x) for x in g["old_hex"]]               # settled front-of-corner WallCorrect fixed pt
    new = [_fh(x) for x in g["new_hex"]]               # f32 clip endpoint just past the seam
    wallA, wallB = tris[1], tris[2]                    # tetra_clip convention
    # interior corner angle + bisector, from the two incident wall NORMALS (XZ only).
    nA = (wallA["n"][0], wallA["n"][2])
    nB = (wallB["n"][0], wallB["n"][2])
    dot = max(-1.0, min(1.0, (nA[0]*nB[0] + nA[1]*nB[1])
                         / (math.hypot(*nA) * math.hypot(*nB))))
    interior = 180.0 - math.degrees(math.acos(dot))    # convex-corner interior angle
    # front-of-corner bisector: -(nA+nB) normalised (into the walkable side), as a world s16 heading.
    bx, bz = -(nA[0] + nB[0]), -(nA[1] + nB[1])
    bis_deg = (math.degrees(math.atan2(bx, bz))) % 360.0
    out = dict(
        stage=g.get("stage", "Hyrule"), bg=0, seam=g.get("seam"),
        source="tests/golden/hyrule_seam_1727_ram.json (live-confirmed RAM capture, slot 3)",
        S=S, interior=round(interior, 3), bisector_deg=bis_deg, link_y=link_y,
        wallA=wallA, wallB=wallB, barrier=tris,          # full CrrPos barrier = all 4 golden tris
        # AUTHORITATIVE live-anchored clip target (a needs-push clip):
        target=dict(old=old, new=new,
                    note=g.get("note", "")))
    json.dump(out, open(OUT, 'w'), indent=1)
    print("wrote", OUT)
    print("  S=%s link_y=%.6f interior=%.3f bisector=%.2fdeg" % (S, link_y, interior, bis_deg))
    print("  wallA poly %d n=%s" % (wallA["poly"], wallA["n"]))
    print("  wallB poly %d n=%s" % (wallB["poly"], wallB["n"]))
    print("  target old=%s new=%s" % (old, new))
    return out


if __name__ == '__main__':
    build()
