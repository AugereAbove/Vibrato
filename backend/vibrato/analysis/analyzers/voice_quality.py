from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from ...dsp.voice import praat_perturbation
from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .common import nan_mean

MIN_PERTURBATION_S = 0.2
BREATHINESS_CPPS_CLEAN_DB = 24.0
BREATHINESS_CPPS_BREATHY_DB = 10.0


def breathiness_index(cpps: float | None) -> float | None:
    if cpps is None:
        return None
    span = BREATHINESS_CPPS_CLEAN_DB - BREATHINESS_CPPS_BREATHY_DB
    return float(np.clip((BREATHINESS_CPPS_CLEAN_DB - cpps) / span, 0.0, 1.0) * 100.0)


@register
class VoiceQualityAnalyzer(Analyzer):
    id = "voice_quality"
    version = "1.1.0"
    category = "phonation"
    label = "Voice quality"
    description = "HNR, smoothed cepstral peak prominence, H1-H2, H2-H4, spectral tilt, alpha ratio, Hammarberg index, jitter and shimmer per note, with a derived breathiness index."
    dependencies = (
        "hnr_db",
        "cpps_db",
        "h1h2_db",
        "h2h4_db",
        "tilt_db_oct",
        "alpha_ratio_db",
        "hammarberg_db",
    )
    supported_segment_types = ("note", "phrase")
    method = (
        "HNR is Praat's cross-correlation harmonicity. CPPS follows Hillenbrand's method on 46 ms frames (7-frame time "
        "and 3-bin quefrency smoothing). H1-H2 and H2-H4 are harmonic amplitudes measured with pitch-synchronous "
        "(4-period) Hann windows at multiples of F0, without formant correction. Jitter/shimmer (local) come from Praat's "
        "periodic point process over each note's stable core."
    )
    assumptions = (
        "The breathiness index is a derived 0-100 rescaling of CPPS (24 dB -> 0, 10 dB -> 100 on this implementation's scale). CPPS was chosen because it varies least across vowels; it is not a clinical scale.",
        "Uncorrected H1-H2 depends on F1; comparisons are made on the same lyric vowel to limit this effect.",
    )
    limitations = (
        "Vibrato and fast pitch changes inflate jitter; values are shown for reference, not scored.",
        "Background noise and reverb lower HNR and CPPS.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "breathiness_cpps_clean_db": BREATHINESS_CPPS_CLEAN_DB,
        "breathiness_cpps_breathy_db": BREATHINESS_CPPS_BREATHY_DB,
        "min_perturbation_s": MIN_PERTURBATION_S,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        tracks = fs.tracks
        irregular = ctx.shared.get("irregular_notes", set())
        results: list[AnalysisResult] = []
        floor = float(fs.meta.get("pitch_floor_hz", 60.0))
        ceiling = float(fs.meta.get("pitch_ceiling_hz", 1000.0))
        for segment in ctx.hierarchy.by_level("note") + ctx.hierarchy.by_level("phrase"):
            if segment.level == "note":
                start = float(segment.props.get("core_start_s", segment.start_s))
                end = float(segment.props.get("core_end_s", segment.end_s))
            else:
                start, end = segment.start_s, segment.end_s
            span = fs.span(start, end)
            voiced = fs.voiced[span]
            builder = self.builder(segment, start, end)
            ctx.apply_quality(builder, "phonation")
            if voiced.sum() < 5:
                results.append(
                    builder.flag("too_few_voiced_frames").factor(0.2, "too few voiced frames").build()
                )
                continue
            values = {
                name: nan_mean(tracks[name][span][voiced])
                for name in (
                    "hnr_db",
                    "cpps_db",
                    "h1h2_db",
                    "h2h4_db",
                    "tilt_db_oct",
                    "alpha_ratio_db",
                    "hammarberg_db",
                    "high_ratio_db",
                    "spr_db",
                )
            }
            units = {
                "hnr_db": "dB",
                "cpps_db": "dB",
                "h1h2_db": "dB",
                "h2h4_db": "dB",
                "tilt_db_oct": "dB/octave",
                "alpha_ratio_db": "dB",
                "hammarberg_db": "dB",
                "high_ratio_db": "dB",
                "spr_db": "dB",
            }
            for key, value in values.items():
                builder.add(key, value, units[key])
            builder.add("breathiness_index", breathiness_index(values["cpps_db"]), "0-100", Basis.DERIVED)
            if segment.level == "note" and end - start >= MIN_PERTURBATION_S:
                if segment.id in irregular:
                    builder.flag("irregular_phonation_excluded_from_jitter")
                else:
                    perturbation = praat_perturbation(ctx.audio, ctx.sample_rate, start, end, floor, ceiling)
                    jitter = perturbation["jitter_local"]
                    shimmer = perturbation["shimmer_local"]
                    builder.add("jitter_local_pct", None if jitter is None else float(jitter) * 100.0, "%")
                    builder.add("shimmer_local_pct", None if shimmer is None else float(shimmer) * 100.0, "%")
            conf = nan_mean(tracks["f0_conf"][span][voiced]) or 0.0
            builder.factor(0.3 + 0.7 * conf, "voicing confidence")
            builder.factor(min(1.0, 0.4 + voiced.mean()), "voiced fraction")
            results.append(builder.build())
        return results
