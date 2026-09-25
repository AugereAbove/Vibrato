from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request

from ..db import get_db
from ..store import auth as auth_store
from ..store import comparisons as comparison_store
from ..store import projects as project_store
from ..store import recordings as recording_store
from .errors import Forbidden, NotFound, Unauthorized

SESSION_COOKIE = "vibrato_session"


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    is_owner: bool


def _user_from_row(row: dict[str, Any]) -> User:
    return User(id=row["id"], display_name=row["display_name"], is_owner=bool(row["is_owner"]))


def get_current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized()
    with get_db().read() as conn:
        row = auth_store.get_session_user(conn, token)
    if row is None:
        raise Unauthorized("Your session has expired.")
    return _user_from_row(row)


def require_owner(user: User = Depends(get_current_user)) -> User:
    if not user.is_owner:
        raise Forbidden()
    return user


def owner_scope(user: User) -> str | None:
    """The owner_id to filter list queries by, or None to mean 'no filter' (site owner sees all)."""
    return None if user.is_owner else user.id


def ensure_owns_project(conn: sqlite3.Connection, project_id: str, user: User) -> dict[str, Any]:
    project = project_store.get_project(conn, project_id)
    if project is None or (not user.is_owner and project.get("owner_id") != user.id):
        raise NotFound("This project does not exist.")
    return project


def ensure_owns_recording(conn: sqlite3.Connection, recording_id: str, user: User) -> dict[str, Any]:
    recording = recording_store.get_recording(conn, recording_id)
    if recording is None:
        raise NotFound("This recording does not exist.")
    project_id = recording.get("project_id")
    if project_id is not None:
        ensure_owns_project(conn, project_id, user)
    elif not user.is_owner:
        raise NotFound("This recording does not exist.")
    return recording


def ensure_owns_comparison(conn: sqlite3.Connection, comparison_id: str, user: User) -> dict[str, Any]:
    comparison = comparison_store.get_comparison(conn, comparison_id)
    if comparison is None:
        raise NotFound("This comparison does not exist.")
    project_id = comparison.get("project_id")
    if project_id is not None:
        ensure_owns_project(conn, project_id, user)
    elif not user.is_owner:
        raise NotFound("This comparison does not exist.")
    return comparison


def ensure_owns_bookmark(conn: sqlite3.Connection, bookmark_id: str, user: User) -> dict[str, Any]:
    row = conn.execute("SELECT recording_id FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()
    if row is None:
        raise NotFound("This bookmark does not exist.")
    ensure_owns_recording(conn, row["recording_id"], user)
    return dict(row)


def ensure_owns_anchor(conn: sqlite3.Connection, anchor_id: str, user: User) -> dict[str, Any]:
    row = conn.execute(
        "SELECT reference_recording_id, take_recording_id FROM alignment_anchors WHERE id = ?",
        (anchor_id,),
    ).fetchone()
    if row is None:
        raise NotFound("This anchor does not exist.")
    ensure_owns_recording(conn, row["take_recording_id"], user)
    return dict(row)


def ensure_owns_render(conn: sqlite3.Connection, render_id: str, user: User) -> dict[str, Any]:
    row = conn.execute(
        "SELECT take_recording_id FROM counterfactual_renders WHERE id = ?", (render_id,)
    ).fetchone()
    if row is None:
        raise NotFound("This synthetic preview no longer exists.")
    ensure_owns_recording(conn, row["take_recording_id"], user)
    return dict(row)


def ensure_owns_calibration_profile(conn: sqlite3.Connection, profile_id: str, user: User) -> None:
    row = conn.execute("SELECT owner_id FROM calibration_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None or (not user.is_owner and row["owner_id"] != user.id):
        raise NotFound("This calibration does not exist.")


def ensure_owns_reference_profile(conn: sqlite3.Connection, profile_id: str, user: User) -> None:
    row = conn.execute("SELECT owner_id FROM reference_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None or (not user.is_owner and row["owner_id"] != user.id):
        raise NotFound("This reference profile does not exist.")


def ensure_owns_task_project(conn: sqlite3.Connection, project_id: str | None, user: User) -> None:
    if project_id is None:
        if not user.is_owner:
            raise NotFound("This task does not exist.")
        return
    ensure_owns_project(conn, project_id, user)
