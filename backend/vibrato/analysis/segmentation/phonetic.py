from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter1d

from ...dsp.framing import runs
from ..features import FeatureSet

CLASSES = ("SIL", "BREATH", "VOWEL", "SON", "VFRIC", "FRIC", "SIB", "CLOSURE", "BURST", "ASP")
CLASS_INDEX = {name: index for index, name in enumerate(CLASSES)}
CLASS_LABELS = {
    "SIL": "silence",
    "BREATH": "breath",
    "VOWEL": "vowel",
    "SON": "voiced consonant",
    "VFRIC": "voiced fricative",
    "FRIC": "fricative",
    "SIB": "sibilant",
    "CLOSURE": "stop closure",
    "BURST": "release burst",
    "ASP": "aspiration",
}
CONSONANT_CLASSES = {"SON", "VFRIC", "FRIC", "SIB", "CLOSURE", "BURST", "ASP"}
LOCAL_MAX_FRAMES = 51
SONORANT_DIP_DB = -7.0
SILENCE_MARGIN_DB = 8.0
SILENCE_REL_DB = -48.0
SIBILANT_RATIO_DB = 2.0
SIBILANT_CENTROID_HZ = 4000.0
FRICATIVE_RATIO_DB = -8.0
FRICATIVE_CENTROID_HZ = 3000.0
VOICED_FRICATIVE_RATIO_DB = -6.0
VOICED_FRICATIVE_MAX_HNR = 12.0
BURST_JUMP_DB = 12.0


@dataclass
class ClassSegment:
    cls: str
    start: int
    end: int
    confidence: float


def silence_threshold_rel(fs: FeatureSet) -> float:
    floor_rel = float(fs.meta.get("noise_floor_db", -90.0)) - float(fs.meta.get("active_level_db", -20.0))
    return max(floor_rel + SILENCE_MARGIN_DB, SILENCE_REL_DB)


def classify_frames(
    fs: FeatureSet, phrase_mask: np.ndarray, breath_mask: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    level = fs.tracks["level_rel_db"]
    voiced = fs.voiced
    sib = np.nan_to_num(fs.tracks["sibilance_ratio_db"], nan=-40.0)
    centroid = np.nan_to_num(fs.tracks["centroid_hz"], nan=0.0)
    hnr = np.nan_to_num(fs.tracks["hnr_db"], nan=0.0)
    local_max = maximum_filter1d(level, size=LOCAL_MAX_FRAMES, mode="nearest")
    dip = level - local_max
    silent = level < silence_threshold_rel(fs)
    labels = np.full(fs.n, CLASS_INDEX["SIL"], dtype=np.int16)
    margin = np.zeros(fs.n)

    vfric = voiced & (sib > VOICED_FRICATIVE_RATIO_DB) & (hnr < VOICED_FRICATIVE_MAX_HNR)
    son = voiced & ~vfric & (dip < SONORANT_DIP_DB)
    vowel = voiced & ~vfric & ~son
    unvoiced = ~voiced
    sibilant = unvoiced & ~silent & (sib > SIBILANT_RATIO_DB) & (centroid > SIBILANT_CENTROID_HZ)
    fric = unvoiced & ~silent & ~sibilant & ((sib > FRICATIVE_RATIO_DB) | (centroid > FRICATIVE_CENTROID_HZ))
    asp = unvoiced & ~silent & ~sibilant & ~fric
    closure = unvoiced & silent

    inside = phrase_mask
    labels[inside & vowel] = CLASS_INDEX["VOWEL"]
    labels[inside & son] = CLASS_INDEX["SON"]
    labels[inside & vfric] = CLASS_INDEX["VFRIC"]
    labels[inside & sibilant] = CLASS_INDEX["SIB"]
    labels[inside & fric] = CLASS_INDEX["FRIC"]
    labels[inside & asp] = CLASS_INDEX["ASP"]
    labels[inside & closure] = CLASS_INDEX["CLOSURE"]
    labels[~inside & breath_mask] = CLASS_INDEX["BREATH"]

    jump = np.zeros(fs.n)
    jump[2:] = level[2:] - np.minimum(level[:-2], level[1:-1])
    previous_quiet = np.zeros(fs.n, dtype=bool)
    previous_quiet[2:] = (labels[1:-1] == CLASS_INDEX["CLOSURE"]) | (labels[:-2] == CLASS_INDEX["CLOSURE"])
    burst = inside & previous_quiet & (jump > BURST_JUMP_DB) & unvoiced
    labels[burst] = CLASS_INDEX["BURST"]

    margin[vowel] = np.clip((dip[vowel] - SONORANT_DIP_DB) / 6.0, 0.0, 1.0)
    margin[son] = np.clip((SONORANT_DIP_DB - dip[son]) / 6.0, 0.0, 1.0)
    margin[sibilant] = np.clip((sib[sibilant] - SIBILANT_RATIO_DB) / 8.0, 0.0, 1.0)
    margin[fric] = np.clip((sib[fric] - FRICATIVE_RATIO_DB) / 8.0, 0.2, 1.0)
    margin[asp] = 0.4
    margin[closure] = 0.8
    margin[burst] = np.clip((jump[burst] - BURST_JUMP_DB) / 10.0, 0.3, 1.0)
    margin[labels == CLASS_INDEX["SIL"]] = 0.9
    margin[labels == CLASS_INDEX["BREATH"]] = 0.6
    labels = _mode_filter(labels, 3)
    return labels, margin


def _mode_filter(labels: np.ndarray, width: int) -> np.ndarray:
    out = labels.copy()
    half = width // 2
    for index in range(half, len(labels) - half):
        window = labels[index - half : index + half + 1]
        if window[0] == window[-1] and labels[index] != window[0]:
            out[index] = window[0]
    return out


def class_segments(labels: np.ndarray, margin: np.ndarray, min_frames: int = 2) -> list[ClassSegment]:
    segments: list[ClassSegment] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            segments.append(
                ClassSegment(CLASSES[int(labels[start])], start, index, float(np.mean(margin[start:index])))
            )
            start = index
    merged: list[ClassSegment] = []
    for segment in segments:
        keep_short = segment.cls == "BURST"
        if merged and segment.end - segment.start < min_frames and not keep_short:
            merged[-1] = ClassSegment(merged[-1].cls, merged[-1].start, segment.end, merged[-1].confidence)
        elif merged and merged[-1].cls == segment.cls:
            merged[-1] = ClassSegment(
                segment.cls, merged[-1].start, segment.end, 0.5 * (merged[-1].confidence + segment.confidence)
            )
        else:
            merged.append(segment)
    return merged


def breath_like_mask(fs: FeatureSet) -> np.ndarray:
    level = fs.tracks["level_rel_db"]
    floor_rel = float(fs.meta.get("noise_floor_db", -90.0)) - float(fs.meta.get("active_level_db", -20.0))
    centroid = np.nan_to_num(fs.tracks["centroid_hz"], nan=0.0)
    sib = np.nan_to_num(fs.tracks["sibilance_ratio_db"], nan=-40.0)
    flatness = np.nan_to_num(fs.tracks["flatness"], nan=0.0)
    return (
        ~fs.voiced
        & (level > floor_rel + 6.0)
        & (level < -10.0)
        & (centroid > 400.0)
        & (centroid < 5500.0)
        & (sib < 2.0)
        & (flatness > 0.01)
    )


def runs_of(labels: np.ndarray, name: str) -> list[tuple[int, int]]:
    return runs(labels == CLASS_INDEX[name])
