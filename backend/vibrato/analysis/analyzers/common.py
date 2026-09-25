from __future__ import annotations

import math
import warnings

import numpy as np


def finite(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return array[np.isfinite(array)]


def nan_mean(values: np.ndarray) -> float | None:
    data = finite(values)
    return float(np.mean(data)) if data.size else None


def nan_median(values: np.ndarray) -> float | None:
    data = finite(values)
    return float(np.median(data)) if data.size else None


def nan_std(values: np.ndarray) -> float | None:
    data = finite(values)
    return float(np.std(data)) if data.size >= 2 else None


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return None
    return float(np.sum(values[mask] * weights[mask]) / np.sum(weights[mask]))


def slope_per_second(values: np.ndarray, hop_s: float) -> float | None:
    values = np.asarray(values, dtype=np.float64)
    mask = np.isfinite(values)
    if mask.sum() < 4:
        return None
    t = np.arange(values.size)[mask] * hop_s
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        slope, _ = np.polyfit(t, values[mask], 1)
    return float(slope)


def fraction(mask: np.ndarray) -> float:
    return float(np.mean(mask)) if mask.size else 0.0


def safe_round(value: float | None, digits: int = 3) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def percentile_range(values: np.ndarray, low: float = 5, high: float = 95) -> float | None:
    data = finite(values)
    if data.size < 3:
        return None
    lo, hi = np.percentile(data, [low, high])
    return float(hi - lo)
