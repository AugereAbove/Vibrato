from __future__ import annotations

import sqlite3
from typing import Any

from ..util import dumps, new_id, utcnow
from .rows import row_to_dict, rows_to_dicts

ACTIONABLE_TIERS = ("primary", "secondary", "minor")


def save_comparison(
    conn: sqlite3.Connection,
    project_id: str | None,
    reference_id: str,
    take_id: str,
    alignment_id: str | None,
    version: str,
    overall_score: float | None,
    overall_confidence: float | None,
    category_scores: dict[str, Any],
    summary: dict[str, Any],
    result_path: str,
    metrics: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    conn.execute(
        "DELETE FROM comparisons WHERE reference_recording_id = ? AND take_recording_id = ?",
        (reference_id, take_id),
    )
    comparison_id = new_id("cmp")
    now = utcnow()
    conn.execute(
        "INSERT INTO comparisons (id, project_id, reference_recording_id, take_recording_id, alignment_id, version, status, overall_score, overall_confidence, category_scores_json, summary_json, result_path, created_at) VALUES (?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, ?, ?)",
        (
            comparison_id,
            project_id,
            reference_id,
            take_id,
            alignment_id,
            version,
            overall_score,
            overall_confidence,
            dumps(category_scores),
            dumps(summary),
            result_path,
            now,
        ),
    )
    conn.executemany(
        "INSERT INTO metric_values (id, comparison_id, metric_id, category, segment_level, ref_segment_id, user_segment_id, label, ref_start_s, ref_end_s, user_start_s, user_end_s, ref_value, user_value, difference, normalized_difference, unit, confidence, validity, score, weight, props_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                new_id("mv"),
                comparison_id,
                m["metric_id"],
                m["category"],
                m["level"],
                m.get("ref_segment_id"),
                m.get("user_segment_id"),
                m.get("label", ""),
                m.get("ref_start"),
                m.get("ref_end"),
                m.get("user_start"),
                m.get("user_end"),
                m["ref_value"] if isinstance(m.get("ref_value"), (int, float)) else None,
                m["user_value"] if isinstance(m.get("user_value"), (int, float)) else None,
                m.get("difference"),
                m.get("normalized"),
                m.get("unit", ""),
                m.get("confidence", 0.0),
                m.get("validity", "VALID"),
                m.get("score"),
                m.get("weight"),
                dumps(
                    {
                        "direction": m.get("direction"),
                        "ref_label": m.get("ref_value") if isinstance(m.get("ref_value"), str) else None,
                        "user_label": m.get("user_value") if isinstance(m.get("user_value"), str) else None,
                    }
                ),
            )
            for m in metrics
        ],
    )
    for rank, finding in enumerate(findings):
        suggestion_id = new_id("sug")
        practice = finding.get("practice") or {}
        conn.execute(
            "INSERT INTO coaching_suggestions (id, comparison_id, finding_key, finding_type, rank, tier, category, title, priority, confidence, importance, persistence, trainability, magnitude, direction, ref_start_s, ref_end_s, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                suggestion_id,
                comparison_id,
                finding["key"],
                finding["metric_id"],
                rank,
                finding.get("tier", "minor"),
                finding["category"],
                finding["title"],
                finding["priority"],
                finding["confidence"],
                finding["importance"],
                finding["persistence"],
                finding["trainability"],
                finding["magnitude"],
                finding.get("direction"),
                practice.get("ref_start"),
                practice.get("ref_end"),
                dumps(
                    {
                        "texts": finding.get("texts"),
                        "ranking": finding.get("ranking"),
                        "systematic": finding.get("systematic"),
                    }
                ),
            ),
        )
        texts = finding.get("texts") or {}
        conn.execute(
            "INSERT INTO interpretations (id, comparison_id, suggestion_id, basis, text, confidence, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("int"),
                comparison_id,
                suggestion_id,
                "inferred" if texts.get("adjust_basis") == "inferred" else "derived",
                str(texts.get("adjust", "")),
                finding["confidence"],
                dumps(finding.get("evidence", [])[:12]),
            ),
        )
    return comparison_id


def get_comparison(conn: sqlite3.Connection, comparison_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM comparisons WHERE id = ?", (comparison_id,)).fetchone())


def comparison_for_pair(conn: sqlite3.Connection, reference_id: str, take_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM comparisons WHERE reference_recording_id = ? AND take_recording_id = ?",
            (reference_id, take_id),
        ).fetchone()
    )


def comparisons_for_reference(conn: sqlite3.Connection, reference_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT c.*, r.created_at AS take_created_at, r.name AS take_name, ut.take_number, ut.session_id, r.favorite AS take_favorite, r.notes AS take_notes, ut.region_start_s, ut.region_end_s FROM comparisons c JOIN recordings r ON r.id = c.take_recording_id LEFT JOIN user_takes ut ON ut.recording_id = r.id WHERE c.reference_recording_id = ? ORDER BY r.created_at",
            (reference_id,),
        ).fetchall()
    )


def comparisons_for_project(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT c.*, r.created_at AS take_created_at, r.name AS take_name, ut.take_number, ut.session_id FROM comparisons c JOIN recordings r ON r.id = c.take_recording_id LEFT JOIN user_takes ut ON ut.recording_id = r.id WHERE c.project_id = ? ORDER BY r.created_at",
            (project_id,),
        ).fetchall()
    )


def metric_values(conn: sqlite3.Connection, comparison_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM metric_values WHERE comparison_id = ? ORDER BY category, ref_start_s",
            (comparison_id,),
        ).fetchall()
    )


def suggestions(conn: sqlite3.Connection, comparison_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM coaching_suggestions WHERE comparison_id = ? ORDER BY rank", (comparison_id,)
        ).fetchall()
    )


def finding_history(conn: sqlite3.Connection, reference_id: str, before: str | None) -> dict[str, int]:
    params: list[Any] = [reference_id]
    clause = ""
    if before:
        clause = "AND r.created_at < ?"
        params.append(before)
    rows = conn.execute(
        f"SELECT cs.finding_key, COUNT(DISTINCT c.take_recording_id) AS takes FROM coaching_suggestions cs JOIN comparisons c ON c.id = cs.comparison_id JOIN recordings r ON r.id = c.take_recording_id WHERE c.reference_recording_id = ? {clause} AND cs.tier IN ('primary', 'secondary', 'minor') GROUP BY cs.finding_key",
        params,
    ).fetchall()
    return {r["finding_key"]: int(r["takes"]) for r in rows}


def suggestions_history(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT cs.*, c.take_recording_id, c.reference_recording_id, r.created_at AS take_created_at, ut.take_number, ut.session_id FROM coaching_suggestions cs JOIN comparisons c ON c.id = cs.comparison_id JOIN recordings r ON r.id = c.take_recording_id LEFT JOIN user_takes ut ON ut.recording_id = r.id WHERE c.project_id = ? ORDER BY r.created_at",
            (project_id,),
        ).fetchall()
    )
