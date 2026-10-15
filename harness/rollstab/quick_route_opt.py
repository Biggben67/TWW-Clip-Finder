"""Small deterministic integer optimizer for short captured-route tails."""
from __future__ import annotations

import random


def optimize(family, initial, *, evaluations=50000, seed=0, log=print):
    rng = random.Random(seed)
    dimensions = len(initial)
    population_size = max(64, dimensions * 32)
    cache = {}

    def evaluate(values):
        key = tuple(max(0, min(255, int(round(value)))) for value in values)
        if key not in cache:
            cache[key] = family.evaluate(key, phase="route refinement")
        result = cache[key]
        score = result.ray_error ** 2 + result.reach_error ** 2
        return key, result, score

    population = [tuple(initial)]
    while len(population) < population_size:
        population.append(tuple(rng.randrange(256) for _ in range(dimensions)))
    ranked = [evaluate(item) for item in population]
    used = len(cache)
    generation = 0
    while used < evaluations:
        generation += 1
        next_ranked = []
        for index, parent in enumerate(ranked):
            choices = [item for i, item in enumerate(ranked) if i != index]
            a, b, c = rng.sample(choices, 3)
            forced = rng.randrange(dimensions)
            trial = []
            for axis in range(dimensions):
                if axis == forced or rng.random() < 0.85:
                    value = a[0][axis] + 0.75 * (b[0][axis] - c[0][axis])
                else:
                    value = parent[0][axis]
                trial.append(value)
            candidate = evaluate(trial)
            next_ranked.append(candidate if candidate[2] <= parent[2] else parent)
            if candidate[1].exact or len(cache) >= evaluations:
                ranked = next_ranked + ranked[len(next_ranked):]
                break
        ranked = sorted(next_ranked + ranked[len(next_ranked):], key=lambda item: item[2])
        used = len(cache)
        best = ranked[0]
        if generation == 1 or generation % 10 == 0 or best[1].exact:
            log(
                f"generation {generation}: evaluations={used}, controls={best[0]}, "
                f"ray={best[1].ray_error:.9f}, reach={best[1].reach_error:.9f}, "
                f"exact={best[1].exact}"
            )
        if best[1].exact:
            return best[1], used

    # Exhaust the immediate integer neighborhood of the best continuous basin.
    best = min(cache.values(), key=lambda item: item.ray_error ** 2 + item.reach_error ** 2)
    center = best.controls
    for radius in (8, 4, 2, 1):
        improved = True
        while improved and len(cache) < evaluations:
            improved = False
            baseline = best.ray_error ** 2 + best.reach_error ** 2
            for axis in range(dimensions):
                for delta in (-radius, radius):
                    trial = list(center)
                    trial[axis] += delta
                    key, result, score = evaluate(trial)
                    if result.exact:
                        return result, len(cache)
                    if score < baseline:
                        center, best, baseline = key, result, score
                        improved = True
    return best, len(cache)
