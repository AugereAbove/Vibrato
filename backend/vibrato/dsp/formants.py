from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import parselmouth
import soxr
from scipy.linalg import solve_toeplitz
from scipy.signal.windows import hamming

from .framing import HOP_S, centered_frames

CEILING_CANDIDATES = (4500.0, 5000.0, 5500.0, 6000.0, 6500.0)
N_TRACKED = 4
WINDOW_S = 0.025
LPC_ORDER = 10
LPC_MAX_BANDWIDTH = 700.0
LPC_MIN_FREQ = 90.0
AGREEMENT_TOLERANCE = 0.12
HIGH_F0_START = 280.0
HIGH_F0_END = 520.0
PRAAT_VERSION = "praat-burg-optceiling/1"
LPC_VERSION = "lpc-autocorrelation/1"


@dataclass
class FormantResult:
    frequencies: np.ndarray
    bandwidths: np.ndarray
    lpc_frequencies: np.ndarray
    agreement: np.ndarray
    confidence: np.ndarray
    ceiling_hz: float
    ceiling_scores: dict[float, float]
    high_f0_fraction: float


def praat_formants(snd: parselmouth.Sound, n: int, ceiling: float) -> tuple[np.ndarray, np.ndarray]:
    formant = snd.to_formant_burg(
        time_step=HOP_S,
        max_number_of_formants=5,
        maximum_formant=ceiling,
        window_length=WINDOW_S,
        pre_emphasis_from=50.0,
    )
    grid = np.arange(n) * HOP_S
    t0 = formant.xs()[0] if formant.n_frames else 0.0
    t1 = formant.xs()[-1] if formant.n_frames else 0.0
    frequencies = np.full((n, N_TRACKED), np.nan)
    bandwidths = np.full((n, N_TRACKED), np.nan)
    inside = (grid >= t0) & (grid <= t1)
    for index in np.flatnonzero(inside):
        t = float(grid[index])
        for k in range(N_TRACKED):
            frequencies[index, k] = formant.get_value_at_time(k + 1, t)
            bandwidths[index, k] = formant.get_bandwidth_at_time(k + 1, t)
    return frequencies, bandwidths


def _stability_score(frequencies: np.ndarray, mask: np.ndarray) -> float:
    if mask.sum() < 10:
        return float("inf")
    f1 = frequencies[mask, 0]
    f2 = frequencies[mask, 1]
    missing = np.mean(~np.isfinite(f1)) + np.mean(~np.isfinite(f2))
    with np.errstate(invalid="ignore", divide="ignore"):
        d1 = np.abs(np.diff(np.log(f1)))
        d2 = np.abs(np.diff(np.log(f2)))
    jitter = (
        float(np.nanmedian(d1) + np.nanmedian(d2)) if np.isfinite(d1).any() and np.isfinite(d2).any() else 1.0
    )
    implausible = float(np.mean(np.nan_to_num(f1, nan=0) < 150) + np.mean(np.nan_to_num(f2, nan=0) < 450))
    return jitter + 0.5 * missing + 0.5 * implausible


def lpc_formants(x: np.ndarray, sr: int, n: int, ceiling: float) -> tuple[np.ndarray, np.ndarray]:
    target_sr = round(2 * ceiling)
    y = soxr.resample(x.astype(np.float64), sr, target_sr)
    alpha = float(np.exp(-2.0 * np.pi * 50.0 / target_sr))
    y = np.concatenate([[y[0]], y[1:] - alpha * y[:-1]])
    length = round(WINDOW_S * target_sr)
    window = hamming(length, sym=False)
    centers = np.round(np.arange(n) * HOP_S * target_sr).astype(int)
    frequencies = np.full((n, N_TRACKED), np.nan)
    bandwidths = np.full((n, N_TRACKED), np.nan)
    chunk = 4000
    for start in range(0, n, chunk):
        frames = centered_frames(y, centers[start : start + chunk], length) * window
        spectrum = np.fft.rfft(frames, 2 * length, axis=1)
        autocorr = np.fft.irfft(np.abs(spectrum) ** 2, axis=1)[:, : LPC_ORDER + 1]
        energy = autocorr[:, 0]
        for row in range(frames.shape[0]):
            if energy[row] <= 1e-10:
                continue
            r = autocorr[row].copy()
            r[0] *= 1.0 + 1e-9
            try:
                coefficients = solve_toeplitz(r[:LPC_ORDER], r[1 : LPC_ORDER + 1])
            except np.linalg.LinAlgError:
                continue
            roots = np.roots(np.concatenate([[1.0], -coefficients]))
            roots = roots[np.imag(roots) > 0]
            freqs = np.angle(roots) * target_sr / (2 * np.pi)
            bws = -target_sr / np.pi * np.log(np.maximum(np.abs(roots), 1e-12))
            keep = (freqs > LPC_MIN_FREQ) & (bws < LPC_MAX_BANDWIDTH) & (freqs < ceiling - 50)
            order = np.argsort(freqs[keep])
            chosen_f = freqs[keep][order][:N_TRACKED]
            chosen_b = bws[keep][order][:N_TRACKED]
            frequencies[start + row, : len(chosen_f)] = chosen_f
            bandwidths[start + row, : len(chosen_b)] = chosen_b
    return frequencies, bandwidths


