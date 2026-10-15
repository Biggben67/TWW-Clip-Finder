"""parse_bmd.py - parse a TWW/J3D BMD/BDL model's skeleton: the INF1 (joint hierarchy +
matrix-calc mode) and JNT1 (per-joint bind TRS + bounding data + name table) chunks. This is
the static skeleton the anim eval poses; see parse_bck.py for the animation tracks.

Spec = the decomp loader:
  J3DModelLoader.cpp readInformation (L250) -> mtx-calc mode = (INF1 mFlags & 0xF): 0=Basic,
    1=Softimage, 2=Maya (J3DModelInfoBlock.mFlags @ chunk+0x08; hierarchy ptr @ chunk+0x14).
  J3DModelLoader.cpp readJoint (L369) + J3DJointFactory::create -> JNT1 = J3DJointBlock:
    0x08 u16 mJointNum, 0x0C u32 ->J3DJointInitData[], 0x10 u32 ->u16 mIndexTable[],
    0x14 u32 ->ResNTAB name table (all offsets from chunk start).
  J3DJointInitData (J3DJointFactory.h) — the header's 0x30 size/mMin@0x28/mMax@0x2C comment is
    MISANNOTATED; the on-disk stride is the standard BMD 0x40:
    0x00 u16 mKind; 0x02 u8 mScaleCompensate; 0x04 J3DTransformInfo (0x20):
      scale Vec@0x04, rotation SVec(3 s16)@0x10 (pad@0x16), translate Vec@0x18;
    0x24 f32 mRadius; 0x28 Vec mMin; 0x34 Vec mMax.  (J3DTransformInfo.h: Size 0x20.)
  Joint rotation is stored in s16 BAM (bind pose is exact-frame data, no decShift here — the
  BCK decShift applies only to animation rotation tracks).

INF1 hierarchy node = {u16 type, u16 index}: 0 finish, 1 open-child, 2 close-child,
  0x10 joint, 0x11 material, 0x12 shape. A joint node's `index` is its JNT1 index; the enclosing
  joint node (via open/close-child nesting) is its FK parent. BMD joint order == the getAnmMtx index.

DEV extraction tool; output (Link's copyrighted skeleton) is written to gitignored _generated/,
regenerated locally, never committed (same policy as savestates / parse_bck.py output).
"""
import os, sys, struct, json

# >>> repo bootstrap: locate the wwrando wwlib (RARC/Yaz0) + repo root
HERE = os.path.dirname(os.path.abspath(__file__))
_rb = HERE
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
WWRANDO = os.path.join(os.path.dirname(_rb), 'ww_model_helpers', 'wwrando')  # sibling repo
if WWRANDO not in sys.path:
    sys.path.insert(0, WWRANDO)
from io import BytesIO
try:
    from wwlib.rarc import RARC
    from wwlib.yaz0 import Yaz0
except ImportError:
    RARC = None
    Yaz0 = None
    from harness.collision.dzb_iso import read_rarc_bytes, yaz0_decompress, gcm_read_file


def _gcm_read_object_arc(iso, name):
    path = 'files/res/Object/%s.arc' % name
    try:
        return gcm_read_file(iso, path)
    except FileNotFoundError:
        return gcm_read_file(iso, path[6:])


def _u8(d, o):  return d[o]
def _s16(d, o): return struct.unpack_from('>h', d, o)[0]
def _u16(d, o): return struct.unpack_from('>H', d, o)[0]
def _u32(d, o): return struct.unpack_from('>I', d, o)[0]
def _f32(d, o): return struct.unpack_from('>f', d, o)[0]
def _vec(d, o): return [_f32(d, o), _f32(d, o + 4), _f32(d, o + 8)]
def _svec(d, o): return [_s16(d, o), _s16(d, o + 2), _s16(d, o + 4)]

MTX_CALC = {0: 'Basic', 1: 'Softimage', 2: 'Maya'}
NODE_FINISH, NODE_OPEN, NODE_CLOSE, NODE_JOINT = 0x00, 0x01, 0x02, 0x10


def _read_name_table(d, base):
    """ResNTAB / J3D string table at absolute offset `base`. Returns list[str]."""
    n = _u16(d, base + 0x00)
    names = []
    for i in range(n):
        e = base + 4 + i * 4
        str_off = _u16(d, e + 0x02)
        s = base + str_off
        end = d.index(b'\x00', s)
        names.append(d[s:end].decode('shift_jis', 'replace'))
    return names


def _find_chunks(d):
    """Map chunk magic -> absolute offset. Header: magic@0, filetype@4, len@8, numChunks@0xC."""
    assert d[:4] == b'J3D2', d[:4]
    num = _u32(d, 0x0C)
    chunks, off = {}, 0x20
    for _ in range(num):
        if off >= len(d):
            break
        magic = d[off:off + 4].decode('ascii', 'replace')
        size = _u32(d, off + 4)
        chunks.setdefault(magic, off)
        off += size
    return chunks


