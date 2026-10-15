"""Offline regression for the FRONT_ROLL body Co cylinder centre (tww_sim.core.anim.body_cyl),
guarded against a LIVE golden captured on GZLJ01 (tests/golden/roll_co_center_live.json).

Two live goldens, both GZLJ01, Link rolling pinned against a wall (current.pos + shape_angle.y frozen
so only the pose + lean move mCyl's centre -- isolating daPy_lk_c::setCollision spD0.x/z =
0.5*(root+neck world joint XZ)):

  * roll_co_center_live.json (older) has NO per-frame shape_z, so it exercises the CLEAN pose
    (shape_z defaulting to 0). Its early-frame residual is the missing setWorldMatrix base z-tilt by
    shape_angle.z (the MOVE turn lean, decaying ~35%/frame), NOT the oldframe-morf. We assert the
    settled tail (anim_frame >= 12, lean ~0) is bit-exact and the pre-settle residual is bounded +
    monotonically decaying.
  * hyrule_roll_lean.json (2026-07-10, harness/rollstab/capture_roll_lean.py) logs shape_z per frame.
    Feeding the PREVIOUS frame's shape_z (the setWorldMatrix/setMoveSlantAngle one-frame lag) makes
    roll_co_center BIT-EXACT (0 ULP) on every settled roll frame -- the real fix. Roll frame 0 (the
    oldframe-morf) and roll frame 1 (still mid-approach, pos not yet frozen) are exempt.

Requires the copyrighted anim keyframe data under _generated/anim (dev machines); SKIPS without it.
"""
import struct
import json
import math
import os

import pytest

from tww_sim.core.anim import body_cyl

_HAVE_ANIM = body_cyl.available()
_GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "roll_co_center_live.json")


def _load():
    with open(_GOLDEN) as f:
        return json.load(f)


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_roll_co_center_settled_bit_exact():
    """Once the roll-entry morf has decayed (anim_frame >= 12) the clean-pose port == the game."""
    g = _load()
    px, _py, pz = g["pos"]
    fac = g["shape_angle_y"]
    checked = 0
    for frame, lx, lz in g["frames"]:
        if frame < 12.0:
            continue
        cx, cz = body_cyl.roll_co_center(px, pz, fac, frame)
        err = math.hypot(cx - lx, cz - lz)
        assert err < 2e-4, f"settled frame {frame}: err {err} (expected < 1 ULP)"
        checked += 1
    assert checked >= 2


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_roll_co_center_transient_bounded_and_decaying():
    """Past the entry frame the residual (the un-modelled oldframe-morf) stays < 0.30 u and decays."""
    g = _load()
    px, _py, pz = g["pos"]
    fac = g["shape_angle_y"]
    errs = []
    for frame, lx, lz in g["frames"]:
        cx, cz = body_cyl.roll_co_center(px, pz, fac, frame)
        errs.append(math.hypot(cx - lx, cz - lz))
    # entry frame (frame 0.0) is ~fully the old running pose -> large; everything after is small.
    for e in errs[1:]:
        assert e < 0.30, f"post-entry residual {e} exceeds the documented morf bound"
    # the lean decays ~35%/frame, so each post-entry residual is <= the previous (allow f32 noise).
    for a, b in zip(errs[1:], errs[2:]):
        assert b <= a + 1e-4, f"residual grew ({a} -> {b}); the base lean should decay monotonically"


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_roll_co_center_leads_the_feet():
    """The whole point: the anim-driven centre is offset well away from the feet (current.pos) --
    the feet-proxy the first tetra_clip pass used is wrong by this much (~10-26 u mid-lunge)."""
    g = _load()
    px, _py, pz = g["pos"]
    fac = g["shape_angle_y"]
    peak = 0.0
    for frame, _lx, _lz in g["frames"]:
        cx, cz = body_cyl.roll_co_center(px, pz, fac, frame)
        peak = max(peak, math.hypot(cx - px, cz - pz))
    assert peak > 10.0, f"expected the roll cyl centre to lead the feet by >10u, got {peak}"


