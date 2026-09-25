from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..util import dumps, new_id, utcnow
from .rows import row_to_dict, rows_to_dicts

SESSION_GAP = timedelta(minutes=30)


def active_session(conn: sqlite3.Connection, project_id: str, kind: str = "practice") -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM sessions WHERE project_id = ? AND ended_at IS NULL ORDER BY last_activity_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    now = datetime.fromisoformat(utcnow())
    if row is not None:
        last = datetime.fromisoformat(row["last_activity_at"])
        if now - last <= SESSION_GAP:
            active = (now - last).total_seconds()
            conn.execute(
                "UPDATE sessions SET last_activity_at = ?, active_seconds = active_seconds + ? WHERE id = ?",
                (now.isoformat(timespec="milliseconds"), active, row["id"]),
            )
            return (
                row_to_dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (row["id"],)).fetchone())
                or {}
            )
        conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (row["last_activity_at"], row["id"]))
    session_id = new_id("ses")
    stamp = now.isoformat(timespec="milliseconds")
    conn.execute(
        "INSERT INTO sessions (id, project_id, kind, started_at, last_activity_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, project_id, kind, stamp, stamp),
    )
    return row_to_dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()) or {}


def list_sessions(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM user_takes ut WHERE ut.session_id = s.id) AS takes FROM sessions s WHERE s.project_id = ? ORDER BY s.started_at DESC",
            (project_id,),
        ).fetchall()
    )


def update_session(
    conn: sqlite3.Connection, session_id: str, notes: str | None = None, end: bool = False
) -> dict[str, Any] | None:
    if notes is not None:
        conn.execute("UPDATE sessions SET notes = ? WHERE id = ?", (notes, session_id))
    if end:
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL", (utcnow(), session_id)
        )
    return row_to_dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def list_bookmarks(conn: sqlite3.Connection, recording_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM bookmarks WHERE recording_id = ? ORDER BY start_s", (recording_id,)
        ).fetchall()
    )


