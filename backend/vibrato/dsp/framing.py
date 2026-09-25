from __future__ import annotations

import warnings

import numpy as np

HOP_S = 0.01


def n_frames(duration_s: float) -> int:
    return int(np.floor(duration_s / HOP_S + 1e-9)) + 1


def frame_times(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) * HOP_S


def time_to_frame(t: float) -> int:
    return round(t / HOP_S)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    if mask.size == 0:
        return []
    padded = np.concatenate([[False], mask.astype(bool), [False]])
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2])]


def remove_short_runs(mask: np.ndarray, min_frames: int) -> np.ndarray:
    out = mask.copy()
    for start, end in runs(mask):
        if end - start < min_frames:
            out[start:end] = False
    return out


def fill_short_gaps(mask: np.ndarray, max_frames: int) -> np.ndarray:
    out = mask.copy()
    for start, end in runs(~mask):
        if start > 0 and end < len(mask) and end - start <= max_frames:
            out[start:end] = True
    return out


def interpolate_gaps(values: np.ndarray, max_gap_frames: int, log_domain: bool = False) -> np.ndarray:
    out = values.astype(np.float64).copy()
    valid = np.isfinite(out)
    if valid.sum() < 2:
        return out
    work = np.log(out) if log_domain else out
    for start, end in runs(~valid):
        if start == 0 or end == len(out) or end - start > max_gap_frames:
            continue
        left = work[start - 1]
        right = work[end]
        steps = np.arange(1, end - start + 1) / (end - start + 1)
        filled = left + (right - left) * steps
        out[start:end] = np.exp(filled) if log_domain else filled
    return out


def resample_track_to_grid(
    src_times: np.ndarray, src_values: np.ndarray, n: int, max_gap_s: float = 0.025
) -> np.ndarray:
    grid = frame_times(n)
    out = np.full(n, np.nan)
    valid = np.isfinite(src_values)
    if valid.sum() == 0:
        return out
    st = src_times[valid]
    sv = src_values[valid]
    if st.size == 1:
        index = time_to_frame(float(st[0]))
        if 0 <= index < n:
            out[index] = sv[0]
        return out
    interpolated = np.interp(grid, st, sv, left=np.nan, right=np.nan)
    positions = np.searchsorted(st, grid)
    left_idx = np.clip(positions - 1, 0, st.size - 1)
    right_idx = np.clip(positions, 0, st.size - 1)
    gap = st[right_idx] - st[left_idx]
    near_left = np.abs(grid - st[left_idx])
    near_right = np.abs(st[right_idx] - grid)
    ok = (gap <= max_gap_s + 1e-9) | (np.minimum(near_left, near_right) <= HOP_S * 0.51)
    out[ok] = interpolated[ok]
    snap = ~ok & (np.minimum(near_left, near_right) <= HOP_S * 0.51)
    out[snap] = np.where(near_left[snap] <= near_right[snap], sv[left_idx[snap]], sv[right_idx[snap]])
    return out


def centered_frames(x: np.ndarray, center_samples: np.ndarray, length: int) -> np.ndarray:
    half = length // 2
    padded = np.pad(x, (half, length - half))
    index = center_samples[:, None] + np.arange(length)[None, :]
    index = np.clip(index, 0, padded.size - 1)
    return padded[index]


def moving_average(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values.astype(np.float64)
    valid = np.isfinite(values)
    filled = np.where(valid, values, 0.0)
    kernel = np.ones(width)
    sums = np.convolve(filled, kernel, mode="same")
    counts = np.convolve(valid.astype(np.float64), kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = sums / counts
    out[counts == 0] = np.nan
    return out


def nan_median_filter(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values.copy()
    half = width // 2
    padded = np.pad(values.astype(np.float64), half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out = np.nanmedian(windows, axis=1) if np.isnan(windows).any() else np.median(windows, axis=1)
    out[~np.isfinite(values)] = np.nan
    return out
