"""The land-camera (dCamera_c) port vs the live courtyard oracle -- 0-ULP, chained.

Oracle: fixtures/courtyard_cam_oracle.json (single-stepped from slot 2; run A of the
session-17 A/B probe re-captured with the full dCamera_c block + statuses + attention).
The camera is seeded ONCE from the f0 block and stepped through all 120 frames with no
reseeding: every committed csangle, the whole view-cache globe (R / elevation / yaw), the
center chase, and the manual-work springs must match the live capture exactly. The window
covers: settled manual camera, active C-stick orbit, 4 followCamera blip frames (L rising
edges), two lockon windows (blend in/out), and the post-release settle.

dup=True frames are single-step double-reads (the game frame did not run) and are skipped.
"""
import json
import os
import struct

import pytest

from tww_sim.core.camera.land_cam import LandCamera, seed_from_block

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "courtyard_cam_oracle.json")


@pytest.fixture(scope="module")
def oracle():
    with open(FIX) as fh:
        return json.load(fh)


def test_land_cam_chained_bit_exact(oracle):
    cam = LandCamera()
    seed_from_block(cam, bytes.fromhex(oracle["seed_cam_raw"]))
    checked = 0
    for fr in oracle["frames"]:
        if fr["dup"]:
            continue
        link = dict(pos=tuple(fr["link"]["pos"]), facing=fr["link"]["facing"],
                    attn_pos=tuple(fr["link"]["attn"]))
        truth = fr["lockstate"] in (1, 2)
        attn = dict(truth=truth, lockon=truth,
                    target_attn=tuple(fr["tattn"]) if truth else None)
        cs = cam.step(fr["pad"], link, attn,
                      status0=fr["status0"], status1=fr["status1"])
        e = fr["expect"]
        f = fr["f"]
        assert cs == e["csangle"], "f%d csangle %d != %d" % (f, cs, e["csangle"])
        assert cam.cur_mode == e["mode"], "f%d mode" % f
        assert cam.vc_dir.r == e["vc_r"], "f%d vc.r" % f
        assert cam.vc_dir.az == e["vc_az"], "f%d vc.az" % f
        assert cam.vc_dir.inc == e["vc_inc"], "f%d vc.inc" % f
        assert list(cam.vc_center) == e["vc_center"], "f%d vc_center" % f
        assert list(cam.vc_eye) == e["vc_eye"], "f%d vc_eye" % f
        assert list(cam.center) == e["center"], "f%d center" % f
        assert list(cam.eye) == e["eye"], "f%d eye" % f
        if e["mode"] == 12:     # manual-work fields are unioned; only valid on manual frames
            assert [cam.w_glob.r, cam.w_glob.az, cam.w_glob.inc] == e["glob"], "f%d glob" % f
            assert cam.w_m398 == e["m398"], "f%d m398" % f
            assert cam.w_m3B0 == e["m3B0"], "f%d m3B0" % f
            assert cam.w_m3B4 == e["m3B4"], "f%d m3B4" % f
        checked += 1
    assert checked >= 118      # 120 frames minus the known dup(s)


def test_land_cam_lock_windows_covered(oracle):
    """The gate exercises both untarget-cycle lockon windows and all four follow blips."""
    lock_frames = [fr["f"] for fr in oracle["frames"] if fr["lockstate"] in (1, 2)]
    blip_frames = [fr["f"] for fr in oracle["frames"] if fr["expect"]["mode"] == 0]
    assert len(lock_frames) >= 20
    assert len(blip_frames) == 4
