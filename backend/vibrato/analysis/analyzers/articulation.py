from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from ..model import Event
from .common import nan_mean

HARD_ONSET_RISE_MS = 15.0
HARD_ONSET_TRANSIENT = 5.0
BREATHY_ONSET_RISE_MS = 60.0
ASPIRATION_LOOKBACK_S = 0.08
ONSET_PEAK_WINDOW_S = 0.15


@register
class ArticulationAnalyzer(Analyzer):
    id = "articulation"
    version = "1.0.0"
    category = "articulation"
    label = "Consonants & onsets"
    description = "Consonant durations, intensity relative to the neighbouring vowel, spectral character, stop closures, release bursts and aspiration, plus hard/balanced/breathy vowel onsets."
    dependencies = ("level_rel_db", "centroid_hz", "sibilance_ratio_db", "voiced")
    supported_segment_types = ("event", "phrase")
    method = (
        "Consonant events come from the acoustic phonetic-class segmentation (voicing, level dips, sibilance ratio "
        "4-11 kHz vs 0.1-4 kHz, spectral centroid). Stops are closure + burst (+ aspiration). Onsets are classified from "
        "the 10-90% intensity rise time at voicing onset and the presence of aspiration noise just before voicing."
    )
    assumptions = (
        "Consonant identities come from lyrics when available; otherwise only the acoustic class is known.",
    )
    limitations = ("Short or voiced consonants inside legato lines can merge with vowels and go undetected.",)
    parameters: ClassVar[dict[str, Any]] = {
        "hard_onset_rise_ms": HARD_ONSET_RISE_MS,
        "breathy_onset_rise_ms": BREATHY_ONSET_RISE_MS,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        level = fs.tracks["level_rel_db"]
        centroid = fs.tracks["centroid_hz"]
        sibilance = fs.tracks["sibilance_ratio_db"]
        voiced = fs.voiced
        results: list[AnalysisResult] = []
        consonants = [e for e in ctx.hierarchy.events if e.type == "consonant"]
        phonemes = ctx.hierarchy.by_level("phoneme")
        for event in consonants:
            span = fs.span(event.start_s, event.end_s)
            builder = self.builder(None, event.start_s, event.end_s)
            builder.segment_id = event.id
            builder.segment_level = "event"
            ctx.apply_quality(builder, "articulation")
            syllable = ctx.hierarchy.get(event.segment_id) if event.segment_id else None
            vowel_level = None
            position = "unknown"
            if syllable is not None:
                ns = float(syllable.props.get("nucleus_start_s", syllable.start_s))
                ne = float(syllable.props.get("nucleus_end_s", syllable.end_s))
                vowel_level = nan_mean(level[fs.span(ns, ne)])
                position = (
                    "onset"
                    if event.end_s <= ns + 0.02
                    else ("coda" if event.start_s >= ne - 0.02 else "internal")
                )
            consonant_level = nan_mean(level[span])
            overlapping = [
                p
                for p in phonemes
                if p.props.get("phoneme_class") not in (None, "vowel")
                and min(p.end_s, event.end_s) - max(p.start_s, event.start_s) > 0
            ]
            builder.add("phoneme", overlapping[0].label if overlapping else None, "", Basis.INFERRED)
            builder.add("kind", str(event.props.get("kind", "")), "")
            builder.add("position", position, "")
            builder.add("duration_ms", (event.end_s - event.start_s) * 1000.0, "ms")
            builder.add("level_db", consonant_level, "dB re singing level")
            builder.add(
                "cv_ratio_db",
                None if (consonant_level is None or vowel_level is None) else consonant_level - vowel_level,
                "dB",
                Basis.DERIVED,
            )
            builder.add("centroid_hz", nan_mean(centroid[span]), "Hz")
            builder.add("sibilance_ratio_db", nan_mean(sibilance[span]), "dB")
            builder.add(
                "voicing_fraction", float(np.mean(voiced[span])) if span.stop > span.start else None, "ratio"
            )
            if event.props.get("kind") == "stop":
                builder.add("closure_ms", float(event.props.get("closure_s", 0.0)) * 1000.0, "ms")
                builder.add("aspiration_ms", float(event.props.get("aspiration_s", 0.0)) * 1000.0, "ms")
                burst_time = event.props.get("burst_s")
                if burst_time is not None:
                    b = fs.frame(float(burst_time))
                    closure_level = nan_mean(level[max(span.start, b - 3) : b])
                    burst_level = float(np.max(level[b : b + 2])) if b + 1 < fs.n else None
                    builder.add(
                        "burst_strength_db",
                        None
                        if (closure_level is None or burst_level is None)
                        else burst_level - closure_level,
                        "dB",
                    )
            builder.factor(event.confidence, "consonant segmentation confidence")
            results.append(builder.build())
        for event in [e for e in ctx.hierarchy.events if e.type == "onset"]:
            results.append(self._onset(ctx, event))
        for phrase in ctx.hierarchy.by_level("phrase"):
            inside = [
                r
                for r in results
                if r.segment_level == "event" and phrase.start_s - 0.01 <= r.timestamp_start < phrase.end_s
            ]
            builder = self.builder(phrase)
            durations = [
                d
                for d in (r.number("duration_ms") for r in inside if r.value("kind") != "onset")
                if d is not None
            ]
            ratios = [v for v in (r.number("cv_ratio_db") for r in inside) if v is not None]
            builder.add("consonants", len(durations), "count")
            builder.add(
                "mean_consonant_ms", float(np.mean(durations)) if durations else None, "ms", Basis.DERIVED
            )
            builder.add("mean_cv_ratio_db", float(np.mean(ratios)) if ratios else None, "dB", Basis.DERIVED)
            builder.factor(
                float(np.median([r.confidence for r in inside])) if inside else 0.3, "consonant confidence"
            )
            results.append(builder.build())
        return results

    def _onset(self, ctx: AnalysisContext, event: Event) -> AnalysisResult:
        fs = ctx.features
        level = fs.tracks["level_rel_db"]
        flux = fs.tracks["flux"]
        start = event.start_s
        b = fs.frame(start)
        window = level[b : b + int(ONSET_PEAK_WINDOW_S / fs.hop_s)]
        builder = self.builder(None, start, start + ONSET_PEAK_WINDOW_S)
        builder.segment_id = event.id
        builder.segment_level = "event"
        ctx.apply_quality(builder, "articulation")
        if window.size < 3:
            return builder.factor(0.2, "onset too close to the end").build()
        base = float(level[max(0, b - 2)])
        peak = float(np.max(window))
        rise = peak - base
        ten = base + 0.1 * rise
        ninety = base + 0.9 * rise
        above_ten = np.flatnonzero(window >= ten)
        above_ninety = np.flatnonzero(window >= ninety)
        rise_ms = (
            float((above_ninety[0] - above_ten[0]) * fs.hop_s * 1000.0)
            if above_ten.size and above_ninety.size
            else None
        )
        lookback = fs.span(start - ASPIRATION_LOOKBACK_S, start)
        noise_before = (
            bool(np.any((~fs.voiced[lookback]) & (level[lookback] > -35.0)))
            if lookback.stop > lookback.start
            else False
        )
        flux_spike = (
            float(np.max(flux[b : b + 3]) / (np.median(flux[max(0, b - 20) : b + 20]) + 1e-9))
            if b + 3 <= fs.n
            else 0.0
        )
        if rise_ms is not None and rise_ms <= HARD_ONSET_RISE_MS and flux_spike > HARD_ONSET_TRANSIENT:
            onset_type = "hard"
        elif noise_before and (rise_ms is None or rise_ms >= BREATHY_ONSET_RISE_MS * 0.6):
            onset_type = "breathy/aspirated"
        else:
            onset_type = "balanced"
        builder.add("kind", "onset", "")
        builder.add("onset_type", onset_type, "", Basis.DERIVED)
        builder.add("rise_ms", rise_ms, "ms")
        builder.add("rise_db", rise, "dB")
        builder.add("aspiration_before_voicing", noise_before, "")
        builder.add("transient_ratio", flux_spike, "ratio", Basis.DERIVED)
        builder.factor(0.75, "onset type is a derived descriptor")
        return builder.build()
