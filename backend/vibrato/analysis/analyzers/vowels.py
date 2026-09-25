from __future__ import annotations

import math
from typing import Any, ClassVar

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .common import nan_median

STANDARD_LOG_MEAN = float(np.mean(np.log([500.0, 1500.0, 2500.0])))
MIN_NUCLEUS_S = 0.06
RELIABLE_CONF = 0.5
DIPHTHONG_MOVEMENT = 0.12
HIGH_F0_HZ = 350.0
TRAJECTORY_WINDOWS = {"start": (0.1, 0.3), "mid": (0.3, 0.7), "end": (0.7, 0.9)}
SHORT_NUCLEUS_S = 0.15
F1_RELIABLE_RATIO = 2.5


def speaker_log_mean(ctx: AnalysisContext) -> tuple[float | None, int, str]:
    if ctx.baseline and isinstance(ctx.baseline.get("formant_log_mean"), (int, float)):
        return (
            float(ctx.baseline["formant_log_mean"]),
            int(ctx.baseline.get("formant_frames", 0)),
            "calibration baseline",
        )
    fs = ctx.features
    mask = np.zeros(fs.n, dtype=bool)
    for syllable in ctx.hierarchy.by_level("syllable"):
        a = fs.frame(float(syllable.props.get("nucleus_start_s", syllable.start_s)))
        b = fs.frame(float(syllable.props.get("nucleus_end_s", syllable.end_s)))
        mask[a:b] = True
    f1, f2, f3 = fs.tracks["f1_hz"], fs.tracks["f2_hz"], fs.tracks["f3_hz"]
    reliable = (
        mask
        & (fs.tracks["formant_conf"] >= RELIABLE_CONF)
        & np.isfinite(f1)
        & np.isfinite(f2)
        & np.isfinite(f3)
    )
    if reliable.sum() < 10:
        return None, int(reliable.sum()), "insufficient reliable vowel frames"
    logs = np.log(np.stack([f1[reliable], f2[reliable], f3[reliable]]))
    return float(np.mean(logs)), int(reliable.sum()), "this recording's vowels"


def normalized_hz(value_hz: float | None, log_mean: float | None) -> float | None:
    if value_hz is None or log_mean is None or value_hz <= 0:
        return None
    return float(math.exp(math.log(value_hz) - log_mean + STANDARD_LOG_MEAN))


