from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...dsp.framing import runs
from ..features import FeatureSet
from .phonetic import breath_like_mask, silence_threshold_rel

PHRASE_GAP_S = 0.25
BREATH_SPLIT_MIN_GAP_S = 0.12
MIN_BREATH_S = 0.1
MAX_BREATH_S = 1.6
MIN_PHRASE_VOICED_S = 0.15
VOICED_CORE_LEVEL_DB = -32.0
CONSONANT_EXTENSION_S = 0.32
MAX_CLOSURE_FRAMES = 12
ATTACHED_ASPIRATION_FRAMES = 10
SECTION_GAP_S = 2.0


@dataclass
class PhraseSpan:
    start: int
    end: int
    voiced_frames: int


@dataclass
class BreathSpan:
    start: int
    end: int
    level_rel_db: float
    centroid_hz: float
    confidence: float
    before_phrase: int | None


def _breath_frames_in(mask: np.ndarray, start: int, end: int) -> int:
    best = 0
    for a, b in runs(mask[start:end]):
        best = max(best, b - a)
    return best


def detect_phrases(fs: FeatureSet) -> list[PhraseSpan]:
    level = fs.tracks["level_rel_db"]
    core = fs.voiced & (level > VOICED_CORE_LEVEL_DB)
    breathy = breath_like_mask(fs)
    groups: list[list[int]] = []
    for start, end in runs(core):
        if groups:
            gap = (start - groups[-1][1]) * fs.hop_s
            breath_in_gap = _breath_frames_in(breathy, groups[-1][1], start) * fs.hop_s
            split = gap > PHRASE_GAP_S or (gap > BREATH_SPLIT_MIN_GAP_S and breath_in_gap >= MIN_BREATH_S)
            if not split:
                groups[-1][1] = end
                groups[-1][2] += end - start
                continue
        groups.append([start, end, end - start])
    silent_rel = silence_threshold_rel(fs)
    extension = round(CONSONANT_EXTENSION_S / fs.hop_s)
    phrases: list[PhraseSpan] = []
    for index, (start, end, voiced_count) in enumerate(groups):
        if voiced_count * fs.hop_s < MIN_PHRASE_VOICED_S:
            continue
        lower_limit = groups[index - 1][1] if index > 0 else 0
        upper_limit = groups[index + 1][0] if index + 1 < len(groups) else fs.n
        new_start = _extend(start, lower_limit, -1, level, silent_rel, breathy, extension)
        new_end = _extend(end - 1, upper_limit - 1, 1, level, silent_rel, breathy, extension) + 1
        phrases.append(PhraseSpan(new_start, new_end, voiced_count))
    return phrases


def _extend(
    position: int,
    limit: int,
    step: int,
    level: np.ndarray,
    silent_rel: float,
    breathy: np.ndarray,
    max_frames: int,
) -> int:
    origin = position
    attached = True
    while (position + step - limit) * step <= 0 and abs(position - origin) < max_frames:
        frame = position + step
        if breathy[frame] and not (attached and abs(frame - origin) <= ATTACHED_ASPIRATION_FRAMES):
            break
        if level[frame] >= silent_rel:
            position = frame
            continue
        probe = frame
        while (
            (probe + step - limit) * step <= 0
            and level[probe] < silent_rel
            and abs(probe - frame) < MAX_CLOSURE_FRAMES
        ):
            probe += step
        closed = level[probe] >= silent_rel and not breathy[probe] and abs(probe - frame) < MAX_CLOSURE_FRAMES
        if closed and abs(probe - origin) < max_frames:
            position = probe
            attached = False
            continue
        break
    return position


def detect_breaths(fs: FeatureSet, phrases: list[PhraseSpan]) -> list[BreathSpan]:
    breathy = breath_like_mask(fs)
    inside = np.zeros(fs.n, dtype=bool)
    for phrase in phrases:
        inside[phrase.start : phrase.end] = True
    candidates = breathy & ~inside
    floor_rel = float(fs.meta.get("noise_floor_db", -90.0)) - float(fs.meta.get("active_level_db", -20.0))
    level = fs.tracks["level_rel_db"]
    centroid = fs.tracks["centroid_hz"]
    breaths: list[BreathSpan] = []
    merged = candidates.copy()
    for start, end in runs(~candidates):
        if start > 0 and end < fs.n and end - start <= 3:
            merged[start:end] = True
    merged &= ~inside
    for start, end in runs(merged):
        duration = (end - start) * fs.hop_s
        if duration < MIN_BREATH_S or duration > MAX_BREATH_S:
            continue
        mean_level = float(np.mean(level[start:end]))
        following = next((i for i, p in enumerate(phrases) if p.start >= end - 1), None)
        gap_to_phrase = (phrases[following].start - end) * fs.hop_s if following is not None else None
        duration_score = float(np.clip((duration - 0.08) / 0.25, 0.0, 1.0))
        level_score = float(np.clip((mean_level - floor_rel - 6.0) / 12.0, 0.0, 1.0))
        position_score = 1.0 if gap_to_phrase is not None and gap_to_phrase < 0.6 else 0.6
        confidence = duration_score * (0.4 + 0.6 * level_score) * position_score
        breaths.append(
            BreathSpan(
                start=start,
                end=end,
                level_rel_db=mean_level,
                centroid_hz=float(np.nanmean(centroid[start:end])),
                confidence=round(confidence, 3),
                before_phrase=following,
            )
        )
    return breaths


def group_sections(phrases: list[PhraseSpan], hop_s: float) -> list[tuple[int, int]]:
    if not phrases:
        return []
    sections: list[tuple[int, int]] = []
    first = 0
    for index in range(1, len(phrases)):
        if (phrases[index].start - phrases[index - 1].end) * hop_s >= SECTION_GAP_S:
            sections.append((first, index - 1))
            first = index
    sections.append((first, len(phrases) - 1))
    return sections
