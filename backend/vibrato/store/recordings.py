from __future__ import annotations

import sqlite3
from typing import Any

from ..util import new_id, utcnow
from .rows import row_to_dict, rows_to_dicts

_SELECT = """
SELECT r.*, a.duration_s, a.source_format, a.source_subtype, a.source_sample_rate, a.source_bit_depth, a.source_channels,
       a.decoder, a.lossy, a.canonical_sample_rate, a.canonical_version, a.qc_json, a.size_bytes, a.original_extension,
       rr.reference_profile_id, rr.singer_label, rr.lyrics, rr.is_primary, rr.excluded_from_profile,
       ut.reference_recording_id, ut.session_id, ut.take_number, ut.synced_to_reference, ut.latency_ms, ut.region_start_s, ut.region_end_s,
       (SELECT c.overall_score FROM comparisons c WHERE c.take_recording_id = r.id ORDER BY c.created_at DESC LIMIT 1) AS overall_score,
       (SELECT c.id FROM comparisons c WHERE c.take_recording_id = r.id ORDER BY c.created_at DESC LIMIT 1) AS comparison_id,
       (SELECT ra.pipeline_version FROM recording_analyses ra WHERE ra.recording_id = r.id AND ra.status = 'complete' ORDER BY ra.created_at DESC LIMIT 1) AS analysis_version
FROM recordings r
JOIN audio_assets a ON a.content_hash = r.content_hash
LEFT JOIN reference_recordings rr ON rr.recording_id = r.id
LEFT JOIN user_takes ut ON ut.recording_id = r.id
"""

RECORDING_FIELDS = ("name", "notes", "favorite")
REFERENCE_FIELDS = ("lyrics", "singer_label", "is_primary", "excluded_from_profile", "reference_profile_id")
TAKE_FIELDS = (
    "synced_to_reference",
    "latency_ms",
    "region_start_s",
    "region_end_s",
    "reference_recording_id",
    "session_id",
)


def get_asset(conn: sqlite3.Connection, content_hash: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute("SELECT * FROM audio_assets WHERE content_hash = ?", (content_hash,)).fetchone()
    )


def insert_asset(conn: sqlite3.Connection, asset: dict[str, Any]) -> None:
    columns = list(asset.keys())
    conn.execute(
        f"INSERT OR REPLACE INTO audio_assets ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        tuple(asset[c] for c in columns),
    )


def get_recording(conn: sqlite3.Connection, recording_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(f"{_SELECT} WHERE r.id = ?", (recording_id,)).fetchone())


def list_recordings(
    conn: sqlite3.Connection, project_id: str | None, kind: str | None = None
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if project_id is not None:
        clauses.append("r.project_id = ?")
        params.append(project_id)
    if kind:
        clauses.append("r.kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return rows_to_dicts(
        conn.execute(
            f"{_SELECT} {where} ORDER BY r.kind, COALESCE(ut.take_number, 0), r.created_at", params
        ).fetchall()
    )


def find_duplicate(
    conn: sqlite3.Connection, project_id: str | None, content_hash: str, kind: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id FROM recordings WHERE project_id IS ? AND content_hash = ? AND kind = ? LIMIT 1",
        (project_id, content_hash, kind),
    ).fetchone()
    return get_recording(conn, row["id"]) if row else None


def next_take_number(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(ut.take_number) AS n FROM user_takes ut JOIN recordings r ON r.id = ut.recording_id WHERE r.project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["n"] or 0) + 1


def create_recording(
    conn: sqlite3.Connection,
    project_id: str | None,
    kind: str,
    name: str,
    original_filename: str,
    content_hash: str,
    source: str = "import",
    reference: dict[str, Any] | None = None,
    take: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recording_id = new_id("rec")
    now = utcnow()
    conn.execute(
        "INSERT INTO recordings (id, project_id, kind, source, name, original_filename, content_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (recording_id, project_id, kind, source, name, original_filename, content_hash, now, now),
    )
    if kind == "reference":
        ref = reference or {}
        conn.execute(
            "INSERT INTO reference_recordings (recording_id, reference_profile_id, singer_label, lyrics, is_primary) VALUES (?, ?, ?, ?, ?)",
            (
                recording_id,
                ref.get("reference_profile_id"),
                ref.get("singer_label", ""),
                ref.get("lyrics", ""),
                int(ref.get("is_primary", 0)),
            ),
        )
    elif kind == "take":
        t = take or {}
        conn.execute(
            "INSERT INTO user_takes (recording_id, reference_recording_id, session_id, take_number, synced_to_reference, latency_ms, region_start_s, region_end_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                recording_id,
                t.get("reference_recording_id"),
                t.get("session_id"),
                int(t.get("take_number", 1)),
                int(bool(t.get("synced_to_reference", False))),
                float(t.get("latency_ms", 0.0)),
                t.get("region_start_s"),
                t.get("region_end_s"),
            ),
        )
    recording = get_recording(conn, recording_id)
    assert recording is not None
    return recording


def update_recording(conn: sqlite3.Connection, recording_id: str, **fields: Any) -> dict[str, Any] | None:
    now = utcnow()
    base = {
        k: (int(v) if isinstance(v, bool) else v)
        for k, v in fields.items()
        if k in RECORDING_FIELDS and v is not None
    }
    if base:
        conn.execute(
            f"UPDATE recordings SET {', '.join(f'{k} = ?' for k in base)}, updated_at = ? WHERE id = ?",
            (*base.values(), now, recording_id),
        )
    ref = {
        k: (int(v) if isinstance(v, bool) else v)
        for k, v in fields.items()
        if k in REFERENCE_FIELDS and v is not None
    }
    if ref:
        conn.execute(
            f"UPDATE reference_recordings SET {', '.join(f'{k} = ?' for k in ref)} WHERE recording_id = ?",
            (*ref.values(), recording_id),
        )
    take = {
        k: (int(v) if isinstance(v, bool) else v)
        for k, v in fields.items()
        if k in TAKE_FIELDS and k in fields
    }
    if take:
        conn.execute(
            f"UPDATE user_takes SET {', '.join(f'{k} = ?' for k in take)} WHERE recording_id = ?",
            (*take.values(), recording_id),
        )
    return get_recording(conn, recording_id)


def delete_recording(conn: sqlite3.Connection, recording_id: str) -> bool:
    return conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,)).rowcount > 0


def primary_reference(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    references = list_recordings(conn, project_id, "reference")
    if not references:
        return None
    primary = [r for r in references if r.get("is_primary")]
    return (primary or references)[0]
