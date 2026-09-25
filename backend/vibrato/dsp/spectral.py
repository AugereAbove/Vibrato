from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from ..audio.loudness import short_window_loudness_db
from .framing import HOP_S

N_FFT = 2048
N_MELS = 64
N_MFCC = 20
INTENSITY_WINDOW_S = 0.03
THIRD_OCTAVE_CENTERS = np.array(
    [
        100,
        125,
        160,
        200,
        250,
        315,
        400,
        500,
        630,
        800,
        1000,
        1250,
        1600,
        2000,
        2500,
        3150,
        4000,
        5000,
        6300,
        8000,
        10000,
        12500,
    ],
    dtype=np.float64,
)
TILT_BAND_RANGE = (125.0, 5000.0)
EPS = 1e-12


@dataclass
class SpectralFeatures:
    tracks: dict[str, np.ndarray]
    mfcc: np.ndarray
    band_levels: np.ndarray
    band_centers: np.ndarray


def _fit_length(matrix: np.ndarray, n: int) -> np.ndarray:
    if matrix.shape[-1] >= n:
        return matrix[..., :n]
    pad = [(0, 0)] * (matrix.ndim - 1) + [(0, n - matrix.shape[-1])]
    return np.pad(matrix, pad, mode="edge")


def power_spectrogram(x: np.ndarray, sr: int, n: int, n_fft: int = N_FFT) -> tuple[np.ndarray, np.ndarray]:
    hop = round(HOP_S * sr)
    spec = librosa.stft(x.astype(np.float32), n_fft=n_fft, hop_length=hop, window="hann", center=True)
    power = (np.abs(spec) ** 2).astype(np.float64)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    return freqs, _fit_length(power, n)


