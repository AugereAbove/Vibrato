from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from scipy import signal

from ...dsp.framing import fill_short_gaps, remove_short_runs, runs
from ...dsp.music import hz_to_midi
from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from ..segmentation.notes import pitch_trend
from .common import nan_mean

MIN_NOTE_S = 0.4
BAND_HZ = (3.0, 10.0)
WINDOW_FRAMES = 36
RATE_RANGE_HZ = (3.5, 9.0)
PERIODICITY_MIN = 0.45
EXTENT_MIN_CENTS = 12.0
MIN_REGION_FRAMES = 20
GAP_FILL_FRAMES = 8
ATTACK_LEVEL = 0.8
ONSET_ENVELOPE_LEVEL = 0.3
EDGE_GUARD_FRAMES = 5


def band_limited_oscillation(cents: np.ndarray, hop_s: float) -> tuple[np.ndarray, np.ndarray]:
    trend = pitch_trend(cents / 100.0, hop_s) * 100.0
    osc = cents - trend
    if osc.size < 16:
        return osc, osc
    sos = signal.butter(2, BAND_HZ, btype="bandpass", fs=1.0 / hop_s, output="sos")
    bp = signal.sosfiltfilt(sos, osc, padlen=min(osc.size - 1, 30))
    return osc, bp


def local_vibrato(bp: np.ndarray, hop_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = bp.size
    half = WINDOW_FRAMES // 2
    lag_lo = int(np.floor(1.0 / (RATE_RANGE_HZ[1] * hop_s)))
    lag_hi = int(np.ceil(1.0 / (RATE_RANGE_HZ[0] * hop_s)))
    periodicity = np.zeros(n)
    amplitude = np.zeros(n)
    rate = np.full(n, np.nan)
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half)
        segment = bp[a:b]
        if segment.size < lag_hi + 4:
            continue
        segment = segment - segment.mean()
        energy = float(np.dot(segment, segment))
        if energy <= 1e-9:
            continue
        ac = np.correlate(segment, segment, mode="full")[segment.size - 1 :]
        ac = ac / energy
        hi = min(lag_hi, ac.size - 1)
        if hi <= lag_lo:
            continue
        lag = lag_lo + int(np.argmax(ac[lag_lo : hi + 1]))
        periodicity[i] = float(ac[lag]) * segment.size / max(1, segment.size - lag)
        amplitude[i] = float(np.sqrt(2.0) * np.std(segment))
        rate[i] = 1.0 / (lag * hop_s)
    return np.clip(periodicity, 0.0, 1.0), amplitude, rate


def refine_onset(bp: np.ndarray, start: int, end: int) -> int:
    if end - start < 4 or bp.size < 8:
        return start
    envelope = np.abs(signal.hilbert(bp))
    reference = float(np.median(envelope[start:end]))
    if reference <= 0:
        return start
    floor = min(start, EDGE_GUARD_FRAMES)
    position = start
    while position > floor and envelope[position - 1] >= ONSET_ENVELOPE_LEVEL * reference:
        position -= 1
    return position


