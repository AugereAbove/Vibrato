from __future__ import annotations

import math

import numpy as np
from scipy import signal

ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
BLOCK_S = 0.4
BLOCK_OVERLAP = 0.75
LOUDNESS_OFFSET = -0.691


def k_weighting_coefficients(sample_rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    f0 = 1681.974450955533
    gain_db = 3.999843853973347
    q = 0.7071752369554196
    k = math.tan(math.pi * f0 / sample_rate)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh**0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf_b = np.array(
        [(vh + vb * k / q + k * k) / a0, 2.0 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]
    )
    shelf_a = np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0])
    f0 = 38.13547087602444
    q = 0.5003270373238773
    k = math.tan(math.pi * f0 / sample_rate)
    denom = 1.0 + k / q + k * k
    hp_b = np.array([1.0, -2.0, 1.0])
    hp_a = np.array([1.0, 2.0 * (k * k - 1.0) / denom, (1.0 - k / q + k * k) / denom])
    return shelf_b, shelf_a, hp_b, hp_a


def k_weight(x: np.ndarray, sample_rate: int) -> np.ndarray:
    shelf_b, shelf_a, hp_b, hp_a = k_weighting_coefficients(sample_rate)
    y = signal.lfilter(shelf_b, shelf_a, x.astype(np.float64))
    return signal.lfilter(hp_b, hp_a, y)


def integrated_loudness(x: np.ndarray, sample_rate: int) -> float | None:
    if x.ndim == 1:
        x = x[np.newaxis, :]
    block = round(BLOCK_S * sample_rate)
    step = round(block * (1.0 - BLOCK_OVERLAP))
    if x.shape[1] < block:
        return None
    weighted = np.stack([k_weight(channel, sample_rate) for channel in x])
    starts = np.arange(0, x.shape[1] - block + 1, step)
    power = np.zeros(len(starts))
    squared = weighted**2
    cumulative = np.concatenate([np.zeros((squared.shape[0], 1)), np.cumsum(squared, axis=1)], axis=1)
    for channel in range(squared.shape[0]):
        power += (cumulative[channel, starts + block] - cumulative[channel, starts]) / block
    with np.errstate(divide="ignore"):
        block_loudness = LOUDNESS_OFFSET + 10.0 * np.log10(power)
    above_abs = power[block_loudness > ABSOLUTE_GATE_LUFS]
    if above_abs.size == 0:
        return None
    relative_gate = LOUDNESS_OFFSET + 10.0 * math.log10(float(np.mean(above_abs))) + RELATIVE_GATE_LU
    gated = power[(block_loudness > ABSOLUTE_GATE_LUFS) & (block_loudness > relative_gate)]
    if gated.size == 0:
        return None
    return LOUDNESS_OFFSET + 10.0 * math.log10(float(np.mean(gated)))


def short_window_loudness_db(
    x: np.ndarray, sample_rate: int, hop_s: float, window_s: float = 0.1
) -> np.ndarray:
    weighted = k_weight(x, sample_rate) ** 2
    window = max(1, round(window_s * sample_rate))
    hop = round(hop_s * sample_rate)
    n_frames = int(len(x) // hop) + 1
    cumulative = np.concatenate([[0.0], np.cumsum(weighted)])
    centers = np.arange(n_frames) * hop
    lo = np.clip(centers - window // 2, 0, len(x))
    hi = np.clip(centers + window // 2, 0, len(x))
    span = np.maximum(hi - lo, 1)
    mean_square = (cumulative[hi] - cumulative[lo]) / span
    with np.errstate(divide="ignore"):
        return (LOUDNESS_OFFSET + 10.0 * np.log10(np.maximum(mean_square, 1e-12))).astype(np.float32)
