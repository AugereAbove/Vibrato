from __future__ import annotations

import sqlite3
from typing import Any

from ..util import dumps, new_id, utcnow
from .rows import row_to_dict, rows_to_dicts


def create_profile(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    profile_id = new_id("cal")
    conn.execute(
        "INSERT INTO calibration_profiles (id, name, status, created_at) VALUES (?, ?, 'in_progress', ?)",
        (profile_id, name, utcnow()),
    )
    return get_profile(conn, profile_id) or {}


def get_profile(conn: sqlite3.Connection, profile_id: str) -> dict[str, Any] | None:
    profile = row_to_dict(
        conn.execute("SELECT * FROM calibration_profiles WHERE id = ?", (profile_id,)).fetchone()
    )
    if profile is not None:
        profile["samples"] = rows_to_dicts(
            conn.execute(
                "SELECT * FROM calibration_samples WHERE calibration_id = ? ORDER BY created_at",
                (profile_id,),
            ).fetchall()
        )
    return profile


def list_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute("SELECT * FROM calibration_profiles ORDER BY created_at DESC").fetchall()
    )


def active_profile(conn: sqlite3.Connection) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM calibration_profiles WHERE is_active = 1 AND status = 'complete' ORDER BY finalized_at DESC LIMIT 1"
        ).fetchone()
    )


def save_sample(
    conn: sqlite3.Connection, profile_id: str, step: str, recording_id: str, results: dict[str, Any]
) -> None:
    conn.execute(
        "INSERT INTO calibration_samples (id, calibration_id, step, recording_id, results_json, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(calibration_id, step) DO UPDATE SET recording_id = excluded.recording_id, results_json = excluded.results_json, created_at = excluded.created_at",
        (new_id("cs"), profile_id, step, recording_id, dumps(results), utcnow()),
    )


def finalize(conn: sqlite3.Connection, profile_id: str, results: dict[str, Any]) -> dict[str, Any] | None:
    conn.execute("UPDATE calibration_profiles SET is_active = 0")
    conn.execute(
        "UPDATE calibration_profiles SET status = 'complete', is_active = 1, results_json = ?, finalized_at = ? WHERE id = ?",
        (dumps(results), utcnow(), profile_id),
    )
    return get_profile(conn, profile_id)


def set_active(conn: sqlite3.Connection, profile_id: str | None) -> None:
    conn.execute("UPDATE calibration_profiles SET is_active = 0")
    if profile_id:
        conn.execute(
            "UPDATE calibration_profiles SET is_active = 1 WHERE id = ? AND status = 'complete'",
            (profile_id,),
        )


def delete_profile(conn: sqlite3.Connection, profile_id: str) -> bool:
    return conn.execute("DELETE FROM calibration_profiles WHERE id = ?", (profile_id,)).rowcount > 0


def create_reference_profile(conn: sqlite3.Connection, name: str, notes: str = "") -> dict[str, Any]:
    profile_id = new_id("rpf")
    now = utcnow()
    conn.execute(
        "INSERT INTO reference_profiles (id, name, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (profile_id, name, notes, now, now),
    )
    return (
        row_to_dict(conn.execute("SELECT * FROM reference_profiles WHERE id = ?", (profile_id,)).fetchone())
        or {}
    )


def list_reference_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT rp.*, (SELECT COUNT(*) FROM reference_recordings rr WHERE rr.reference_profile_id = rp.id) AS recordings FROM reference_profiles rp ORDER BY rp.name COLLATE NOCASE"
        ).fetchall()
    )


def get_reference_profile(conn: sqlite3.Connection, profile_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute("SELECT * FROM reference_profiles WHERE id = ?", (profile_id,)).fetchone()
    )


def update_reference_profile(
    conn: sqlite3.Connection, profile_id: str, name: str | None, notes: str | None
) -> dict[str, Any] | None:
    if name is not None:
        conn.execute(
            "UPDATE reference_profiles SET name = ?, updated_at = ? WHERE id = ?",
            (name, utcnow(), profile_id),
        )
    if notes is not None:
        conn.execute(
            "UPDATE reference_profiles SET notes = ?, updated_at = ? WHERE id = ?",
            (notes, utcnow(), profile_id),
        )
    return get_reference_profile(conn, profile_id)


def delete_reference_profile(conn: sqlite3.Connection, profile_id: str) -> bool:
    return conn.execute("DELETE FROM reference_profiles WHERE id = ?", (profile_id,)).rowcount > 0


def profile_recordings(conn: sqlite3.Connection, profile_id: str) -> list[str]:
    return [
        r["recording_id"]
        for r in conn.execute(
            "SELECT recording_id FROM reference_recordings WHERE reference_profile_id = ?", (profile_id,)
        ).fetchall()
    ]
