from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..alignment.aligner import ALIGNMENT_VERSION, Alignment, Anchor, align, realign_region
from ..audio.errors import UserFacingError
from ..coaching.engine import coaching_report, why_different
from ..compare.comparator import COMPARISON_VERSION, compare
from ..compare.model import MetricComparison
from ..compare.scoring import category_scores
from ..db import get_db
from ..logging_setup import get_logger
from ..storage import alignment_file, comparison_file
from ..store import comparisons as comparison_store
from ..store import misc as misc_store
from ..store import projects as project_store
from ..store import recordings as recording_store
from ..store.auth import get_owner_id
from ..store.misc import get_preferences
from ..tasks.manager import TaskContext
from ..util import read_json, stable_hash, write_json_atomic
from .analysis_service import load_view

log = get_logger("comparison")


def _anchors(reference_id: str, take_id: str) -> list[Anchor]:
    with get_db().read() as conn:
        rows = misc_store.list_anchors(conn, reference_id, take_id)
    return [
        Anchor(r["ref_time_s"], r["user_time_s"], bool(r["locked"]), r["source"], r["id"], r["label"])
        for r in rows
    ]


def scoring_preferences() -> tuple[dict[str, bool], dict[str, float]]:
    with get_db().read() as conn:
        prefs = get_preferences(conn, get_owner_id(conn))
    enabled = {k.split(".", 2)[2]: bool(v) for k, v in prefs.items() if k.startswith("scoring.enabled.")}
    weights = {k.split(".", 2)[2]: float(v) for k, v in prefs.items() if k.startswith("scoring.weight.")}
    return enabled, weights


def get_alignment(
    reference_id: str,
    take_id: str,
    ref_view: Any,
    take_view: Any,
    take: dict[str, Any],
    ref_analysis: dict[str, Any],
    take_analysis: dict[str, Any],
    force: bool = False,
) -> tuple[Alignment, str]:
    anchors = _anchors(reference_id, take_id)
    region = (
        (float(take["region_start_s"]), float(take["region_end_s"]))
        if take.get("region_start_s") is not None and take.get("region_end_s") is not None
        else None
    )
    key = stable_hash(
        {
            "version": ALIGNMENT_VERSION,
            "ref": ref_analysis["id"],
            "take": take_analysis["id"],
            "anchors": [(round(a.ref_time_s, 3), round(a.user_time_s, 3), a.locked) for a in anchors],
            "synced": bool(take.get("synced_to_reference")),
            "region": region,
        }
    )
    path = alignment_file(reference_id, take_id, key)
    if path.exists() and not force:
        alignment = Alignment.load(path)
    else:
        from ..analysis.segmentation.hierarchy import Hierarchy

        ref_h = Hierarchy(
            segments=ref_view.segments,
            events=ref_view.events,
            phrases=[],
            breaths=[],
            syllables=[],
            notes=[],
            class_segments=[],
        )
        take_h = Hierarchy(
            segments=take_view.segments,
            events=take_view.events,
            phrases=[],
            breaths=[],
            syllables=[],
            notes=[],
            class_segments=[],
        )
        alignment = align(
            ref_view.features,
            take_view.features,
            ref_h,
            take_h,
            anchors,
            synced=bool(take.get("synced_to_reference")),
            latency_s=0.0,
            ref_region=region,
        )
        alignment.save(path)
    with get_db().tx() as conn:
        alignment_id = misc_store.save_alignment(
            conn,
            reference_id,
            take_id,
            alignment.version,
            alignment.method,
            alignment.overall_confidence,
            alignment.global_offset_s,
            alignment.tempo_ratio,
            alignment.transposition_semitones,
            key,
            str(path),
            alignment.summary(),
        )
    return alignment, alignment_id


