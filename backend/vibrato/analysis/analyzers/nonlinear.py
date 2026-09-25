from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import parselmouth
from scipy.signal.windows import hann

from ...dsp.framing import HOP_S, remove_short_runs, resample_track_to_grid, runs
from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis

SHR_THRESHOLD = 0.25
SUBHARMONIC_MIN_FRAMES = 5
FRY_CEILING_HZ = 80.0
FRY_MIN_FRAMES = 5
ROUGH_HNR_DROP_DB = 10.0
IRREGULAR_MIN_FRAMES = 4
ANALYSIS_ORDERS = 6


def subharmonic_ratio(x: np.ndarray, sr: int, f0: np.ndarray) -> np.ndarray:
    hop = round(HOP_S * sr)
    out = np.full(len(f0), np.nan)
    for index in np.flatnonzero(np.isfinite(f0)):
        frequency = f0[index]
        length = int(np.clip(6.0 * sr / frequency, 0.03 * sr, 0.1 * sr))
        start = index * hop - length // 2
        if start < 0 or start + length > len(x):
            continue
        window = hann(length, sym=False)
        segment = x[start : start + length] * window
        orders = np.arange(1, 2 * ANALYSIS_ORDERS + 1) * 0.5
        valid = orders * frequency < 0.45 * sr
        basis = np.exp(-2j * np.pi * np.outer(orders[valid] * frequency, np.arange(length)) / sr)
        amplitude = np.abs(basis @ segment)
        harmonic = amplitude[1::2].sum()
        sub = amplitude[0::2].sum()
        out[index] = sub / harmonic if harmonic > 0 else np.nan
    return out


def fry_track(x: np.ndarray, sr: int, n: int) -> np.ndarray:
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(
        time_step=HOP_S, pitch_floor=25.0, pitch_ceiling=120.0, voicing_threshold=0.35, octave_jump_cost=0.2
    )
    f0 = pitch.selected_array["frequency"].astype(np.float64)
    f0[f0 <= 0] = np.nan
    return resample_track_to_grid(np.asarray(pitch.xs()), f0, n)


