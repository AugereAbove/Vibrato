from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soxr
from scipy import signal

from .decode import DecodedAudio

CANONICAL_SR = 44100
CANONICAL_VERSION = 1
HIGHPASS_HZ = 20.0
ANTIPHASE_CORRELATION = -0.3
SILENT_CHANNEL_RATIO = 1e-4


@dataclass
class CanonicalAudio:
    samples: np.ndarray
    sample_rate: int
    mixdown: str
    notes: list[str]

    @property
    def duration_s(self) -> float:
        return float(self.samples.shape[0]) / float(self.sample_rate)


def mixdown(samples: np.ndarray) -> tuple[np.ndarray, str, list[str]]:
    notes: list[str] = []
    if samples.shape[0] == 1:
        return samples[0].astype(np.float64), "mono source", notes
    energies = np.mean(samples.astype(np.float64) ** 2, axis=1)
    loudest = int(np.argmax(energies))
    if energies.max() <= 0:
        return samples[0].astype(np.float64), "silent source", notes
    active = energies > energies.max() * SILENT_CHANNEL_RATIO
    if active.sum() == 1:
        notes.append(f"Only channel {loudest + 1} contains signal; it was used on its own.")
        return samples[loudest].astype(np.float64), f"channel {loudest + 1} only", notes
    if samples.shape[0] == 2:
        left = samples[0].astype(np.float64)
        right = samples[1].astype(np.float64)
        denom = np.sqrt(np.sum(left**2) * np.sum(right**2))
        correlation = float(np.sum(left * right) / denom) if denom > 0 else 0.0
        if correlation < ANTIPHASE_CORRELATION:
            notes.append(
                "The stereo channels are largely out of phase, so averaging them would cancel the voice; "
                f"channel {loudest + 1} was used instead."
            )
            return samples[loudest].astype(np.float64), f"channel {loudest + 1} (anti-phase source)", notes
    return samples.astype(np.float64).mean(axis=0), f"average of {samples.shape[0]} channels", notes


def canonicalize(decoded: DecodedAudio) -> CanonicalAudio:
    mono, mode, notes = mixdown(decoded.samples)
    if decoded.sample_rate != CANONICAL_SR:
        mono = soxr.resample(mono, decoded.sample_rate, CANONICAL_SR, quality="HQ")
        notes.append(f"Resampled from {decoded.sample_rate} Hz to {CANONICAL_SR} Hz for analysis.")
    if mono.shape[0] > 64:
        sos = signal.butter(2, HIGHPASS_HZ, btype="highpass", fs=CANONICAL_SR, output="sos")
        mono = signal.sosfiltfilt(sos, mono)
    return CanonicalAudio(
        samples=mono.astype(np.float32), sample_rate=CANONICAL_SR, mixdown=mode, notes=notes
    )
