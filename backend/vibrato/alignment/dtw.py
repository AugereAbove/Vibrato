from __future__ import annotations

import numpy as np
from numba import njit

INF = 1e30


@njit(cache=True)
def _distance(a: np.ndarray, b: np.ndarray) -> float:
    total = 0.0
    for k in range(a.shape[0]):
        d = a[k] - b[k]
        total += d * d
    return np.sqrt(total)


@njit(cache=True)
def _banded(
    a: np.ndarray, b: np.ndarray, lo: np.ndarray, hi: np.ndarray, step_penalty: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = a.shape[0]
    widths = hi - lo + 1
    offsets = np.zeros(n + 1, dtype=np.int64)
    for i in range(n):
        offsets[i + 1] = offsets[i] + widths[i]
    total = offsets[n]
    acc = np.full(total, INF)
    local = np.zeros(total)
    move = np.zeros(total, dtype=np.int8)
    for i in range(n):
        for j in range(lo[i], hi[i] + 1):
            index = offsets[i] + (j - lo[i])
            c = _distance(a[i], b[j])
            local[index] = c
            if i == 0 and j == 0:
                acc[index] = c
                continue
            best = INF
            choice = 0
            if i > 0 and lo[i - 1] <= j - 1 <= hi[i - 1]:
                candidate = acc[offsets[i - 1] + (j - 1 - lo[i - 1])] + 2.0 * c
                if candidate < best:
                    best = candidate
                    choice = 1
            if i > 0 and lo[i - 1] <= j <= hi[i - 1]:
                candidate = acc[offsets[i - 1] + (j - lo[i - 1])] + c + step_penalty
                if candidate < best:
                    best = candidate
                    choice = 2
            if j - 1 >= lo[i]:
                candidate = acc[index - 1] + c + step_penalty
                if candidate < best:
                    best = candidate
                    choice = 3
            acc[index] = best
            move[index] = choice
    path_i = np.zeros(n + b.shape[0], dtype=np.int64)
    path_j = np.zeros(n + b.shape[0], dtype=np.int64)
    path_c = np.zeros(n + b.shape[0])
    i = n - 1
    j = b.shape[0] - 1
    count = 0
    while True:
        index = offsets[i] + (j - lo[i])
        path_i[count] = i
        path_j[count] = j
        path_c[count] = local[index]
        count += 1
        step = move[index]
        if step == 0:
            break
        if step == 1:
            i -= 1
            j -= 1
        elif step == 2:
            i -= 1
        else:
            j -= 1
    return path_i[:count][::-1], path_j[:count][::-1], path_c[:count][::-1]


def full_band(n: int, m: int) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros(n, dtype=np.int64), np.full(n, m - 1, dtype=np.int64)


def diagonal_band(
    n: int, m: int, radius: int, offset: float = 0.0, slope: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    slope = (m - 1) / max(1, n - 1) if slope is None else slope
    centers = offset + slope * np.arange(n)
    lo = np.floor(centers - radius).astype(np.int64)
    hi = np.ceil(centers + radius).astype(np.int64)
    return fix_band(lo, hi, m)


def band_from_path(
    path_i: np.ndarray, path_j: np.ndarray, factor: int, n: int, m: int, radius: int
) -> tuple[np.ndarray, np.ndarray]:
    coarse_rows = int(path_i.max()) + 1 if path_i.size else 1
    coarse_lo = np.full(coarse_rows, np.iinfo(np.int64).max, dtype=np.int64)
    coarse_hi = np.full(coarse_rows, -1, dtype=np.int64)
    for ci, cj in zip(path_i, path_j):
        coarse_lo[ci] = min(coarse_lo[ci], cj)
        coarse_hi[ci] = max(coarse_hi[ci], cj)
    rows = np.minimum(np.arange(n) // factor, coarse_rows - 1)
    lo = coarse_lo[rows] * factor - radius
    hi = (coarse_hi[rows] + 1) * factor - 1 + radius
    return fix_band(lo, hi, m)


def fix_band(lo: np.ndarray, hi: np.ndarray, m: int) -> tuple[np.ndarray, np.ndarray]:
    n = lo.size
    lo = np.clip(lo, 0, m - 1).astype(np.int64)
    hi = np.clip(hi, 0, m - 1).astype(np.int64)
    lo = np.minimum.accumulate(lo[::-1])[::-1]
    hi = np.maximum.accumulate(hi)
    lo[0] = 0
    hi[-1] = m - 1
    for i in range(1, n):
        if lo[i] > hi[i - 1] + 1:
            lo[i] = hi[i - 1] + 1
        if hi[i] < lo[i]:
            hi[i] = lo[i]
    return lo, np.minimum(hi, m - 1)


def banded_dtw(
    a: np.ndarray, b: np.ndarray, lo: np.ndarray, hi: np.ndarray, step_penalty: float = 0.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return _banded(
        np.ascontiguousarray(a, dtype=np.float64),
        np.ascontiguousarray(b, dtype=np.float64),
        lo.astype(np.int64),
        hi.astype(np.int64),
        float(step_penalty),
    )


def pool(features: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return features
    n = int(np.ceil(features.shape[0] / factor))
    padded = np.full((n * factor, features.shape[1]), np.nan)
    padded[: features.shape[0]] = features
    blocks = padded.reshape(n, factor, features.shape[1])
    with np.errstate(invalid="ignore"):
        counts = np.sum(np.isfinite(blocks), axis=1)
        sums = np.nansum(blocks, axis=1)
    return np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)


def multiscale_dtw(
    a: np.ndarray,
    b: np.ndarray,
    synced_offset: int | None = None,
    synced_radius: int = 60,
    step_penalty: float = 0.05,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n, m = a.shape[0], b.shape[0]
    if n < 2 or m < 2:
        steps = max(n, m)
        return (
            np.linspace(0, n - 1, steps).round().astype(np.int64),
            np.linspace(0, m - 1, steps).round().astype(np.int64),
            np.zeros(steps),
        )
    levels = [20, 4, 1]
    path_i: np.ndarray | None = None
    path_j: np.ndarray | None = None
    costs = np.zeros(0)
    factor_prev = 1
    for factor in levels:
        pa = pool(a, factor)
        pb = pool(b, factor)
        pn, pm = pa.shape[0], pb.shape[0]
        if path_i is None:
            if synced_offset is not None:
                lo, hi = diagonal_band(
                    pn, pm, max(3, synced_radius // factor), offset=synced_offset / factor, slope=1.0
                )
            elif pn * pm <= 4_000_000:
                lo, hi = full_band(pn, pm)
            else:
                lo, hi = diagonal_band(pn, pm, max(10, int(0.3 * max(pn, pm))))
        else:
            assert path_j is not None
            ratio = factor_prev // factor
            radius = 25 if factor == 4 else 15
            lo, hi = band_from_path(path_i, path_j, ratio, pn, pm, radius)
        path_i, path_j, costs = banded_dtw(pa, pb, lo, hi, step_penalty)
        factor_prev = factor
    assert path_i is not None and path_j is not None
    return path_i, path_j, costs
