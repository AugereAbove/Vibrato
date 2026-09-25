from __future__ import annotations

import importlib.util
import warnings
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np
import parselmouth
from parselmouth.praat import call
from scipy import signal

from ..alignment.aligner import Alignment
from ..analysis.analyzers.vibrato import band_limited_oscillation
from ..analysis.model import Segment
from ..audio.errors import UserFacingError
from ..audio.loudness import integrated_loudness
from ..compare.matching import match_segments
from ..compare.view import RecordingView
from ..dsp.framing import HOP_S, moving_average
from ..dsp.music import hz_to_midi

COUNTERFACTUAL_VERSION = "cf/1.1"
MAX_GAIN_DB = 12.0
MAX_EQ_DB = 6.0
PSOLA_WARN_SEMITONES = 4.0
RAMP_S = 0.03
VIBRATO_RAMP_S = 0.18
EQ_TAPS = 1025
MIN_ANCHOR_GAP_S = 0.03
MIN_STRETCH = 0.4
MAX_STRETCH = 2.5
EDGE_EPSILON_S = 0.001

TRANSFORMS: dict[str, dict[str, Any]] = {
    "note_centers": {
        "label": "Reference note centres",
        "description": "Each note is shifted to the reference's note centre. Your own vibrato, scoops and timing are kept.",
        "method": "PSOLA pitch shift (Praat overlap-add)",
        "experimental": False,
    },
    "pitch_contour": {
        "label": "Reference pitch contour",
        "description": "Your voice follows the reference's full pitch line, including scoops, glides and vibrato.",
        "method": "PSOLA pitch replacement (Praat overlap-add)",
        "experimental": False,
    },
    "vibrato_rate": {
        "label": "Reference vibrato rate",
        "description": "Your vibrato keeps its width and onset but oscillates at the reference's rate.",
        "method": "Vibrato re-synthesis on your pitch trend + PSOLA",
        "experimental": False,
    },
    "vibrato_extent": {
        "label": "Reference vibrato width",
        "description": "Your vibrato keeps its rate and onset but swings as widely as the reference's.",
        "method": "Vibrato re-synthesis on your pitch trend + PSOLA",
        "experimental": False,
    },
    "vibrato_onset": {
        "label": "Reference vibrato onset",
        "description": "Your vibrato starts when the reference's does; rate and width stay yours.",
        "method": "Vibrato re-synthesis on your pitch trend + PSOLA",
        "experimental": False,
    },
    "vibrato_all": {
        "label": "Reference-like vibrato",
        "description": "Vibrato rate, width and onset all follow the reference.",
        "method": "Vibrato re-synthesis on your pitch trend + PSOLA",
        "experimental": False,
    },
    "timing": {
        "label": "Reference timing",
        "description": "Your take is time-stretched so every moment lines up with the reference.",
        "method": "Time-varying PSOLA duration change (Praat) driven by the alignment",
        "experimental": False,
    },
    "dynamics": {
        "label": "Reference loudness shape",
        "description": "A gain envelope gives your take the reference's loudness shape (relative to each singer's own level).",
        "method": "Smoothed gain envelope",
        "experimental": False,
    },
    "spectral_balance": {
        "label": "Reference spectral balance (EQ)",
        "description": "A gentle EQ (±6 dB) moves your broad spectral balance toward the reference's. It changes brightness only; it does not transfer the reference's vocal tract or voice.",
        "method": "Linear-phase EQ from level-normalised band differences",
        "experimental": True,
    },
    "breathiness": {
        "label": "Reference-like airiness (WORLD)",
        "description": "The aperiodic (noise) part of your voice is adjusted toward the reference's breathiness.",
        "method": "WORLD analysis/synthesis with modified aperiodicity",
        "experimental": True,
        "requires": "pyworld",
    },
}


@dataclass
class RenderResult:
    audio: np.ndarray
    sample_rate: int
    transform: str
    parameters: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    approximate: bool = True
    output_timeline: str = "take"


def world_available() -> bool:
    return importlib.util.find_spec("pyworld") is not None


def _psola(
    x: np.ndarray,
    sr: int,
    floor: float,
    ceiling: float,
    target_f0: np.ndarray | None,
    duration_points: list[tuple[float, float]] | None,
) -> np.ndarray:
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    manipulation = call(snd, "To Manipulation", HOP_S, max(40.0, floor * 0.8), min(1600.0, ceiling * 1.25))
    duration = snd.get_total_duration()
    if target_f0 is not None:
        tier = call("Create PitchTier", "target", 0.0, duration)
        times = np.arange(target_f0.size) * HOP_S
        for t, f in zip(times, target_f0):
            if np.isfinite(f) and f > 0:
                call(tier, "Add point", float(t), float(f))
        call([tier, manipulation], "Replace pitch tier")
    if duration_points:
        tier = call("Create DurationTier", "timing", 0.0, duration)
        for t, factor in duration_points:
            call(tier, "Add point", float(t), float(factor))
        call([tier, manipulation], "Replace duration tier")
    result = call(manipulation, "Get resynthesis (overlap-add)")
    return np.asarray(result.values[0], dtype=np.float64)


