from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from scipy import signal

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .common import nan_mean, percentile_range, slope_per_second

CRESCENDO_DB = 2.5
ATTACK_WINDOW_S = 0.12
RELEASE_WINDOW_S = 0.15
TREMOLO_BAND_HZ = (3.5, 9.0)


def phrase_shape(values: np.ndarray) -> str:
    finite = values[np.isfinite(values)]
    if finite.size < 9:
        return "short"
    thirds = np.array_split(finite, 3)
    a, b, c = (float(np.mean(t)) for t in thirds)
    if c - a >= CRESCENDO_DB and b <= c:
        return "crescendo"
    if a - c >= CRESCENDO_DB and b <= a:
        return "decrescendo"
    if b - max(a, c) >= 1.5:
        return "arch"
    if min(a, c) - b >= 1.5:
        return "dip"
    return "level"


@register
class DynamicsAnalyzer(Analyzer):
    id = "dynamics"
    version = "1.0.0"
    category = "dynamics"
    label = "Dynamics"
    description = "Phrase loudness, range and shape; note emphasis, attack rise, release decay, crescendo/decrescendo and loudness modulation."
    dependencies = ("loudness_db", "level_rel_db")
    supported_segment_types = ("note", "phrase", "recording")
    method = (
        "Loudness is K-weighted (ITU-R BS.1770 filter) power in a 100 ms window every 10 ms, expressed relative to the "
        "recording's typical singing level (90th percentile of voiced frames), so comparisons are independent of "
        "recording gain. Crescendo/decrescendo requires at least 2.5 dB change between the first and last third."
    )
    assumptions = (
        "Microphone distance changes look like dynamics; keep a constant distance while recording.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "crescendo_db": CRESCENDO_DB,
        "attack_window_s": ATTACK_WINDOW_S,
        "release_window_s": RELEASE_WINDOW_S,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        loud = fs.tracks["loudness_db"]
        voiced = fs.voiced
        reference = (
            float(np.percentile(loud[voiced], 90)) if voiced.sum() >= 10 else float(np.percentile(loud, 95))
        )
        rel = loud - reference
        results: list[AnalysisResult] = []
        phrase_means: dict[str, float] = {}
        for phrase in ctx.hierarchy.by_level("phrase"):
            span = ctx.span(phrase)
            values = np.where(voiced[span], rel[span], np.nan)
            builder = self.builder(phrase)
            ctx.apply_quality(builder, "dynamics")
            mean = nan_mean(values)
            if mean is not None:
                phrase_means[phrase.id] = mean
            builder.add("mean_db", mean, "dB re singing level")
            builder.add(
                "peak_db",
                float(np.nanmax(values)) if np.isfinite(values).any() else None,
                "dB re singing level",
            )
            builder.add("range_db", percentile_range(values), "dB")
            builder.add("slope_db_per_s", slope_per_second(values, fs.hop_s), "dB/s", Basis.DERIVED)
            builder.add("shape", phrase_shape(values), "", Basis.DERIVED)
            finite = np.isfinite(values)
            if finite.any():
                builder.add(
                    "peak_position",
                    float(np.nanargmax(values) / max(1, values.size - 1)),
                    "ratio",
                    Basis.DERIVED,
                )
            builder.factor(min(1.0, 0.4 + finite.mean()), "voiced fraction")
            results.append(builder.build())
        for note in ctx.hierarchy.by_level("note"):
            span = ctx.span(note)
            values = np.where(voiced[span], rel[span], np.nan)
            builder = self.builder(note)
            ctx.apply_quality(builder, "dynamics")
            mean = nan_mean(values)
            parent_phrase = next(
                (p for p in ctx.hierarchy.by_level("phrase") if p.start_s - 0.01 <= note.start_s < p.end_s),
                None,
            )
            builder.add("mean_db", mean, "dB re singing level")
            if mean is not None and parent_phrase is not None and parent_phrase.id in phrase_means:
                builder.add(
                    "emphasis_db", mean - phrase_means[parent_phrase.id], "dB re phrase", Basis.DERIVED
                )
            attack_frames = int(ATTACK_WINDOW_S / fs.hop_s)
            head = rel[span][:attack_frames]
            if head.size >= 3:
                builder.add("attack_rise_db", float(np.max(head) - head[0]), "dB")
                reach = np.flatnonzero(head >= np.max(head) - 1.0)
                builder.add(
                    "attack_time_ms", float(reach[0] * fs.hop_s * 1000.0) if reach.size else None, "ms"
                )
            tail = rel[span][-int(RELEASE_WINDOW_S / fs.hop_s) :]
            if tail.size >= 5:
                builder.add("release_slope_db_per_s", slope_per_second(tail, fs.hop_s), "dB/s")
            finite = values[np.isfinite(values)]
            if finite.size >= 9:
                thirds = np.array_split(finite, 3)
                change = float(np.mean(thirds[2]) - np.mean(thirds[0]))
                builder.add("change_db", change, "dB")
                builder.add(
                    "contour",
                    "crescendo"
                    if change >= CRESCENDO_DB
                    else ("decrescendo" if change <= -CRESCENDO_DB else "steady"),
                    "",
                    Basis.DERIVED,
                )
            if finite.size >= 40:
                detrended = finite - np.convolve(finite, np.ones(25) / 25, mode="same")
                sos = signal.butter(2, TREMOLO_BAND_HZ, btype="bandpass", fs=1.0 / fs.hop_s, output="sos")
                band = signal.sosfiltfilt(sos, detrended[12:-12]) if detrended.size > 40 else detrended
                builder.add(
                    "loudness_modulation_db", float(np.sqrt(2.0) * np.std(band)), "dB (±)", Basis.DERIVED
                )
            builder.factor(
                min(1.0, 0.4 + (np.isfinite(values).mean() if values.size else 0.0)), "voiced fraction"
            )
            results.append(builder.build())
        summary = self.builder(None, 0.0, fs.duration_s)
        summary.add("dynamic_range_db", percentile_range(rel[voiced]) if voiced.any() else None, "dB")
        means = list(phrase_means.values())
        summary.add(
            "phrase_level_spread_db", float(np.std(means)) if len(means) >= 2 else None, "dB", Basis.DERIVED
        )
        summary.add("reference_loudness_db", reference, "dB (K-weighted)")
        summary.factor(0.9, None)
        results.append(summary.build())
        return results
