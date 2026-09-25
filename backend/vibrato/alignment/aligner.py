from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from ..analysis.features import FeatureSet
from ..analysis.segmentation.hierarchy import Hierarchy
from ..dsp.framing import HOP_S, moving_average
from ..dsp.music import hz_to_midi
from .dtw import banded_dtw, fix_band, multiscale_dtw

ALIGNMENT_VERSION = "align/1.2"
EDGE_PAD_S = 0.25
MFCC_COEFFICIENTS = 12
WEIGHTS = {"mfcc": 1.0, "pitch": 1.6, "voicing": 1.2, "level": 0.6, "onset": 0.5}
PITCH_CLIP_ST = 6.0
CONFIDENCE_SMOOTH_FRAMES = 15
NULL_SAMPLES = 3000
SLOPE_LIMITS = (0.33, 3.0)
TRANSPOSITION_MIN_ST = 0.75
REALIGN_RADIUS_S = 0.5


@dataclass
class Anchor:
    ref_time_s: float
    user_time_s: float
    locked: bool = True
    source: str = "manual"
    id: str | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ref_time_s": self.ref_time_s,
            "user_time_s": self.user_time_s,
            "locked": self.locked,
            "source": self.source,
            "label": self.label,
        }


@dataclass
class Alignment:
    ref_times: np.ndarray
    user_times: np.ndarray
    confidence: np.ndarray
    overall_confidence: float
    global_offset_s: float
    tempo_ratio: float
    transposition_semitones: float
    pitch_offset_cents: float | None
    method: str
    anchors: list[Anchor] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ref_range: tuple[float, float] = (0.0, 0.0)
    user_range: tuple[float, float] = (0.0, 0.0)
    version: str = ALIGNMENT_VERSION

    def ref_to_user(self, t: float | np.ndarray) -> np.ndarray:
        values = np.asarray(t, dtype=np.float64)
        out = np.interp(values, self.ref_times, self.user_times)
        before = values < self.ref_times[0]
        after = values > self.ref_times[-1]
        out = np.where(before, self.user_times[0] + (values - self.ref_times[0]), out)
        return np.where(after, self.user_times[-1] + (values - self.ref_times[-1]), out)

    def user_to_ref(self, t: float | np.ndarray) -> np.ndarray:
        values = np.asarray(t, dtype=np.float64)
        order = np.argsort(self.user_times, kind="stable")
        out = np.interp(values, self.user_times[order], self.ref_times[order])
        before = values < self.user_times[0]
        after = values > self.user_times[-1]
        out = np.where(before, self.ref_times[0] + (values - self.user_times[0]), out)
        return np.where(after, self.ref_times[-1] + (values - self.user_times[-1]), out)

    def confidence_at(self, t: float | np.ndarray) -> np.ndarray:
        return np.interp(
            np.asarray(t, dtype=np.float64), self.ref_times, self.confidence, left=0.0, right=0.0
        )

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "method": self.method,
            "overall_confidence": round(self.overall_confidence, 3),
            "global_offset_s": round(self.global_offset_s, 4),
            "tempo_ratio": round(self.tempo_ratio, 4),
            "transposition_semitones": round(self.transposition_semitones, 3),
            "pitch_offset_cents": None
            if self.pitch_offset_cents is None
            else round(self.pitch_offset_cents, 1),
            "warnings": self.warnings,
            "ref_range": [round(v, 3) for v in self.ref_range],
            "user_range": [round(v, 3) for v in self.user_range],
            "anchors": [a.to_dict() for a in self.anchors],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp.npz")
        np.savez_compressed(
            tmp,
            ref_times=self.ref_times.astype(np.float32),
            user_times=self.user_times.astype(np.float32),
            confidence=self.confidence.astype(np.float32),
            summary=np.frombuffer(json.dumps(self.summary()).encode("utf-8"), dtype=np.uint8),
        )
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> Alignment:
        with np.load(path) as data:
            summary = json.loads(bytes(data["summary"]).decode("utf-8"))
            return cls(
                ref_times=data["ref_times"].astype(np.float64),
                user_times=data["user_times"].astype(np.float64),
                confidence=data["confidence"].astype(np.float64),
                overall_confidence=float(summary["overall_confidence"]),
                global_offset_s=float(summary["global_offset_s"]),
                tempo_ratio=float(summary["tempo_ratio"]),
                transposition_semitones=float(summary["transposition_semitones"]),
                pitch_offset_cents=summary.get("pitch_offset_cents"),
                method=str(summary["method"]),
                anchors=[
                    Anchor(
                        a["ref_time_s"],
                        a["user_time_s"],
                        bool(a["locked"]),
                        a.get("source", "manual"),
                        a.get("id"),
                        a.get("label", ""),
                    )
                    for a in summary.get("anchors", [])
                ],
                warnings=list(summary.get("warnings", [])),
                ref_range=tuple(summary.get("ref_range", [0.0, 0.0])),
                user_range=tuple(summary.get("user_range", [0.0, 0.0])),
                version=str(summary.get("version", ALIGNMENT_VERSION)),
            )


