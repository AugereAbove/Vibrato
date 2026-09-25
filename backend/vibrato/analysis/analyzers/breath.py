from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .common import nan_mean, nan_median

PHRASE_END_WINDOW_S = 0.3
NOISY_INHALE_DB = -15.0


@register
class BreathAnalyzer(Analyzer):
    id = "breath"
    version = "1.0.0"
    category = "breath"
    label = "Breathing"
    description = "Inhale timing, duration and loudness, breath-to-onset gaps, and increases in breathiness at phrase ends."
    dependencies = ("level_rel_db", "centroid_hz", "cpps_db")
    supported_segment_types = ("event", "phrase", "recording")
    method = (
        "Inhales are unvoiced, noise-like regions between phrases whose level lies between the noise floor + 6 dB and "
        "10 dB below the singing level, with a spectral centroid of 0.4-5.5 kHz and at least 100 ms duration. "
        "Phrase-end breathiness compares CPPS in the final 300 ms of voicing with the phrase median."
    )
    limitations = (
        "Very quiet inhales below the noise floor cannot be detected; reverb tails can mask them.",
    )
    parameters: ClassVar[dict[str, Any]] = {"phrase_end_window_s": PHRASE_END_WINDOW_S}

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        cpps = fs.tracks["cpps_db"]
        results: list[AnalysisResult] = []
        breaths = [e for e in ctx.hierarchy.events if e.type == "breath"]
        phrases = ctx.hierarchy.by_level("phrase")
        for event in breaths:
            builder = self.builder(None, event.start_s, event.end_s)
            builder.segment_id = event.id
            builder.segment_level = "event"
            ctx.apply_quality(builder, "breath")
            level = float(event.props.get("level_rel_db", -30.0))
            before = event.props.get("before_phrase")
            builder.add("start_s", event.start_s, "s")
            builder.add("duration_ms", (event.end_s - event.start_s) * 1000.0, "ms")
            builder.add("level_db", level, "dB re singing level")
            builder.add("centroid_hz", float(event.props.get("centroid_hz", 0.0)), "Hz")
            builder.add("before_phrase", int(before) if before is not None else None, "index")
            if before is not None and int(before) < len(phrases):
                builder.add("gap_to_onset_ms", (phrases[int(before)].start_s - event.end_s) * 1000.0, "ms")
            if level > NOISY_INHALE_DB:
                builder.flag("noisy_inhale")
            builder.factor(event.confidence, "breath detection confidence")
            results.append(builder.build())
        for index, phrase in enumerate(phrases):
            builder = self.builder(phrase)
            ctx.apply_quality(builder, "breath")
            preceding = [e for e in breaths if e.props.get("before_phrase") == index]
            builder.add("breath_before", bool(preceding), "")
            if preceding:
                builder.add("breath_before_ms", (preceding[-1].end_s - preceding[-1].start_s) * 1000.0, "ms")
            span = ctx.span(phrase)
            voiced_idx = np.flatnonzero(fs.voiced[span])
            if voiced_idx.size >= 20:
                end_frames = voiced_idx[-int(PHRASE_END_WINDOW_S / fs.hop_s) :] + span.start
                phrase_median = nan_median(cpps[span.start + voiced_idx])
                end_mean = nan_mean(cpps[end_frames])
                if phrase_median is not None and end_mean is not None:
                    builder.add("end_cpps_change_db", end_mean - phrase_median, "dB", Basis.DERIVED)
                    builder.add("end_breathier", (end_mean - phrase_median) < -2.0, "", Basis.DERIVED)
            builder.factor(
                0.85 if voiced_idx.size >= 20 else 0.4, None if voiced_idx.size >= 20 else "short phrase"
            )
            results.append(builder.build())
        summary = self.builder(None, 0.0, fs.duration_s)
        durations = [(e.end_s - e.start_s) for e in breaths]
        summary.add("breaths", len(breaths), "count")
        summary.add("mean_duration_ms", float(np.mean(durations)) * 1000.0 if durations else None, "ms")
        summary.add(
            "breaths_per_minute", len(breaths) / max(fs.duration_s / 60.0, 1e-6), "per minute", Basis.DERIVED
        )
        summary.factor(0.8, None)
        results.append(summary.build())
        return results
