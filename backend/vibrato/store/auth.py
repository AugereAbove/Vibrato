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


def set_disabled(conn: sqlite3.Connection, user_id: str, disabled: bool) -> None:
    conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (int(disabled), user_id))


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


def find_usable_invite(conn: sqlite3.Connection, user_id: str, not_before: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM invites WHERE user_id = ? AND used_at IS NULL "
            "AND (created_at > ? OR user_id IN (SELECT id FROM users WHERE is_owner = 0)) "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, not_before),
        ).fetchone()
    )


def consume_invite(conn: sqlite3.Connection, code: str, not_before: str) -> bool:
    cursor = conn.execute(
        "UPDATE invites SET used_at = ? WHERE code = ? AND used_at IS NULL "
        "AND (created_at > ? OR user_id IN (SELECT id FROM users WHERE is_owner = 0))",
        (utcnow(), code, not_before),
    )
    return cursor.rowcount == 1


def delete_invites(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("DELETE FROM invites WHERE user_id = ?", (user_id,))


def list_testers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    now = utcnow()
    return rows_to_dicts(
        conn.execute(
            "SELECT u.id, u.display_name, u.disabled, u.created_at, "
            "(SELECT i.code FROM invites i WHERE i.user_id = u.id AND i.used_at IS NULL "
            " ORDER BY i.created_at DESC LIMIT 1) AS pending_code, "
            "(SELECT MAX(i.used_at) FROM invites i WHERE i.user_id = u.id) AS last_claimed_at, "
            "(SELECT COUNT(*) FROM auth_sessions s WHERE s.user_id = u.id AND s.expires_at > ?) AS active_sessions, "
            "(SELECT COUNT(*) FROM projects p WHERE p.owner_id = u.id) AS projects "
            "FROM users u WHERE u.is_owner = 0 ORDER BY u.created_at DESC",
            (now,),
        ).fetchall()
    )


def create_session(conn: sqlite3.Connection, user_id: str, token: str, expires_at: str) -> None:
    conn.execute(
        "INSERT INTO auth_sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, utcnow(), expires_at),
    )


def get_session_user(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT u.* FROM auth_sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ? AND u.disabled = 0",
            (token, utcnow()),
        ).fetchone()
    )


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))


def delete_sessions(conn: sqlite3.Connection, user_id: str, keep_token: str | None = None) -> None:
    conn.execute(
        "DELETE FROM auth_sessions WHERE user_id = ? AND token IS NOT ?",
        (user_id, keep_token),
    )


def purge_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (utcnow(),))