def add_bookmark(
    conn: sqlite3.Connection, recording_id: str, start_s: float, end_s: float | None, label: str, color: str
) -> dict[str, Any]:
    bookmark_id = new_id("bmk")
    conn.execute(
        "INSERT INTO bookmarks (id, recording_id, start_s, end_s, label, color, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (bookmark_id, recording_id, start_s, end_s, label, color, utcnow()),
    )
    return row_to_dict(conn.execute("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()) or {}


def update_bookmark(conn: sqlite3.Connection, bookmark_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        k: v for k, v in fields.items() if k in {"start_s", "end_s", "label", "color"} and v is not None
    }
    if allowed:
        conn.execute(
            f"UPDATE bookmarks SET {', '.join(f'{k} = ?' for k in allowed)} WHERE id = ?",
            (*allowed.values(), bookmark_id),
        )
    return row_to_dict(conn.execute("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone())


def delete_bookmark(conn: sqlite3.Connection, bookmark_id: str) -> bool:
    return conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,)).rowcount > 0


def list_sections(conn: sqlite3.Connection, recording_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM song_sections WHERE recording_id = ? ORDER BY start_s", (recording_id,)
        ).fetchall()
    )


def replace_sections(
    conn: sqlite3.Connection, recording_id: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    conn.execute("DELETE FROM song_sections WHERE recording_id = ?", (recording_id,))
    now = utcnow()
    for index, section in enumerate(sorted(sections, key=lambda s: float(s["start_s"]))):
        conn.execute(
            "INSERT INTO song_sections (id, recording_id, label, start_s, end_s, ordinal, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("sec"),
                recording_id,
                str(section.get("label") or f"Section {index + 1}"),
                float(section["start_s"]),
                float(section["end_s"]),
                index,
                now,
            ),
        )
    return list_sections(conn, recording_id)


def pronunciation_overrides(conn: sqlite3.Connection, recording_id: str) -> dict[int, str]:
    return {
        int(r["word_index"]): r["pronunciation"]
        for r in conn.execute(
            "SELECT word_index, pronunciation FROM pronunciation_overrides WHERE recording_id = ?",
            (recording_id,),
        ).fetchall()
    }


def set_pronunciation(
    conn: sqlite3.Connection, recording_id: str, word_index: int, word: str, pronunciation: str | None
) -> None:
    if not pronunciation:
        conn.execute(
            "DELETE FROM pronunciation_overrides WHERE recording_id = ? AND word_index = ?",
            (recording_id, word_index),
        )
        return
    conn.execute(
        "INSERT INTO pronunciation_overrides (id, recording_id, word_index, word, pronunciation, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(recording_id, word_index) DO UPDATE SET pronunciation = excluded.pronunciation, word = excluded.word",
        (new_id("prn"), recording_id, word_index, word, pronunciation.upper().strip(), utcnow()),
    )


def get_preferences(conn: sqlite3.Connection) -> dict[str, Any]:
    import json

    return {
        r["key"]: json.loads(r["value_json"])
        for r in conn.execute("SELECT key, value_json FROM user_preferences").fetchall()
    }


def set_preferences(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    now = utcnow()
    for key, value in values.items():
        if value is None:
            conn.execute("DELETE FROM user_preferences WHERE key = ?", (key,))
        else:
            conn.execute(
                "INSERT INTO user_preferences (key, value_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                (key, dumps(value), now),
            )


def clear_preferences(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM user_preferences")


def coaching_overrides(
    conn: sqlite3.Connection, project_id: str | None
) -> tuple[dict[str, str], dict[str, int]]:
    rows = conn.execute(
        "SELECT finding_type, action FROM coaching_overrides WHERE project_id IS ? OR project_id IS NULL ORDER BY created_at",
        (project_id,),
    ).fetchall()
    actions: dict[str, str] = {}
    dismissals: dict[str, int] = {}
    for row in rows:
        if row["action"] == "dismiss":
            dismissals[row["finding_type"]] = dismissals.get(row["finding_type"], 0) + 1
        else:
            actions[row["finding_type"]] = row["action"]
    return actions, dismissals


def add_coaching_override(
    conn: sqlite3.Connection, project_id: str | None, finding_type: str, action: str
) -> None:
    if action in {"ignore", "boost"}:
        conn.execute(
            "DELETE FROM coaching_overrides WHERE project_id IS ? AND finding_type = ? AND action IN ('ignore', 'boost')",
            (project_id, finding_type),
        )
    conn.execute(
        "INSERT INTO coaching_overrides (id, project_id, finding_type, action, created_at) VALUES (?, ?, ?, ?, ?)",
        (new_id("ovr"), project_id, finding_type, action, utcnow()),
    )


def clear_coaching_overrides(
    conn: sqlite3.Connection, project_id: str | None, finding_type: str | None = None
) -> None:
    if finding_type:
        conn.execute(
            "DELETE FROM coaching_overrides WHERE project_id IS ? AND finding_type = ?",
            (project_id, finding_type),
        )
    else:
        conn.execute("DELETE FROM coaching_overrides WHERE project_id IS ?", (project_id,))


def list_overrides(conn: sqlite3.Connection, project_id: str | None) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM coaching_overrides WHERE project_id IS ? ORDER BY created_at", (project_id,)
        ).fetchall()
    )


def add_milestone(
    conn: sqlite3.Connection,
    project_id: str,
    take_id: str | None,
    kind: str,
    title: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO milestones (id, project_id, take_recording_id, kind, title, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id("mil"), project_id, take_id, kind, title, dumps(payload), utcnow()),
    )


def list_milestones(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY created_at", (project_id,)
        ).fetchall()
    )


def list_anchors(conn: sqlite3.Connection, reference_id: str, take_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM alignment_anchors WHERE reference_recording_id = ? AND take_recording_id = ? ORDER BY ref_time_s",
            (reference_id, take_id),
        ).fetchall()
    )


def add_anchor(
    conn: sqlite3.Connection,
    reference_id: str,
    take_id: str,
    ref_time_s: float,
    user_time_s: float,
    locked: bool,
    source: str,
    label: str,
) -> dict[str, Any]:
    anchor_id = new_id("anc")
    conn.execute(
        "INSERT INTO alignment_anchors (id, reference_recording_id, take_recording_id, ref_time_s, user_time_s, locked, source, label, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (anchor_id, reference_id, take_id, ref_time_s, user_time_s, int(locked), source, label, utcnow()),
    )
    return (
        row_to_dict(conn.execute("SELECT * FROM alignment_anchors WHERE id = ?", (anchor_id,)).fetchone())
        or {}
    )


