"""Exact cached scan of the final delivered stick in dispatch-26 route family."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
from pathlib import Path


NEAR = (0, 249, 151, 116, 219, 64, 255, 207, 0, 155, 255, 40, 90, 242, 0)


def _scan(trace_path, c_lo, c_hi):
    from harness.collision.offline_moving_drop import _step
    from harness.rollstab.smart_route_search import RouteFamily

    trace = json.loads(Path(trace_path).read_text(encoding="ascii"))
    family = RouteFamily(trace, 26)
    # Anchor-21 replay has a stable sub-millimeter residual at the captured
    # row-23 checkpoint. Apply that measured translation before exact wall
    # acceptance; the seam dust is narrower than the residual itself.
    baseline = family.evaluate(family.controls_from_rows(), phase="route synthesis",
                               synthesize_buttons=True)
    captured = next(frame["after"] for frame in trace["trace"] if int(frame["row"]) == 23)
    correction = (float(captured["x"]) - baseline.old[0],
                  float(captured["z"]) - baseline.old[1])
    rows = family.rows_from_controls(NEAR, synthesize_buttons=True)
    node = copy.copy(family.start)
    node.state = family.start.state.clone()
    pending = list(node.state._inbuf)
    for offset, index in enumerate(family.pending_control_rows):
        item = list(pending[offset])
        item[0], item[1], item[4] = (
            rows[index]["stickX"], rows[index]["stickY"], rows[index]["substickX"]
        )
        pending[offset] = tuple(item)
    node.state._inbuf = pending
    for index in (22, 23, 24):
        node = _step(node, rows[index])

    for cx in range(c_lo, c_hi):
        for sx in range(128, 177):
            for sy in range(128, 241):
                candidate = copy.copy(node)
                candidate.state = node.state.clone()
                queued = list(candidate.state._inbuf)
                delivered = list(queued[0])
                delivered[0], delivered[1], delivered[4] = sx, sy, cx
                queued[0] = tuple(delivered)
                candidate.state._inbuf = queued
                candidate = _step(candidate, rows[25])
                state = candidate.state
                old = (state.pos_x + correction[0], state.pos_z + correction[1])
                dispatch = rows[26]
                state.enter_cut_from_move(
                    dispatch["stickX"], dispatch["stickY"],
                    csx=dispatch["substickX"], csy=dispatch["substickY"],
                )
                new = (state.pos_x + correction[0], state.pos_z + correction[1])
                if family.seam.genuine_clip(old, new):
                    controls = list(NEAR)
                    controls[9], controls[10], controls[11] = sx, sy, cx
                    return {"controls": controls, "old": old, "new": new,
                            "facing": state.facing, "travel": state.travel}
    return None


def main():
    trace = str(Path("_generated/current_walk_slash/manual_route_trace.json").resolve())
    ranges = [(value, min(256, value + 16)) for value in range(0, 256, 16)]
    with ProcessPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_scan, trace, lo, hi) for lo, hi in ranges]
        for future in as_completed(futures):
            result = future.result()
            if result:
                print(json.dumps(result), flush=True)
                for pending in futures:
                    pending.cancel()
                return
    print("NO_HIT", flush=True)


if __name__ == "__main__":
    main()
