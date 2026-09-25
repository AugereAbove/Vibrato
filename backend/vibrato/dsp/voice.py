from __future__ import annotations

import numpy as np
import parselmouth
from scipy.ndimage import uniform_filter1d
from scipy.signal.windows import hann

from .framing import HOP_S, centered_frames, resample_track_to_grid

CPP_FRAME = 2048
CPP_TIME_SMOOTH = 7
CPP_QUEF_SMOOTH = 3
CPP_FMIN = 60.0
CPP_FMAX = 1000.0
CPP_CHUNK = 1500
HARMONICS = 10
HARMONIC_PERIODS = 4.0
HARMONIC_MIN_S = 0.02
HARMONIC_MAX_S = 0.08


def praat_hnr(x: np.ndarray, sr: int, n: int, floor_hz: float) -> np.ndarray:
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    harmonicity = snd.to_harmonicity_cc(
        time_step=HOP_S, minimum_pitch=max(50.0, floor_hz), silence_threshold=0.1, periods_per_window=1.0
    )
    values = np.asarray(harmonicity.values[0], dtype=np.float64)
    values[values < -150] = np.nan
    return resample_track_to_grid(np.asarray(harmonicity.xs()), values, n, max_gap_s=HOP_S * 1.01)


def cpp_track(x: np.ndarray, sr: int, n: int, f0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hop = round(HOP_S * sr)
    window = hann(CPP_FRAME, sym=False)
    q_lo = int(np.floor(sr / CPP_FMAX))
    q_hi = min(int(np.ceil(sr / CPP_FMIN)), CPP_FRAME // 2 - 2)
    quef = np.arange(q_lo, q_hi + 1) / sr
    design = np.stack([quef, np.ones_like(quef)], axis=1)
    pinv = np.linalg.pinv(design)
    raw = np.full(n, np.nan)
    smoothed = np.full(n, np.nan)
    margin = CPP_TIME_SMOOTH // 2
    x64 = x.astype(np.float64)
    for start in range(0, n, CPP_CHUNK):
        lo = max(0, start - margin)
        hi = min(n, start + CPP_CHUNK + margin)
        centers = np.arange(lo, hi) * hop
        frames = centered_frames(x64, centers, CPP_FRAME) * window
        spectrum = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        log_spec = 10.0 * np.log10(spectrum + 1e-12)
        ceps = np.fft.irfft(log_spec, n=CPP_FRAME, axis=1)[:, q_lo : q_hi + 1]
        ceps_db = 10.0 * np.log10(ceps**2 + 1e-12)
        time_smooth = uniform_filter1d(ceps_db, CPP_TIME_SMOOTH, axis=0, mode="nearest")
        both_smooth = uniform_filter1d(time_smooth, CPP_QUEF_SMOOTH, axis=1, mode="nearest")
        for source, target in ((ceps_db, raw), (both_smooth, smoothed)):
            coefficients = source @ pinv.T
            baseline = coefficients[:, 0:1] * quef[None, :] + coefficients[:, 1:2]
            prominence = source - baseline
            local_f0 = f0[lo:hi]
            peak = np.empty(prominence.shape[0])
            for row in range(prominence.shape[0]):
                if np.isfinite(local_f0[row]) and local_f0[row] > 0:
                    center = sr / local_f0[row] - q_lo
                    a = int(max(0, np.floor(center * 0.85)))
                    b = int(min(prominence.shape[1] - 1, np.ceil(center * 1.15)))
                    if b > a:
                        peak[row] = prominence[row, a : b + 1].max()
                        continue
                peak[row] = prominence[row].max()
            keep_from = start - lo
            keep_to = keep_from + min(CPP_CHUNK, n - start)
            target[start : start + (keep_to - keep_from)] = peak[keep_from:keep_to]
    return raw, smoothed


def harmonic_amplitudes(x: np.ndarray, sr: int, f0: np.ndarray, n_harmonics: int = HARMONICS) -> np.ndarray:
    n = len(f0)
    hop = round(HOP_S * sr)
    out = np.full((n, n_harmonics), np.nan)
    x64 = x.astype(np.float64)
    nyquist_guard = 0.45 * sr
    for index in np.flatnonzero(np.isfinite(f0)):
        frequency = f0[index]
        length = int(np.clip(HARMONIC_PERIODS * sr / frequency, HARMONIC_MIN_S * sr, HARMONIC_MAX_S * sr))
        center = index * hop
        start = center - length // 2
        if start < 0 or start + length > len(x64):
            continue
        segment = x64[start : start + length]
        window = hann(length, sym=False)
        weighted = segment * window
        orders = np.arange(1, n_harmonics + 1)
        valid = orders * frequency < nyquist_guard
        phase = np.exp(-2j * np.pi * np.outer(orders[valid] * frequency, np.arange(length)) / sr)
        amplitude = 2.0 * np.abs(phase @ weighted) / window.sum()
        out[index, : valid.sum()] = 20.0 * np.log10(amplitude + 1e-12)
    return out


def praat_perturbation(
    x: np.ndarray, sr: int, start_s: float, end_s: float, floor_hz: float, ceiling_hz: float
) -> dict[str, float | None]:
    lo = int(max(0, start_s * sr))
    hi = int(min(len(x), end_s * sr))
    if hi - lo < int(0.1 * sr):
        return {"jitter_local": None, "shimmer_local": None, "periods": 0}
    from parselmouth.praat import call

    snd = parselmouth.Sound(x[lo:hi].astype(np.float64), sampling_frequency=sr)
    try:
        points = call(
            snd, "To PointProcess (periodic, cc)", max(40.0, floor_hz * 0.8), min(1500.0, ceiling_hz * 1.2)
        )
        periods = int(call(points, "Get number of periods", 0, 0, 0.0001, 0.02, 1.3))
        if periods < 8:
            return {"jitter_local": None, "shimmer_local": None, "periods": periods}
        jitter = call(points, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = call([snd, points], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    except Exception:
        return {"jitter_local": None, "shimmer_local": None, "periods": 0}
    jitter_value = float(jitter) if np.isfinite(jitter) else None
    shimmer_value = float(shimmer) if np.isfinite(shimmer) else None
    return {"jitter_local": jitter_value, "shimmer_local": shimmer_value, "periods": periods}
