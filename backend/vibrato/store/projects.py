from __future__ import annotations

import sqlite3
from typing import Any

from ..util import new_id, utcnow
from .rows import row_to_dict, rows_to_dicts

EDITABLE = (
    "name",
    "song_title",
    "song_artist",
    "singer_label",
    "notes",
    "favorite",
    "archived",
    "reference_profile_id",
)
SORTS = {
    "recent": "COALESCE(p.last_opened_at, p.updated_at) DESC",
    "name": "p.name COLLATE NOCASE ASC",
    "created": "p.created_at DESC",
    "updated": "p.updated_at DESC",
    "score": "best_score IS NULL, best_score DESC",
}

_SELECT = """
SELECT p.*,
  (SELECT COUNT(*) FROM recordings r WHERE r.project_id = p.id AND r.kind = 'reference') AS reference_count,
  (SELECT COUNT(*) FROM recordings r WHERE r.project_id = p.id AND r.kind = 'take') AS take_count,
  (SELECT MAX(c.overall_score) FROM comparisons c WHERE c.project_id = p.id) AS best_score,
  (SELECT c.overall_score FROM comparisons c WHERE c.project_id = p.id ORDER BY c.created_at DESC LIMIT 1) AS latest_score
FROM projects p
"""


def list_projects(
    conn: sqlite3.Connection,
    search: str | None = None,
    sort: str = "recent",
    include_archived: bool = False,
    favorites_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if not include_archived:
        clauses.append("p.archived = 0")
    if favorites_only:
        clauses.append("p.favorite = 1")
    if search:
        clauses.append(
            "(p.name LIKE ? OR p.song_title LIKE ? OR p.song_artist LIKE ? OR p.singer_label LIKE ? OR p.notes LIKE ?)"
        )
        params.extend([f"%{search}%"] * 5)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = SORTS.get(sort, SORTS["recent"])
    rows = conn.execute(f"{_SELECT} {where} ORDER BY p.favorite DESC, {order}", params).fetchall()
    return rows_to_dicts(rows)


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(f"{_SELECT} WHERE p.id = ?", (project_id,)).fetchone())


def create_project(
    conn: sqlite3.Connection,
    name: str,
    song_title: str = "",
    song_artist: str = "",
    singer_label: str = "",
    notes: str = "",
    is_demo: bool = False,
) -> dict[str, Any]:
    project_id = new_id("prj")
    now = utcnow()
    conn.execute(
        "INSERT INTO projects (id, name, song_title, song_artist, singer_label, notes, is_demo, created_at, updated_at, last_opened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            name.strip() or "Untitled project",
            song_title,
            song_artist,
            singer_label,
            notes,
            int(is_demo),
            now,
            now,
            now,
        ),
    )
    project = get_project(conn, project_id)
    assert project is not None
    return project


def update_project(conn: sqlite3.Connection, project_id: str, **fields: Any) -> dict[str, Any] | None:
    updates = {
        k: (int(v) if isinstance(v, bool) else v)
        for k, v in fields.items()
        if k in EDITABLE and v is not None
    }
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE projects SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), utcnow(), project_id),
        )
    return get_project(conn, project_id)


def touch_project(conn: sqlite3.Connection, project_id: str, opened: bool = False) -> None:
    now = utcnow()
    if opened:
        conn.execute("UPDATE projects SET last_opened_at = ? WHERE id = ?", (now, project_id))
    else:
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))


def delete_project(conn: sqlite3.Connection, project_id: str) -> bool:
    return conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0


def duplicate_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    source = get_project(conn, project_id)
    if source is None:
        return None
    copy = create_project(
        conn,
        f"{source['name']} (copy)",
        source["song_title"],
        source["song_artist"],
        source["singer_label"],
        source["notes"],
    )
    mapping: dict[str, str] = {}
    recordings = conn.execute(
        "SELECT * FROM recordings WHERE project_id = ? ORDER BY created_at", (project_id,)
    ).fetchall()
    now = utcnow()
    for row in recordings:
        new_rec = new_id("rec")
        mapping[row["id"]] = new_rec
        conn.execute(
            "INSERT INTO recordings (id, project_id, kind, source, name, original_filename, content_hash, favorite, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_rec,
                copy["id"],
                row["kind"],
                row["source"],
                row["name"],
                row["original_filename"],
                row["content_hash"],
                row["favorite"],
                row["notes"],
                row["created_at"],
                now,
            ),
        )
    for old, new in mapping.items():
        ref = conn.execute("SELECT * FROM reference_recordings WHERE recording_id = ?", (old,)).fetchone()
        if ref:
            conn.execute(
                "INSERT INTO reference_recordings (recording_id, reference_profile_id, singer_label, lyrics, is_primary, excluded_from_profile) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    new,
                    ref["reference_profile_id"],
                    ref["singer_label"],
                    ref["lyrics"],
                    ref["is_primary"],
                    ref["excluded_from_profile"],
                ),
            )
        take = conn.execute("SELECT * FROM user_takes WHERE recording_id = ?", (old,)).fetchone()
        if take:
            conn.execute(
                "INSERT INTO user_takes (recording_id, reference_recording_id, session_id, take_number, synced_to_reference, latency_ms, region_start_s, region_end_s) VALUES (?, ?, NULL, ?, ?, ?, ?, ?)",
                (
                    new,
                    mapping.get(take["reference_recording_id"]),
                    take["take_number"],
                    take["synced_to_reference"],
                    take["latency_ms"],
                    take["region_start_s"],
                    take["region_end_s"],
                ),
            )
        for table, columns in (
            ("song_sections", "label, start_s, end_s, ordinal, created_at"),
            ("bookmarks", "start_s, end_s, label, color, created_at"),
            ("pronunciation_overrides", "word_index, word, pronunciation, created_at"),
        ):
            prefix = {"song_sections": "sec", "bookmarks": "bmk", "pronunciation_overrides": "prn"}[table]
            for item in conn.execute(
                f"SELECT {columns} FROM {table} WHERE recording_id = ?", (old,)
            ).fetchall():
                conn.execute(
                    f"INSERT INTO {table} (id, recording_id, {columns}) VALUES (?, ?, {', '.join('?' for _ in item)})",
                    (new_id(prefix), new, *tuple(item)),
                )
    return get_project(conn, copy["id"])
