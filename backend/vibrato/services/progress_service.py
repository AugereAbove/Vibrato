from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

from ..compare.metrics import CATEGORIES, CATEGORY_LABELS, METRICS
from ..db import get_db
from ..store import comparisons as comparison_store
from ..store import misc as misc_store
from ..store import recordings as recording_store

ROLLING_WINDOW = 3
REGRESSION_DROP = 8.0
PERSISTENT_MIN_TAKES = 3
PERSISTENT_RECENT = 5
PERSISTENT_FRACTION = 0.6
STRENGTH_MIN_TAKES = 3
STRENGTH_SCORE = 85.0


def _slope(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    x = np.arange(len(values), dtype=np.float64)
    slope, _ = np.polyfit(x, np.array(values, dtype=np.float64), 1)
    return float(slope)


def project_progress(project_id: str, reference_id: str | None = None) -> dict[str, Any]:
    with get_db().read() as conn:
        if reference_id is None:
            primary = recording_store.primary_reference(conn, project_id)
            reference_id = primary["id"] if primary else None
        rows = comparison_store.comparisons_for_reference(conn, reference_id) if reference_id else []
        sessions = misc_store.list_sessions(conn, project_id)
        milestones = misc_store.list_milestones(conn, project_id)
        suggestion_rows = comparison_store.suggestions_history(conn, project_id)
        metric_rows = {row["id"]: comparison_store.metric_values(conn, row["id"]) for row in rows}
    takes: list[dict[str, Any]] = []
    for row in rows:
        categories = row.get("category_scores") or {}
        takes.append(
            {
                "comparison_id": row["id"],
                "take_id": row["take_recording_id"],
                "take_number": row.get("take_number"),
                "take_name": row.get("take_name"),
                "created_at": row.get("take_created_at"),
                "session_id": row.get("session_id"),
                "overall": row.get("overall_score"),
                "confidence": row.get("overall_confidence"),
                "categories": {c: (categories.get(c) or {}).get("score") for c in CATEGORIES},
                "category_confidence": {c: (categories.get(c) or {}).get("confidence") for c in CATEGORIES},
                "favorite": bool(row.get("take_favorite")),
                "notes": row.get("take_notes") or "",
                "region": [row.get("region_start_s"), row.get("region_end_s")]
                if row.get("region_start_s") is not None
                else None,
                "primary_focus": (row.get("summary") or {}).get("primary"),
            }
        )
    trends: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    for key in ("overall", *CATEGORIES):
        series = [(t["overall"] if key == "overall" else t["categories"].get(key)) for t in takes]
        confidences = [
            (t["confidence"] if key == "overall" else t["category_confidence"].get(key)) for t in takes
        ]
        rolling: list[float | None] = []
        for index in range(len(series)):
            window = [
                (v, c)
                for v, c in zip(
                    series[max(0, index - ROLLING_WINDOW + 1) : index + 1],
                    confidences[max(0, index - ROLLING_WINDOW + 1) : index + 1],
                )
                if v is not None and (c or 0) >= 0.3
            ]
            rolling.append(
                round(
                    float(
                        np.average([v for v, _ in window], weights=[max(c or 0.3, 0.3) for _, c in window])
                    ),
                    1,
                )
                if window
                else None
            )
        valid = [v for v in series if v is not None]
        best = max(valid) if valid else None
        latest = series[-1] if series else None
        previous = next((v for v in reversed(series[:-1]) if v is not None), None)
        delta = None if latest is None or previous is None else round(latest - previous, 1)
        trends[key] = {
            "label": "Overall" if key == "overall" else CATEGORY_LABELS[key],
            "series": series,
            "rolling": rolling,
            "best": best,
            "latest": latest,
            "delta": delta,
            "slope_per_take": _slope(valid),
        }
        if (
            len(valid) >= 3
            and latest is not None
            and rolling[-2] is not None
            and latest < (rolling[-2] or 0) - REGRESSION_DROP
            and (confidences[-1] or 0) >= 0.45
        ):
            warnings.append(
                {
                    "category": key,
                    "label": trends[key]["label"],
                    "text": f"{trends[key]['label']} dropped to {latest:.0f} from a recent average of {rolling[-2]:.0f}.",
                    "latest": latest,
                    "average": rolling[-2],
                }
            )
    phrase_history: dict[str, dict[str, Any]] = {}
    for take in takes:
        for metric in metric_rows.get(take["comparison_id"], []):
            if metric["score"] is None or metric["confidence"] < 0.25:
                continue
            if metric["segment_level"] != "phrase":
                continue
            phrase_label = str(metric["label"])
            entry = phrase_history.setdefault(phrase_label, {"label": phrase_label, "takes": {}})
            entry["takes"].setdefault(take["take_id"], []).append(metric["score"])
    phrases = []
    for label, entry in phrase_history.items():
        per_take = [
            {"take_id": tid, "score": round(float(np.mean(scores)), 1)}
            for tid, scores in entry["takes"].items()
        ]
        phrases.append(
            {
                "label": label,
                "history": per_take,
                "latest": per_take[-1]["score"] if per_take else None,
                "best": max(p["score"] for p in per_take) if per_take else None,
            }
        )
    frequency: dict[str, dict[str, Any]] = defaultdict(lambda: {"takes": 0, "minutes": 0.0})
    for take in takes:
        if take["created_at"]:
            day = take["created_at"][:10]
            frequency[day]["takes"] += 1
    for session in sessions:
        day = (session.get("started_at") or "")[:10]
        if day:
            frequency[day]["minutes"] += round(float(session.get("active_seconds") or 0.0) / 60.0, 1)
    best_take = max((t for t in takes if t["overall"] is not None), key=lambda t: t["overall"], default=None)
    return {
        "reference_id": reference_id,
        "takes": takes,
        "trends": trends,
        "regressions": warnings,
        "best_take": best_take,
        "latest_take": takes[-1] if takes else None,
        "phrases": phrases,
        "practice_frequency": [{"date": d, **v} for d, v in sorted(frequency.items())],
        "sessions": sessions,
        "milestones": milestones,
        "weaknesses": weakness_tracker(suggestion_rows, takes),
        "strengths": strengths(metric_rows, takes),
        "personal_bests": personal_bests(metric_rows, takes),
    }


def weakness_tracker(rows: list[dict[str, Any]], takes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {t["take_id"]: i for i, t in enumerate(takes)}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["tier"] not in comparison_store.ACTIONABLE_TIERS or row["take_recording_id"] not in order:
            continue
        grouped[row["finding_key"]].append(row)
    recent_ids = [t["take_id"] for t in takes[-PERSISTENT_RECENT:]]
    out = []
    for key, items in grouped.items():
        take_ids = sorted({i["take_recording_id"] for i in items}, key=lambda t: order[t])
        sessions = {i["session_id"] for i in items if i.get("session_id")}
        magnitudes = [i["magnitude"] for i in sorted(items, key=lambda i: order[i["take_recording_id"]])]
        recent_hits = sum(1 for t in recent_ids if t in take_ids)
        persistent = (
            len(take_ids) >= PERSISTENT_MIN_TAKES
            and recent_hits / max(1, len(recent_ids)) >= PERSISTENT_FRACTION
        )
        slope = _slope(magnitudes)
        payload = items[-1].get("payload") or {}
        texts = payload.get("texts") or {}
        metric_id = key.split(":", 1)[0]
        definition = METRICS.get(metric_id)
        trend = (
            "improving"
            if slope is not None and slope < -0.1
            else ("worsening" if slope is not None and slope > 0.1 else "stable")
        )
        out.append(
            {
                "key": key,
                "title": items[-1]["title"],
                "category": items[-1]["category"],
                "metric": definition.name if definition else metric_id,
                "occurrences": len(items),
                "takes": len(take_ids),
                "sessions": len(sessions),
                "median_magnitude": round(float(np.median(magnitudes)), 3),
                "latest_magnitude": magnitudes[-1],
                "trend": trend,
                "trend_slope": None if slope is None else round(slope, 3),
                "confidence": round(float(np.median([i["confidence"] for i in items])), 3),
                "persistent": persistent,
                "recent_hits": recent_hits,
                "recent_window": len(recent_ids),
                "last_seen_take": take_ids[-1],
                "first_seen_take": take_ids[0],
                "summary": texts.get("expert"),
                "label": "Persistent habit"
                if persistent
                else ("Recurring" if len(take_ids) >= 2 else "Seen once"),
            }
        )
    out.sort(key=lambda w: (not w["persistent"], -w["takes"], -w["median_magnitude"]))
    return out


def strengths(
    metric_rows: dict[str, list[dict[str, Any]]], takes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    per_metric: dict[str, list[float]] = defaultdict(list)
    for take in takes:
        values = defaultdict(list)
        for metric in metric_rows.get(take["comparison_id"], []):
            if (
                metric["score"] is not None
                and metric["confidence"] >= 0.45
                and METRICS.get(metric["metric_id"])
                and METRICS[metric["metric_id"]].weight > 0
            ):
                values[metric["metric_id"]].append(metric["score"])
        for metric_id, scores in values.items():
            per_metric[metric_id].append(float(np.median(scores)))
    out: list[dict[str, Any]] = []
    for metric_id, medians in per_metric.items():
        if (
            len(medians) >= STRENGTH_MIN_TAKES
            and float(np.median(medians)) >= STRENGTH_SCORE
            and min(medians[-3:]) >= STRENGTH_SCORE - 10
        ):
            definition = METRICS[metric_id]
            out.append(
                {
                    "metric_id": metric_id,
                    "name": definition.name,
                    "category": definition.category,
                    "median_score": round(float(np.median(medians)), 1),
                    "takes": len(medians),
                    "text": f"{definition.name} is consistently close to the reference ({len(medians)} takes).",
                }
            )
    out.sort(key=lambda s: -float(s["median_score"]))
    return out


def personal_bests(
    metric_rows: dict[str, list[dict[str, Any]]], takes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for take in takes:
        grouped = defaultdict(list)
        for metric in metric_rows.get(take["comparison_id"], []):
            if metric["score"] is not None and metric["confidence"] >= 0.45:
                grouped[metric["metric_id"]].append(metric["score"])
        for metric_id, scores in grouped.items():
            value = float(np.mean(scores))
            if metric_id not in best or value > best[metric_id]["score"]:
                best[metric_id] = {
                    "metric_id": metric_id,
                    "name": METRICS[metric_id].name if metric_id in METRICS else metric_id,
                    "score": round(value, 1),
                    "take_id": take["take_id"],
                    "take_number": take["take_number"],
                }
    return sorted(best.values(), key=lambda b: b["name"])


def days_since(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    return (
        datetime.now(datetime.fromisoformat(timestamp).tzinfo) - datetime.fromisoformat(timestamp)
    ).total_seconds() / 86400.0