def run_comparison(
    take_id: str,
    reference_id: str | None = None,
    context: TaskContext | None = None,
    force_align: bool = False,
) -> dict[str, Any]:
    with get_db().read() as conn:
        take = recording_store.get_recording(conn, take_id)
    if take is None or take["kind"] != "take":
        raise UserFacingError(
            "This take no longer exists.",
            "It may have been deleted.",
            "Refresh the project.",
            code="not_found",
        )
    reference_id = reference_id or take.get("reference_recording_id")
    if not reference_id:
        raise UserFacingError(
            what="This take has no reference to compare against.",
            why="No reference recording has been imported into the project yet.",
            action="Import a reference vocal, then run the comparison again.",
            code="no_reference",
        )
    if context:
        context.progress(0.01, "Analysing reference", stage="reference")
    ref_view, ref_analysis = load_view(reference_id, _Sub(context, 0.0, 0.4) if context else None)
    if context:
        context.progress(0.4, "Analysing take", stage="take")
    take_view, take_analysis = load_view(take_id, _Sub(context, 0.4, 0.8) if context else None)
    if context:
        context.progress(0.82, "Aligning take to reference", stage="align")
    alignment, alignment_id = get_alignment(
        reference_id, take_id, ref_view, take_view, take, ref_analysis, take_analysis, force_align
    )
    if context:
        context.progress(0.88, "Comparing measurements", stage="compare")
    enabled, weights = scoring_preferences()
    region = (
        (float(take["region_start_s"]), float(take["region_end_s"]))
        if take.get("region_start_s") is not None
        else None
    )
    result = compare(
        ref_view,
        take_view,
        alignment,
        synced=bool(take.get("synced_to_reference")),
        enabled_categories=enabled,
        category_weights=weights,
        region=region,
    )
    with get_db().read() as conn:
        history = comparison_store.finding_history(conn, reference_id, take["created_at"])
        overrides, dismissals = misc_store.coaching_overrides(conn, take.get("project_id"))
    if context:
        context.progress(0.94, "Building coaching", stage="coach")
    coaching = coaching_report(
        result.metrics,
        ref_view,
        alignment.transposition_semitones,
        history,
        overrides,
        dismissals,
        result.scores,
    )
    payload = result.to_json()
    payload["coaching"] = coaching
    payload["reference_id"] = reference_id
    payload["take_id"] = take_id
    payload["reference_analysis"] = {"id": ref_analysis["id"], "version": ref_analysis["pipeline_version"]}
    payload["take_analysis"] = {"id": take_analysis["id"], "version": take_analysis["pipeline_version"]}
    overall = result.scores["overall"]
    summary = {
        "summary_text": coaching["summary"],
        "primary": coaching["primary"][0]["title"] if coaching["primary"] else None,
        "alignment_confidence": alignment.overall_confidence,
        "transposition": alignment.transposition_semitones,
        "coverage": result.coverage,
    }
    with get_db().tx() as conn:
        comparison_id = comparison_store.save_comparison(
            conn,
            take.get("project_id"),
            reference_id,
            take_id,
            alignment_id,
            COMPARISON_VERSION,
            overall["score"],
            overall["confidence"],
            {
                k: {"score": v["score"], "confidence": v["confidence"]}
                for k, v in result.scores["categories"].items()
            },
            summary,
            "",
            [m.to_dict() | {"unit": _unit(m)} for m in result.metrics],
            [f for tier in ("primary", "secondary", "minor") for f in coaching[tier]],
        )
        path = comparison_file(comparison_id)
        conn.execute("UPDATE comparisons SET result_path = ? WHERE id = ?", (str(path), comparison_id))
        if take.get("project_id"):
            _record_milestones(conn, take, reference_id, comparison_id, result.scores)
            project_store.touch_project(conn, take["project_id"])
    payload["id"] = comparison_id
    write_json_atomic(path, payload)
    if context:
        context.progress(1.0, "Comparison ready")
    return {
        "comparison_id": comparison_id,
        "take_id": take_id,
        "reference_id": reference_id,
        "overall": overall["score"],
    }


def _unit(metric: MetricComparison) -> str:
    from ..compare.metrics import METRICS

    return METRICS[metric.metric_id].unit


class _Sub:
    def __init__(self, parent: TaskContext | None, start: float, end: float) -> None:
        self.parent = parent
        self.start = start
        self.end = end

    def progress(self, fraction: float, message: str = "", stage: str | None = None) -> None:
        if self.parent:
            self.parent.progress(self.start + (self.end - self.start) * fraction, message, stage)

    def sub(self, start: float, end: float) -> Callable[[float, str], None]:
        def report(fraction: float, message: str) -> None:
            self.progress(start + (end - start) * fraction, message)

        return report

    def check_cancelled(self) -> None:
        if self.parent:
            self.parent.check_cancelled()