def _match_loudness(y: np.ndarray, reference: np.ndarray, sr: int) -> np.ndarray:
    target = integrated_loudness(reference, sr)
    current = integrated_loudness(y, sr)
    if target is None or current is None:
        return y
    out = y * 10.0 ** ((target - current) / 20.0)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    return out * (0.98 / peak) if peak > 0.98 else out


def _ramped_blend(base: np.ndarray, modified: np.ndarray, mask: np.ndarray) -> np.ndarray:
    weight = moving_average(mask.astype(np.float64), max(1, int(RAMP_S / HOP_S) * 2 + 1))
    weight = np.nan_to_num(weight, nan=0.0)
    return np.where(
        np.isfinite(modified), base * (1 - weight) + np.nan_to_num(modified, nan=0.0) * weight, base
    )


def _note_pairs(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> list[tuple[Segment, Segment]]:
    return [
        (m.ref, m.user)
        for m in match_segments(ref.by_level("note"), take.by_level("note"), alignment)
        if m.user is not None
    ]


def target_note_centers(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> tuple[np.ndarray, dict[str, Any]]:
    f0 = take.features.tracks["f0_hz"].copy()
    target = f0.copy()
    shifts: list[float] = []
    mask = np.zeros(f0.size, dtype=bool)
    for ref_note, user_note in _note_pairs(ref, take, alignment):
        rc = ref.result("pitch", ref_note.id)
        uc = take.result("pitch", user_note.id)
        ref_center = rc.number("center_midi") if rc is not None else None
        user_center = uc.number("center_midi") if uc is not None else None
        if ref_center is None or user_center is None:
            continue
        shift = (ref_center + alignment.transposition_semitones - user_center) * 100.0
        span = take.features.span(user_note.start_s, user_note.end_s)
        target[span] = f0[span] * 2.0 ** (shift / 1200.0)
        mask[span] = True
        shifts.append(shift)
    blended = _ramped_blend(f0, target, mask)
    return blended, {
        "notes_shifted": len(shifts),
        "median_shift_cents": float(np.median(shifts)) if shifts else 0.0,
        "max_shift_cents": float(np.max(np.abs(shifts))) if shifts else 0.0,
    }


def target_pitch_contour(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> tuple[np.ndarray, dict[str, Any]]:
    f0 = take.features.tracks["f0_hz"].copy()
    times = np.arange(f0.size) * HOP_S
    ref_times = alignment.user_to_ref(times)
    ref_frames = np.clip(np.round(ref_times / HOP_S).astype(int), 0, ref.features.n - 1)
    ref_f0 = ref.features.tracks["f0_hz"][ref_frames] * 2.0 ** (alignment.transposition_semitones / 12.0)
    inside = (ref_times >= alignment.ref_range[0]) & (ref_times <= alignment.ref_range[1])
    usable = np.isfinite(f0) & np.isfinite(ref_f0) & inside & (alignment.confidence_at(ref_times) > 0.3)
    target = np.where(usable, ref_f0, np.nan)
    blended = _ramped_blend(f0, target, usable)
    shifts = 1200.0 * np.log2(ref_f0[usable] / f0[usable]) if usable.any() else np.array([0.0])
    return blended, {
        "frames_replaced": int(usable.sum()),
        "median_shift_cents": float(np.median(shifts)),
        "max_shift_cents": float(np.max(np.abs(shifts))),
    }


def _synthesize_vibrato(
    n: int, onset_frames: int, rate: float, extent: float, envelope: np.ndarray | None = None
) -> np.ndarray:
    t = np.arange(n) * HOP_S
    active = np.clip((t - onset_frames * HOP_S) / VIBRATO_RAMP_S, 0.0, 1.0)
    amplitude = extent * active if envelope is None else envelope * active
    phase = 2.0 * np.pi * rate * np.maximum(t - onset_frames * HOP_S, 0.0)
    return amplitude * np.sin(phase)


def target_vibrato(
    ref: RecordingView, take: RecordingView, alignment: Alignment, mode: str
) -> tuple[np.ndarray, dict[str, Any]]:
    f0 = take.features.tracks["f0_hz"].copy()
    target = f0.copy()
    mask = np.zeros(f0.size, dtype=bool)
    changed: list[dict[str, Any]] = []
    for ref_note, user_note in _note_pairs(ref, take, alignment):
        rv = ref.result("vibrato", ref_note.id)
        uv = take.result("vibrato", user_note.id)
        if rv is None or uv is None or rv.value("present") is None:
            continue
        span = take.features.span(user_note.start_s, user_note.end_s)
        segment = f0[span]
        valid = np.isfinite(segment)
        if valid.sum() < 20:
            continue
        cents = np.interp(np.arange(segment.size), np.flatnonzero(valid), hz_to_midi(segment[valid])) * 100.0
        osc, bp = band_limited_oscillation(cents, HOP_S)
        trend = cents - osc
        ref_present = bool(rv.value("present"))
        user_present = bool(uv.value("present"))
        ref_rate = rv.number("rate_hz") or 5.5
        ref_extent = rv.number("extent_cents") or 0.0
        ref_onset = rv.number("onset_s") or 0.0
        user_rate = uv.number("rate_hz") or ref_rate
        user_extent = uv.number("extent_cents") or ref_extent
        user_onset = uv.number("onset_s") or ref_onset
        onset_frames = round(
            (user_onset if mode in {"vibrato_rate", "vibrato_extent"} else ref_onset) / HOP_S
        )
        if not ref_present and not user_present:
            continue
        if not ref_present and mode in {"vibrato_all", "vibrato_onset"}:
            new_osc = np.zeros_like(osc)
        elif mode == "vibrato_extent" and user_present and user_extent > 0:
            new_osc = osc * (ref_extent / user_extent)
        elif mode == "vibrato_rate" and user_present:
            envelope = np.abs(signal.hilbert(bp)) if bp.size > 8 else None
            new_osc = _synthesize_vibrato(
                osc.size, round(user_onset / HOP_S), ref_rate, user_extent, envelope
            )
        elif mode == "vibrato_onset" and user_present:
            new_osc = _synthesize_vibrato(osc.size, onset_frames, user_rate, user_extent)
        else:
            new_osc = _synthesize_vibrato(osc.size, onset_frames, ref_rate, ref_extent)
        new_cents = trend + new_osc
        target[span] = 440.0 * 2.0 ** ((new_cents / 100.0 - 69.0) / 12.0)
        target[span][~valid] = np.nan
        mask[span] = valid
        changed.append(
            {
                "note": user_note.label,
                "reference": {
                    "rate_hz": ref_rate,
                    "extent_cents": ref_extent,
                    "onset_s": ref_onset,
                    "present": ref_present,
                },
                "take": {
                    "rate_hz": user_rate if user_present else None,
                    "extent_cents": user_extent if user_present else None,
                    "onset_s": user_onset if user_present else None,
                    "present": user_present,
                },
            }
        )
    blended = _ramped_blend(f0, np.where(mask, target, np.nan), mask)
    return blended, {"notes_changed": len(changed), "notes": changed}


def timing_anchors(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for level in ("phrase", "note"):
        for match in match_segments(ref.by_level(level), take.by_level(level), alignment):
            if match.user is None:
                continue
            pairs.append((match.user.start_s, match.ref.start_s))
            pairs.append((match.user.end_s, match.ref.end_s))
    pairs.sort()
    monotone: list[tuple[float, float]] = []
    for user_t, ref_t in pairs:
        if monotone and (
            user_t - monotone[-1][0] < MIN_ANCHOR_GAP_S or ref_t - monotone[-1][1] < MIN_ANCHOR_GAP_S
        ):
            continue
        monotone.append((user_t, ref_t))
    return monotone


def duration_points(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    anchors = timing_anchors(ref, take, alignment)
    if len(anchors) < 2:
        return [], {"segments": 0}
    points: list[tuple[float, float]] = []
    factors: list[float] = []
    for (u0, r0), (u1, r1) in pairwise(anchors):
        factor = float(np.clip((r1 - r0) / (u1 - u0), MIN_STRETCH, MAX_STRETCH))
        points.append((u0 + EDGE_EPSILON_S, factor))
        points.append((u1 - EDGE_EPSILON_S, factor))
        factors.append(factor)
    points = [
        (max(0.0, anchors[0][0] - EDGE_EPSILON_S), 1.0),
        *points,
        (anchors[-1][0] + EDGE_EPSILON_S, 1.0),
    ]
    return points, {
        "anchors": len(anchors),
        "min_factor": round(min(factors), 3),
        "max_factor": round(max(factors), 3),
        "method": "piecewise-constant stretch between matched note and phrase boundaries",
    }


def gain_envelope(
    ref: RecordingView, take: RecordingView, alignment: Alignment
) -> tuple[np.ndarray, dict[str, Any]]:
    def relative(view: RecordingView) -> np.ndarray:
        loud = view.features.tracks["loudness_db"]
        voiced = view.features.voiced
        reference = (
            float(np.percentile(loud[voiced], 90)) if voiced.sum() >= 10 else float(np.percentile(loud, 95))
        )
        return loud - reference

    ref_rel = relative(ref)
    take_rel = relative(take)
    times = np.arange(take.features.n) * HOP_S
    ref_frames = np.clip(np.round(alignment.user_to_ref(times) / HOP_S).astype(int), 0, ref.features.n - 1)
    active = take.features.voiced & ref.features.voiced[ref_frames]
    gain = np.where(active, ref_rel[ref_frames] - take_rel, 0.0)
    gain = np.clip(moving_average(gain, 9), -MAX_GAIN_DB, MAX_GAIN_DB)
    gain = np.nan_to_num(gain, nan=0.0)
    return gain, {
        "median_gain_db": float(np.median(gain[active])) if active.any() else 0.0,
        "max_gain_db": float(np.max(np.abs(gain))) if gain.size else 0.0,
    }


def eq_curve(ref: RecordingView, take: RecordingView) -> tuple[list[float], list[float], dict[str, Any]]:
    ref_profile = next(
        (
            r.raw_supporting_data.get("band_profile")
            for r in ref.results_for("timbre")
            if r.segment_id is None and r.raw_supporting_data.get("band_profile")
        ),
        None,
    )
    take_profile = next(
        (
            r.raw_supporting_data.get("band_profile")
            for r in take.results_for("timbre")
            if r.segment_id is None and r.raw_supporting_data.get("band_profile")
        ),
        None,
    )
    if not ref_profile or not take_profile:
        raise UserFacingError(
            "Spectral-balance data is missing for one of the recordings.",
            "Timbre analysis did not produce a spectral profile (too little voiced audio).",
            "Re-analyse both recordings, or use another transform.",
            code="no_spectral_profile",
        )
    centers = [125.0, 354.0, 707.0, 1414.0, 2828.0, 5657.0, 11314.0]
    diffs = [
        (float(r) - float(t)) if r is not None and t is not None else 0.0
        for r, t in zip(ref_profile, take_profile)
    ]
    mean = float(np.mean(diffs[1:6]))
    gains = [float(np.clip(d - mean, -MAX_EQ_DB, MAX_EQ_DB)) for d in diffs]
    gains[0] = 0.0
    return (
        centers,
        gains,
        {
            "band_gains_db": dict(
                zip(
                    ["<250", "250-500", "500-1k", "1-2k", "2-4k", "4-8k", "8k+"], [round(g, 2) for g in gains]
                )
            )
        },
    )


def apply_eq(x: np.ndarray, sr: int, centers: list[float], gains_db: list[float]) -> np.ndarray:
    nyquist = sr / 2.0
    freqs = [0.0, *[min(c, nyquist * 0.99) for c in centers], nyquist]
    gains = [gains_db[0], *gains_db, gains_db[-1]]
    amplitude = [10.0 ** (g / 20.0) for g in gains]
    fir = signal.firwin2(EQ_TAPS, [f / nyquist for f in freqs], amplitude)
    y = signal.fftconvolve(x, fir, mode="full")
    delay = (EQ_TAPS - 1) // 2
    return y[delay : delay + x.size]


def world_breathiness(x: np.ndarray, sr: int, delta_index: float) -> tuple[np.ndarray, dict[str, Any]]:
    if not world_available():
        raise UserFacingError(
            what="The breathiness experiment needs the optional WORLD vocoder.",
            why="The 'pyworld' package is not installed.",
            action='Install it with: pip install pyworld "setuptools<81" (a C compiler is needed on some systems), then restart Vibrato.',
            code="model_unavailable",
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import pyworld

    x64 = np.ascontiguousarray(x.astype(np.float64))
    f0, t = pyworld.dio(x64, sr, frame_period=5.0)
    f0 = pyworld.stonemask(x64, f0, t, sr)
    sp = pyworld.cheaptrick(x64, f0, t, sr)
    ap = pyworld.d4c(x64, f0, t, sr)
    freqs = np.linspace(0, sr / 2, ap.shape[1])
    weight = np.clip((freqs - 800.0) / 2000.0, 0.0, 1.0)[None, :]
    change = float(np.clip(delta_index / 100.0, -0.8, 0.8))
    if change >= 0:
        ap_new = ap + (1.0 - ap) * change * 0.6 * weight
    else:
        ap_new = ap * (1.0 + change * 0.8 * weight)
    y = pyworld.synthesize(f0, sp, np.clip(ap_new, 0.0, 1.0), sr, frame_period=5.0)
    return y[: x.size] if y.size >= x.size else np.pad(y, (0, x.size - y.size)), {
        "aperiodicity_change": round(change, 3)
    }


def render_counterfactual(
    transform: str, x: np.ndarray, sr: int, ref: RecordingView, take: RecordingView, alignment: Alignment
) -> RenderResult:
    if transform not in TRANSFORMS:
        raise UserFacingError(
            f"Unknown transform '{transform}'.",
            "The requested preview type is not supported.",
            "Choose one of the listed previews.",
            code="bad_transform",
        )
    warnings: list[str] = []
    floor = float(take.features.meta.get("pitch_floor_hz", 60.0))
    ceiling = float(take.features.meta.get("pitch_ceiling_hz", 1000.0))
    params: dict[str, Any] = {}
    output_timeline = "take"
    if alignment.overall_confidence < 0.5:
        warnings.append(
            f"Alignment confidence is {alignment.overall_confidence:.0%}; the reference values may be mapped onto the wrong moments."
        )
    if transform in {"note_centers", "pitch_contour"} or transform.startswith("vibrato"):
        if transform == "note_centers":
            target, params = target_note_centers(ref, take, alignment)
        elif transform == "pitch_contour":
            target, params = target_pitch_contour(ref, take, alignment)
        else:
            target, params = target_vibrato(ref, take, alignment, transform)
            if not params.get("notes_changed"):
                warnings.append(
                    "No matched sustained notes had vibrato to change; the preview is close to your original."
                )
        max_shift = float(params.get("max_shift_cents", 0.0) or 0.0)
        if max_shift / 100.0 > PSOLA_WARN_SEMITONES:
            warnings.append(
                f"Some notes are shifted by more than {PSOLA_WARN_SEMITONES:.0f} semitones; PSOLA artefacts become audible at large shifts."
            )
        y = _psola(x, sr, floor, ceiling, target, None)
    elif transform == "timing":
        points, params = duration_points(ref, take, alignment)
        if not points:
            raise UserFacingError(
                "Not enough matched notes to re-time the take.",
                "Timing previews need at least two matched notes between take and reference.",
                "Check the alignment or add anchors, then try again.",
                code="no_timing_anchors",
            )
        y = _psola(x, sr, floor, ceiling, None, points)
        anchors = timing_anchors(ref, take, alignment)
        shift = anchors[0][0] - anchors[0][1]
        offset = round(abs(shift) * sr)
        y = y[offset:] if shift > 0 else np.concatenate([np.zeros(offset), y])
        output_timeline = "reference"
        params["timeline"] = "Output time matches the reference timeline."
    elif transform == "dynamics":
        gain_db, params = gain_envelope(ref, take, alignment)
        sample_gain = np.interp(np.arange(x.size) / sr, np.arange(gain_db.size) * HOP_S, gain_db)
        y = x.astype(np.float64) * 10.0 ** (sample_gain / 20.0)
    elif transform == "spectral_balance":
        centers, gains, params = eq_curve(ref, take)
        y = apply_eq(x.astype(np.float64), sr, centers, gains)
        warnings.append(
            "Experimental: this EQ changes broad brightness only. It cannot reproduce another voice's resonances."
        )
    else:
        ref_index = _median_result(ref, "voice_quality", "breathiness_index")
        take_index = _median_result(take, "voice_quality", "breathiness_index")
        if ref_index is None or take_index is None:
            raise UserFacingError(
                "Breathiness could not be measured on both recordings.",
                "Voice-quality analysis needs sustained voiced notes.",
                "Try a take with longer notes.",
                code="no_breathiness",
            )
        y, params = world_breathiness(x, sr, ref_index - take_index)
        params.update({"reference_breathiness_index": ref_index, "take_breathiness_index": take_index})
        warnings.append(
            "Experimental: WORLD resynthesis changes the whole voice slightly, not only breathiness."
        )
    y = _match_loudness(np.nan_to_num(y), x.astype(np.float64), sr)
    return RenderResult(
        audio=y.astype(np.float32),
        sample_rate=sr,
        transform=transform,
        parameters=params,
        warnings=warnings,
        approximate=True,
        output_timeline=output_timeline,
    )


def _median_result(view: RecordingView, analyzer: str, key: str) -> float | None:
    values = [v for v in (r.number(key) for r in view.results_for(analyzer, "note")) if v is not None]
    return float(np.median(values)) if values else None
