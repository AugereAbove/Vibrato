from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from ..analysis.contract import LOW_CONFIDENCE_THRESHOLD, VALID_THRESHOLD, Validity
from ..util import to_jsonable
from .metrics import METRICS, PRESENCE_MISMATCH_Z

SIMILAR_Z = 0.25
MIN_SCORING_CONFIDENCE = 0.25


def metric_score(normalized: float) -> float:
    return 100.0 * math.exp(-math.log(2.0) * (normalized / 2.0) ** 2)


@dataclass
class MetricComparison:
    metric_id: str
    category: str
    level: str
    label: str
    ref_segment_id: str | None
    user_segment_id: str | None
    ref_start: float
    ref_end: float
    user_start: float | None
    user_end: float | None
    ref_value: float | str | None
    user_value: float | str | None
    difference: float | None
    normalized: float | None
    direction: str
    confidence: float
    validity: str
    score: float | None
    weight: float
    importance: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.normalized is not None and self.confidence >= MIN_SCORING_CONFIDENCE

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricComparison:
        return cls(**data)


def make_comparison(
    metric_id: str,
    level: str,
    label: str,
    ref_segment_id: str | None,
    user_segment_id: str | None,
    ref_span: tuple[float, float],
    user_span: tuple[float, float] | None,
    ref_value: float | str | None,
    user_value: float | str | None,
    difference: float | None,
    confidence: float,
    importance: float = 1.0,
    evidence: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    mismatch: bool | None = None,
    tolerance: float | None = None,
) -> MetricComparison:
    definition = METRICS[metric_id]
    effective_tolerance = tolerance if tolerance is not None and tolerance > 0 else definition.tolerance
    if definition.kind in {"presence", "label"}:
        if mismatch is None:
            normalized = None
        else:
            normalized = PRESENCE_MISMATCH_Z if mismatch else 0.0
        if mismatch:
            direction = definition.higher if (difference or 0.0) > 0 else definition.lower
        else:
            direction = "matches"
    elif difference is None or not math.isfinite(difference):
        normalized = None
        direction = "unknown"
    else:
        normalized = abs(difference) / effective_tolerance
        if normalized < SIMILAR_Z:
            direction = "similar"
        else:
            direction = definition.higher if difference > 0 else definition.lower
    if normalized is None:
        validity = Validity.UNAVAILABLE.value
    elif confidence >= VALID_THRESHOLD:
        validity = Validity.VALID.value
    else:
        validity = Validity.LOW_CONFIDENCE.value
    note_list = list(notes or [])
    if effective_tolerance != definition.tolerance:
        evidence = {
            **(evidence or {}),
            "tolerance_used": round(effective_tolerance, 3),
            "tolerance_default": definition.tolerance,
        }
    if normalized is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        note_list.append(
            "Insufficient confidence: this comparison is shown for reference only and is not scored."
        )
    return MetricComparison(
        metric_id=metric_id,
        category=definition.category,
        level=level,
        label=label,
        ref_segment_id=ref_segment_id,
        user_segment_id=user_segment_id,
        ref_start=round(ref_span[0], 4),
        ref_end=round(ref_span[1], 4),
        user_start=None if user_span is None else round(user_span[0], 4),
        user_end=None if user_span is None else round(user_span[1], 4),
        ref_value=_round(ref_value),
        user_value=_round(user_value),
        difference=_round_number(difference),
        normalized=_round_number(normalized),
        direction=direction,
        confidence=round(float(confidence), 3),
        validity=validity,
        score=None if normalized is None else round(metric_score(normalized), 1),
        weight=definition.weight,
        importance=round(float(importance), 3),
        evidence=to_jsonable(evidence or {}),
        notes=note_list,
    )


def _round(value: float | str | None) -> float | str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return float(value)
    number = float(value)
    return round(number, 4) if math.isfinite(number) else None


def _round_number(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return round(number, 4) if math.isfinite(number) else None
