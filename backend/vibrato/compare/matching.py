from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..alignment.aligner import Alignment
from ..analysis.model import Event, Segment, overlap

MIN_OVERLAP = 0.3


@dataclass
class Match:
    ref: Segment
    user: Segment | None
    overlap_ratio: float
    align_confidence: float
    mapped_start: float
    mapped_end: float


@dataclass
class EventMatch:
    ref: Event
    user: Event | None
    align_confidence: float
    mapped_start: float
    mapped_end: float


def map_span(alignment: Alignment, start: float, end: float) -> tuple[float, float]:
    mapped = alignment.ref_to_user(np.array([start, end]))
    return float(mapped[0]), float(max(mapped[1], mapped[0] + 1e-3))


def span_confidence(alignment: Alignment, start: float, end: float) -> float:
    times = np.linspace(start, end, max(2, int((end - start) / 0.01)))
    return float(np.mean(alignment.confidence_at(times)))


def match_segments(
    ref_segments: list[Segment],
    user_segments: list[Segment],
    alignment: Alignment,
    min_overlap: float = MIN_OVERLAP,
) -> list[Match]:
    proposals: list[tuple[float, int, int]] = []
    mapped: list[tuple[float, float]] = []
    for ri, ref in enumerate(ref_segments):
        us, ue = map_span(alignment, ref.start_s, ref.end_s)
        mapped.append((us, ue))
        for ui, user in enumerate(user_segments):
            amount = overlap(us, ue, user.start_s, user.end_s)
            if amount <= 0:
                continue
            ratio = amount / max(1e-6, min(ue - us, user.end_s - user.start_s))
            if ratio >= min_overlap:
                proposals.append((ratio, ri, ui))
    proposals.sort(reverse=True)
    taken_ref: dict[int, tuple[int, float]] = {}
    taken_user: set[int] = set()
    for ratio, ri, ui in proposals:
        if ri in taken_ref or ui in taken_user:
            continue
        taken_ref[ri] = (ui, ratio)
        taken_user.add(ui)
    matches: list[Match] = []
    for ri, ref in enumerate(ref_segments):
        us, ue = mapped[ri]
        conf = span_confidence(alignment, ref.start_s, ref.end_s)
        if ri in taken_ref:
            ui, ratio = taken_ref[ri]
            matches.append(Match(ref, user_segments[ui], ratio, conf, us, ue))
        else:
            matches.append(Match(ref, None, 0.0, conf, us, ue))
    return matches


def match_words(ref_words: list[Segment], user_words: list[Segment], alignment: Alignment) -> list[Match]:
    keyed = {(w.props.get("line_index"), w.props.get("word_index")): w for w in user_words}
    if ref_words and all((w.props.get("line_index"), w.props.get("word_index")) in keyed for w in ref_words):
        out = []
        for ref in ref_words:
            user = keyed[(ref.props.get("line_index"), ref.props.get("word_index"))]
            us, ue = map_span(alignment, ref.start_s, ref.end_s)
            ratio = overlap(us, ue, user.start_s, user.end_s) / max(
                1e-6, min(ue - us, user.end_s - user.start_s)
            )
            out.append(Match(ref, user, ratio, span_confidence(alignment, ref.start_s, ref.end_s), us, ue))
        return out
    return match_segments(ref_words, user_words, alignment)


def compatible_kind(a: str, b: str) -> bool:
    families = {
        "stop": "stop",
        "fricative": "fric",
        "sibilant": "fric",
        "aspiration": "fric",
        "voiced fricative": "voiced",
        "voiced consonant": "voiced",
    }
    return families.get(a, a) == families.get(b, b)


def match_events(
    ref_events: list[Event], user_events: list[Event], alignment: Alignment, tolerance_s: float = 0.06
) -> list[EventMatch]:
    used: set[int] = set()
    out: list[EventMatch] = []
    for ref in ref_events:
        us, ue = map_span(alignment, ref.start_s, ref.end_s)
        best: tuple[float, int] | None = None
        for index, user in enumerate(user_events):
            if index in used:
                continue
            if not compatible_kind(str(ref.props.get("kind", "")), str(user.props.get("kind", ""))):
                continue
            gap = max(user.start_s - ue, us - user.end_s, 0.0)
            if gap > tolerance_s:
                continue
            score = overlap(us, ue, user.start_s, user.end_s) - gap
            if best is None or score > best[0]:
                best = (score, index)
        conf = span_confidence(alignment, ref.start_s, ref.end_s)
        if best is not None:
            used.add(best[1])
            out.append(EventMatch(ref, user_events[best[1]], conf, us, ue))
        else:
            out.append(EventMatch(ref, None, conf, us, ue))
    return out


def pair_confidence(ref_conf: float, user_conf: float, align_conf: float) -> float:
    base = min(math.sqrt(max(ref_conf, 0.0) * max(user_conf, 0.0)), min(ref_conf, user_conf) + 0.15)
    align_factor = min(1.0, max(0.3, align_conf / 0.7))
    return round(max(0.0, min(1.0, base * align_factor)), 3)


def theil_sen(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if x.size < 2:
        return 1.0, float(y[0] - x[0]) if x.size else 0.0
    slopes = []
    for i in range(x.size):
        for j in range(i + 1, x.size):
            if abs(x[j] - x[i]) > 1e-6:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    slope = float(np.median(slopes)) if slopes else 1.0
    intercept = float(np.median(y - slope * x))
    return slope, intercept
