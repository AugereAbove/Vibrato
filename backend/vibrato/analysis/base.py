from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from .contract import AnalysisResult, ResultBuilder
from .features import FeatureSet
from .model import Segment
from .segmentation.hierarchy import Hierarchy


@dataclass
class AnalysisContext:
    audio: np.ndarray
    sample_rate: int
    features: FeatureSet
    hierarchy: Hierarchy
    quality_factors: dict[str, float] = field(default_factory=dict)
    quality_reasons: dict[str, list[str]] = field(default_factory=dict)
    baseline: dict[str, Any] | None = None
    options: dict[str, Any] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)

    def apply_quality(self, builder: ResultBuilder, category: str) -> ResultBuilder:
        factor = self.quality_factors.get(category, 1.0)
        if factor < 0.999:
            reasons = "; ".join(self.quality_reasons.get(category, [])) or "recording quality"
            builder.factor(factor, f"recording quality: {reasons}")
        return builder

    def span(self, segment: Segment) -> slice:
        return self.features.span(segment.start_s, segment.end_s)


class Analyzer(ABC):
    id: ClassVar[str]
    version: ClassVar[str]
    category: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    dependencies: ClassVar[tuple[str, ...]] = ()
    supported_segment_types: ClassVar[tuple[str, ...]] = ()
    experimental: ClassVar[bool] = False
    requires: ClassVar[tuple[str, ...]] = ()
    method: ClassVar[str] = ""
    assumptions: ClassVar[tuple[str, ...]] = ()
    limitations: ClassVar[tuple[str, ...]] = ()
    parameters: ClassVar[dict[str, Any]] = {}

    def available(self, ctx: AnalysisContext | None = None) -> tuple[bool, str]:
        return True, ""

    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        raise NotImplementedError

    def confidence(self, result: AnalysisResult) -> float:
        return result.confidence

    def builder(
        self, segment: Segment | None, start: float | None = None, end: float | None = None
    ) -> ResultBuilder:
        return ResultBuilder(
            self.id,
            self.version,
            segment.id if segment else None,
            segment.level if segment else None,
            segment.start_s if segment and start is None else (start or 0.0),
            segment.end_s if segment and end is None else (end or 0.0),
        )

    def explain(self) -> dict[str, Any]:
        ok, reason = self.available()
        return {
            "id": self.id,
            "version": self.version,
            "category": self.category,
            "label": self.label,
            "description": self.description,
            "method": self.method,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
            "supported_segment_types": list(self.supported_segment_types),
            "experimental": self.experimental,
            "requires": list(self.requires),
            "available": ok,
            "unavailable_reason": reason,
        }


REGISTRY: dict[str, type[Analyzer]] = {}


def register(cls: type[Analyzer]) -> type[Analyzer]:
    REGISTRY[cls.id] = cls
    return cls


def all_analyzers() -> list[Analyzer]:
    from . import analyzers as _analyzers

    _analyzers.load_all()
    return [cls() for cls in REGISTRY.values()]


def analyzer_versions() -> dict[str, str]:
    return {a.id: a.version for a in all_analyzers()}