def update_anchor(conn: sqlite3.Connection, anchor_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        k: (int(v) if isinstance(v, bool) else v)
        for k, v in fields.items()
        if k in {"ref_time_s", "user_time_s", "locked", "label"} and v is not None
    }
    if allowed:
        conn.execute(
            f"UPDATE alignment_anchors SET {', '.join(f'{k} = ?' for k in allowed)} WHERE id = ?",
            (*allowed.values(), anchor_id),
        )
    return row_to_dict(conn.execute("SELECT * FROM alignment_anchors WHERE id = ?", (anchor_id,)).fetchone())


def delete_anchor(conn: sqlite3.Connection, anchor_id: str) -> bool:
    return conn.execute("DELETE FROM alignment_anchors WHERE id = ?", (anchor_id,)).rowcount > 0


def save_alignment(
    conn: sqlite3.Connection,
    reference_id: str,
    take_id: str,
    version: str,
    method: str,
    confidence: float,
    offset: float,
    tempo: float,
    transposition: float,
    anchors_hash: str,
    path: str,
    summary: dict[str, Any],
) -> str:
    existing = conn.execute(
        "SELECT id FROM alignments WHERE reference_recording_id = ? AND take_recording_id = ?",
        (reference_id, take_id),
    ).fetchone()
    now = utcnow()
    if existing:
        conn.execute(
            "UPDATE alignments SET version = ?, method = ?, status = 'complete', confidence = ?, global_offset_s = ?, tempo_ratio = ?, transposition_semitones = ?, anchors_hash = ?, path_file = ?, summary_json = ?, updated_at = ? WHERE id = ?",
            (
                version,
                method,
                confidence,
                offset,
                tempo,
                transposition,
                anchors_hash,
                path,
                dumps(summary),
                now,
                existing["id"],
            ),
        )
        return str(existing["id"])
    alignment_id = new_id("aln")
    conn.execute(
        "INSERT INTO alignments (id, reference_recording_id, take_recording_id, version, method, status, confidence, global_offset_s, tempo_ratio, transposition_semitones, anchors_hash, path_file, summary_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            alignment_id,
            reference_id,
            take_id,
            version,
            method,
            confidence,
            offset,
            tempo,
            transposition,
            anchors_hash,
            path,
            dumps(summary),
            now,
            now,
        ),
    )
    return alignment_id


def get_alignment(conn: sqlite3.Connection, reference_id: str, take_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM alignments WHERE reference_recording_id = ? AND take_recording_id = ?",
            (reference_id, take_id),
        ).fetchone()
    )


def save_render(
    conn: sqlite3.Connection,
    render_id: str,
    take_id: str,
    reference_id: str,
    transform: str,
    params: dict[str, Any],
    params_hash: str,
    version: str,
    path: str,
    approximate: bool,
    warnings: list[str],
    description: dict[str, Any],
) -> dict[str, Any]:
    existing = conn.execute(
        "SELECT id FROM counterfactual_renders WHERE take_recording_id = ? AND reference_recording_id = ? AND params_hash = ? AND version = ?",
        (take_id, reference_id, params_hash, version),
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM counterfactual_renders WHERE id = ?", (existing["id"],))
    conn.execute(
        "INSERT INTO counterfactual_renders (id, take_recording_id, reference_recording_id, transform, params_json, params_hash, version, path, approximate, warnings_json, description_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            render_id,
            take_id,
            reference_id,
            transform,
            dumps(params),
            params_hash,
            version,
            path,
            int(approximate),
            dumps(warnings),
            dumps(description),
            utcnow(),
        ),
    )
    return (
        row_to_dict(
            conn.execute("SELECT * FROM counterfactual_renders WHERE id = ?", (render_id,)).fetchone()
        )
        or {}
    )


def find_render(
    conn: sqlite3.Connection, take_id: str, reference_id: str, params_hash: str, version: str
) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM counterfactual_renders WHERE take_recording_id = ? AND reference_recording_id = ? AND params_hash = ? AND version = ?",
            (take_id, reference_id, params_hash, version),
        ).fetchone()
    )


def get_render(conn: sqlite3.Connection, render_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute("SELECT * FROM counterfactual_renders WHERE id = ?", (render_id,)).fetchone()
    )


def list_renders(conn: sqlite3.Connection, take_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM counterfactual_renders WHERE take_recording_id = ? ORDER BY created_at DESC",
            (take_id,),
        ).fetchall()
    )
