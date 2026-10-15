"""extract_zl1.py - extract Tetra's (daNpc_Zl1_c / Zl.arc) skeleton + look-relevant BCKs for the
Tetra eyePos model (tww_sim/core/npc_zl1_look.py). Mirrors parse_bmd/parse_bck's Link extraction:
the output (copyrighted game anim data) goes to the gitignored _generated/anim/, regenerated
locally from the user's own disc dump, never committed.

  python -m harness.anim.extract_zl1            # writes zl1_skeleton.json + zl1_anims.json

Pulls Zl.arc from the TWW-JP iso (the real-TAS disc; falls back to the default sandbox key if
absent). Anims extracted = the stt-3 courtyard set: wait03 (the being-pushed idle, anm_prm 8),
look (the random look-around, anm_prm 0xc), wait (anm_prm 0, the stt-1 idle -- cheap to carry).
"""
import os, sys, json
from io import BytesIO

# >>> repo bootstrap
HERE = os.path.dirname(os.path.abspath(__file__))
_rb = HERE
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from harness import dolphin_env
from harness.anim.parse_bmd import load_from_arc
from harness.anim.parse_bck import parse_bck, to_jsonable

ANIMS = ('wait03', 'look', 'wait')


def zl_arc_bytes():
    try:
        return dolphin_env.object_arc_bytes('Zl', iso_key='TWW-JP')
    except SystemExit:
        return dolphin_env.object_arc_bytes('Zl')


def main():
    from wwlib.rarc import RARC
    from wwlib.yaz0 import Yaz0
    raw = zl_arc_bytes()
    if raw[:4] == b'Yaz0':
        raw = Yaz0.decompress(BytesIO(raw)).getvalue()

    sk = load_from_arc(raw, 'zl.bdl')
    print("zl.bdl: %d joints, mtxCalc=%s" % (sk['num_joints'], sk['mtx_calc']))

    r = RARC(); r.read(BytesIO(raw))
    anms = {}
    for name in ANIMS:
        fe = next(x for x in r.file_entries if x.name == name + '.bck')
        d = fe.data.getvalue() if hasattr(fe.data, 'getvalue') else fe.data
        a = parse_bck(d)
        anms[name] = to_jsonable(a)
        print("  %s.bck: loop=%d frame_max=%d dec_shift=%d" % (
            name, a['attribute'], a['frame_max'], a['dec_shift']))

    outdir = os.path.join(_rb, '_generated', 'anim')
    os.makedirs(outdir, exist_ok=True)
    p1 = os.path.join(outdir, 'zl1_skeleton.json')
    p2 = os.path.join(outdir, 'zl1_anims.json')
    json.dump(sk, open(p1, 'w'))
    json.dump(anms, open(p2, 'w'))
    print("wrote", p1)
    print("wrote", p2)


if __name__ == '__main__':
    main()
