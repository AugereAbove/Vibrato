from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy import signal

from ..features import FeatureSet
from .phonetic import ClassSegment
from .phrases import PhraseSpan

NUCLEUS_MIN_FRAMES = 5
DIP_SPLIT_DB = 3.0
DIP_MIN_SIDE_FRAMES = 6
STOP_UNIT = {"CLOSURE", "BURST", "ASP"}


@dataclass
class SyllableSpan:
    start: int
    end: int
    nucleus_start: int
    nucleus_end: int
    confidence: float
    phrase_index: int


def _split_on_dips(level: np.ndarray, start: int, end: int) -> list[tuple[int, int]]:
    if end - start < 2 * DIP_MIN_SIDE_FRAMES + 1:
        return [(start, end)]
    smooth = np.convolve(level[start:end], np.ones(5) / 5.0, mode="same")
    minima, _ = signal.find_peaks(-smooth, prominence=DIP_SPLIT_DB, distance=DIP_MIN_SIDE_FRAMES)
    cuts = [start + int(m) for m in minima if DIP_MIN_SIDE_FRAMES <= m <= (end - start) - DIP_MIN_SIDE_FRAMES]
    edges = [start, *cuts, end]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _consonant_units(segments: list[ClassSegment]) -> list[list[ClassSegment]]:
    units: list[list[ClassSegment]] = []
    for segment in segments:
        if segment.cls == "SIL":
            continue
        if units and segment.cls in {"BURST", "ASP"} and units[-1][-1].cls in {"CLOSURE", "BURST"}:
            units[-1].append(segment)
        else:
            units.append([segment])
    return units


def segment_syllables(
    fs: FeatureSet, phrases: list[PhraseSpan], class_segments: list[ClassSegment]
) -> list[SyllableSpan]:
    level = fs.tracks["level_rel_db"]
    syllables: list[SyllableSpan] = []
    for phrase_index, phrase in enumerate(phrases):
        inside = [s for s in class_segments if s.end > phrase.start and s.start < phrase.end]
        nuclei: list[tuple[int, int, float]] = []
        for segment in inside:
            if segment.cls != "VOWEL":
                continue
            a = max(segment.start, phrase.start)
            b = min(segment.end, phrase.end)
            if nuclei and a - nuclei[-1][1] <= 2:
                prev = nuclei.pop()
                a = prev[0]
            for piece in _split_on_dips(level, a, b):
                nuclei.append((piece[0], piece[1], segment.confidence))
        nuclei = [n for n in nuclei if n[1] - n[0] >= NUCLEUS_MIN_FRAMES] or nuclei[:1]
        if not nuclei:
            continue
        boundaries = [phrase.start]
        for current, following in pairwise(nuclei):
            between = [
                s
                for s in inside
                if s.start >= current[1] - 1 and s.end <= following[0] + 1 and s.cls not in {"VOWEL"}
            ]
            units = _consonant_units(between)
            if units:
                boundary = units[-1][0].start
            else:
                window = level[current[1] - 1 : following[0] + 1]
                boundary = current[1] - 1 + int(np.argmin(window)) if window.size else current[1]
            boundary = int(np.clip(boundary, current[1], following[0]))
            boundaries.append(boundary)
        boundaries.append(phrase.end)
        for index, nucleus in enumerate(nuclei):
            start, end = boundaries[index], boundaries[index + 1]
            if end <= start:
                continue
            confidence = float(np.clip(0.45 + 0.5 * nucleus[2], 0.0, 0.95))
            syllables.append(
                SyllableSpan(start, end, nucleus[0], nucleus[1], round(confidence, 3), phrase_index)
            )
    return syllables


def split_at_note_boundaries(
    syllables: list[SyllableSpan], note_starts: list[int], min_side: int = DIP_MIN_SIDE_FRAMES
) -> tuple[list[SyllableSpan], set[int]]:
    result: list[SyllableSpan] = []
    pitch_split: set[int] = set()
    for syllable in syllables:
        cuts = [
            b
            for b in note_starts
            if syllable.nucleus_start + min_side <= b <= syllable.nucleus_end - min_side
        ]
        if not cuts:
            result.append(syllable)
            continue
        edges = [syllable.start, *cuts, syllable.end]
        nucleus_edges = [syllable.nucleus_start, *cuts, syllable.nucleus_end]
        for index in range(len(edges) - 1):
            if index > 0:
                pitch_split.add(len(result))
            result.append(
                SyllableSpan(
                    start=edges[index],
                    end=edges[index + 1],
                    nucleus_start=nucleus_edges[index],
                    nucleus_end=nucleus_edges[index + 1],
                    confidence=round(syllable.confidence * 0.8, 3),
                    phrase_index=syllable.phrase_index,
                )
            )
    return result, pitch_split
