"""Parallel refinement of measured delayed-sidehop landing bands."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import json
from pathlib import Path


BANDS = (
    (160, 0, -17.992828369140625, 7.083984375),
    (152, 40, -17.08074951171875, 6.693603515625),
    (152, 32, -16.167083740234375, 6.309326171875),
    (152, 16, -15.25262451171875, 5.92529296875),
    (152, 0, -14.33697509765625, 5.54443359375),
    (144, 88, -12.042694091796875, 4.60205078125),
    (144, 64, -11.123077392578125, 4.230712890625),
    (112, 0, -9.74127197265625, 3.681396484375),
    (112, 44, -8.8184814453125, 3.316650390625),
)


def _worker(trace_path, band, budget, seed):
    from harness.rollstab.quick_route_opt import optimize
    from harness.rollstab.smart_route_search import RouteFamily

    trace = json.loads(Path(trace_path).read_text(encoding="ascii"))
    family = RouteFamily(trace, 24)
    family.position_offset = (band[2], band[3])
    result, count = optimize(
        family, family.controls_from_rows(), evaluations=budget, seed=seed,
        log=lambda _message: None,
    )
    return {**asdict(result), "evaluations": count, "band": list(band)}


def main():
    trace = Path("_generated/current_walk_slash/manual_route_trace.json").resolve()
    output = Path("_generated/current_walk_slash_fast/parallel_result.json")
    results = []
    with ProcessPoolExecutor(max_workers=len(BANDS)) as pool:
        futures = {
            pool.submit(_worker, str(trace), band, 4000, 9917 + index * 1009): band
            for index, band in enumerate(BANDS)
        }
        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            print(
                f"band {item['band'][:2]}: ray={item['ray_error']:.9f}, "
                f"reach={item['reach_error']:.9f}, exact={item['exact']}",
                flush=True,
            )
    results.sort(key=lambda item: (
        not item["exact"], item["ray_error"] ** 2 + item["reach_error"] ** 2
    ))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="ascii")
    print("BEST", json.dumps(results[0]), flush=True)


if __name__ == "__main__":
    main()
