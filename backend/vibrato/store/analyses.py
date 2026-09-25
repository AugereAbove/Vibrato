from __future__ import annotations

import sqlite3
from typing import Any

from ..util import dumps, new_id, utcnow
from .rows import row_to_dict, rows_to_dicts


def latest_analysis(
    conn: sqlite3.Connection, recording_id: str, params_hash: str | None = None
) -> dict[str, Any] | None:
    if params_hash:
        row = conn.execute(
            "SELECT * FROM recording_analyses WHERE recording_id = ? AND params_hash = ? AND status = 'complete' ORDER BY created_at DESC LIMIT 1",
            (recording_id, params_hash),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM recording_analyses WHERE recording_id = ? AND status = 'complete' ORDER BY created_at DESC LIMIT 1",
            (recording_id,),
        ).fetchone()
    return row_to_dict(row)


def save_analysis(
    conn: sqlite3.Connection,
    recording_id: str,
    content_hash: str,
    pipeline_version: str,
    params_hash: str,
    features_path: str,
    analysis_path: str,
    summary: dict[str, Any],
    duration_ms: float,
    segments: list[dict[str, Any]],
    events: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> str:
    analysis_id = new_id("ana")
    now = utcnow()
    conn.execute(
        "INSERT INTO recording_analyses (id, recording_id, content_hash, pipeline_version, params_hash, status, features_path, analysis_path, summary_json, duration_ms, created_at) VALUES (?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, ?)",
        (
            analysis_id,
            recording_id,
            content_hash,
            pipeline_version,
            params_hash,
            features_path,
            analysis_path,
            dumps(summary),
            duration_ms,
            now,
        ),
    )
    conn.executemany(
        "INSERT INTO segments (id, analysis_id, recording_id, level, parent_id, ordinal, start_s, end_s, label, confidence, props_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                f"{analysis_id}:{s['id']}",
                analysis_id,
                recording_id,
                s["level"],
                s.get("parent_id"),
                s["ordinal"],
                s["start_s"],
                s["end_s"],
                s.get("label", ""),
                s.get("confidence", 0.0),
                dumps(s.get("props", {})),
            )
            for s in segments
        ],
    )
    conn.executemany(
        "INSERT INTO acoustic_events (id, analysis_id, recording_id, type, start_s, end_s, segment_id, confidence, props_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                f"{analysis_id}:{e['id']}",
                analysis_id,
                recording_id,
                e["type"],
                e["start_s"],
                e["end_s"],
                e.get("segment_id"),
                e.get("confidence", 0.0),
                dumps(e.get("props", {})),
            )
            for e in events
        ],
    )
    conn.executemany(
        "INSERT INTO analyzer_runs (id, analysis_id, analyzer_id, analyzer_version, status, validity, confidence, result_count, duration_ms, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                new_id("run"),
                analysis_id,
                r["analyzer_id"],
                r["analyzer_version"],
                r.get("status", "ok"),
                r.get("validity"),
                r.get("median_confidence"),
                int(r.get("result_count", 0)),
                r.get("duration_ms"),
                r.get("error"),
                now,
            )
            for r in runs
        ],
    )
    return analysis_id


def analyzer_runs(conn: sqlite3.Connection, analysis_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM analyzer_runs WHERE analysis_id = ? ORDER BY created_at", (analysis_id,)
        ).fetchall()
    )


def timing_statistics(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT analyzer_id, analyzer_version, COUNT(*) AS runs, AVG(duration_ms) AS mean_ms, MAX(duration_ms) AS max_ms, SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS failures FROM analyzer_runs GROUP BY analyzer_id, analyzer_version ORDER BY analyzer_id"
        ).fetchall()
    )


def outdated_recordings(conn: sqlite3.Connection, current_version: str) -> list[str]:
    rows = conn.execute(
        "SELECT recording_id, pipeline_version FROM recording_analyses ra WHERE status = 'complete' AND created_at = (SELECT MAX(created_at) FROM recording_analyses x WHERE x.recording_id = ra.recording_id)"
    ).fetchall()
    return [r["recording_id"] for r in rows if r["pipeline_version"] != current_version]
