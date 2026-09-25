from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np

from ..alignment.aligner import Alignment
from .metrics import CATEGORIES
from .model import MetricComparison
from .view import RecordingView

FINE_BIN_S = 0.25
MAX_Z = 4.0
ROWS = (*CATEGORIES, "confidence")


def _cells(
    metrics: list[MetricComparison], columns: list[dict[str, Any]], alignment: Alignment
) -> dict[str, list[dict[str, Any] | None]]:
    rows: dict[str, list[dict[str, Any] | None]] = {row: [] for row in ROWS}
    for column in columns:
        start, end = float(column["start_s"]), float(column["end_s"])
        for category in CATEGORIES:
            inside = [
                m
                for m in metrics
                if m.category == category and m.usable and min(m.ref_end, end) - max(m.ref_start, start) > 0
            ]
            if not inside:
                rows[category].append(None)
                continue
            worst = max(inside, key=lambda m: min(m.normalized or 0.0, MAX_Z) * m.confidence)
            rows[category].append(
                {
                    "value": round(min(worst.normalized or 0.0, MAX_Z) / MAX_Z, 3),
                    "z": round(worst.normalized or 0.0, 3),
                    "confidence": worst.confidence,
                    "metric_id": worst.metric_id,
                    "label": worst.label,
                    "direction": worst.direction,
                    "ref_start": worst.ref_start,
                    "ref_end": worst.ref_end,
                    "segment_id": worst.ref_segment_id,
                    "count": len(inside),
                }
            )
        times = np.linspace(start, end, max(2, int((end - start) / 0.02)))
        conf = float(np.mean(alignment.confidence_at(times)))
        rows["confidence"].append(
            {"value": round(conf, 3), "confidence": round(conf, 3), "ref_start": start, "ref_end": end}
        )
    return rows


def build_heatmap(
    metrics: list[MetricComparison], ref: RecordingView, alignment: Alignment
) -> dict[str, Any]:
    views: dict[str, Any] = {}
    phrase_columns = [
        {"id": p.id, "label": p.label, "start_s": p.start_s, "end_s": p.end_s} for p in ref.by_level("phrase")
    ]
    words = ref.by_level("word")
    word_level = "word" if words else "syllable"
    word_columns = [
        {
            "id": s.id,
            "label": s.label or f"{word_level} {s.ordinal + 1}",
            "start_s": s.start_s,
            "end_s": s.end_s,
        }
        for s in (words or ref.by_level("syllable"))
    ]
    start, end = alignment.ref_range
    edges = np.arange(start, end + FINE_BIN_S, FINE_BIN_S)
    fine_columns = [
        {"id": f"bin{i}", "label": f"{a:.2f}s", "start_s": round(float(a), 3), "end_s": round(float(b), 3)}
        for i, (a, b) in enumerate(pairwise(edges))
    ]
    for name, columns in (("phrase", phrase_columns), ("word", word_columns), ("fine", fine_columns)):
        views[name] = {"columns": columns, "rows": _cells(metrics, columns, alignment)}
    return {"rows": list(ROWS), "views": views, "word_level": word_level, "max_z": MAX_Z}
