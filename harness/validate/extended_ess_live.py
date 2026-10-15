"""Reversible, explicit live camera diagnostics; never runs during a movie."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import open_dolphin
from harness.dolphin_scripts.extended_ess_core import State, Pad, advance, choose_camera


def capture(reader):
    p = reader.u32(0x803AD860)
    c = reader.u32(reader.u32(0x803AD380) + 0x34) + 0x244
    style = reader.u32(c + 0x510)
    row = 0x803485AC + style * 0x84 + 4
    state = State(
        reader.f32(p + 0x34E4), reader.u16(p + 0x12E), reader.u16(p + 0x136),
        reader.u16(c + 0x6C), reader.u16(c + 0x42), reader.u16(c + 0x3AE),
        reader.f32(p + 0x1D0), reader.f32(row + 24 * 4), reader.f32(row + 21 * 4),
    )
    return dict(
        frame=reader.u32(0x803E9D34), model=asdict(state),
        mode=reader.u32(c + 0x13C), proc=reader.u32(p + 0x3100),
        speedF=reader.f32(p + 0x17C), raw_angle=reader.u16(p + 0x3404),
        target_angle=reader.u16(p + 0x3410), msd=reader.f32(p + 0x34D8),
        camera_pad=[reader.f32(c + o) for o in (0x154, 0x158, 0x16C, 0x170)],
        pad=list(reader.read_bytes(0x803E4410, 8)),
        position=[reader.f32(p + o) for o in (0x120, 0x124, 0x128)],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--name", default="camera_pulses")
    parser.add_argument("--x", type=int, default=128)
    parser.add_argument("--y", type=int, default=110)
    parser.add_argument("--closed-loop", action="store_true")
    parser.add_argument("--margin", type=int, default=256)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    c = DolphinControl(args.pid)
    status = c.command("status")
    if status.get("recording") or status.get("playing") or status.get("state") != "paused":
        raise RuntimeError("Pause Dolphin and stop movie recording/playback first")
    reader = open_dolphin(args.pid)
    root = Path("_generated/extended_ess").resolve()
    root.mkdir(parents=True, exist_ok=True)
    sav = root / (args.name + ".sav")
    records = []
    c.save_state(str(sav))
    original = capture(reader)
    try:
        c.command("clearinput")
        records.append(dict(vi=-1, issued=None, **capture(reader)))
        sequence = [128] * 4 + [152] * 2 + [128] * 6 + [104] * 2 + [128] * 8
        if args.closed_loop:
            sequence = [128] * args.frames
        output = 128
        last_frame = None
        for vi, cx in enumerate(sequence):
            if args.closed_loop:
                live = capture(reader)
                if live["frame"] != last_frame:
                    queued = Pad(*live["pad"][2:6])
                    plan = choose_camera(State(**live["model"]), Pad(args.x, args.y),
                                         pending=(queued,), margin=args.margin)
                    output = plan.cx if plan else 128
                    last_frame = live["frame"]
                cx = output
            c.advance_with(stickX=args.x, stickY=args.y, substickX=cx,
                           substickY=128, frames=1)
            time.sleep(0.06)
            if c.command("status").get("state") != "paused":
                raise RuntimeError("Frame advance did not return to pause; stopping diagnostic")
            result = dict(vi=vi, issued=[args.x, args.y, cx, 128], **capture(reader))
            records.append(result)
            delta = (result["frame"] - records[-2]["frame"]) & 0xFFFFFFFF
            if delta != 1:
                raise RuntimeError("Unexpected game-frame delta %d; stopping diagnostic" % delta)
            print(vi, result["frame"], cx, result["camera_pad"],
                  result["model"]["velocity"], result["model"]["controlled"], flush=True)
    finally:
        path = root / (args.name + ".json")
        restored = None
        try:
            c.load_state(str(sav))
            time.sleep(0.25)
            c.command("clearinput")
            c.pause()
            restored = capture(reader)
        finally:
            path.write_text(json.dumps(dict(original=original, restored=restored, records=records), indent=2))
            reader.close()
            print("trace:", path)
        print("restored position/frame:", restored["position"] == original["position"],
              restored["frame"] == original["frame"])


if __name__ == "__main__":
    main()
