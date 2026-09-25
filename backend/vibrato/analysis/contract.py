from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ..util import to_jsonable


class Validity(StrEnum):
    VALID = "VALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONTAMINATED = "CONTAMINATED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


class Basis(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"
    EXPERIMENTAL = "experimental"


VALID_THRESHOLD = 0.6
LOW_CONFIDENCE_THRESHOLD = 0.25
Scalar = float | int | str | bool | None


@dataclass
class AnalysisResult:
    analyzer_id: str
    analyzer_version: str
    segment_id: str | None
    segment_level: str | None
    values: dict[str, Scalar]
    units: dict[str, str]
    basis: dict[str, str]
    confidence: float
    confidence_reasons: list[str]
    validity: str
    warning_flags: list[str]
    timestamp_start: float
    timestamp_end: float
    raw_supporting_data: dict[str, Any] = field(default_factory=dict)
    derived_interpretation: dict[str, Any] | None = None

    def value(self, key: str) -> Scalar:
        return self.values.get(key)

    def number(self, key: str) -> float | None:
        value = self.values.get(key)
        if isinstance(value, bool) or value is None or isinstance(value, str):
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisResult:
        return cls(**data)


class ResultBuilder:
    def __init__(
        self,
        analyzer_id: str,
        analyzer_version: str,
        segment_id: str | None,
        segment_level: str | None,
        start: float,
        end: float,
    ) -> None:
        self.analyzer_id = analyzer_id
        self.analyzer_version = analyzer_version
        self.segment_id = segment_id
        self.segment_level = segment_level
        self.start = start
        self.end = end
        self.values: dict[str, Scalar] = {}
        self.units: dict[str, str] = {}
        self.basis: dict[str, str] = {}
        self.confidence = 1.0
        self.reasons: list[str] = []
        self.flags: list[str] = []
        self.raw: dict[str, Any] = {}
        self.interpretation: dict[str, Any] | None = None
        self.forced_validity: Validity | None = None

    def add(
        self, key: str, value: Scalar, unit: str = "", basis: Basis = Basis.MEASURED, digits: int | None = 3
    ) -> ResultBuilder:
        if isinstance(value, float):
            value = (
                round(value, digits)
                if (digits is not None and math.isfinite(value))
                else (value if math.isfinite(value) else None)
            )
        self.values[key] = value
        self.units[key] = unit
        self.basis[key] = basis.value
        return self

    def factor(self, value: float, reason: str | None = None) -> ResultBuilder:
        value = max(0.0, min(1.0, float(value)))
        if value < 0.999 and reason:
            self.reasons.append(f"{reason} (x{value:.2f})")
        self.confidence *= value
        return self

    def reason(self, text: str) -> ResultBuilder:
        self.reasons.append(text)
        return self

    def flag(self, code: str) -> ResultBuilder:
        if code not in self.flags:
            self.flags.append(code)
        return self

    def support(self, **data: object) -> ResultBuilder:
        self.raw.update(data)
        return self

    def interpret(
        self,
        label: str,
        text: str,
        basis: Basis = Basis.INFERRED,
        confidence: float | None = None,
        **extra: object,
    ) -> ResultBuilder:
        self.interpretation = {
            "label": label,
            "text": text,
            "basis": basis.value,
            "confidence": round(self.confidence if confidence is None else confidence, 3),
            **extra,
        }
        return self

    def validity(self, value: Validity) -> ResultBuilder:
        self.forced_validity = value
        return self

    def build(self) -> AnalysisResult:
        confidence = round(max(0.0, min(1.0, self.confidence)), 3)
        if self.forced_validity is not None:
            validity = self.forced_validity
        elif not any(v is not None for v in self.values.values()):
            validity = Validity.UNAVAILABLE
        elif confidence >= VALID_THRESHOLD:
            validity = Validity.VALID
        elif confidence >= LOW_CONFIDENCE_THRESHOLD:
            validity = Validity.LOW_CONFIDENCE
        else:
            validity = Validity.LOW_CONFIDENCE
            if "insufficient_confidence" not in self.flags:
                self.flags.append("insufficient_confidence")
        return AnalysisResult(
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            segment_id=self.segment_id,
            segment_level=self.segment_level,
            values=self.values,
            units=self.units,
            basis=self.basis,
            confidence=confidence,
            confidence_reasons=self.reasons,
            validity=validity.value,
            warning_flags=self.flags,
            timestamp_start=round(self.start, 4),
            timestamp_end=round(self.end, 4),
            raw_supporting_data=to_jsonable(self.raw),
            derived_interpretation=to_jsonable(self.interpretation) if self.interpretation else None,
        )