def alignment_features(fs: FeatureSet) -> np.ndarray:
    mfcc = fs.matrices["mfcc"][1 : MFCC_COEFFICIENTS + 1].T.astype(np.float64)
    level = fs.tracks["level_rel_db"]
    active = level > -40.0
    if active.sum() >= 10:
        mean = mfcc[active].mean(axis=0)
        std = mfcc[active].std(axis=0) + 1e-6
    else:
        mean = mfcc.mean(axis=0)
        std = mfcc.std(axis=0) + 1e-6
    mfcc_norm = (mfcc - mean) / std / np.sqrt(MFCC_COEFFICIENTS)
    midi = hz_to_midi(fs.tracks["f0_hz"])
    voiced = np.isfinite(midi)
    median = float(np.median(midi[voiced])) if voiced.any() else 60.0
    pitch = np.where(voiced, np.clip(midi - median, -PITCH_CLIP_ST, PITCH_CLIP_ST) / PITCH_CLIP_ST, 0.0)
    level_scaled = np.clip((level + 40.0) / 40.0, 0.0, 1.2)
    onset = np.clip(np.gradient(moving_average(level, 3)) / 6.0, -1.0, 1.0)
    return np.column_stack(
        [
            mfcc_norm * WEIGHTS["mfcc"],
            pitch * WEIGHTS["pitch"],
            voiced.astype(np.float64) * WEIGHTS["voicing"],
            level_scaled * WEIGHTS["level"],
            np.nan_to_num(onset) * WEIGHTS["onset"],
        ]
    )


def active_range(hierarchy: Hierarchy, duration: float) -> tuple[float, float]:
    phrases = hierarchy.by_level("phrase")
    if not phrases:
        return 0.0, duration
    return max(0.0, phrases[0].start_s - EDGE_PAD_S), min(duration, phrases[-1].end_s + EDGE_PAD_S)


def rf(t: float) -> int:
    return round(t / HOP_S)


