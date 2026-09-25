from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from ...dsp.music import describe_pitch, hz_to_midi
from ...dsp.pitch import AGREE_CENTS
from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from ..segmentation.notes import pitch_trend
from .common import nan_mean, slope_per_second

SCOOP_MIN_CENTS = 40.0
TARGET_BAND_CENTS = 25.0
OVERSHOOT_MIN_CENTS = 30.0
OVERSHOOT_WINDOW_S = 0.15
LEGATO_GAP_S = 0.04
RELEASE_FRAMES = 4
ONSET_FRAMES = 3
EDGE_SEARCH_FRAMES = 10
EDGE_MIN_CONFIDENCE = 0.5


@register
class PitchAnalyzer(Analyzer):
    id = "pitch"
    version = "1.2.0"
    category = "pitch"
    label = "Pitch & intonation"
    description = "Note centres, intonation relative to equal temperament, attacks (scoops), overshoot, drift, stability, releases and note-to-note transitions."
    dependencies = ("f0_hz", "f0_conf", "pitch_agreement")
    supported_segment_types = ("note", "phrase", "recording")
    method = (
        "F0 is the consensus of Praat autocorrelation (two-pass, range adapted to the singer) and a vectorised YIN "
        "estimator on a 10 ms grid. Each note's centre is the mean F0 (in semitones) over its stable core, where the "
        "vibrato-free trend (2.5 Hz low-pass) stays within ±40 cents of its median. Attacks are the frames between the "
        "note onset and the start of the core; a scoop is an approach from more than 40 cents below (or above) the centre."
    )
    assumptions = (
        "Equal temperament with A4 = 440 Hz is used only to name notes; comparisons use the reference performance, not the score.",
        "Frames with low F0 confidence are excluded from centre estimates.",
    )
    limitations = (
        "Very breathy or noisy notes may have too few confident frames to measure.",
        "Portamento shape is summarised by duration and asymmetry only.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "hop_s": 0.01,
        "trend_cutoff_hz": 2.5,
        "scoop_min_cents": SCOOP_MIN_CENTS,
        "target_band_cents": TARGET_BAND_CENTS,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        f0 = fs.tracks["f0_hz"]
        conf = fs.tracks["f0_conf"]
        agreement = fs.tracks["pitch_agreement"]
        octave = fs.tracks["octave_conflict"]
        notes = ctx.hierarchy.by_level("note")
        results: list[AnalysisResult] = []
        centers: list[tuple[float, float]] = []
        previous_end: float | None = None
        previous_center: float | None = None
        for note in notes:
            span = ctx.span(note)
            midi = hz_to_midi(f0[span])
            valid = np.isfinite(midi)
            builder = self.builder(note)
            ctx.apply_quality(builder, "pitch")
            if valid.sum() < 5:
                builder.flag("too_few_voiced_frames")
                results.append(builder.factor(0.2, "fewer than 5 voiced frames").build())
                continue
            filled = np.interp(np.arange(midi.size), np.flatnonzero(valid), midi[valid])
            trend = pitch_trend(filled, fs.hop_s)
            core_a = fs.frame(float(note.props["core_start_s"])) - span.start
            core_b = fs.frame(float(note.props["core_end_s"])) - span.start
            core_a = int(np.clip(core_a, 0, midi.size - 1))
            core_b = int(np.clip(core_b, core_a + 1, midi.size))
            core_mask = valid.copy()
            core_mask[:core_a] = False
            core_mask[core_b:] = False
            center = (
                float(np.average(midi[core_mask], weights=np.maximum(conf[span][core_mask], 0.05)))
                if core_mask.any()
                else float(np.nanmean(midi))
            )
            described = describe_pitch(center)
            builder.add("center_midi", center, "semitones")
            builder.add("center_hz", float(described["hz"]), "Hz")
            builder.add("note", str(described["note"]), "")
            builder.add("cents_from_equal_temperament", float(described["cents_from_note"]), "cents")
            builder.add("duration_s", note.duration_s, "s")
            builder.add("voiced_fraction", float(valid.mean()), "ratio")
            core_trend_cents = trend[core_a:core_b] * 100.0
            stability = (
                float(np.std(core_trend_cents - np.mean(core_trend_cents)))
                if core_trend_cents.size > 3
                else None
            )
            builder.add("stability_cents", stability, "cents", Basis.DERIVED)
            drift = slope_per_second(core_trend_cents, fs.hop_s) if core_b - core_a >= 10 else None
            builder.add("drift_cents_per_s", drift, "cents/s", Basis.DERIVED)
            note_conf = conf[span]
            confident = valid & (note_conf >= EDGE_MIN_CONFIDENCE)
            head = np.flatnonzero(confident[:EDGE_SEARCH_FRAMES])
            tail = np.flatnonzero(confident[-EDGE_SEARCH_FRAMES:])
            onset_known = head.size >= 2
            onset_cents = float(np.median(midi[head[:ONSET_FRAMES]]) - center) * 100.0 if onset_known else 0.0
            legato = previous_end is not None and note.start_s - previous_end <= LEGATO_GAP_S
            attack_frames = core_a
            if attack_frames > 0:
                reach = np.flatnonzero(np.abs(trend - center) * 100.0 <= TARGET_BAND_CENTS)
                reach_frame = int(reach[0]) if reach.size else core_a
            else:
                reach_frame = 0
            attack_ms = reach_frame * fs.hop_s * 1000.0
            builder.add("onset_offset_cents", onset_cents if onset_known else None, "cents")
            if not onset_known:
                builder.flag("onset_pitch_unreliable")
            builder.add("attack_duration_ms", attack_ms, "ms")
            builder.add("attack_type", "legato" if legato else "from silence or consonant", "")
            scoop = "none"
            if not legato and onset_cents <= -SCOOP_MIN_CENTS and attack_ms >= 25:
                scoop = "up"
            elif not legato and onset_cents >= SCOOP_MIN_CENTS and attack_ms >= 25:
                scoop = "down"
            builder.add("scoop", scoop, "")
            builder.add("scoop_extent_cents", abs(onset_cents) if scoop != "none" else 0.0, "cents")
            builder.add("scoop_duration_ms", attack_ms if scoop != "none" else 0.0, "ms")
            approach = np.sign(-onset_cents) if abs(onset_cents) >= SCOOP_MIN_CENTS else 0.0
            overshoot = 0.0
            if approach != 0.0:
                window = trend[reach_frame : reach_frame + int(OVERSHOOT_WINDOW_S / fs.hop_s)]
                if window.size:
                    excursion = float(np.max((window - center) * 100.0 * approach))
                    overshoot = excursion if excursion >= OVERSHOOT_MIN_CENTS else 0.0
            builder.add("overshoot_cents", overshoot, "cents", Basis.DERIVED)
            tail_frames = (
                midi[-EDGE_SEARCH_FRAMES:][tail[-RELEASE_FRAMES:]] if tail.size >= 2 else np.array([])
            )
            release_cents = float(np.median(tail_frames) - center) * 100.0 if tail_frames.size else None
            builder.add("release_offset_cents", release_cents, "cents")
            release_frames = midi.size - core_b
            builder.add("release_duration_ms", release_frames * fs.hop_s * 1000.0, "ms")
            if previous_center is not None:
                interval = center - previous_center
                builder.add("interval_from_previous_st", interval, "semitones", Basis.DERIVED)
                builder.add("transition", "legato" if legato else "detached", "")
                if legato:
                    builder.add(
                        "transition_duration_ms", attack_frames * fs.hop_s * 1000.0, "ms", Basis.DERIVED
                    )
                    if attack_frames >= 4:
                        glide = trend[:attack_frames]
                        progress = (
                            (glide - glide[0]) / (center - glide[0])
                            if abs(center - glide[0]) > 0.05
                            else np.zeros_like(glide)
                        )
                        half = np.flatnonzero(progress >= 0.5)
                        asymmetry = float(half[0] / attack_frames) if half.size else None
                        builder.add("transition_midpoint_ratio", asymmetry, "ratio", Basis.DERIVED)
            mean_conf = nan_mean(conf[span][valid]) or 0.0
            builder.factor(0.25 + 0.75 * mean_conf, "F0 tracking confidence")
            agree = nan_mean(agreement[span][valid])
            if agree is not None:
                builder.add("estimator_agreement", agree, "ratio", Basis.DERIVED)
                if agree < 0.7:
                    builder.factor(
                        0.6 + 0.4 * agree, f"pitch estimators disagree beyond {AGREE_CENTS:.0f} cents"
                    )
                    builder.flag("estimator_disagreement")
            if np.nanmean(octave[span]) > 0.05:
                builder.flag("octave_error_risk")
                builder.factor(0.7, "possible octave errors")
            if valid.mean() < 0.7:
                builder.factor(0.5 + 0.5 * float(valid.mean()), "part of the note is unvoiced")
            result = builder.build()
            results.append(result)
            if scoop != "none":
                ctx.hierarchy.add_event(
                    "scoop_up" if scoop == "up" else "scoop_down",
                    note.start_s,
                    note.start_s + attack_ms / 1000.0,
                    result.confidence,
                    note.id,
                    extent_cents=round(abs(onset_cents), 1),
                )
            if overshoot:
                ctx.hierarchy.add_event(
                    "overshoot",
                    note.start_s + attack_ms / 1000.0,
                    note.start_s + attack_ms / 1000.0 + OVERSHOOT_WINDOW_S,
                    result.confidence,
                    note.id,
                    extent_cents=round(overshoot, 1),
                )
            if legato and attack_frames >= 5:
                ctx.hierarchy.add_event(
                    "portamento",
                    note.start_s,
                    note.start_s + attack_frames * fs.hop_s,
                    result.confidence,
                    note.id,
                )
            elif attack_ms > 0:
                ctx.hierarchy.add_event(
                    "pitch_attack",
                    note.start_s,
                    note.start_s + attack_ms / 1000.0,
                    result.confidence,
                    note.id,
                    onset_offset_cents=round(onset_cents, 1),
                )
            centers.append((center, result.confidence))
            previous_end = note.end_s
            previous_center = center
        results.extend(self._phrase_summaries(ctx, results))
        results.append(self._recording_summary(ctx, centers))
        return results

    def _phrase_summaries(
        self, ctx: AnalysisContext, note_results: list[AnalysisResult]
    ) -> list[AnalysisResult]:
        out: list[AnalysisResult] = []
        for phrase in ctx.hierarchy.by_level("phrase"):
            inside = [
                r
                for r in note_results
                if r.segment_id
                and r.timestamp_start >= phrase.start_s - 0.01
                and r.timestamp_end <= phrase.end_s + 0.01
            ]
            builder = self.builder(phrase)
            deviations = [
                abs(r.number("cents_from_equal_temperament") or 0.0) for r in inside if r.validity == "VALID"
            ]
            builder.add("notes", len(inside), "count")
            builder.add(
                "mean_abs_cents_from_equal_temperament",
                float(np.mean(deviations)) if deviations else None,
                "cents",
                Basis.DERIVED,
            )
            builder.add("scoops", sum(1 for r in inside if r.value("scoop") in {"up", "down"}), "count")
            confidences = [r.confidence for r in inside]
            builder.factor(float(np.median(confidences)) if confidences else 0.2, "median note confidence")
            out.append(builder.build())
        return out

    def _recording_summary(self, ctx: AnalysisContext, centers: list[tuple[float, float]]) -> AnalysisResult:
        fs = ctx.features
        builder = self.builder(None, 0.0, fs.duration_s)
        f0 = fs.tracks["f0_hz"]
        voiced = f0[np.isfinite(f0)]
        builder.add("voiced_s", float(np.isfinite(f0).sum() * fs.hop_s), "s")
        if voiced.size:
            low, median, high = np.percentile(voiced, [5, 50, 95])
            builder.add("f0_median_hz", float(median), "Hz")
            builder.add("f0_p05_hz", float(low), "Hz")
            builder.add("f0_p95_hz", float(high), "Hz")
            builder.add("range_semitones", float(12 * np.log2(high / low)), "semitones", Basis.DERIVED)
        good = [(c, w) for c, w in centers if w >= 0.5]
        if good:
            offsets = np.array([(c - round(c)) * 100.0 for c, _ in good])
            weights = np.array([w for _, w in good])
            builder.add(
                "tuning_offset_cents", float(np.average(offsets, weights=weights)), "cents", Basis.DERIVED
            )
        builder.add("notes", len(centers), "count")
        builder.factor(0.9 if good else 0.3, None if good else "few confident notes")
        return builder.build()