# The shape_z base-lean fixture (hyrule_roll_lean.json): the real, 0-ULP fix.
_LEAN = os.path.join(os.path.dirname(__file__), "..", "fixtures", "hyrule_roll_lean.json")


def _bits(x):
    return struct.unpack('>i', struct.pack('>f', body_cyl.fp.f32(x)))[0]


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
@pytest.mark.skipif(not os.path.exists(_LEAN), reason="hyrule_roll_lean.json capture not present")
def test_roll_co_center_bit_exact_with_lean():
    """With the PREVIOUS frame's shape_z fed to roll_co_center, the Co centre is BIT-EXACT (0 ULP)
    vs the live mCyl on every settled roll frame. This is the body-lean fix: the residual was the
    missing setWorldMatrix base z-tilt, not the oldframe-morf. Roll frame 0 (the morf) and roll frame
    1 (pos not yet frozen mid-approach) are exempt; both precede the push overlap (roll frame ~6)."""
    fix = json.load(open(_LEAN))
    roll_rows = [r for r in fix["frames"] if r["proc"] == 30 and r.get("cyl")]
    assert len(roll_rows) >= 10, "capture has too few roll frames"
    checked = 0
    prev_shz = None
    for k, r in enumerate(roll_rows):
        af = r["anim_frame"]
        px, _py, pz = r["pos"]
        fac = r["shape_y"]
        lx, lz = r["cyl"][0], r["cyl"][2]
        base_lean = prev_shz if prev_shz is not None else r["shape_z"]
        cx, cz = body_cyl.roll_co_center(px, pz, fac, af, shape_z=base_lean)
        prev_shz = r["shape_z"]
        if k < 2:                                   # roll frame 0 (morf) + frame 1 (approach): exempt
            continue
        dx = _bits(cx) - _bits(lx)
        dz = _bits(cz) - _bits(lz)
        # Exact 0 ULP through the push zone (animF <= 13, spans the roll-frame-~6 convergence); the far
        # decayed tail (animF > 13, magnitude ~965) may carry 1 ULP of f32 noise (lean-independent).
        tol = 0 if af <= 13.0 else 1
        assert abs(dx) <= tol and abs(dz) <= tol, (
            "roll frame %d (animF %.2f): centre off by dx=%d dz=%d (tol %d, shape_z lean=%d)"
            % (k, af, dx, dz, tol, base_lean))
        checked += 1
    assert checked >= 8, f"only {checked} settled roll frames checked"


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
@pytest.mark.skipif(not os.path.exists(_LEAN), reason="hyrule_roll_lean.json capture not present")
def test_the_body_chn_twist_leaves_the_live_lean_golden_bit_exact():
    """The `body_chn` counter-twist (session 87) is ADDITIVE against this capture, which is why it
    went unnoticed: feeding each frame's own POST-update lean as `body_lean` reproduces the same 0 ULP
    the untwisted call does. The capture's leans never exceed 28 past the exempt entry frames -- below
    the sine-table bucket where the twist first moves the midpoint -- so this fixture cannot decide
    the term either way. What decided it was a console delivery at leans an order of magnitude
    larger; that gate went with the parked route planner, so this asserts only that the fix did not
    disturb the older lean golden. See knowledge/history/co-centre-body-chn-twist.md."""
    fix = json.load(open(_LEAN))
    roll_rows = [r for r in fix["frames"] if r["proc"] == 30 and r.get("cyl")]
    assert max(abs(r["shape_z"]) for r in roll_rows[2:]) <= 30, (
        "the capture grew a real lean -- it can now decide the twist, so assert it directly")
    prev_shz = None
    checked = 0
    for k, r in enumerate(roll_rows):
        base_lean = prev_shz if prev_shz is not None else r["shape_z"]
        cx, cz = body_cyl.roll_co_center(r["pos"][0], r["pos"][2], r["shape_y"], r["anim_frame"],
                                         shape_z=base_lean, body_lean=r["shape_z"])
        prev_shz = r["shape_z"]
        if k < 2:
            continue
        tol = 0 if r["anim_frame"] <= 13.0 else 1
        assert abs(_bits(cx) - _bits(r["cyl"][0])) <= tol
        assert abs(_bits(cz) - _bits(r["cyl"][2])) <= tol
        checked += 1
    assert checked >= 8


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_the_body_chn_twist_moves_the_centre_at_a_real_turn_lean():
    """Guard the term's SHAPE, since no live capture here carries a lean big enough to: the twist is
    a no-op at the small leans the old fixture has and worth a real distance at the ones a roll off
    a curved approach carries (the courtyard entry hit rolls at m351C >> 1 == -388). Keeps a future
    refactor from quietly dropping it back to always-off."""
    fac, frame, base = 40820, 4.4, -388
    c0 = body_cyl.roll_co_center(0.0, 0.0, fac, frame, shape_z=base, body_lean=0)
    small = body_cyl.roll_co_center(0.0, 0.0, fac, frame, shape_z=base, body_lean=-28)
    big = body_cyl.roll_co_center(0.0, 0.0, fac, frame, shape_z=base, body_lean=-388)
    assert (_bits(small[0]), _bits(small[1])) == (_bits(c0[0]), _bits(c0[1])), (
        "a 28-BAM twist is below the sine-table bucket -- it must be a no-op")
    moved = math.hypot(big[0] - c0[0], big[1] - c0[1])
    assert 0.01 < moved < 1.0, "a real turn lean moves the centre by a push-relevant distance: %r" % moved
    # and the chain-consts decomposition must carry it identically (what ShoveCtx bakes)
    rc, nc = body_cyl.roll_co_chain_consts(fac, frame, shape_z=base, body_lean=-388)
    tx_r, tz_r, tx_n, tz_n = 0.0, 0.0, 0.0, 0.0
    for cx_, cz_ in rc:
        tx_r, tz_r = body_cyl.fp.fadds(cx_, tx_r), body_cyl.fp.fadds(cz_, tz_r)
    for cx_, cz_ in nc:
        tx_n, tz_n = body_cyl.fp.fadds(cx_, tx_n), body_cyl.fp.fadds(cz_, tz_n)
    assert body_cyl.fp.fmuls(0.5, body_cyl.fp.fadds(tx_r, tx_n)) == big[0]
    assert body_cyl.fp.fmuls(0.5, body_cyl.fp.fadds(tz_r, tz_n)) == big[1]