def _segment_path(
    a: np.ndarray, b: np.ndarray, synced_offset: int | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return multiscale_dtw(a, b, synced_offset=synced_offset)


def _null_cost(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> float:
    ia = rng.integers(0, a.shape[0], NULL_SAMPLES)
    ib = rng.integers(0, b.shape[0], NULL_SAMPLES)
    return float(np.median(np.linalg.norm(a[ia] - b[ib], axis=1))) or 1.0


def _mapping_from_path(
    path_i: np.ndarray, path_j: np.ndarray, costs: np.ndarray, n: int
) -> tuple[np.ndarray, np.ndarray]:
    sums = np.zeros(n)
    counts = np.zeros(n)
    cost_sums = np.zeros(n)
    np.add.at(sums, path_i, path_j)
    np.add.at(counts, path_i, 1.0)
    np.add.at(cost_sums, path_i, costs)
    counts = np.maximum(counts, 1.0)
    mapping = sums / counts
    mapping = np.maximum.accumulate(mapping)
    return mapping, cost_sums / counts


def _local_confidence(
    costs: np.ndarray,
    mapping: np.ndarray,
    null: float,
    ref_voiced: np.ndarray,
    user_voiced_mapped: np.ndarray,
) -> np.ndarray:
    smoothed = moving_average(costs, CONFIDENCE_SMOOTH_FRAMES)
    ratio = smoothed / max(null, 1e-9)
    conf = np.clip((0.95 - ratio) / 0.55, 0.0, 1.0)
    slope = np.gradient(moving_average(mapping, 9))
    extreme = (slope < SLOPE_LIMITS[0]) | (slope > SLOPE_LIMITS[1])
    conf = np.where(extreme, conf * 0.5, conf)
    agreement = moving_average((ref_voiced == user_voiced_mapped).astype(np.float64), 11)
    return np.clip(conf * (0.6 + 0.4 * agreement), 0.0, 1.0)


def align(
    ref_fs: FeatureSet,
    user_fs: FeatureSet,
    ref_h: Hierarchy,
    user_h: Hierarchy,
    anchors: list[Anchor] | None = None,
    synced: bool = False,
    latency_s: float = 0.0,
    ref_region: tuple[float, float] | None = None,
    seed: int = 0,
) -> Alignment:
    rng = np.random.default_rng(seed)
    a_all = alignment_features(ref_fs)
    b_all = alignment_features(user_fs)
    ref_start, ref_end = ref_region if ref_region else active_range(ref_h, ref_fs.duration_s)
    user_start, user_end = active_range(user_h, user_fs.duration_s)
    if ref_region:
        ref_start = max(0.0, ref_start - EDGE_PAD_S)
        ref_end = min(ref_fs.duration_s, ref_end + EDGE_PAD_S)
    locked = sorted(
        [
            x
            for x in (anchors or [])
            if x.locked and ref_start < x.ref_time_s < ref_end and user_start < x.user_time_s < user_end
        ],
        key=lambda x: x.ref_time_s,
    )
    monotone: list[Anchor] = []
    for anchor in locked:
        if not monotone or anchor.user_time_s > monotone[-1].user_time_s:
            monotone.append(anchor)
    points = (
        [(ref_start, user_start)] + [(x.ref_time_s, x.user_time_s) for x in monotone] + [(ref_end, user_end)]
    )
    warnings: list[str] = []
    if synced:
        points = (
            [(ref_start, ref_start + latency_s)]
            + [(x.ref_time_s, x.user_time_s) for x in monotone]
            + [(ref_end, min(user_fs.duration_s, ref_end + latency_s))]
        )
    n_total = rf(ref_end) - rf(ref_start) + 1
    mapping_parts: list[np.ndarray] = []
    cost_parts: list[np.ndarray] = []
    for (r0, u0), (r1, u1) in pairwise(points):
        i0, i1 = rf(r0), max(rf(r0) + 1, rf(r1))
        j0, j1 = rf(u0), max(rf(u0) + 1, rf(u1))
        i1 = min(i1, a_all.shape[0] - 1)
        j1 = min(j1, b_all.shape[0] - 1)
        a = a_all[i0 : i1 + 1]
        b = b_all[j0 : j1 + 1]
        synced_offset = 0 if synced else None
        path_i, path_j, costs = _segment_path(a, b, synced_offset)
        mapping, local = _mapping_from_path(path_i, path_j, costs, a.shape[0])
        if mapping_parts:
            mapping = mapping[1:]
            local = local[1:]
        mapping_parts.append(mapping + j0)
        cost_parts.append(local)
    mapping = np.concatenate(mapping_parts)[:n_total]
    costs = np.concatenate(cost_parts)[:n_total]
    ref_frames = np.arange(rf(ref_start), rf(ref_start) + mapping.size)
    ref_times = ref_frames * HOP_S
    user_times = mapping * HOP_S
    null = _null_cost(a_all[rf(ref_start) : rf(ref_end)], b_all[rf(user_start) : rf(user_end)], rng)
    ref_voiced = ref_fs.voiced[np.clip(ref_frames, 0, ref_fs.n - 1)]
    user_voiced = user_fs.voiced[np.clip(np.round(mapping).astype(int), 0, user_fs.n - 1)]
    confidence = _local_confidence(costs, mapping, null, ref_voiced, user_voiced)
    active = ref_fs.tracks["level_rel_db"][np.clip(ref_frames, 0, ref_fs.n - 1)] > -40.0
    overall = float(np.mean(confidence[active])) if active.any() else float(np.mean(confidence))
    if overall < 0.4:
        warnings.append(
            "Alignment confidence is low: the take may contain different material, long improvisations, or heavy noise. Consider adding manual anchors."
        )
    fit = np.polyfit(ref_times[active], user_times[active], 1) if active.sum() >= 10 else np.array([1.0, 0.0])
    tempo_ratio = float(fit[0])
    offset = float(user_times[0] - ref_times[0])
    ref_midi = hz_to_midi(ref_fs.tracks["f0_hz"])[np.clip(ref_frames, 0, ref_fs.n - 1)]
    user_midi = hz_to_midi(user_fs.tracks["f0_hz"])[np.clip(np.round(mapping).astype(int), 0, user_fs.n - 1)]
    both = np.isfinite(ref_midi) & np.isfinite(user_midi) & (confidence > 0.4)
    transposition = 0.0
    pitch_offset = None
    if both.sum() >= 20 and overall >= 0.4:
        median = float(np.median(user_midi[both] - ref_midi[both]))
        if abs(median) >= TRANSPOSITION_MIN_ST:
            transposition = float(round(median))
            warnings.append(
                f"The take is transposed by {transposition:+.0f} semitones relative to the reference; pitch is compared after removing this shift."
            )
        pitch_offset = (median - transposition) * 100.0
    if tempo_ratio < 0.7 or tempo_ratio > 1.4:
        warnings.append(f"The overall tempo differs strongly from the reference (ratio {tempo_ratio:.2f}).")
    method = "multiscale DTW (MFCC, relative pitch, voicing, level, onsets)"
    if synced:
        method += ", constrained to the synced recording timeline"
    if monotone:
        method += f", {len(monotone)} locked anchor(s)"
    return Alignment(
        ref_times=ref_times,
        user_times=user_times,
        confidence=confidence,
        overall_confidence=overall,
        global_offset_s=offset,
        tempo_ratio=tempo_ratio,
        transposition_semitones=transposition,
        pitch_offset_cents=pitch_offset,
        method=method,
        anchors=list(anchors or []),
        warnings=warnings,
        ref_range=(ref_start, ref_end),
        user_range=(user_start, user_end),
    )


def realign_region(
    alignment: Alignment, ref_fs: FeatureSet, user_fs: FeatureSet, start_s: float, end_s: float
) -> Alignment:
    a_all = alignment_features(ref_fs)
    b_all = alignment_features(user_fs)
    r0 = round(max(alignment.ref_times[0], start_s) / HOP_S)
    r1 = round(min(alignment.ref_times[-1], end_s) / HOP_S)
    if r1 - r0 < 5:
        return alignment
    u0 = round(float(alignment.ref_to_user(r0 * HOP_S)) / HOP_S)
    u1 = round(float(alignment.ref_to_user(r1 * HOP_S)) / HOP_S)
    a = a_all[r0 : r1 + 1]
    b = b_all[u0 : u1 + 1]
    radius = int(REALIGN_RADIUS_S / HOP_S)
    slope = (b.shape[0] - 1) / max(1, a.shape[0] - 1)
    centers = slope * np.arange(a.shape[0])
    lo, hi = fix_band(
        np.floor(centers - radius).astype(np.int64), np.ceil(centers + radius).astype(np.int64), b.shape[0]
    )
    path_i, path_j, costs = banded_dtw(a, b, lo, hi, 0.05)
    mapping, _ = _mapping_from_path(path_i, path_j, costs, a.shape[0])
    ref_times = alignment.ref_times.copy()
    user_times = alignment.user_times.copy()
    first = int(np.searchsorted(ref_times, r0 * HOP_S - 1e-9))
    count = min(mapping.size, ref_times.size - first)
    user_times[first : first + count] = (mapping[:count] + u0) * HOP_S
    user_times = np.maximum.accumulate(user_times)
    return Alignment(
        ref_times=ref_times,
        user_times=user_times,
        confidence=alignment.confidence,
        overall_confidence=alignment.overall_confidence,
        global_offset_s=alignment.global_offset_s,
        tempo_ratio=alignment.tempo_ratio,
        transposition_semitones=alignment.transposition_semitones,
        pitch_offset_cents=alignment.pitch_offset_cents,
        method=alignment.method + f", region {start_s:.2f}-{end_s:.2f} s realigned",
        anchors=alignment.anchors,
        warnings=alignment.warnings,
        ref_range=alignment.ref_range,
        user_range=alignment.user_range,
    )