@register
class VowelAnalyzer(Analyzer):
    id = "vowels"
    version = "1.1.0"
    category = "vowel"
    label = "Vowels & formants"
    description = "F1-F3 at the start, middle and end of each vowel nucleus, speaker-normalised vowel position, trajectory and diphthong movement."
    dependencies = ("f1_hz", "f2_hz", "f3_hz", "formant_conf", "f0_hz")
    supported_segment_types = ("syllable", "recording")
    method = (
        "Formants come from Praat's Burg LPC (5 formants, 25 ms window) with the formant ceiling chosen per recording "
        "among 4.5-6.5 kHz by track stability; an independent autocorrelation LPC (order 10) checks agreement. "
        "Vowel position is normalised with the log-mean method (Nearey): each formant's log is referenced to the "
        "singer's mean log formant, which removes the uniform scaling caused by vocal-tract length. Normalised values "
        "are displayed on a standard scale (mean log formant of 500/1500/2500 Hz)."
    )
    assumptions = (
        "Normalisation assumes vocal-tract length scales all formants approximately uniformly.",
        "When a calibration baseline exists it defines the singer's mean; otherwise the recording's own vowels do (both singers sing the same lyrics, so their vowel inventories match).",
        "F1 correlates with openness (jaw/tongue height) and F2 with frontness, but these are acoustic correlates, not direct observations of articulation.",
    )
    limitations = (
        "Above about 350 Hz F0 the harmonics are too sparse for reliable formant estimation; confidence is reduced accordingly.",
        "Nasalised or very breathy vowels can shift formant estimates.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "min_nucleus_s": MIN_NUCLEUS_S,
        "trajectory_windows": TRAJECTORY_WINDOWS,
        "diphthong_movement_log": DIPHTHONG_MOVEMENT,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        log_mean, frames, source = speaker_log_mean(ctx)
        f = [fs.tracks["f1_hz"], fs.tracks["f2_hz"], fs.tracks["f3_hz"]]
        bandwidths = [fs.tracks["b1_hz"], fs.tracks["b2_hz"]]
        conf = fs.tracks["formant_conf"]
        f0 = fs.tracks["f0_hz"]
        agreement = fs.tracks["formant_agreement"]
        vowel_labels = self._vowel_labels(ctx)
        results: list[AnalysisResult] = []
        for syllable in ctx.hierarchy.by_level("syllable"):
            start = float(syllable.props.get("nucleus_start_s", syllable.start_s))
            end = float(syllable.props.get("nucleus_end_s", syllable.end_s))
            builder = self.builder(syllable, start, end)
            ctx.apply_quality(builder, "vowel")
            if end - start < MIN_NUCLEUS_S:
                builder.add("vowel", vowel_labels.get(syllable.id), "")
                results.append(
                    builder.flag("nucleus_too_short").factor(0.3, "vowel nucleus shorter than 60 ms").build()
                )
                continue
            a, b = fs.frame(start), fs.frame(end)
            points: dict[str, list[float | None]] = {}
            for name, (first, last) in TRAJECTORY_WINDOWS.items():
                lo = a + int(np.floor((b - a) * first))
                hi = max(lo + 1, a + int(np.ceil((b - a) * last)))
                good = conf[lo:hi] >= 0.3
                points[name] = [nan_median(track[lo:hi][good]) if good.any() else None for track in f]
            builder.add("vowel", vowel_labels.get(syllable.id), "", Basis.INFERRED)
            for name in ("start", "mid", "end"):
                builder.add(f"f1_{name}_hz", points[name][0], "Hz")
                builder.add(f"f2_{name}_hz", points[name][1], "Hz")
            builder.add("f3_mid_hz", points["mid"][2], "Hz")
            builder.add("b1_mid_hz", nan_median(bandwidths[0][a:b]), "Hz")
            builder.add("b2_mid_hz", nan_median(bandwidths[1][a:b]), "Hz")
            for name in ("start", "mid", "end"):
                builder.add(
                    f"f1_norm_{name}",
                    normalized_hz(points[name][0], log_mean),
                    "Hz (normalised)",
                    Basis.DERIVED,
                )
                builder.add(
                    f"f2_norm_{name}",
                    normalized_hz(points[name][1], log_mean),
                    "Hz (normalised)",
                    Basis.DERIVED,
                )
            movement = None
            s1, s2 = points["start"][0], points["start"][1]
            e1, e2 = points["end"][0], points["end"][1]
            if s1 and s2 and e1 and e2:
                d1 = math.log(e1) - math.log(s1)
                d2 = math.log(e2) - math.log(s2)
                movement = math.hypot(d1, d2)
                builder.add("movement_log", movement, "log units", Basis.DERIVED)
                builder.add("diphthong", movement >= DIPHTHONG_MOVEMENT, "", Basis.DERIVED)
                builder.add("f1_change_pct", (math.exp(d1) - 1.0) * 100.0, "%", Basis.DERIVED)
                builder.add("f2_change_pct", (math.exp(d2) - 1.0) * 100.0, "%", Basis.DERIVED)
            if points["mid"][0] and log_mean is not None:
                builder.add(
                    "openness_index", math.log(points["mid"][0]) - log_mean, "log units", Basis.DERIVED
                )
            if points["mid"][1] and log_mean is not None:
                builder.add(
                    "frontness_index", math.log(points["mid"][1]) - log_mean, "log units", Basis.DERIVED
                )
            median_conf = nan_median(conf[a:b]) or 0.0
            builder.factor(max(0.05, median_conf), "formant tracking confidence")
            median_f0 = nan_median(f0[a:b])
            if end - start < SHORT_NUCLEUS_S:
                builder.factor(0.5 + 0.5 * (end - start) / SHORT_NUCLEUS_S, "short vowel nucleus")
                builder.flag("short_vowel")
            if median_f0 is not None:
                builder.add("median_f0_hz", median_f0, "Hz")
                f1_mid = points["mid"][0]
                if f1_mid is not None and f1_mid < F1_RELIABLE_RATIO * median_f0:
                    ratio = f1_mid / median_f0
                    builder.factor(
                        float(np.clip(0.3 + 0.7 * (ratio - 1.0) / (F1_RELIABLE_RATIO - 1.0), 0.3, 1.0)),
                        f"F1 is only {ratio:.1f}x F0, so few harmonics define it",
                    )
                    builder.flag("f1_near_f0")
                if median_f0 > HIGH_F0_HZ:
                    builder.flag("high_f0_formants")
                    builder.reason(f"F0 {median_f0:.0f} Hz is high; formants may follow harmonics")
            agree = nan_median(agreement[a:b])
            if agree is not None:
                builder.add("estimator_agreement", agree, "ratio", Basis.DERIVED)
                if agree < 0.5:
                    builder.flag("formant_estimators_disagree")
            if log_mean is None:
                builder.flag("normalisation_unavailable")
            builder.support(normalisation=source, log_mean=log_mean)
            results.append(builder.build())
        summary = self.builder(None, 0.0, fs.duration_s)
        summary.add("log_mean", log_mean, "ln Hz", Basis.DERIVED)
        summary.add("normalisation_source", source, "")
        summary.add("reliable_frames", frames, "count")
        summary.add("formant_ceiling_hz", float(fs.meta.get("formant_ceiling_hz", 0.0)), "Hz")
        summary.add("high_f0_fraction", float(fs.meta.get("formant_high_f0_fraction", 0.0)), "ratio")
        summary.factor(min(1.0, frames / 200.0) if frames else 0.1, "amount of reliable vowel data")
        results.append(summary.build())
        return results

    def _vowel_labels(self, ctx: AnalysisContext) -> dict[str, str]:
        labels: dict[str, str] = {}
        for phoneme in ctx.hierarchy.by_level("phoneme"):
            if phoneme.props.get("phoneme_class") == "vowel" and phoneme.parent_id:
                labels.setdefault(phoneme.parent_id, phoneme.label)
        return labels