def formant_confidence(
    frequencies: np.ndarray,
    bandwidths: np.ndarray,
    agreement: np.ndarray,
    voiced: np.ndarray,
    f0: np.ndarray,
    level_rel_db: np.ndarray,
) -> np.ndarray:
    high_f0_penalty = np.ones(len(f0))
    with np.errstate(invalid="ignore"):
        ramp = (f0 - HIGH_F0_START) / (HIGH_F0_END - HIGH_F0_START)
    high_f0_penalty = np.where(np.isfinite(ramp), 1.0 - 0.8 * np.clip(ramp, 0.0, 1.0), 1.0)
    bw_ok = np.clip(1.0 - (np.nan_to_num(bandwidths[:, 1], nan=1000.0) - 250.0) / 600.0, 0.2, 1.0)
    level_ok = np.clip((level_rel_db + 30.0) / 20.0, 0.0, 1.0)
    present = np.isfinite(frequencies[:, 0]) & np.isfinite(frequencies[:, 1])
    agreement_factor = 0.55 + 0.45 * np.nan_to_num(agreement, nan=0.0)
    confidence = high_f0_penalty * bw_ok * level_ok * agreement_factor
    confidence[~(voiced & present)] = 0.0
    return np.clip(confidence, 0.0, 1.0)


def analyze_formants(
    x: np.ndarray,
    sr: int,
    n: int,
    voiced: np.ndarray,
    f0: np.ndarray,
    level_rel_db: np.ndarray,
    ceiling_hint: float | None = None,
) -> FormantResult:
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    stable_mask = voiced & (level_rel_db > -20.0)
    scores: dict[float, float] = {}
    candidates = (ceiling_hint,) if ceiling_hint else CEILING_CANDIDATES
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for ceiling in candidates:
        if ceiling is None:
            continue
        frequencies, bandwidths = praat_formants(snd, n, float(ceiling))
        score = _stability_score(frequencies, stable_mask)
        scores[float(ceiling)] = round(score, 5) if np.isfinite(score) else float("nan")
        if best is None or score < _stability_score(best[1], stable_mask):
            best = (float(ceiling), frequencies, bandwidths)
    assert best is not None
    ceiling, frequencies, bandwidths = best
    lpc_f, _ = lpc_formants(x, sr, n, ceiling)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = np.abs(lpc_f[:, :2] - frequencies[:, :2]) / frequencies[:, :2]
    agree = np.where(np.isfinite(rel), (rel <= AGREEMENT_TOLERANCE).astype(np.float64), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        agreement = np.nanmean(agree, axis=1) if agree.size else np.full(n, np.nan)
    frequencies[~voiced] = np.nan
    bandwidths[~voiced] = np.nan
    confidence = formant_confidence(frequencies, bandwidths, agreement, voiced, f0, level_rel_db)
    voiced_f0 = f0[voiced & np.isfinite(f0)]
    high_fraction = float(np.mean(voiced_f0 > HIGH_F0_START)) if voiced_f0.size else 0.0
    return FormantResult(
        frequencies=frequencies,
        bandwidths=bandwidths,
        lpc_frequencies=lpc_f,
        agreement=agreement,
        confidence=confidence,
        ceiling_hz=ceiling,
        ceiling_scores=scores,
        high_f0_fraction=high_fraction,
    )
