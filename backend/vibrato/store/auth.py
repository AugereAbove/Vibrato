from __future__ import annotations

import sqlite3
from typing import Any

from ..util import new_id, utcnow
from .rows import row_to_dict, rows_to_dicts


def create_user(conn: sqlite3.Connection, display_name: str, is_owner: bool = False) -> dict[str, Any]:
    user_id = new_id("usr")
    conn.execute(
        "INSERT INTO users (id, display_name, is_owner, created_at) VALUES (?, ?, ?, ?)",
        (user_id, display_name, int(is_owner), utcnow()),
    )
    user = get_user(conn, user_id)
    assert user is not None
    return user


def get_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def find_owner(conn: sqlite3.Connection) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM users WHERE is_owner = 1 LIMIT 1").fetchone())


def get_owner_id(conn: sqlite3.Connection) -> str:
    """The single site-owner user id. Global/pipeline settings (analysis tuning,
    scoring weights) are read from the owner's preferences regardless of which
    tester's recording is being processed - these are instance-wide technical
    settings, not per-tester personalization."""
    row = conn.execute("SELECT id FROM users WHERE is_owner = 1 LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No owner user exists - auth_service.bootstrap_owner() should run at startup")
    return str(row["id"])


def create_invite(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    code = new_id("inv")
    conn.execute(
        "INSERT INTO invites (code, user_id, created_at) VALUES (?, ?, ?)",
        (code, user_id, utcnow()),
    )
    invite = get_invite(conn, code)
    assert invite is not None
    return invite


def get_invite(conn: sqlite3.Connection, code: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone())


def find_unused_invite_for_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM invites WHERE user_id = ? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    )


def mark_invite_used(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("UPDATE invites SET used_at = ? WHERE code = ? AND used_at IS NULL", (utcnow(), code))


def list_tester_invites(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT i.code, i.created_at, i.used_at, u.id AS user_id, u.display_name "
            "FROM invites i JOIN users u ON u.id = i.user_id "
            "WHERE u.is_owner = 0 ORDER BY i.created_at DESC"
        ).fetchall()
    )


def create_session(conn: sqlite3.Connection, user_id: str, token: str, expires_at: str) -> None:
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, utcnow(), expires_at),
    )


def get_session_user(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.expires_at > ?",
            (token, utcnow()),
        ).fetchone()
    )


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
