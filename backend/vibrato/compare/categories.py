from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..alignment.aligner import Alignment
from ..analysis.contract import AnalysisResult
from ..analysis.model import Segment
from ..dsp.music import describe_pitch
from .matching import Match, map_span, match_events, match_segments, pair_confidence, theil_sen
from .metrics import METRICS
from .model import MetricComparison, make_comparison
from .view import RecordingView

VOWEL_PAIR_MIN_CONFIDENCE = 0.4
RESOLUTION_FRACTION = 0.25
RELIABLE_F1_RATIO = 2.5
BREATHINESS_BIAS_DIFF = 20.0
BREATHINESS_BIAS_FACTOR = 0.6
MISSING_CONSONANT_MIN_CONFIDENCE = 0.6
MISSING_CONSONANT_MIN_S = 0.04
ONSET_LABEL_MIN_CONFIDENCE = 0.5
LOW_BAND_LIMIT_HZ = 500
HIGH_BAND_LIMIT_HZ = 8000


@dataclass
class CompareContext:
    ref: RecordingView
    user: RecordingView
    alignment: Alignment
    synced: bool = False
    note_matches: list[Match] = field(default_factory=list)
    phrase_matches: list[Match] = field(default_factory=list)
    syllable_matches: list[Match] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    last_notes: set[str] = field(default_factory=set)

    @property
    def transposition_cents(self) -> float:
        return self.alignment.transposition_semitones * 100.0

    def conf(
        self, ref_result: AnalysisResult | None, user_result: AnalysisResult | None, match: Match
    ) -> float:
        if ref_result is None or user_result is None:
            return 0.0
        return pair_confidence(ref_result.confidence, user_result.confidence, match.align_confidence)


def note_importance(note: Segment, phrase_last: bool) -> float:
    base = 0.6 + 0.4 * min(1.0, note.duration_s / 1.0)
    return min(1.15, base + (0.15 if phrase_last else 0.0))


def _span(segment: Segment) -> tuple[float, float]:
    return (segment.start_s, segment.end_s)


def matched(matches: list[Match]) -> Iterator[tuple[Match, Segment]]:
    for match in matches:
        if match.user is not None:
            yield match, match.user


def parent_label(view: RecordingView, segment: Segment, fallback: str) -> str:
    parent = view.segment(segment.parent_id)
    return parent.label if parent is not None else fallback


def _num(result: AnalysisResult | None, key: str) -> float | None:
    return None if result is None else result.number(key)


def prepare(ctx: CompareContext) -> None:
    ctx.phrase_matches = match_segments(
        ctx.ref.by_level("phrase"), ctx.user.by_level("phrase"), ctx.alignment
    )
    ctx.note_matches = match_segments(ctx.ref.by_level("note"), ctx.user.by_level("note"), ctx.alignment)
    ctx.syllable_matches = match_segments(
        ctx.ref.by_level("syllable"), ctx.user.by_level("syllable"), ctx.alignment
    )
    for phrase in ctx.ref.by_level("phrase"):
        notes = ctx.ref.notes_in(phrase)
        if notes:
            ctx.last_notes.add(notes[-1].id)


