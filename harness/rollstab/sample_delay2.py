"""Sample two steering frames before a delayed sidehop and rank landing offsets."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import math
from pathlib import Path
import random


def _sample(trace_path, seed, count):
    from harness.collision.offline_moving_drop import _make_seed, _step
    from harness.rollstab.live_slash import _mesh_tris
    from harness.rollstab.smart_route_search import RouteFamily

    trace = json.loads(Path(trace_path).read_text(encoding="ascii"))
    base = _make_seed(trace["seeds"][4], _mesh_tris(trace["wall_mesh"]),
                      force_state=None, model_draw=False)
    family = RouteFamily(trace, 24)
    baseline = family.evaluate(family.controls_from_rows())
    trigger = dict(trace["route"]["rows"][5])
    trigger.update(stickX=0, stickY=156, substickX=174, substickY=128,
                   buttons=0x140, triggerL=255)
    rng = random.Random(seed)
    found = []
    for _ in range(count):
        controls = tuple(rng.randrange(256) for _ in range(4))
        node = _make_seed(trace["seeds"][4], _mesh_tris(trace["wall_mesh"]),
                          force_state=None, model_draw=False)
        node.state._inbuf = [
            (controls[0], controls[1], 0, 0, 174, 128),
            (controls[2], controls[3], 0, 0, 174, 128),
        ]
        rows = [trigger] + [dict(row) for row in trace["route"]["rows"][6:22]]
        landing = None
        for row in rows:
            node = _step(node, row)
            if node.state.state == 11:
                landing = (node.state.pos_x, node.state.pos_z, node.state.facing)
                break
        if landing is None:
            continue
        dx = landing[0] - (-441.34381103515625)
        dz = landing[1] - (-2320.103759765625)
        old = (baseline.old[0] + dx, baseline.old[1] + dz)
        new = (baseline.new[0] + dx, baseline.new[1] + dz)
        vx, vz = new[0] - old[0], new[1] - old[1]
        length = math.hypot(vx, vz)
        sx, sz = family.seam.S
        along = ((sx - old[0]) * vx + (sz - old[1]) * vz) / length
        reach = max(0.0, -along) + max(0.0, along - length)
        ray = abs(family.seam.perp_to_ray(old, new))
        found.append((reach * 4.0 + ray, reach, ray, controls, dx, dz, landing[2]))
    return sorted(found)[:20]


def main():
    trace = str(Path("_generated/current_walk_slash/manual_route_trace.json").resolve())
    with ProcessPoolExecutor(max_workers=8) as pool:
        groups = list(pool.map(_sample, [trace] * 8,
                               [771 + i * 8191 for i in range(8)], [1000] * 8))
    rows = sorted(item for group in groups for item in group)
    for item in rows[:40]:
        print(item, flush=True)
    path = Path("_generated/current_walk_slash_fast/delay2_landings.json")
    path.write_text(json.dumps(rows[:100], indent=2), encoding="ascii")


if __name__ == "__main__":
    main()