@register
class NonlinearAnalyzer(Analyzer):
    id = "nonlinear"
    version = "1.0.0"
    category = "phonation"
    label = "Nonlinear & irregular phonation"
    description = (
        "Vocal fry, subharmonics (period doubling), rough or irregular onsets and probable growl regions."
    )
    dependencies = ("f0_hz", "hnr_db", "level_rel_db")
    supported_segment_types = ("note", "recording")
    experimental = True
    method = (
        "Subharmonic-to-harmonic ratio (after Sun, 2002) compares spectral amplitude at half-integer multiples of F0 with "
        "the harmonics, using 6-period Hann windows. Fry is detected with a dedicated low-range Praat pitch pass "
        "(25-120 Hz) where the main tracker is unvoiced or much higher and the level is low. Irregular regions combine "
        "sharp HNR drops relative to the note with loud phonation."
    )
    assumptions = (
        "Events are candidates with confidence values; they are never used for diagnosis below 50% confidence.",
    )
    limitations = (
        "Distortion effects vary widely; growl and diplophonia labels are tentative.",
        "Clipping and heavy reverb can mimic irregularity.",
    )
    parameters: ClassVar[dict[str, Any]] = {
        "shr_threshold": SHR_THRESHOLD,
        "fry_ceiling_hz": FRY_CEILING_HZ,
    }

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        f0 = fs.tracks["f0_hz"]
        level = fs.tracks["level_rel_db"]
        hnr = fs.tracks["hnr_db"]
        shr = subharmonic_ratio(ctx.audio.astype(np.float64), ctx.sample_rate, f0)
        sub_mask = remove_short_runs(np.nan_to_num(shr, nan=0.0) > SHR_THRESHOLD, SUBHARMONIC_MIN_FRAMES)
        low = fry_track(ctx.audio, ctx.sample_rate, fs.n)
        fry_mask = (
            np.isfinite(low)
            & (low < FRY_CEILING_HZ)
            & (~np.isfinite(f0) | (f0 > low * 1.6) | (f0 < FRY_CEILING_HZ))
            & (level > -40.0)
            & (level < -6.0)
        )
        fry_mask = remove_short_runs(fry_mask, FRY_MIN_FRAMES)
        irregular_notes: set[str] = set()
        results: list[AnalysisResult] = []
        for start, end in runs(sub_mask):
            loud = float(np.nanmean(level[start:end])) > -12.0
            mean_shr = float(np.nanmean(shr[start:end]))
            kind = (
                "probable growl"
                if loud and (end - start) >= 15 and float(np.nanmean(hnr[start:end])) < 12.0
                else "subharmonics (period doubling)"
            )
            confidence = float(np.clip((mean_shr - SHR_THRESHOLD) / 0.3, 0.2, 0.85))
            note = ctx.hierarchy.best_overlap("note", start * fs.hop_s, end * fs.hop_s)
            ctx.hierarchy.add_event(
                "subharmonic",
                start * fs.hop_s,
                end * fs.hop_s,
                confidence,
                note.id if note else None,
                kind=kind,
                shr=round(mean_shr, 3),
            )
            if note is not None:
                irregular_notes.add(note.id)
        for start, end in runs(fry_mask):
            confidence = float(np.clip(0.3 + (end - start) * 0.03, 0.3, 0.8))
            note = ctx.hierarchy.best_overlap("note", start * fs.hop_s, end * fs.hop_s)
            ctx.hierarchy.add_event(
                "fry",
                start * fs.hop_s,
                end * fs.hop_s,
                confidence,
                note.id if note else None,
                median_f0_hz=round(float(np.nanmedian(low[start:end])), 1),
            )
            if note is not None:
                irregular_notes.add(note.id)
        for note in ctx.hierarchy.by_level("note"):
            span = ctx.span(note)
            builder = self.builder(note)
            ctx.apply_quality(builder, "phonation")
            note_hnr = hnr[span]
            finite = np.isfinite(note_hnr)
            if finite.sum() < 6:
                results.append(
                    builder.flag("too_few_voiced_frames").factor(0.2, "too few voiced frames").build()
                )
                continue
            reference = float(np.nanpercentile(note_hnr, 75))
            dips = remove_short_runs(
                finite & (note_hnr < reference - ROUGH_HNR_DROP_DB) & (level[span] > -15.0),
                IRREGULAR_MIN_FRAMES,
            )
            onset_window = min(8, dips.size)
            rough_onset = bool(dips[:onset_window].any())
            builder.add("subharmonic_fraction", float(np.mean(sub_mask[span])), "ratio")
            builder.add("fry_fraction", float(np.mean(fry_mask[span])), "ratio")
            builder.add("irregular_fraction", float(np.mean(dips)), "ratio", Basis.DERIVED)
            builder.add("rough_onset", rough_onset, "", Basis.DERIVED)
            builder.add(
                "median_shr",
                float(np.nanmedian(shr[span])) if np.isfinite(shr[span]).any() else None,
                "ratio",
            )
            if rough_onset:
                ctx.hierarchy.add_event(
                    "roughness",
                    note.start_s,
                    note.start_s + onset_window * fs.hop_s,
                    0.5,
                    note.id,
                    kind="rough attack",
                )
            if dips.mean() > 0.2:
                irregular_notes.add(note.id)
            builder.factor(0.75, "nonlinear-event detection is experimental")
            results.append(builder.build())
        ctx.shared["irregular_notes"] = irregular_notes
        summary = self.builder(None, 0.0, fs.duration_s)
        summary.add("subharmonic_regions", len(runs(sub_mask)), "count")
        summary.add("fry_regions", len(runs(fry_mask)), "count")
        summary.add("irregular_notes", len(irregular_notes), "count")
        summary.factor(0.7, "nonlinear-event detection is experimental")
        results.append(summary.build())
        return results