def compare_pitch(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    last_notes = ctx.last_notes
    for match, user in matched(ctx.note_matches):
        rp = ctx.ref.result("pitch", match.ref.id)
        up = ctx.user.result("pitch", user.id)
        if rp is None or up is None:
            continue
        conf = ctx.conf(rp, up, match)
        importance = note_importance(match.ref, match.ref.id in last_notes)
        label = f"{match.ref.label} ({parent_label(ctx.ref, match.ref, 'note')})"
        ref_center = _num(rp, "center_midi")
        user_center = _num(up, "center_midi")
        if ref_center is not None and user_center is not None:
            diff = (user_center - ref_center) * 100.0 - ctx.transposition_cents
            interval = _num(rp, "interval_from_previous_st")
            context = None
            if interval is not None and abs(interval) >= 0.5:
                heading = "ascending" if interval > 0 else "descending"
                shortfall = diff * np.sign(interval)
                context = (
                    f"{'overshoots' if shortfall > 0 else 'undershoots'} the {heading} interval"
                    if abs(diff) >= 10
                    else None
                )
            out.append(
                make_comparison(
                    "pitch.center",
                    "note",
                    label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    ref_center * 100.0,
                    user_center * 100.0 - ctx.transposition_cents,
                    diff,
                    conf,
                    importance,
                    evidence={
                        "reference": describe_pitch(ref_center),
                        "take": describe_pitch(user_center),
                        "transposition_semitones": ctx.alignment.transposition_semitones,
                        "interval_context": context,
                    },
                )
            )
        ref_onset = _num(rp, "onset_offset_cents")
        user_onset = _num(up, "onset_offset_cents")
        legato = rp.value("attack_type") == "legato" or up.value("attack_type") == "legato"
        if ref_onset is not None and user_onset is not None and not legato:
            ref_scoop = -ref_onset
            user_scoop = -user_onset
            if abs(ref_scoop) >= 40.0 or abs(user_scoop) >= 40.0:
                out.append(
                    make_comparison(
                        "pitch.scoop",
                        "note",
                        label,
                        match.ref.id,
                        user.id,
                        _span(match.ref),
                        _span(user),
                        ref_scoop,
                        user_scoop,
                        user_scoop - ref_scoop,
                        conf,
                        importance,
                        evidence={
                            "reference_scoop": rp.value("scoop"),
                            "take_scoop": up.value("scoop"),
                            "reference_attack_ms": _num(rp, "attack_duration_ms"),
                            "take_attack_ms": _num(up, "attack_duration_ms"),
                        },
                    )
                )
        for metric_id, key in (
            ("pitch.attack_time", "attack_duration_ms"),
            ("pitch.overshoot", "overshoot_cents"),
            ("pitch.drift", "drift_cents_per_s"),
            ("pitch.stability", "stability_cents"),
            ("pitch.release", "release_offset_cents"),
        ):
            rv, uv = _num(rp, key), _num(up, key)
            if rv is None or uv is None:
                continue
            if metric_id == "pitch.attack_time" and legato:
                continue
            if metric_id in {"pitch.drift", "pitch.stability"} and match.ref.duration_s < 0.35:
                continue
            out.append(
                make_comparison(
                    metric_id,
                    "note",
                    label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rv,
                    uv,
                    uv - rv,
                    conf * 0.9,
                    importance,
                )
            )
        if rp.value("transition") == "legato" and up.value("transition") == "legato":
            rv, uv = _num(rp, "transition_duration_ms"), _num(up, "transition_duration_ms")
            if rv is not None and uv is not None:
                out.append(
                    make_comparison(
                        "pitch.transition",
                        "note",
                        label,
                        match.ref.id,
                        user.id,
                        _span(match.ref),
                        _span(user),
                        rv,
                        uv,
                        uv - rv,
                        conf * 0.85,
                        importance,
                    )
                )
    return out


def _first_note(view: RecordingView, phrase: Segment) -> Segment | None:
    notes = view.notes_in(phrase)
    return notes[0] if notes else None


def compare_timing(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    pairs: list[tuple[Match, Segment, Segment, Segment]] = []
    for match, user in matched(ctx.phrase_matches):
        rn, un = _first_note(ctx.ref, match.ref), _first_note(ctx.user, user)
        if rn is not None and un is not None:
            pairs.append((match, user, rn, un))
    if not pairs:
        return out
    x = np.array([p[2].start_s for p in pairs])
    y = np.array([p[3].start_s for p in pairs])
    if ctx.synced:
        slope, intercept = 1.0, 0.0
        model_label = "synced recording: the reference timeline is the target"
    elif len(pairs) >= 3:
        slope, intercept = theil_sen(x, y)
        model_label = "robust line through matched phrase entries (overall tempo and offset removed)"
    else:
        slope = (
            float(ctx.alignment.tempo_ratio)
            if len(pairs) == 1
            else float((y[-1] - y[0]) / max(1e-6, x[-1] - x[0]))
        )
        intercept = float(np.median(y - slope * x))
        model_label = "tempo from alignment; offset from phrase entries"
    ctx.extras["timing_model"] = {
        "slope": round(slope, 4),
        "intercept_s": round(intercept, 4),
        "description": model_label,
        "phrases_used": len(pairs),
    }
    last_notes = ctx.last_notes
    note_lookup = {m.ref.id: m for m in ctx.note_matches if m.user is not None}
    for match, user, rn, un in pairs:
        predicted = intercept + slope * rn.start_s
        deviation = (un.start_s - predicted) * 1000.0
        align_conf = match.align_confidence
        conf = pair_confidence(rn.confidence, un.confidence, align_conf) * (
            0.9 if len(pairs) >= 3 or ctx.synced else 0.6
        )
        out.append(
            make_comparison(
                "timing.phrase_onset",
                "phrase",
                match.ref.label,
                match.ref.id,
                user.id,
                _span(match.ref),
                _span(user),
                rn.start_s * 1000.0,
                un.start_s * 1000.0,
                deviation,
                conf,
                1.0,
                evidence={
                    "predicted_s": round(predicted, 3),
                    "model": ctx.extras["timing_model"],
                    "local_tempo_ratio": round(user.duration_s / max(1e-6, match.ref.duration_s) / slope, 3),
                },
            )
        )
        for note in ctx.ref.notes_in(match.ref):
            note_match = note_lookup.get(note.id)
            if note_match is None or note_match.user is None:
                continue
            user_note = note_match.user
            nconf = pair_confidence(note.confidence, user_note.confidence, note_match.align_confidence)
            importance = note_importance(note, note.id in last_notes)
            if note.id != rn.id:
                expected = un.start_s + slope * (note.start_s - rn.start_s)
                dev = (user_note.start_s - expected) * 1000.0
                out.append(
                    make_comparison(
                        "timing.note_onset",
                        "note",
                        note.label,
                        note.id,
                        user_note.id,
                        _span(note),
                        _span(user_note),
                        note.start_s * 1000.0,
                        user_note.start_s * 1000.0,
                        dev,
                        nconf * 0.9,
                        importance,
                    )
                )
            ratio = user_note.duration_s / max(1e-6, note.duration_s * slope)
            if note.id in last_notes:
                hold = (user_note.duration_s - note.duration_s * slope) * 1000.0
                out.append(
                    make_comparison(
                        "timing.hold",
                        "note",
                        note.label,
                        note.id,
                        user_note.id,
                        _span(note),
                        _span(user_note),
                        note.duration_s * 1000.0,
                        user_note.duration_s * 1000.0,
                        hold,
                        nconf * 0.85,
                        importance,
                    )
                )
            elif note.duration_s >= 0.15:
                out.append(
                    make_comparison(
                        "timing.duration",
                        "note",
                        note.label,
                        note.id,
                        user_note.id,
                        _span(note),
                        _span(user_note),
                        note.duration_s * 1000.0,
                        user_note.duration_s * 1000.0,
                        (ratio - 1.0) * 100.0,
                        nconf * 0.8,
                        importance,
                    )
                )
    return out


def compare_vibrato(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    last_notes = ctx.last_notes
    for match, user in matched(ctx.note_matches):
        rv = ctx.ref.result("vibrato", match.ref.id)
        uv = ctx.user.result("vibrato", user.id)
        if rv is None or uv is None or rv.value("present") is None or uv.value("present") is None:
            continue
        conf = ctx.conf(rv, uv, match)
        importance = note_importance(match.ref, match.ref.id in last_notes)
        label = f"{match.ref.label} ({parent_label(ctx.ref, match.ref, 'note')})"
        ref_present = bool(rv.value("present"))
        user_present = bool(uv.value("present"))
        out.append(
            make_comparison(
                "vibrato.presence",
                "note",
                label,
                match.ref.id,
                user.id,
                _span(match.ref),
                _span(user),
                "vibrato" if ref_present else "straight",
                "vibrato" if user_present else "straight",
                float(user_present) - float(ref_present),
                conf,
                importance,
                mismatch=ref_present != user_present,
            )
        )
        if ref_present and user_present:
            for metric_id, key, scale in (
                ("vibrato.rate", "rate_hz", 1.0),
                ("vibrato.extent", "extent_cents", 1.0),
                ("vibrato.onset", "onset_s", 1000.0),
                ("vibrato.regularity", "regularity", 1.0),
            ):
                a, b = _num(rv, key), _num(uv, key)
                if a is None or b is None:
                    continue
                out.append(
                    make_comparison(
                        metric_id,
                        "note",
                        label,
                        match.ref.id,
                        user.id,
                        _span(match.ref),
                        _span(user),
                        a * scale,
                        b * scale,
                        (b - a) * scale,
                        conf,
                        importance,
                    )
                )
    return out


@dataclass
class VowelPair:
    match: Match
    user: Segment
    rv: AnalysisResult
    uv: AnalysisResult
    formants_ref: dict[str, float]
    formants_user: dict[str, float]
    f0_ref: float
    f0_user: float


def _formants(result: AnalysisResult) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in (
        "f1_mid_hz",
        "f2_mid_hz",
        "f3_mid_hz",
        "f1_start_hz",
        "f2_start_hz",
        "f1_end_hz",
        "f2_end_hz",
    ):
        value = _num(result, key)
        if value is not None and value > 0:
            out[key] = value
    return out


def _vowel_pairs(ctx: CompareContext) -> list[VowelPair]:
    pairs: list[VowelPair] = []
    for match, user in matched(ctx.syllable_matches):
        rv = ctx.ref.result("vowels", match.ref.id)
        uv = ctx.user.result("vowels", user.id)
        if rv is None or uv is None:
            continue
        ref_formants, user_formants = _formants(rv), _formants(uv)
        if not all(k in ref_formants and k in user_formants for k in ("f1_mid_hz", "f2_mid_hz")):
            continue
        pairs.append(
            VowelPair(
                match,
                user,
                rv,
                uv,
                ref_formants,
                user_formants,
                _num(rv, "median_f0_hz") or 0.0,
                _num(uv, "median_f0_hz") or 0.0,
            )
        )
    return pairs


def _vocal_tract_scale(pairs: list[VowelPair]) -> list[float]:
    ratios: list[float] = []
    for pair in pairs:
        if min(pair.rv.confidence, pair.uv.confidence) < VOWEL_PAIR_MIN_CONFIDENCE:
            continue
        keys = ["f2_mid_hz", "f3_mid_hz"]
        if (
            pair.f0_ref > 0
            and pair.f0_user > 0
            and min(
                pair.formants_ref["f1_mid_hz"] / pair.f0_ref, pair.formants_user["f1_mid_hz"] / pair.f0_user
            )
            >= RELIABLE_F1_RATIO
        ):
            keys.append("f1_mid_hz")
        logs = [
            math.log(pair.formants_user[k] / pair.formants_ref[k])
            for k in keys
            if k in pair.formants_user and k in pair.formants_ref
        ]
        if logs:
            ratios.append(float(np.mean(logs)))
    return ratios


def compare_vowels(ctx: CompareContext) -> list[MetricComparison]:
    pairs = _vowel_pairs(ctx)
    ratios = _vocal_tract_scale(pairs)
    scale = float(np.median(ratios)) if len(ratios) >= 3 else 0.0
    ctx.extras["vowel_scaling"] = {
        "log_scale": round(scale, 4),
        "factor": round(math.exp(scale), 4),
        "pairs": len(ratios),
        "description": "Median formant ratio between the two voices across matched vowels (F2 and F3, plus F1 where it is well above F0); removed before comparing vowels so vocal-tract size is not treated as a mistake."
        if len(ratios) >= 3
        else "Too few reliable vowel pairs to estimate vocal-tract scaling; raw ratios are used.",
    }
    out: list[MetricComparison] = []
    for pair in pairs:
        match, user, rv, uv = pair.match, pair.user, pair.rv, pair.uv
        conf = ctx.conf(rv, uv, match)
        breathiness_gap = _breathiness_gap(ctx, match, user)
        vowel = rv.value("vowel") or uv.value("vowel") or ""
        label = f"{match.ref.label or 'syllable'} /{vowel}/" if vowel else (match.ref.label or "syllable")
        span = (float(rv.timestamp_start), float(rv.timestamp_end))
        user_span = (float(uv.timestamp_start), float(uv.timestamp_end))
        flags = sorted(set(rv.warning_flags) | set(uv.warning_flags))
        for metric_id, key in (("vowel.f1", "f1"), ("vowel.f2", "f2")):
            r_mid, u_mid = pair.formants_ref[f"{key}_mid_hz"], pair.formants_user[f"{key}_mid_hz"]
            normalized = (math.exp(math.log(u_mid / r_mid) - scale) - 1.0) * 100.0
            f0_r, f0_u = pair.f0_ref, pair.f0_user
            resolution = RESOLUTION_FRACTION * 100.0 * max(f0_r / r_mid, f0_u / u_mid)
            tolerance = math.hypot(METRICS[metric_id].tolerance, resolution)
            evidence = {
                "reference_hz": {p: _num(rv, f"{key}_{p}_hz") for p in ("start", "mid", "end")},
                "take_hz": {p: _num(uv, f"{key}_{p}_hz") for p in ("start", "mid", "end")},
                "raw_difference_pct": round((u_mid / r_mid - 1.0) * 100.0, 2),
                "vocal_tract_factor": round(math.exp(scale), 4),
                "vowel_start_difference_pct": _pct(
                    _num(rv, f"{key}_start_hz"), _num(uv, f"{key}_start_hz"), scale
                ),
                "vowel_end_difference_pct": _pct(_num(rv, f"{key}_end_hz"), _num(uv, f"{key}_end_hz"), scale),
                "flags": flags,
            }
            evidence["harmonic_resolution_pct"] = round(resolution, 2)
            pair_conf = conf
            notes: list[str] = []
            near_f0 = f0_r > 0 and f0_u > 0 and min(r_mid / f0_r, u_mid / f0_u) < RELIABLE_F1_RATIO
            if (
                metric_id == "vowel.f1"
                and near_f0
                and breathiness_gap is not None
                and breathiness_gap >= BREATHINESS_BIAS_DIFF
            ):
                pair_conf = conf * BREATHINESS_BIAS_FACTOR
                notes.append(
                    "The two performances differ strongly in breathiness; with F1 this close to F0, the stronger fundamental of the breathier voice can pull the F1 estimate down."
                )
            out.append(
                make_comparison(
                    metric_id,
                    "syllable",
                    label,
                    match.ref.id,
                    user.id,
                    span,
                    user_span,
                    r_mid,
                    u_mid,
                    normalized,
                    pair_conf,
                    1.0,
                    evidence=evidence,
                    tolerance=tolerance,
                    notes=notes,
                )
            )
        rm, um = _num(rv, "movement_log"), _num(uv, "movement_log")
        if rm is not None and um is not None and max(rm, um) >= 0.08:
            out.append(
                make_comparison(
                    "vowel.movement",
                    "syllable",
                    label,
                    match.ref.id,
                    user.id,
                    span,
                    user_span,
                    rm,
                    um,
                    um - rm,
                    conf * 0.85,
                    0.9,
                )
            )
    return out


def _breathiness_gap(ctx: CompareContext, match: Match, user: Segment) -> float | None:
    ref_notes = [
        n
        for n in ctx.ref.by_level("note")
        if min(n.end_s, match.ref.end_s) - max(n.start_s, match.ref.start_s) > 0
    ]
    user_notes = [
        n for n in ctx.user.by_level("note") if min(n.end_s, user.end_s) - max(n.start_s, user.start_s) > 0
    ]
    ref_values = [
        v
        for v in (_num(ctx.ref.result("voice_quality", n.id), "breathiness_index") for n in ref_notes)
        if v is not None
    ]
    user_values = [
        v
        for v in (_num(ctx.user.result("voice_quality", n.id), "breathiness_index") for n in user_notes)
        if v is not None
    ]
    if not ref_values or not user_values:
        return None
    return abs(float(np.mean(user_values)) - float(np.mean(ref_values)))


def _pct(ref: float | None, user: float | None, scale: float) -> float | None:
    if not ref or not user:
        return None
    return round((math.exp(math.log(user / ref) - scale) - 1.0) * 100.0, 2)


def _loudness_rel(view: RecordingView) -> np.ndarray:
    fs = view.features
    loud = fs.tracks["loudness_db"]
    voiced = fs.voiced
    reference = (
        float(np.percentile(loud[voiced], 90)) if voiced.sum() >= 10 else float(np.percentile(loud, 95))
    )
    return loud - reference


def compare_dynamics(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    ref_loud = _loudness_rel(ctx.ref)
    user_loud = _loudness_rel(ctx.user)
    rfs, ufs = ctx.ref.features, ctx.user.features
    envelopes: list[dict[str, Any]] = []
    for match, user in matched(ctx.phrase_matches):
        span = rfs.span(match.ref.start_s, match.ref.end_s)
        frames = np.arange(span.start, span.stop)
        voiced = rfs.voiced[frames]
        if voiced.sum() < 20:
            continue
        ref_times = frames * rfs.hop_s
        user_times = ctx.alignment.ref_to_user(ref_times)
        user_frames = np.clip(np.round(user_times / ufs.hop_s).astype(int), 0, ufs.n - 1)
        both = voiced & ufs.voiced[user_frames]
        if both.sum() < 20:
            continue
        a = ref_loud[frames][both]
        b = user_loud[user_frames][both]
        r = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 1e-6 and np.std(b) > 1e-6 else 0.0
        rms = float(np.sqrt(np.mean(((a - a.mean()) - (b - b.mean())) ** 2)))
        rp = ctx.ref.result("dynamics", match.ref.id)
        up = ctx.user.result("dynamics", user.id)
        conf = ctx.conf(rp, up, match) if rp and up else match.align_confidence * 0.7
        envelopes.append({"phrase": match.ref.id, "correlation": round(r, 3)})
        out.append(
            make_comparison(
                "dynamics.contour",
                "phrase",
                match.ref.label,
                match.ref.id,
                user.id,
                _span(match.ref),
                _span(user),
                1.0,
                round(r, 4),
                1.0 - r,
                conf,
                1.0,
                evidence={
                    "correlation": round(r, 3),
                    "shape_rms_db": round(rms, 2),
                    "reference_shape": rp.value("shape") if rp else None,
                    "take_shape": up.value("shape") if up else None,
                },
            )
        )
        rv, uv = _num(rp, "mean_db"), _num(up, "mean_db")
        if rv is not None and uv is not None:
            out.append(
                make_comparison(
                    "dynamics.phrase_level",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rv,
                    uv,
                    uv - rv,
                    conf,
                    0.8,
                )
            )
    ctx.extras["dynamic_envelopes"] = envelopes
    last_notes = ctx.last_notes
    for match, user in matched(ctx.note_matches):
        rp = ctx.ref.result("dynamics", match.ref.id)
        up = ctx.user.result("dynamics", user.id)
        if rp is None or up is None:
            continue
        conf = ctx.conf(rp, up, match)
        importance = note_importance(match.ref, match.ref.id in last_notes)
        for metric_id, key, min_s in (
            ("dynamics.note_change", "change_db", 0.4),
            ("dynamics.emphasis", "emphasis_db", 0.0),
            ("dynamics.attack", "attack_rise_db", 0.0),
        ):
            if match.ref.duration_s < min_s:
                continue
            rv, uv = _num(rp, key), _num(up, key)
            if rv is None or uv is None:
                continue
            out.append(
                make_comparison(
                    metric_id,
                    "note",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rv,
                    uv,
                    uv - rv,
                    conf,
                    importance,
                    evidence={"reference_contour": rp.value("contour"), "take_contour": up.value("contour")}
                    if metric_id == "dynamics.note_change"
                    else None,
                )
            )
    return out


def compare_phonation(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    last_notes = ctx.last_notes
    for match, user in matched(ctx.note_matches):
        if match.ref.duration_s < 0.15:
            continue
        rq = ctx.ref.result("voice_quality", match.ref.id)
        uq = ctx.user.result("voice_quality", user.id)
        if rq is None or uq is None:
            continue
        conf = ctx.conf(rq, uq, match)
        importance = note_importance(match.ref, match.ref.id in last_notes)
        rl = ctx.ref.result("phonation", match.ref.id)
        ul = ctx.user.result("phonation", user.id)
        evidence = {
            "reference_label": rl.value("label") if rl else None,
            "take_label": ul.value("label") if ul else None,
            "reference_hnr_db": _num(rq, "hnr_db"),
            "take_hnr_db": _num(uq, "hnr_db"),
            "reference_cpps_db": _num(rq, "cpps_db"),
            "take_cpps_db": _num(uq, "cpps_db"),
        }
        for metric_id, key in (
            ("phonation.breathiness", "breathiness_index"),
            ("phonation.h1h2", "h1h2_db"),
            ("phonation.hnr", "hnr_db"),
            ("phonation.cpps", "cpps_db"),
        ):
            rv, uv = _num(rq, key), _num(uq, key)
            if rv is None or uv is None:
                continue
            out.append(
                make_comparison(
                    metric_id,
                    "note",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rv,
                    uv,
                    uv - rv,
                    conf,
                    importance,
                    evidence=evidence if metric_id == "phonation.breathiness" else None,
                )
            )
        rr = ctx.ref.result("register", match.ref.id)
        ur = ctx.user.result("register", user.id)
        if (
            rr
            and ur
            and rr.value("label") not in (None, "uncertain")
            and ur.value("label") not in (None, "uncertain")
            and rr.value("label") != ur.value("label")
        ):
            ctx.observations.append(
                {
                    "kind": "register",
                    "basis": "experimental",
                    "ref_start": match.ref.start_s,
                    "ref_end": match.ref.end_s,
                    "segment_id": match.ref.id,
                    "text": f"Register probably differs on {match.ref.label}: reference {rr.value('label')}, take {ur.value('label')}.",
                    "confidence": round(min(rr.confidence, ur.confidence), 3),
                }
            )
    for event_type in ("fry", "subharmonic"):
        ref_events = ctx.ref.events_of(event_type)
        user_events = ctx.user.events_of(event_type)
        for event in ref_events:
            us, ue = map_span(ctx.alignment, event.start_s, event.end_s)
            present = any(min(ue, e.end_s) - max(us, e.start_s) > -0.05 for e in user_events)
            if not present and event.confidence >= 0.5:
                ctx.observations.append(
                    {
                        "kind": event_type,
                        "basis": "experimental",
                        "ref_start": event.start_s,
                        "ref_end": event.end_s,
                        "segment_id": event.segment_id,
                        "text": f"The reference uses {event_type} here ({event.props.get('kind', event_type)}); it was not detected in the take.",
                        "confidence": round(event.confidence * 0.8, 3),
                    }
                )
    return out


def compare_articulation(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    ref_events = ctx.ref.events_of("consonant")
    user_events = ctx.user.events_of("consonant")
    ref_results = {r.segment_id: r for r in ctx.ref.results_for("articulation", "event")}
    user_results = {r.segment_id: r for r in ctx.user.results_for("articulation", "event")}
    for em in match_events(ref_events, user_events, ctx.alignment):
        rr = ref_results.get(em.ref.id)
        if rr is None:
            continue
        phoneme = rr.value("phoneme")
        label = f"/{phoneme}/ ({rr.value('kind')})" if phoneme else str(rr.value("kind"))
        if em.user is None:
            duration = em.ref.end_s - em.ref.start_s
            if (
                em.ref.confidence >= MISSING_CONSONANT_MIN_CONFIDENCE
                and duration >= MISSING_CONSONANT_MIN_S
                and em.ref.props.get("kind") in {"stop", "sibilant", "fricative"}
            ):
                out.append(
                    make_comparison(
                        "articulation.missing_consonant",
                        "event",
                        label,
                        em.ref.id,
                        None,
                        (em.ref.start_s, em.ref.end_s),
                        (em.mapped_start, em.mapped_end),
                        "present",
                        "not found",
                        -1.0,
                        pair_confidence(em.ref.confidence, 0.7, em.align_confidence) * 0.8,
                        0.8,
                        mismatch=True,
                    )
                )
            continue
        ur = user_results.get(em.user.id)
        if ur is None:
            continue
        conf = pair_confidence(rr.confidence, ur.confidence, em.align_confidence)
        for metric_id, key in (
            ("articulation.consonant_duration", "duration_ms"),
            ("articulation.cv_ratio", "cv_ratio_db"),
        ):
            rv, uv = _num(rr, key), _num(ur, key)
            if rv is None or uv is None:
                continue
            out.append(
                make_comparison(
                    metric_id,
                    "event",
                    label,
                    em.ref.id,
                    em.user.id,
                    (em.ref.start_s, em.ref.end_s),
                    (em.user.start_s, em.user.end_s),
                    rv,
                    uv,
                    uv - rv,
                    conf,
                    0.8,
                    evidence={
                        "kind": rr.value("kind"),
                        "position": rr.value("position"),
                        "reference_closure_ms": _num(rr, "closure_ms"),
                        "take_closure_ms": _num(ur, "closure_ms"),
                    },
                )
            )
    ref_onsets = [r for r in ctx.ref.results_for("articulation", "event") if r.value("kind") == "onset"]
    user_onsets = [r for r in ctx.user.results_for("articulation", "event") if r.value("kind") == "onset"]
    for match, user in matched(ctx.phrase_matches):
        ro = next(
            (r for r in ref_onsets if match.ref.start_s - 0.05 <= r.timestamp_start <= match.ref.end_s), None
        )
        uo = next(
            (r for r in user_onsets if user.start_s - 0.05 <= r.timestamp_start <= user.end_s),
            None,
        )
        if ro is None or uo is None:
            continue
        conf = pair_confidence(ro.confidence, uo.confidence, match.align_confidence)
        if conf < ONSET_LABEL_MIN_CONFIDENCE:
            continue
        rt, ut = ro.value("onset_type"), uo.value("onset_type")
        out.append(
            make_comparison(
                "articulation.onset_type",
                "phrase",
                match.ref.label,
                match.ref.id,
                user.id,
                _span(match.ref),
                _span(user),
                rt,
                ut,
                1.0 if rt != ut else 0.0,
                conf,
                0.8,
                evidence={"reference_rise_ms": _num(ro, "rise_ms"), "take_rise_ms": _num(uo, "rise_ms")},
                mismatch=rt != ut,
            )
        )
    return out


def compare_breath(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    ref_breaths = {
        int(e.props["before_phrase"]): e
        for e in ctx.ref.events_of("breath")
        if e.props.get("before_phrase") is not None
    }
    user_breaths = {
        int(e.props["before_phrase"]): e
        for e in ctx.user.events_of("breath")
        if e.props.get("before_phrase") is not None
    }
    ref_phrases = ctx.ref.by_level("phrase")
    user_phrases = ctx.user.by_level("phrase")
    for match, user in matched(ctx.phrase_matches):
        ri = ref_phrases.index(match.ref)
        ui = user_phrases.index(user)
        rb, ub = ref_breaths.get(ri), user_breaths.get(ui)
        rpr = ctx.ref.result("breath", match.ref.id)
        upr = ctx.user.result("breath", user.id)
        base_conf = pair_confidence(
            rpr.confidence if rpr else 0.5, upr.confidence if upr else 0.5, match.align_confidence
        )
        if ri > 0 or rb is not None or ub is not None:
            confidence = base_conf * max(rb.confidence if rb else 0.6, ub.confidence if ub else 0.6)
            out.append(
                make_comparison(
                    "breath.presence",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    (rb.start_s, rb.end_s) if rb else (match.ref.start_s - 0.4, match.ref.start_s),
                    (ub.start_s, ub.end_s) if ub else (user.start_s - 0.4, user.start_s),
                    "breath" if rb else "no breath",
                    "breath" if ub else "no breath",
                    float(ub is not None) - float(rb is not None),
                    confidence,
                    0.8,
                    mismatch=(rb is not None) != (ub is not None),
                )
            )
        if rb is not None and ub is not None:
            conf = base_conf * min(rb.confidence, ub.confidence)
            out.append(
                make_comparison(
                    "breath.duration",
                    "event",
                    match.ref.label,
                    rb.id,
                    ub.id,
                    (rb.start_s, rb.end_s),
                    (ub.start_s, ub.end_s),
                    (rb.end_s - rb.start_s) * 1000.0,
                    (ub.end_s - ub.start_s) * 1000.0,
                    ((ub.end_s - ub.start_s) - (rb.end_s - rb.start_s)) * 1000.0,
                    conf,
                    0.6,
                )
            )
            rl, ul = float(rb.props.get("level_rel_db", 0.0)), float(ub.props.get("level_rel_db", 0.0))
            out.append(
                make_comparison(
                    "breath.level",
                    "event",
                    match.ref.label,
                    rb.id,
                    ub.id,
                    (rb.start_s, rb.end_s),
                    (ub.start_s, ub.end_s),
                    rl,
                    ul,
                    ul - rl,
                    conf,
                    0.6,
                )
            )
        rv, uv = _num(rpr, "end_cpps_change_db"), _num(upr, "end_cpps_change_db")
        if rv is not None and uv is not None:
            end = match.ref.end_s
            out.append(
                make_comparison(
                    "breath.phrase_end",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    (max(match.ref.start_s, end - 0.3), end),
                    (max(user.start_s, user.end_s - 0.3), user.end_s),
                    rv,
                    uv,
                    uv - rv,
                    base_conf * 0.8,
                    0.7,
                )
            )
    return out


def compare_timbre(ctx: CompareContext) -> list[MetricComparison]:
    out: list[MetricComparison] = []
    for match, user in matched(ctx.phrase_matches):
        rt = ctx.ref.result("timbre", match.ref.id)
        ut = ctx.user.result("timbre", user.id)
        if rt is None or ut is None:
            continue
        conf = ctx.conf(rt, ut, match)
        keys = [k for k in rt.values if k.startswith("band_") and _band_in_range(k)]
        diffs: dict[str, float] = {}
        for key in keys:
            rv, uv = _num(rt, key), _num(ut, key)
            if rv is not None and uv is not None:
                diffs[key] = uv - rv
        if diffs:
            offset = float(np.mean(list(diffs.values())))
            centered = {k: v - offset for k, v in diffs.items()}
            worst = max(centered, key=lambda k: abs(centered[k]))
            lo, hi = worst.split("_")[1:3]
            out.append(
                make_comparison(
                    "timbre.band_balance",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    _num(rt, worst),
                    _num(ut, worst),
                    centered[worst],
                    conf,
                    0.8,
                    evidence={
                        "band": f"{lo}-{hi} Hz",
                        "band_differences_db": {
                            k.replace("band_", "").replace("_db", "").replace("_", "-") + " Hz": round(v, 2)
                            for k, v in centered.items()
                        },
                    },
                )
            )
        rc, uc = _num(rt, "centroid_hz"), _num(ut, "centroid_hz")
        if rc and uc:
            out.append(
                make_comparison(
                    "timbre.centroid",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rc,
                    uc,
                    (uc / rc - 1.0) * 100.0,
                    conf,
                    0.8,
                )
            )
        rs, us = _num(rt, "spr_db"), _num(ut, "spr_db")
        if rs is not None and us is not None:
            out.append(
                make_comparison(
                    "timbre.spr",
                    "phrase",
                    match.ref.label,
                    match.ref.id,
                    user.id,
                    _span(match.ref),
                    _span(user),
                    rs,
                    us,
                    us - rs,
                    conf,
                    0.8,
                )
            )
    ref_embedding = next(
        (
            r.raw_supporting_data.get("embedding")
            for r in ctx.ref.results_for("timbre")
            if r.segment_id is None and r.raw_supporting_data.get("embedding")
        ),
        None,
    )
    user_embedding = next(
        (
            r.raw_supporting_data.get("embedding")
            for r in ctx.user.results_for("timbre")
            if r.segment_id is None and r.raw_supporting_data.get("embedding")
        ),
        None,
    )
    if ref_embedding and user_embedding:
        a = np.asarray(ref_embedding, dtype=np.float64)
        b = np.asarray(user_embedding, dtype=np.float64)
        cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        ctx.extras["embedding_similarity"] = {
            "kind": "MFCC statistics (non-learned baseline)",
            "cosine_similarity": round(cosine, 4),
            "note": "Kept separate from the interpretable scores. It reflects overall spectral similarity, which includes voice identity, and is not a measure of how well you copied the performance.",
        }
    return out


def _band_in_range(key: str) -> bool:
    try:
        lo = int(key.split("_")[1])
        hi = int(key.split("_")[2])
    except (IndexError, ValueError):
        return False
    return lo >= LOW_BAND_LIMIT_HZ and hi <= HIGH_BAND_LIMIT_HZ


CATEGORY_FUNCTIONS = {
    "pitch": compare_pitch,
    "timing": compare_timing,
    "vowel": compare_vowels,
    "vibrato": compare_vibrato,
    "dynamics": compare_dynamics,
    "phonation": compare_phonation,
    "articulation": compare_articulation,
    "breath": compare_breath,
    "timbre": compare_timbre,
}
