"""parse_bck.py - parse a TWW/J3D BCK (bone animation, ANK1 chunk) into per-joint
scale/rotation/translation keyframe tracks. Spec = the decomp JSystem loader/eval:
  J3DAnmLoader.cpp setAnmTransform (chunk field layout) + J3DAnimation.cpp calcTransform
  (how mAnmTable[idx*3+axis].{mScale,mRotation,mTranslate} + the S/R/T data arrays are read).

ANK1 chunk layout (offsets from chunk start; all big-endian):
  0x00 "ANK1"; 0x04 u32 size
  0x08 u8 loop_mode(mAttribute); 0x09 u8 mDecShift; 0x0A s16 mFrameMax (duration)
  0x0C u16 num_joints; 0x0E u16 scale_count; 0x10 u16 rot_count; 0x12 u16 trans_count
  0x14 u32 table_offset  -> J3DAnmTransformKeyTable[num_joints*3]  (0x12 bytes each)
  0x18 u32 scale_offset  -> f32[scale_count]
  0x1C u32 rot_offset    -> s16[rot_count]
  0x20 u32 trans_offset  -> f32[trans_count]
J3DAnmTransformKeyTable (one AXIS of one joint, 0x12 bytes) = 3x J3DAnmKeyTableBase:
  mScale, mRotation, mTranslate; each = {u16 mMaxFrame(count), u16 mOffset, u16 mType(tangent)}
mAnmTable is indexed [joint*3 + axis]; for joint j the x/y/z tracks are entries j*3+0/1/2, and
within entry j*3+axis you read .mScale/.mRotation/.mTranslate for THAT axis (see calcTransform).

This is a DEV extraction tool; its output (Link's copyrighted anim data) is written to the
gitignored _generated/ dir, regenerated locally, never committed (like the savestates).
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


class KeyTable:
    """One S/R/T track: count keyframes at data[offset:], tangent type (0=one, 1=in/out)."""
    __slots__ = ('count', 'offset', 'ttype')
    def __init__(self, count, offset, ttype):
        self.count, self.offset, self.ttype = count, offset, ttype
    def as_list(self): return [self.count, self.offset, self.ttype]


def _read_keytable(d, o):
    return KeyTable(_u16(d, o), _u16(d, o + 2), _u16(d, o + 4))


def parse_bck(bck_bytes):
    """Parse BCK bytes -> dict with per-joint x/y/z S/R/T tracks + the raw data arrays."""
    d = bck_bytes
    if d[:4] == b'Yaz0':
        d = Yaz0.decompress(BytesIO(d)).getvalue() if Yaz0 else yaz0_decompress(d)
    assert d[:4] == b'J3D1', d[:4]
    assert d[4:8] == b'bck1', d[4:8]
    # find ANK1 chunk (right after the 0x20 header for these files)
    off = 0x20
    assert d[off:off+4] == b'ANK1', d[off:off+4]
    base = off
    attribute  = _u8(d, base + 0x08)          # mAttribute (loop mode) -> J3DFrameCtrl
    dec_shift  = _u8(d, base + 0x09)
    frame_max  = _s16(d, base + 0x0A)
    num_joints = _u16(d, base + 0x0C)
    scale_cnt  = _u16(d, base + 0x0E)
    rot_cnt    = _u16(d, base + 0x10)
    trans_cnt  = _u16(d, base + 0x12)
    table_off  = base + _u32(d, base + 0x14)
    scale_off  = base + _u32(d, base + 0x18)
    rot_off    = base + _u32(d, base + 0x1C)
    trans_off  = base + _u32(d, base + 0x20)

    scale_data = list(struct.unpack_from('>%df' % scale_cnt, d, scale_off))
    rot_data   = list(struct.unpack_from('>%dh' % rot_cnt,   d, rot_off))
    trans_data = list(struct.unpack_from('>%df' % trans_cnt, d, trans_off))

    # mAnmTable[num_joints*3], each 0x12 bytes = {mScale, mRotation, mTranslate} for one axis.
    joints = []
    for j in range(num_joints):
        axes = {'s': [], 'r': [], 't': []}   # [x,y,z] KeyTables for scale/rot/translate
        for axis in range(3):
            e = table_off + (j * 3 + axis) * 0x12
            axes['s'].append(_read_keytable(d, e + 0x00))
            axes['r'].append(_read_keytable(d, e + 0x06))
            axes['t'].append(_read_keytable(d, e + 0x0C))
        joints.append(axes)

    return dict(attribute=attribute, dec_shift=dec_shift, frame_max=frame_max, num_joints=num_joints,
                scale_data=scale_data, rot_data=rot_data, trans_data=trans_data,
                joints=joints)


def to_jsonable(anm):
    j = dict(anm)
    j['joints'] = [{k: [kt.as_list() for kt in v] for k, v in axes.items()} for axes in anm['joints']]
    return j


def load_from_lkanm(lkanm_bytes_or_path, names=('walk', 'dash', 'waits', 'freeb', 'rollf', 'rot', 'slip',
                                                'atnwls', 'atnwrs', 'atnls', 'atnrs', 'atndls', 'atndrs',
                                                'atnwb', 'atndb')):
    """Parse the named .bck anims from LkAnm.arc, given either raw arc bytes or a path."""
    if isinstance(lkanm_bytes_or_path, (bytes, bytearray)):
        raw_arc = bytes(lkanm_bytes_or_path)
    else:
        raw_arc = open(lkanm_bytes_or_path, 'rb').read()
    if RARC is None:
        files = read_rarc_bytes(raw_arc, 'LkAnm.arc')
        return {nm: parse_bck(files[nm + '.bck']) for nm in names}
    r = RARC(); r.read(BytesIO(raw_arc))
    out = {}
    for nm in names:
        fe = next(x for x in r.file_entries if x.name == nm + '.bck')
        raw = fe.data.getvalue() if hasattr(fe.data, 'getvalue') else fe.data
        out[nm] = parse_bck(raw)
    return out


# Two output sets: the walk/dash foot-chain anims (foot_speedf), and the sword-cut root-motion anims
# (land.py CUT_F/CUT_A use only the joint-0 translate; cutturnb = spin-attack roll cut, kept, unmodeled).
_OUTPUTS = {
    # 'dashs'/'walks' = the sword-drawn dash/walk (getAnmData mSwordAnmIndexTable; different leg
    # rotations than the sheathed clips, waits unchanged). See knowledge/model/anim-engine.md.
    # 'waitatob' = ANM_WAITATOB, the low-life wait A->B transition procWait_init plays before
    # settling into the WAITB/WALK idle blend. See knowledge/model/wait-stop-pose.md.
    # 'waitb' = ANM_WAITB, the steady critical-health idle selected by setBlendMoveAnime.
    'link_anim_walk_dash.json': ('walk', 'walks', 'dash', 'dashs', 'waits', 'freeb', 'rollf', 'rot',
                                 'slip', 'atnwls', 'atnwrs', 'atnls', 'atnrs', 'atndls', 'atndrs',
                                 'atnwb', 'atndb', 'waitatob', 'waitb'),
    'link_anim_cuts.json': ('cutf', 'cuta', 'cutturnb'),
    # Carried-item poses. A normal B/DROP uses the previous GRABWAIT hand pose,
    # then ``setAnimeEquipSword`` installs REST in the upper layer. Keep the
    # actual GRABTHROW/GRABRE resources for the separate throw path.
    'link_anim_grab.json': ('grabwait', 'grabwaitb', 'grabup', 'grabthrow', 'grabre', 'rest'),
}


def extract_animation_sets(src, *, which=None, outdir=None):
    """Extract selected Link animation sets from an ISO path or LkAnm.arc."""
    if isinstance(src, (str, os.PathLike)) and str(src).lower().endswith('.iso'):
        src = _gcm_read_object_arc(str(src), 'LkAnm')
    if outdir is None:
        outdir = os.path.join(_rb, '_generated', 'anim')
    os.makedirs(outdir, exist_ok=True)
    written = []
    for fname, names in _OUTPUTS.items():
        if which and which not in fname:
            continue
        anms = load_from_lkanm(src, names=names)
        outp = os.path.join(outdir, fname)
        with open(outp, 'w') as stream:
            json.dump({nm: to_jsonable(a) for nm, a in anms.items()}, stream)
        written.append(outp)
    return written


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    if 'lkanm' in o:
        src = o['lkanm']                                    # explicit path override
    elif 'iso' in o:
        src = _gcm_read_object_arc(o['iso'], 'LkAnm')
    else:
        from harness import dolphin_env                     # resolve from extract dir or ISO
        src = dolphin_env.object_arc_bytes('LkAnm')
    for outp in extract_animation_sets(src, which=o.get('which')):
        print("wrote", outp)


if __name__ == '__main__':
    main()