def _parse_inf1(d, base):
    """Return (mtx_calc_name, parent[]) where parent[jntIdx] = FK parent jntIdx (-1 for root)."""
    flags = _u16(d, base + 0x08)
    mtx_calc = MTX_CALC.get(flags & 0xF, 'Basic')
    hier = base + _u32(d, base + 0x14)
    parent = {}
    stack = [-1]          # current parent joint index; -1 = root
    prev_joint = -1
    o = hier
    while True:
        typ = _u16(d, o); idx = _u16(d, o + 2); o += 4
        if typ == NODE_FINISH:
            break
        elif typ == NODE_JOINT:
            parent[idx] = stack[-1]
            prev_joint = idx
        elif typ == NODE_OPEN:
            stack.append(prev_joint)
        elif typ == NODE_CLOSE:
            stack.pop()
        # material/shape nodes ignored
    n = max(parent) + 1 if parent else 0
    return mtx_calc, [parent.get(i, -1) for i in range(n)]


def _parse_jnt1(d, base):
    """Return list of joint dicts (in JNT1 index order) with bind TRS + bounds + name."""
    njoints = _u16(d, base + 0x08)
    init_off = base + _u32(d, base + 0x0C)
    index_off = base + _u32(d, base + 0x10)
    name_off_raw = _u32(d, base + 0x14)
    names = _read_name_table(d, base + name_off_raw) if name_off_raw else [''] * njoints
    STRIDE = 0x40
    joints = []
    for i in range(njoints):
        ii = _u16(d, index_off + i * 2)          # index into J3DJointInitData[]
        b = init_off + ii * STRIDE
        joints.append(dict(
            index=i, init_index=ii,
            name=names[i] if i < len(names) else '',
            kind=_u16(d, b + 0x00),
            scale_compensate=_u8(d, b + 0x02),
            scale=_vec(d, b + 0x04),
            rotation=_svec(d, b + 0x10),          # s16 BAM
            translate=_vec(d, b + 0x18),
            radius=_f32(d, b + 0x24),
            bb_min=_vec(d, b + 0x28),
            bb_max=_vec(d, b + 0x34),
        ))
    return joints


def parse_bmd(bmd_bytes):
    d = bmd_bytes
    if d[:4] == b'Yaz0':
        d = Yaz0.decompress(BytesIO(d)).getvalue() if Yaz0 else yaz0_decompress(d)
    chunks = _find_chunks(d)
    assert 'INF1' in chunks and 'JNT1' in chunks, chunks.keys()
    mtx_calc, parent = _parse_inf1(d, chunks['INF1'])
    joints = _parse_jnt1(d, chunks['JNT1'])
    for j in joints:
        j['parent'] = parent[j['index']] if j['index'] < len(parent) else -1
    return dict(mtx_calc=mtx_calc, num_joints=len(joints), joints=joints)


def load_from_arc(arc_bytes_or_path, model_name='cl.bdl'):
    """Parse a model from an .arc, given raw arc bytes or a path. Link.arc is Yaz0-compressed on
    disc; decompress transparently."""
    if isinstance(arc_bytes_or_path, (bytes, bytearray)):
        raw_arc = bytes(arc_bytes_or_path)
    else:
        raw_arc = open(arc_bytes_or_path, 'rb').read()
    if raw_arc[:4] == b'Yaz0':
        raw_arc = Yaz0.decompress(BytesIO(raw_arc)).getvalue() if Yaz0 else yaz0_decompress(raw_arc)
    if RARC is None:
        files = read_rarc_bytes(raw_arc, 'Link.arc')
        return parse_bmd(files[model_name])
    r = RARC(); r.read(BytesIO(raw_arc))
    fe = next(x for x in r.file_entries if x.name == model_name)
    raw = fe.data.getvalue() if hasattr(fe.data, 'getvalue') else fe.data
    return parse_bmd(raw)


def extract_skeleton(src, *, outdir=None, model='cl.bdl'):
    """Extract Link's skeleton from an ISO path or Link.arc."""
    if isinstance(src, (str, os.PathLike)) and str(src).lower().endswith('.iso'):
        src = _gcm_read_object_arc(str(src), 'Link')
    m = load_from_arc(src, model)
    if outdir is None:
        outdir = os.path.join(_rb, '_generated', 'anim')
    os.makedirs(outdir, exist_ok=True)
    outp = os.path.join(outdir, 'link_skeleton.json')
    with open(outp, 'w') as stream:
        json.dump(m, stream)
    return outp


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    model = o.get('model', 'cl.bdl')
    if 'arc' in o:
        src = o['arc']                                      # explicit path override
    elif 'iso' in o:
        src = _gcm_read_object_arc(o['iso'], 'Link')
    else:
        from harness import dolphin_env                     # resolve from extract dir or ISO
        src = dolphin_env.object_arc_bytes('Link')
    m = load_from_arc(src, model)
    print("%s: %d joints, mtxCalc=%s" % (model, m['num_joints'], m['mtx_calc']))
    for j in m['joints']:
        print("  [%2d] parent=%-3d %-12s S=%s R=%s T=%s" % (
            j['index'], j['parent'], j['name'],
            ['%.3f' % v for v in j['scale']], j['rotation'],
            ['%.3f' % v for v in j['translate']]))
    outp = extract_skeleton(src, model=model)
    print("wrote", outp)


if __name__ == '__main__':
    main()
