from __future__ import annotations

from typing import Any

import numpy as np

from .metrics import CATEGORIES, CATEGORY_LABELS, CATEGORY_WEIGHT_RATIONALE, DEFAULT_CATEGORY_WEIGHTS, METRICS
from .model import MetricComparison

SCORE_FORMULA = "score = 100 x exp(-ln 2 x (|difference| / (2 x tolerance))^2): a difference equal to the tolerance scores 84, twice the tolerance scores 50."
COVERAGE_FULL = 5


def category_scores(
    metrics: list[MetricComparison],
    enabled: dict[str, bool] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    enabled = enabled or {}
    weights = {**DEFAULT_CATEGORY_WEIGHTS, **(weights or {})}
    categories: dict[str, dict[str, Any]] = {}
    for category in CATEGORIES:
        items = [
            m for m in metrics if m.category == category and m.usable and METRICS[m.metric_id].weight > 0
        ]
        breakdown: dict[str, dict[str, Any]] = {}
        for metric_id in sorted({m.metric_id for m in metrics if m.category == category}):
            definition = METRICS[metric_id]
            instances = [m for m in metrics if m.metric_id == metric_id]
            usable = [m for m in instances if m.usable]
            breakdown[metric_id] = {
                "name": definition.name,
                "unit": definition.unit,
                "tolerance": definition.tolerance,
                "weight": definition.weight,
                "instances": len(instances),
                "scored_instances": len(usable) if definition.weight > 0 else 0,
                "mean_score": round(float(np.mean([m.score for m in usable])), 1) if usable else None,
                "mean_confidence": round(float(np.mean([m.confidence for m in usable])), 3)
                if usable
                else None,
                "median_difference": round(
                    float(np.median([m.difference for m in usable if m.difference is not None])), 3
                )
                if any(m.difference is not None for m in usable)
                else None,
                "basis": definition.basis,
                "normalisation": definition.tolerance_basis,
                "evidence_only": definition.weight == 0,
            }
        if not items:
            categories[category] = {
                "label": CATEGORY_LABELS[category],
                "score": None,
                "confidence": 0.0,
                "status": "insufficient_data",
                "reason": "No comparisons with enough confidence in this category.",
                "enabled": enabled.get(category, True),
                "weight": weights[category],
                "metrics": breakdown,
                "count": 0,
            }
            continue
        w = np.array([METRICS[m.metric_id].weight * m.importance * m.confidence for m in items])
        s = np.array([m.score for m in items], dtype=np.float64)
        base_w = np.array([METRICS[m.metric_id].weight * m.importance for m in items])
        c = np.array([m.confidence for m in items])
        score = float(np.sum(w * s) / np.sum(w)) if np.sum(w) > 0 else None
        coverage = min(1.0, 0.4 + 0.6 * len(items) / COVERAGE_FULL)
        confidence = float(np.sum(base_w * c) / np.sum(base_w)) * coverage if np.sum(base_w) > 0 else 0.0
        categories[category] = {
            "label": CATEGORY_LABELS[category],
            "score": None if score is None else round(score, 1),
            "confidence": round(confidence, 3),
            "status": "ok" if confidence >= 0.45 else "low_confidence",
            "enabled": enabled.get(category, True),
            "weight": weights[category],
            "metrics": breakdown,
            "count": len(items),
        }
    numerator = 0.0
    denominator = 0.0
    contributions: list[dict[str, Any]] = []
    for category, data in categories.items():
        if data["score"] is None or not data["enabled"]:
            continue
        weight = float(data["weight"]) * float(data["confidence"])
        numerator += float(data["score"]) * weight
        denominator += weight
        contributions.append(
            {"category": category, "score": data["score"], "effective_weight": round(weight, 3)}
        )
    overall = round(numerator / denominator, 1) if denominator > 0 else None
    overall_conf = (
        round(
            min(
                1.0,
                denominator / max(1e-9, sum(float(d["weight"]) for d in categories.values() if d["enabled"])),
            ),
            3,
        )
        if denominator > 0
        else 0.0
    )
    return {
        "categories": categories,
        "overall": {
            "score": overall,
            "confidence": overall_conf,
            "contributions": contributions,
            "disclaimer": "The overall score is a convenience summary. It is not diagnostic: two very different performances can share a score. Use the individual findings and measurements to decide what to practise.",
        },
        "method": {
            "metric_score": SCORE_FORMULA,
            "category_score": "Confidence- and importance-weighted mean of metric scores in the category (metric weight x segment importance x comparison confidence). Metrics marked evidence-only are shown but not scored.",
            "overall_score": "Mean of enabled category scores weighted by category weight x category confidence.",
            "category_weights": weights,
            "category_weight_rationale": CATEGORY_WEIGHT_RATIONALE,
            "minimum_confidence": "Comparisons below 25% confidence are never scored.",
        },
    }
