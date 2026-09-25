from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any

from ..alignment.aligner import Alignment
from ..logging_setup import get_logger
from ..util import to_jsonable
from .categories import CATEGORY_FUNCTIONS, CompareContext, prepare
from .heatmap import build_heatmap
from .metrics import METRICS_VERSION
from .model import MetricComparison
from .scoring import category_scores
from .view import RecordingView

COMPARISON_VERSION = f"compare/1.3|{METRICS_VERSION}"
log = get_logger("compare")


@dataclass
class ComparisonResult:
    version: str
    metrics: list[MetricComparison]
    scores: dict[str, Any]
    heatmap: dict[str, Any]
    observations: list[dict[str, Any]]
    extras: dict[str, Any]
    alignment: dict[str, Any]
    coverage: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return to_jsonable(
            {
                "version": self.version,
                "metrics": [m.to_dict() for m in self.metrics],
                "scores": self.scores,
                "heatmap": self.heatmap,
                "observations": self.observations,
                "extras": self.extras,
                "alignment": self.alignment,
                "coverage": self.coverage,
                "warnings": self.warnings,
            }
        )


def compare(
    ref: RecordingView,
    user: RecordingView,
    alignment: Alignment,
    synced: bool = False,
    enabled_categories: dict[str, bool] | None = None,
    category_weights: dict[str, float] | None = None,
    region: tuple[float, float] | None = None,
) -> ComparisonResult:
    ctx = CompareContext(ref=ref, user=user, alignment=alignment, synced=synced)
    prepare(ctx)
    if region is not None:
        lo, hi = region
        ctx.phrase_matches = [m for m in ctx.phrase_matches if m.ref.end_s > lo and m.ref.start_s < hi]
        ctx.note_matches = [m for m in ctx.note_matches if m.ref.end_s > lo and m.ref.start_s < hi]
        ctx.syllable_matches = [m for m in ctx.syllable_matches if m.ref.end_s > lo and m.ref.start_s < hi]
    metrics: list[MetricComparison] = []
    warnings = list(alignment.warnings)
    for category, function in CATEGORY_FUNCTIONS.items():
        try:
            metrics.extend(function(ctx))
        except Exception as exc:
            log.error("Comparison for %s failed: %s", category, exc)
            warnings.append(
                f"The {category} comparison could not be completed ({type(exc).__name__}). Other categories are unaffected."
            )
            ctx.extras.setdefault("errors", []).append(
                {"category": category, "error": str(exc), "traceback": traceback.format_exc(limit=5)}
            )
    if region is not None:
        lo, hi = region
        metrics = [m for m in metrics if m.ref_end > lo and m.ref_start < hi]
    matched_notes = sum(1 for m in ctx.note_matches if m.user is not None)
    matched_phrases = sum(1 for m in ctx.phrase_matches if m.user is not None)
    coverage = {
        "reference_notes": len(ctx.note_matches),
        "matched_notes": matched_notes,
        "reference_phrases": len(ctx.phrase_matches),
        "matched_phrases": matched_phrases,
        "unmatched_reference_notes": [m.ref.id for m in ctx.note_matches if m.user is None],
    }
    if ctx.note_matches and matched_notes / len(ctx.note_matches) < 0.6:
        warnings.append(
            f"Only {matched_notes} of {len(ctx.note_matches)} reference notes could be matched in the take; comparisons cover part of the performance."
        )
    return ComparisonResult(
        version=COMPARISON_VERSION,
        metrics=metrics,
        scores=category_scores(metrics, enabled_categories, category_weights),
        heatmap=build_heatmap(metrics, ref, alignment),
        observations=ctx.observations,
        extras=ctx.extras,
        alignment=alignment.summary(),
        coverage=coverage,
        warnings=warnings,
    )