def intensity_db(x: np.ndarray, sr: int, n: int, window_s: float = INTENSITY_WINDOW_S) -> np.ndarray:
    hop = round(HOP_S * sr)
    window = max(1, round(window_s * sr))
    squared = x.astype(np.float64) ** 2
    cumulative = np.concatenate([[0.0], np.cumsum(squared)])
    centers = np.arange(n) * hop
    lo = np.clip(centers - window // 2, 0, len(x))
    hi = np.clip(centers + window // 2, 0, len(x))
    mean_square = (cumulative[hi] - cumulative[lo]) / np.maximum(hi - lo, 1)
    return (10.0 * np.log10(np.maximum(mean_square, 1e-12))).astype(np.float64)


def band_levels_db(
    power: np.ndarray, freqs: np.ndarray, centers: np.ndarray = THIRD_OCTAVE_CENTERS
) -> np.ndarray:
    levels = np.full((len(centers), power.shape[1]), np.nan)
    factor = 2.0 ** (1.0 / 6.0)
    for index, center in enumerate(centers):
        mask = (freqs >= center / factor) & (freqs < center * factor)
        if mask.any():
            levels[index] = 10.0 * np.log10(power[mask].sum(axis=0) + EPS)
    return levels


def _band_energy(power: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs < hi)
    return power[mask].sum(axis=0) + EPS


def _band_max_db(power_db: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs < hi)
    return power_db[mask].max(axis=0)


def compute_spectral(x: np.ndarray, sr: int, n: int) -> SpectralFeatures:
    freqs, power = power_spectrogram(x, sr, n)
    total = power.sum(axis=0) + EPS
    power_db = 10.0 * np.log10(power + EPS)
    centroid = (freqs[:, None] * power).sum(axis=0) / total
    cumulative = np.cumsum(power, axis=0)
    rolloff_index = np.argmax(cumulative >= 0.85 * cumulative[-1][None, :], axis=0)
    rolloff = freqs[rolloff_index]
    flat_band = (freqs >= 100) & (freqs <= 10000)
    band_power = power[flat_band] + EPS
    flatness = np.exp(np.mean(np.log(band_power), axis=0)) / np.mean(band_power, axis=0)
    low = _band_energy(power, freqs, 50, 1000)
    mid = _band_energy(power, freqs, 1000, 5000)
    alpha_ratio = 10.0 * np.log10(mid / low)
    hammarberg = _band_max_db(power_db, freqs, 0, 2000) - _band_max_db(power_db, freqs, 2000, 5000)
    singing_power_ratio = _band_max_db(power_db, freqs, 2000, 4000) - _band_max_db(power_db, freqs, 0, 2000)
    high_ratio = 10.0 * np.log10(_band_energy(power, freqs, 4000, 20000) / total)
    sibilance_ratio = 10.0 * np.log10(
        _band_energy(power, freqs, 4000, 11000) / _band_energy(power, freqs, 100, 4000)
    )
    sub_bass_ratio = 10.0 * np.log10(
        _band_energy(power, freqs, 20, 90) / _band_energy(power, freqs, 90, 5000)
    )
    bands = band_levels_db(power, freqs)
    tilt_mask = (TILT_BAND_RANGE[0] <= THIRD_OCTAVE_CENTERS) & (TILT_BAND_RANGE[1] >= THIRD_OCTAVE_CENTERS)
    octave_axis = np.log2(THIRD_OCTAVE_CENTERS[tilt_mask])
    centered_axis = octave_axis - octave_axis.mean()
    tilt = (centered_axis[:, None] * (bands[tilt_mask] - bands[tilt_mask].mean(axis=0))).sum(axis=0) / np.sum(
        centered_axis**2
    )
    mel = librosa.feature.melspectrogram(S=power, sr=sr, n_mels=N_MELS, fmin=50, fmax=min(12000, sr / 2))
    mel_db = librosa.power_to_db(mel, ref=1.0, amin=1e-10)
    mfcc = librosa.feature.mfcc(S=mel_db, n_mfcc=N_MFCC)
    flux = librosa.onset.onset_strength(S=mel_db, sr=sr, hop_length=round(HOP_S * sr), lag=1, max_size=3)
    flux = _fit_length(flux[None, :], n)[0]
    zcr = librosa.feature.zero_crossing_rate(
        x.astype(np.float32), frame_length=1024, hop_length=round(HOP_S * sr), center=True
    )[0]
    zcr = _fit_length(zcr[None, :], n)[0]
    tracks = {
        "centroid_hz": centroid,
        "rolloff_hz": rolloff.astype(np.float64),
        "flatness": flatness,
        "alpha_ratio_db": alpha_ratio,
        "hammarberg_db": hammarberg,
        "spr_db": singing_power_ratio,
        "high_ratio_db": high_ratio,
        "sibilance_ratio_db": sibilance_ratio,
        "sub_bass_ratio_db": sub_bass_ratio,
        "tilt_db_oct": tilt,
        "flux": flux.astype(np.float64),
        "zcr": zcr.astype(np.float64),
        "loudness_db": short_window_loudness_db(x, sr, HOP_S)[:n].astype(np.float64),
    }
    if len(tracks["loudness_db"]) < n:
        tracks["loudness_db"] = np.pad(
            tracks["loudness_db"], (0, n - len(tracks["loudness_db"])), mode="edge"
        )
    return SpectralFeatures(
        tracks=tracks,
        mfcc=mfcc.astype(np.float32),
        band_levels=bands.astype(np.float32),
        band_centers=THIRD_OCTAVE_CENTERS,
    )


def display_spectrogram(
    x: np.ndarray, sr: int, max_freq: float, n_bins: int, hop_s: float, n_fft: int
) -> tuple[np.ndarray, np.ndarray]:
    hop = max(1, round(hop_s * sr))
    spec = (
        np.abs(librosa.stft(x.astype(np.float32), n_fft=n_fft, hop_length=hop, window="hann", center=True))
        ** 2
    )
    bin_hz = sr / n_fft
    target = np.geomspace(40.0, min(max_freq, sr / 2 - bin_hz), n_bins)
    edges = np.concatenate([[target[0] / 1.02], np.sqrt(target[:-1] * target[1:]), [target[-1] * 1.02]])
    lo = np.floor(edges[:-1] / bin_hz).astype(int)
    hi = np.ceil(edges[1:] / bin_hz).astype(int)
    cumulative = np.concatenate([np.zeros((1, spec.shape[1])), np.cumsum(spec, axis=0)], axis=0)
    wide = hi - lo >= 2
    out = np.empty((n_bins, spec.shape[1]), dtype=np.float64)
    out[wide] = (cumulative[hi[wide]] - cumulative[lo[wide]]) / (hi[wide] - lo[wide])[:, None]
    position = target[~wide] / bin_hz
    base = np.clip(np.floor(position).astype(int), 0, spec.shape[0] - 2)
    weight = (position - base)[:, None]
    out[~wide] = spec[base] * (1.0 - weight) + spec[base + 1] * weight
    return target, 10.0 * np.log10(out + 1e-12)