def measure_region(
    osc: np.ndarray, bp: np.ndarray, start: int, end: int, hop_s: float
) -> dict[str, float | None]:
    region = bp[start:end]
    distance = max(3, int(0.8 / (RATE_RANGE_HZ[1] * hop_s)))
    peaks, _ = signal.find_peaks(region, distance=distance)
    troughs, _ = signal.find_peaks(-region, distance=distance)
    extrema = sorted([(int(p), 1) for p in peaks] + [(int(t), -1) for t in troughs])
    cleaned: list[tuple[int, int]] = []
    for position, kind in extrema:
        if cleaned and cleaned[-1][1] == kind:
            previous = cleaned[-1]
            if kind * region[position] > kind * region[previous[0]]:
                cleaned[-1] = (position, kind)
            continue
        cleaned.append((position, kind))
    values: dict[str, float | None] = {"cycles": 0.0}
    if len(cleaned) < 3:
        return values
    positions = np.array([c[0] for c in cleaned], dtype=np.float64)
    refined = []
    for position, kind in cleaned:
        lo = max(0, position - 2)
        hi = min(region.size, position + 3)
        window = osc[start + lo : start + hi]
        refined.append(float(window.max() if kind == 1 else window.min()))
    refined_arr = np.array(refined)
    half_periods = np.diff(positions) * hop_s
    half_extents = np.abs(np.diff(refined_arr)) / 2.0
    periods = half_periods[:-1] + half_periods[1:] if half_periods.size >= 2 else half_periods * 2
    rates = 1.0 / np.maximum(periods, 1e-3)
    rate_times = positions[1:-1] if periods.size == half_periods.size - 1 else positions[:-1]
    kinds = np.array([c[1] for c in cleaned])
    rises = []
    for i in range(len(cleaned) - 2):
        if kinds[i] == -1 and kinds[i + 1] == 1 and kinds[i + 2] == -1:
            rise = positions[i + 1] - positions[i]
            fall = positions[i + 2] - positions[i + 1]
            if rise + fall > 0:
                rises.append(rise / (rise + fall))
    envelope = np.abs(signal.hilbert(region)) if region.size > 8 else np.abs(region)
    target = ATTACK_LEVEL * np.median(half_extents) if half_extents.size else 0.0
    reach = np.flatnonzero(envelope >= target)
    values.update(
        {
            "cycles": float(len(cleaned) - 1) / 2.0,
            "rate_hz": float(np.median(rates)),
            "rate_std_hz": float(np.std(rates)) if rates.size > 1 else 0.0,
            "extent_cents": float(np.median(half_extents)),
            "extent_std_cents": float(np.std(half_extents)) if half_extents.size > 1 else 0.0,
            "rate_drift_hz_per_s": slope_from(rate_times * hop_s, rates),
            "extent_drift_cents_per_s": slope_from(positions[1:] * hop_s, half_extents),
            "symmetry": float(np.mean(rises)) if rises else None,
            "attack_ms": float(reach[0] * hop_s * 1000.0) if reach.size else None,
        }
    )
    cv_period = (
        float(np.std(periods) / np.mean(periods)) if periods.size > 1 and np.mean(periods) > 0 else 0.0
    )
    cv_extent = (
        float(np.std(half_extents) / np.mean(half_extents))
        if half_extents.size > 1 and np.mean(half_extents) > 0
        else 0.0
    )
    values["regularity"] = float(np.clip(1.0 - (cv_period + cv_extent) / 2.0, 0.0, 1.0))
    return values


def slope_from(times: np.ndarray, values: np.ndarray) -> float | None:
    if times.size < 3 or values.size != times.size:
        n = min(times.size, values.size)
        if n < 3:
            return None
        times = times[:n]
        values = values[:n]
    slope, _ = np.polyfit(times, values, 1)
    return float(slope)


