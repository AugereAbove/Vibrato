from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..analysis.contract import AnalysisResult
from ..analysis.features import FeatureSet
from ..analysis.model import Event, Segment
from ..analysis.pipeline import RecordingAnalysis


@dataclass
class RecordingView:
    recording_id: str
    features: FeatureSet
    segments: list[Segment]
    events: list[Event]
    results: list[AnalysisResult]
    summary: dict[str, Any] = field(default_factory=dict)
    _by_key: dict[tuple[str, str | None], AnalysisResult] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for result in self.results:
            self._by_key.setdefault((result.analyzer_id, result.segment_id), result)

    def by_level(self, level: str) -> list[Segment]:
        return [s for s in self.segments if s.level == level]

    def result(self, analyzer_id: str, segment_id: str | None) -> AnalysisResult | None:
        return self._by_key.get((analyzer_id, segment_id))

    def results_for(self, analyzer_id: str, level: str | None = None) -> list[AnalysisResult]:
        return [
            r
            for r in self.results
            if r.analyzer_id == analyzer_id and (level is None or r.segment_level == level)
        ]

    def events_of(self, event_type: str) -> list[Event]:
        return [e for e in self.events if e.type == event_type]

    def segment(self, segment_id: str | None) -> Segment | None:
        if segment_id is None:
            return None
        return next((s for s in self.segments if s.id == segment_id), None)

    def notes_in(self, phrase: Segment) -> list[Segment]:
        return [n for n in self.by_level("note") if phrase.start_s - 0.02 <= n.start_s < phrase.end_s]

    @classmethod
    def from_analysis(cls, recording_id: str, analysis: RecordingAnalysis) -> RecordingView:
        return cls(
            recording_id=recording_id,
            features=analysis.features,
            segments=analysis.hierarchy.segments,
            events=analysis.hierarchy.events,
            results=analysis.results,
            summary=analysis.summary,
        )

    @classmethod
    def from_json(cls, recording_id: str, payload: dict[str, Any], features: FeatureSet) -> RecordingView:
        return cls(
            recording_id=recording_id,
            features=features,
            segments=[Segment.from_dict(s) for s in payload.get("segments", [])],
            events=[Event.from_dict(e) for e in payload.get("events", [])],
            results=[AnalysisResult.from_dict(r) for r in payload.get("results", [])],
            summary=dict(payload.get("summary", {})),
        )
