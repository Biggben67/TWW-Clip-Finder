"""Search the captured Hyrule barrier route with the correct input-buffer timing."""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path
import random
import time

from harness.collision.offline_moving_drop import _make_seed
from harness.rollstab.live_slash import _mesh_tris
from harness.rollstab.barrier_slash import _seed_kind
from harness.rollstab.seamgeo import SeamGeo


def _set_pending(state, index, stick):
    row = list(state._inbuf[index])
    row[0], row[1] = stick
    state._inbuf[index] = tuple(row)


def _approach(base, rows, row5, row6):
    state = base.clone()
    _set_pending(state, 0, row5)
    _set_pending(state, 1, row6)
    for index in (7, 8):
        row = rows[index]
        state.step(
            row["stickX"], row["stickY"], row.get("buttons", 0),
            row.get("triggerL", 0), row.get("substickX", 128),
            row.get("substickY", 128),
        )
    return state


def _fire(state, row9, stick, seam):
    fired = state.clone()
    pending = list(fired._inbuf[0])
    pending[0], pending[1] = stick
    fired._inbuf[0] = tuple(pending)
    old = (fired.pos_x, fired.pos_z)
    fired.enter_cut_from_move(
        row9["stickX"], row9["stickY"],
        csx=row9.get("substickX", 128), csy=row9.get("substickY", 128),
    )
    new = (fired.pos_x, fired.pos_z)
    return {
        "old": old,
        "new": new,
        "facing": fired.facing,
        "travel": fired.travel,
        "speedF": fired.speedF,
        "ray_error": seam.perp_to_ray(old, new),
        "genuine_clip": seam.genuine_clip(old, new),
        "planes": (seam.wA.pla.func(seam.p32(*new)),
                   seam.wB.pla.func(seam.p32(*new))),
    }


def _rank(result):
    # Both endpoint planes must be appreciably behind the near-flat barrier.
    depth = -min(result["planes"])
    depth_penalty = max(0.0, 0.25 - depth)
    return abs(result["ray_error"]) + depth_penalty * 10.0


def search(trace, samples, finalists, seed):
    rows = [dict(row) for row in trace["route"]["rows"]]
    seed_data = dict(trace["seeds"][6])
    seed_data["seed_kind"] = _seed_kind(
        int(trace["trace"][5]["after"]["state"]),
        int(trace["trace"][6]["after"]["state"]),
    )
    base = _make_seed(
        seed_data, _mesh_tris(trace["wall_mesh"]),
        force_state=None, model_draw=False,
    ).state
    seam = SeamGeo(trace["geo"], trace["seeds"][6]["snapshot"]["camera"])
    rng = random.Random(seed)
    heap = []
    seen = set()
    started = time.monotonic()

    # Mix a dense neighborhood of the known 0.0073-unit miss with broad samples.
    for index in range(samples):
        if index < samples * 3 // 4:
            row5 = (rng.randrange(128, 256), rng.randrange(148, 170))
            row6 = (rng.randrange(1, 100), rng.randrange(70, 160))
        else:
            row5 = (rng.randrange(1, 256), rng.randrange(80, 256))
            row6 = (rng.randrange(1, 256), rng.randrange(80, 256))
        state = _approach(base, rows, row5, row6)
        key = (
            state.pos_x, state.pos_z, state.facing, state.travel,
            state.speedF, state.nspeed,
        )
        if key in seen:
            continue
        seen.add(key)
        result = _fire(state, rows[9], (156, 251), seam)
        score = _rank(result)
        item = (-score, index, row5, row6, state, result)
        if len(heap) < finalists:
            heapq.heappush(heap, item)
        elif score < -heap[0][0]:
            heapq.heapreplace(heap, item)
        if result["genuine_clip"]:
            yield row5, row6, (156, 251), result
        if (index + 1) % 25000 == 0:
            print(
                f"approach {index + 1}/{samples}: {len(seen)} unique; "
                f"best score={-max(heap)[0]:.9f}; {time.monotonic() - started:.1f}s",
                flush=True,
            )

    ranked = sorted(heap, key=lambda item: -item[0])
    print(f"refining {len(ranked)} approach finalists", flush=True)
    tested = set()
    for rank, (_, _, row5, row6, state, coarse) in enumerate(ranked, 1):
        # The useful direction is near (156,251), but include every upper-half
        # byte pair so quantized angle and magnitude boundaries are not skipped.
        for sy in range(128, 256):
            for sx in range(1, 256):
                stick = (sx, sy)
                result = _fire(state, rows[9], stick, seam)
                signature = (
                    result["new"], result["facing"], result["travel"],
                    result["speedF"], row5, row6,
                )
                if signature in tested:
                    continue
                tested.add(signature)
                if result["genuine_clip"]:
                    yield row5, row6, stick, result
        if rank % 5 == 0:
            print(
                f"refine {rank}/{len(ranked)}; {len(tested)} unique cuts; "
                f"{time.monotonic() - started:.1f}s", flush=True,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=150000)
    parser.add_argument("--finalists", type=int, default=40)
    parser.add_argument("--seed", type=int, default=91583)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())
    hits = []
    for row5, row6, row7, result in search(
        trace, args.samples, args.finalists, args.seed,
    ):
        hit = {
            "row5": list(row5), "row6": list(row6), "row7": list(row7),
            **{key: list(value) if isinstance(value, tuple) else value
               for key, value in result.items()},
        }
        hits.append(hit)
        print("HIT " + json.dumps(hit, separators=(",", ":")), flush=True)
        if len(hits) >= 32:
            break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(hits, indent=2) + "\n")
    print(f"saved {len(hits)} hit(s) to {args.output}", flush=True)


if __name__ == "__main__":
    main()