@register
class VibratoAnalyzer(Analyzer):
    id = "vibrato"
    version = "1.1.0"
    category = "vibrato"
    label = "Vibrato"
    description = (
        "Presence, onset, rate, extent, regularity, drift, symmetry and attack of vibrato on sustained notes."
    )
    dependencies = ("f0_hz", "f0_conf")
    supported_segment_types = ("note", "recording")
    method = (
        "The note's F0 (cents) is detrended with a 2.5 Hz zero-phase low-pass and band-limited to 3-10 Hz. A sliding "
        "0.36 s autocorrelation finds periodic oscillation in the 3.5-9 Hz range; vibrato is present where periodicity "
        "exceeds 0.45 and the oscillation exceeds ±12 cents. Rate and extent come from successive peaks and troughs: "
        "extent is half the peak-to-trough distance (±cents)."
    )
    assumptions = (
        "Extent is reported as ± cents (half of peak-to-trough).",
        "Only notes of at least 0.4 s are assessed.",
    )
    limitations = (
        "Very slow (< 3.5 Hz) or very fast (> 9 Hz) oscillations are not classified as vibrato.",
        "Tremolo (loudness vibrato) is not measured here; see dynamics.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "band_hz": BAND_HZ,
        "window_s": WINDOW_FRAMES * 0.01,
        "periodicity_min": PERIODICITY_MIN,
        "extent_min_cents": EXTENT_MIN_CENTS,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        f0 = fs.tracks["f0_hz"]
        conf = fs.tracks["f0_conf"]
        results: list[AnalysisResult] = []
        rates: list[float] = []
        extents: list[float] = []
        onsets: list[float] = []
        for note in ctx.hierarchy.by_level("note"):
            if note.duration_s < MIN_NOTE_S:
                continue
            span = ctx.span(note)
            midi = hz_to_midi(f0[span])
            valid = np.isfinite(midi)
            builder = self.builder(note)
            ctx.apply_quality(builder, "vibrato")
            if valid.sum() < 20:
                builder.flag("too_few_voiced_frames")
                results.append(builder.factor(0.2, "too few voiced frames").build())
                continue
            cents = np.interp(np.arange(midi.size), np.flatnonzero(valid), midi[valid]) * 100.0
            osc, bp = band_limited_oscillation(cents, fs.hop_s)
            periodicity, amplitude, _ = local_vibrato(bp, fs.hop_s)
            present = (periodicity >= PERIODICITY_MIN) & (amplitude >= EXTENT_MIN_CENTS) & valid
            present = fill_short_gaps(present, GAP_FILL_FRAMES)
            present = remove_short_runs(present, MIN_REGION_FRAMES)
            regions = runs(present)
            mean_conf = nan_mean(conf[span][valid]) or 0.0
            builder.factor(0.3 + 0.7 * mean_conf, "F0 tracking confidence")
            if not regions:
                builder.add("present", False, "")
                builder.add("straight_tone_s", note.duration_s, "s")
                builder.add("coverage", 0.0, "ratio")
                builder.add(
                    "max_periodicity",
                    float(periodicity.max()) if periodicity.size else 0.0,
                    "ratio",
                    Basis.DERIVED,
                )
                builder.add(
                    "max_oscillation_cents",
                    float(amplitude.max()) if amplitude.size else 0.0,
                    "cents",
                    Basis.DERIVED,
                )
                results.append(builder.build())
                continue
            start, end = max(regions, key=lambda r: r[1] - r[0])
            start = refine_onset(bp, start, end)
            measured = measure_region(osc, bp, start, end, fs.hop_s)
            onset_s = start * fs.hop_s
            builder.add("present", True, "")
            builder.add("onset_s", onset_s, "s")
            builder.add("straight_tone_s", onset_s, "s")
            builder.add("offset_before_end_s", (midi.size - end) * fs.hop_s, "s")
            builder.add("duration_s", (end - start) * fs.hop_s, "s")
            builder.add("coverage", (end - start) / midi.size, "ratio", Basis.DERIVED)
            for key, unit, basis in (
                ("rate_hz", "Hz", Basis.MEASURED),
                ("extent_cents", "cents (±)", Basis.MEASURED),
                ("rate_std_hz", "Hz", Basis.DERIVED),
                ("extent_std_cents", "cents", Basis.DERIVED),
                ("rate_drift_hz_per_s", "Hz/s", Basis.DERIVED),
                ("extent_drift_cents_per_s", "cents/s", Basis.DERIVED),
                ("regularity", "ratio", Basis.DERIVED),
                ("symmetry", "ratio", Basis.DERIVED),
                ("attack_ms", "ms", Basis.DERIVED),
                ("cycles", "count", Basis.MEASURED),
            ):
                builder.add(key, measured.get(key), unit, basis)
            attack = measured.get("attack_ms")
            if attack is not None:
                builder.add(
                    "attack_character",
                    "gradual" if attack > 250 else ("quick" if attack < 120 else "moderate"),
                    "",
                    Basis.DERIVED,
                )
            periodic = float(np.mean(periodicity[start:end]))
            builder.add("periodicity", periodic, "ratio", Basis.DERIVED)
            builder.factor(0.4 + 0.6 * periodic, "vibrato periodicity")
            cycles = measured.get("cycles") or 0.0
            if cycles < 3:
                builder.factor(0.4 + 0.2 * cycles, "fewer than three vibrato cycles")
                builder.flag("few_cycles")
            result = builder.build()
            results.append(result)
            measured_rate = measured.get("rate_hz")
            if measured_rate is not None:
                rates.append(float(measured_rate))
                extents.append(float(measured["extent_cents"] or 0.0))
                onsets.append(onset_s)
                ctx.hierarchy.add_event(
                    "vibrato",
                    note.start_s + onset_s,
                    note.start_s + end * fs.hop_s,
                    result.confidence,
                    note.id,
                    rate_hz=round(float(measured_rate), 3),
                    extent_cents=round(float(measured["extent_cents"] or 0.0), 1),
                )
        summary = self.builder(None, 0.0, fs.duration_s)
        summary.add("notes_with_vibrato", len(rates), "count")
        summary.add("median_rate_hz", float(np.median(rates)) if rates else None, "Hz")
        summary.add("median_extent_cents", float(np.median(extents)) if extents else None, "cents (±)")
        summary.add("median_onset_s", float(np.median(onsets)) if onsets else None, "s")
        summary.add(
            "rate_iqr_hz",
            float(np.subtract(*np.percentile(rates, [75, 25]))) if len(rates) >= 3 else None,
            "Hz",
            Basis.DERIVED,
        )
        summary.factor(min(1.0, 0.3 + 0.2 * len(rates)), "number of vibrato notes")
        results.append(summary.build())
        return results