def _record_milestones(
    conn: Any, take: dict[str, Any], reference_id: str, comparison_id: str, scores: dict[str, Any]
) -> None:
    previous = [
        c
        for c in comparison_store.comparisons_for_reference(conn, reference_id)
        if c["take_recording_id"] != take["id"]
    ]
    overall = scores["overall"]["score"]
    if overall is None:
        return
    earlier = [c["overall_score"] for c in previous if c["overall_score"] is not None]
    if earlier and overall > max(earlier):
        misc_store.add_milestone(
            conn,
            take["project_id"],
            take["id"],
            "personal_best",
            f"Personal best: {overall:.0f}",
            {"score": overall, "previous_best": max(earlier), "comparison_id": comparison_id},
        )
    for category, data in scores["categories"].items():
        score = data.get("score")
        if score is None or float(data.get("confidence", 0)) < 0.5:
            continue
        values = [
            float(v)
            for v in (((c.get("category_scores") or {}).get(category) or {}).get("score") for c in previous)
            if v is not None
        ]
        if len(values) >= 2 and score >= 90 and max(values) < 90:
            misc_store.add_milestone(
                conn,
                take["project_id"],
                take["id"],
                "category_mastery",
                f"{category.title()} reached {score:.0f}",
                {"category": category, "score": score},
            )


def comparison_payload(comparison_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        row = comparison_store.get_comparison(conn, comparison_id)
        if row is None:
            raise UserFacingError(
                "This comparison no longer exists.",
                "The take or reference may have been deleted or re-analysed.",
                "Run the comparison again.",
                code="not_found",
            )
        take = recording_store.get_recording(conn, row["take_recording_id"])
        history = comparison_store.comparisons_for_reference(conn, row["reference_recording_id"])
    payload = read_json(comparison_file(comparison_id))
    ordered = [h for h in history]
    index = next((i for i, h in enumerate(ordered) if h["id"] == comparison_id), None)
    previous = ordered[index - 1] if index is not None and index > 0 else None
    best = max(
        (h for h in ordered if h["overall_score"] is not None), key=lambda h: h["overall_score"], default=None
    )
    payload["take"] = take
    payload["previous"] = (
        None
        if previous is None
        else {
            "comparison_id": previous["id"],
            "take_id": previous["take_recording_id"],
            "take_number": previous.get("take_number"),
            "overall": previous["overall_score"],
            "categories": previous.get("category_scores"),
        }
    )
    payload["personal_best"] = (
        None
        if best is None
        else {
            "comparison_id": best["id"],
            "take_id": best["take_recording_id"],
            "take_number": best.get("take_number"),
            "overall": best["overall_score"],
            "categories": best.get("category_scores"),
        }
    )
    payload["created_at"] = row["created_at"]
    payload["is_outdated"] = row["version"] != COMPARISON_VERSION
    return payload


def rescore(comparison_id: str, enabled: dict[str, bool], weights: dict[str, float]) -> dict[str, Any]:
    payload = read_json(comparison_file(comparison_id))
    metrics = [MetricComparison.from_dict(m) for m in payload["metrics"]]
    return category_scores(metrics, enabled, weights)


def explain_region(comparison_id: str, start_s: float, end_s: float) -> dict[str, Any]:
    payload = read_json(comparison_file(comparison_id))
    metrics = [MetricComparison.from_dict(m) for m in payload["metrics"]]
    ref_view, _ = load_view(payload["reference_id"])
    with get_db().read() as conn:
        take = recording_store.get_recording(conn, payload["take_id"])
        history = comparison_store.finding_history(
            conn, payload["reference_id"], take["created_at"] if take else None
        )
        overrides, _ = misc_store.coaching_overrides(conn, take.get("project_id") if take else None)
    return why_different(
        metrics,
        ref_view,
        start_s,
        end_s,
        float(payload["alignment"].get("transposition_semitones", 0.0)),
        history,
        overrides,
    )


def realign(comparison_id: str, start_s: float, end_s: float) -> dict[str, Any]:
    payload = read_json(comparison_file(comparison_id))
    reference_id, take_id = payload["reference_id"], payload["take_id"]
    ref_view, ref_analysis = load_view(reference_id)
    take_view, take_analysis = load_view(take_id)
    with get_db().read() as conn:
        take = recording_store.get_recording(conn, take_id)
    alignment, _ = get_alignment(
        reference_id, take_id, ref_view, take_view, take or {}, ref_analysis, take_analysis
    )
    updated = realign_region(alignment, ref_view.features, take_view.features, start_s, end_s)
    with get_db().tx() as conn:
        for t in (start_s, end_s):
            misc_store.add_anchor(
                conn,
                reference_id,
                take_id,
                t,
                float(updated.ref_to_user(t)),
                True,
                "realign",
                "region boundary",
            )
    return run_comparison(take_id, reference_id)
