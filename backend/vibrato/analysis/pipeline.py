from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..logging_setup import get_logger
from ..util import stable_hash
from .base import REGISTRY, AnalysisContext, all_analyzers
from .contract import AnalysisResult, Validity
from .features import FEATURES_VERSION, FeatureSet, extract_features
from .segmentation.hierarchy import Hierarchy, build_hierarchy
from .segmentation.phonetic import CLASS_LABELS

log = get_logger("pipeline")

SEGMENTATION_VERSION = "segmentation/1.3"
ANALYZER_ORDER = (
    "pitch",
    "vibrato",
    "nonlinear",
    "voice_quality",
    "phonation",
    "register",
    "vowels",
    "articulation",
    "breath",
    "dynamics",
    "timbre",
    "quality",
)
ProgressFn = Callable[[float, str], None]


class AnalysisCancelled(Exception):
    pass


def _noop_progress(fraction: float, message: str) -> None:
    return None


def _noop_cancel() -> None:
    return None


def pipeline_version() -> str:
    versions = {a.id: a.version for a in all_analyzers()}
    return f"{FEATURES_VERSION}|{SEGMENTATION_VERSION}|{stable_hash(versions)}"


def features_key(options: dict[str, Any]) -> str:
    return stable_hash(
        {
            "features": FEATURES_VERSION,
            "pyin": bool(options.get("use_pyin")),
            "crepe": bool(options.get("use_crepe")),
        }
    )


@dataclass
class RecordingAnalysis:
    features: FeatureSet
    hierarchy: Hierarchy
    results: list[AnalysisResult]
    runs: list[dict[str, Any]]
    summary: dict[str, Any]
    version: str
    contamination: dict[str, Any] = field(default_factory=dict)

    def results_for(self, analyzer_id: str, level: str | None = None) -> list[AnalysisResult]:
        return [
            r
            for r in self.results
            if r.analyzer_id == analyzer_id and (level is None or r.segment_level == level)
        ]

    def result(self, analyzer_id: str, segment_id: str | None) -> AnalysisResult | None:
        for r in self.results:
            if r.analyzer_id == analyzer_id and r.segment_id == segment_id:
                return r
        return None

    def to_json(self) -> dict[str, Any]:
        fs = self.features
        return {
            "pipeline_version": self.version,
            "segments": [s.to_dict() for s in self.hierarchy.segments],
            "events": [e.to_dict() for e in self.hierarchy.events],
            "results": [r.to_dict() for r in self.results],
            "analyzer_runs": self.runs,
            "summary": self.summary,
            "lyrics": self.hierarchy.lyrics_status,
            "phonetic_classes": [
                {
                    "class": c.cls,
                    "label": CLASS_LABELS[c.cls],
                    "start_s": round(c.start * fs.hop_s, 4),
                    "end_s": round(c.end * fs.hop_s, 4),
                    "confidence": round(c.confidence, 3),
                }
                for c in self.hierarchy.class_segments
            ],
            "contamination": self.contamination,
            "features_meta": fs.meta,
        }


def note_vowels(hierarchy: Hierarchy) -> dict[str, str]:
    syllable_vowel: dict[str, str] = {}
    for phoneme in hierarchy.by_level("phoneme"):
        if phoneme.props.get("phoneme_class") == "vowel" and phoneme.parent_id:
            syllable_vowel.setdefault(phoneme.parent_id, phoneme.label)
    mapping: dict[str, str] = {}
    for note in hierarchy.by_level("note"):
        if note.parent_id and note.parent_id in syllable_vowel:
            mapping[note.id] = syllable_vowel[note.parent_id]
    return mapping


def summarize(fs: FeatureSet, hierarchy: Hierarchy, results: list[AnalysisResult]) -> dict[str, Any]:
    voiced_s = float(fs.voiced.sum() * fs.hop_s)
    confidences = [r.confidence for r in results if r.segment_level in {"note", "syllable", "phrase"}]
    return {
        "duration_s": round(fs.duration_s, 3),
        "voiced_s": round(voiced_s, 3),
        "phrases": len(hierarchy.by_level("phrase")),
        "words": len(hierarchy.by_level("word")),
        "syllables": len(hierarchy.by_level("syllable")),
        "notes": len(hierarchy.by_level("note")),
        "phonemes": len(hierarchy.by_level("phoneme")),
        "events": len(hierarchy.events),
        "breaths": sum(1 for e in hierarchy.events if e.type == "breath"),
        "median_confidence": round(float(np.median(confidences)), 3) if confidences else None,
        "too_little_voice": voiced_s < 1.0,
        "pitch_estimators": fs.meta.get("pitch_estimators"),
        "noise_floor_db": fs.meta.get("noise_floor_db"),
        "active_level_db": fs.meta.get("active_level_db"),
    }


