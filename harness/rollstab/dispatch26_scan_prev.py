"""Residual-corrected exhaustive scan of the previous delivered stick pair."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy, json
from pathlib import Path

NEAR = (0, 249, 151, 116, 219, 64, 255, 207, 0, 149, 186, 40, 90, 242, 0)

def hits_requested_vertex(seam, old, new, radius=1.0):
    """Reject crossings through another part of a long wall mesh."""
    sx, sz = seam.S
    dx, dz = new[0] - old[0], new[1] - old[1]
    den = dx * dx + dz * dz
    if den <= 0.0:
        return False
    t = ((sx - old[0]) * dx + (sz - old[1]) * dz) / den
    if not (0.0 <= t <= 1.0):
        return False
    ix, iz = old[0] + t * dx, old[1] + t * dz
    return (ix - sx) ** 2 + (iz - sz) ** 2 <= radius * radius

def scan(path, lo, hi):
    from harness.collision.offline_moving_drop import _step
    from harness.rollstab.smart_route_search import RouteFamily
    t = json.loads(Path(path).read_text(encoding="ascii"))
    f = RouteFamily(t, 26)
    base = f.evaluate(f.controls_from_rows(), phase="route synthesis", synthesize_buttons=True)
    cap = next(x["after"] for x in t["trace"] if int(x["row"]) == 23)
    correction = (float(cap["x"]) - base.old[0], float(cap["z"]) - base.old[1])
    rows = f.rows_from_controls(NEAR, synthesize_buttons=True)
    node = copy.copy(f.start); node.state = f.start.state.clone()
    pending = list(node.state._inbuf)
    for off, index in enumerate(f.pending_control_rows):
        item = list(pending[off]); item[0] = rows[index]["stickX"]; item[1] = rows[index]["stickY"]; item[4] = rows[index]["substickX"]; pending[off] = tuple(item)
    node.state._inbuf = pending
    for index in (22, 23): node = _step(node, rows[index])
    for sx in range(lo, hi):
        for sy in range(256):
            n = copy.copy(node); n.state = node.state.clone(); q = list(n.state._inbuf); item = list(q[0]); item[0], item[1], item[4] = sx, sy, NEAR[8]; q[0] = tuple(item); n.state._inbuf = q
            n = _step(n, rows[24]); n = _step(n, rows[25]); st = n.state
            old = (st.pos_x + correction[0], st.pos_z + correction[1]); d = rows[26]
            st.enter_cut_from_move(d["stickX"], d["stickY"], csx=d["substickX"], csy=d["substickY"])
            new = (st.pos_x + correction[0], st.pos_z + correction[1])
            if f.seam.genuine_clip(old, new) and hits_requested_vertex(f.seam, old, new):
                c = list(NEAR); c[6], c[7] = sx, sy
                return {"controls": c, "old": old, "new": new, "facing": st.facing, "travel": st.travel}
    return None

def main():
    path = str(Path("_generated/current_walk_slash/manual_route_trace.json").resolve())
    ranges = [(i, min(256, i + 16)) for i in range(0, 256, 16)]
    with ProcessPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(scan, path, lo, hi) for lo, hi in ranges]
        for future in as_completed(futures):
            result = future.result()
            if result:
                print(json.dumps(result), flush=True)
                for pending in futures: pending.cancel()
                return
    print("NO_HIT", flush=True)

if __name__ == "__main__": main()