@pytest.mark.skipif(not _HAVE_ANIM, reason="anim keyframe data (_generated/anim) not present")
@pytest.mark.skipif(not os.path.exists(_LEAN), reason="hyrule_roll_lean.json capture not present")
def test_lean_matters_only_off_axis():
    """Guard the fix's shape: feeding shape_z changes the centre on a leaning frame (nonzero lean)
    but is a NO-OP once the lean has decayed to 0 -- so a straight-approach roll (lean 0) is
    unaffected. Prevents a future refactor from silently making shape_z always-on or always-off."""
    fix = json.load(open(_LEAN))
    roll_rows = [r for r in fix["frames"] if r["proc"] == 30 and r.get("cyl")]
    leaning = next(r for r in roll_rows if abs(r["shape_z"]) > 20)
    settled = next(r for r in roll_rows if r["shape_z"] == 0)
    for r, must_differ in ((leaning, True), (settled, False)):
        px, _py, pz = r["pos"]
        fac = r["shape_y"]
        af = r["anim_frame"]
        c0 = body_cyl.roll_co_center(px, pz, fac, af, shape_z=0)
        cz_ = body_cyl.roll_co_center(px, pz, fac, af, shape_z=r["shape_z"])
        differs = (_bits(c0[0]) != _bits(cz_[0])) or (_bits(c0[1]) != _bits(cz_[1]))
        assert differs == must_differ, (
            "shape_z=%d: expected differs=%s got %s" % (r["shape_z"], must_differ, differs))