def run_analysis(
    audio: np.ndarray,
    sample_rate: int,
    noise_floor_db: float,
    quality_factors: dict[str, float] | None = None,
    quality_reasons: dict[str, list[str]] | None = None,
    lyrics: str = "",
    pronunciation_overrides: dict[int, str] | None = None,
    sections: list[dict[str, Any]] | None = None,
    baseline: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    features: FeatureSet | None = None,
    progress: ProgressFn = _noop_progress,
    check_cancelled: Callable[[], None] = _noop_cancel,
) -> RecordingAnalysis:
    options = options or {}
    x = audio.astype(np.float64)
    if features is None:
        features = extract_features(
            x,
            sample_rate,
            noise_floor_db,
            use_pyin=bool(options.get("use_pyin")),
            use_crepe=bool(options.get("use_crepe")),
            progress=lambda f, m: progress(0.75 * f, m),
            check_cancelled=check_cancelled,
        )
    check_cancelled()
    progress(0.78, "Segmenting phrases, syllables, notes and phonemes")
    hierarchy = build_hierarchy(features, lyrics, pronunciation_overrides, sections)
    context = AnalysisContext(
        audio=x,
        sample_rate=sample_rate,
        features=features,
        hierarchy=hierarchy,
        quality_factors=quality_factors or {},
        quality_reasons=quality_reasons or {},
        baseline=baseline,
        options=options,
    )
    context.shared["note_vowels"] = note_vowels(hierarchy)
    analyzers = {a.id: a for a in all_analyzers()}
    order = [name for name in ANALYZER_ORDER if name in analyzers] + [
        name for name in REGISTRY if name not in ANALYZER_ORDER
    ]
    disabled = set(options.get("disabled_analyzers", []) or [])
    results: list[AnalysisResult] = []
    runs: list[dict[str, Any]] = []
    for position, name in enumerate(order):
        check_cancelled()
        analyzer = analyzers[name]
        progress(0.8 + 0.19 * position / max(1, len(order)), f"Running {analyzer.label}")
        started = time.perf_counter()
        record: dict[str, Any] = {
            "analyzer_id": analyzer.id,
            "analyzer_version": analyzer.version,
            "category": analyzer.category,
        }
        if name in disabled:
            record.update(
                {
                    "status": "disabled",
                    "validity": Validity.NOT_APPLICABLE.value,
                    "result_count": 0,
                    "duration_ms": 0.0,
                }
            )
            runs.append(record)
            continue
        ok, reason = analyzer.available(context)
        if not ok:
            record.update(
                {
                    "status": "unavailable",
                    "validity": Validity.MODEL_UNAVAILABLE.value,
                    "error": reason,
                    "result_count": 0,
                    "duration_ms": 0.0,
                }
            )
            runs.append(record)
            continue
        try:
            produced = analyzer.analyze(context)
        except AnalysisCancelled:
            raise
        except Exception as exc:
            log.error("Analyzer %s failed: %s", name, exc)
            record.update(
                {
                    "status": "failed",
                    "validity": Validity.UNAVAILABLE.value,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=6),
                    "result_count": 0,
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
                }
            )
            runs.append(record)
            continue
        if name == "voice_quality":
            context.shared["voice_quality_results"] = produced
        confidences = [r.confidence for r in produced]
        valid = sum(1 for r in produced if r.validity == Validity.VALID.value)
        record.update(
            {
                "status": "ok",
                "validity": Validity.VALID.value
                if valid
                else (Validity.LOW_CONFIDENCE.value if produced else Validity.NOT_APPLICABLE.value),
                "result_count": len(produced),
                "valid_count": valid,
                "median_confidence": round(float(np.median(confidences)), 3) if confidences else None,
                "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
            }
        )
        runs.append(record)
        results.extend(produced)
    progress(0.99, "Summarising")
    return RecordingAnalysis(
        features=features,
        hierarchy=hierarchy,
        results=results,
        runs=runs,
        summary=summarize(features, hierarchy, results),
        version=pipeline_version(),
        contamination=dict(context.shared.get("contamination", {})),
    )
