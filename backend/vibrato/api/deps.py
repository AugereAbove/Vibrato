from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request

from ..config import get_settings
from ..db import get_db
from ..store import auth as auth_store
from ..store import comparisons as comparison_store
from ..store import projects as project_store
from ..store import recordings as recording_store
from ..tasks.manager import get_tasks
from .errors import Forbidden, NotFound, QuotaExceeded, Unauthorized

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


def ensure_recording_in_project(
    conn: sqlite3.Connection, recording_id: str, project_id: str | None, user: User
) -> dict[str, Any]:
    recording = ensure_owns_recording(conn, recording_id, user)
    if recording.get("project_id") != project_id:
        raise NotFound("That recording is not part of this project.")
    return recording


def storage_used(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(a.size_bytes), 0) AS used FROM recordings r "
        "JOIN audio_assets a ON a.content_hash = r.content_hash "
        "WHERE r.project_id IN (SELECT id FROM projects WHERE owner_id = ?) "
        "OR r.id IN (SELECT cs.recording_id FROM calibration_samples cs "
        "JOIN calibration_profiles cp ON cp.id = cs.calibration_id WHERE cp.owner_id = ?)",
        (user_id, user_id),
    ).fetchone()
    return int(row["used"])


def ensure_storage_quota(conn: sqlite3.Connection, user: User, incoming_bytes: int) -> None:
    if user.is_owner:
        return
    limit = get_settings().tester_storage_bytes
    if storage_used(conn, user.id) + incoming_bytes > limit:
        raise QuotaExceeded(
            f"This account has used its {limit // (1024 * 1024)} MB of storage.",
            "Delete recordings or projects you no longer need, then try again.",
        )


def ensure_project_quota(conn: sqlite3.Connection, user: User) -> None:
    if user.is_owner:
        return
    limit = get_settings().tester_max_projects
    count = conn.execute("SELECT COUNT(*) AS n FROM projects WHERE owner_id = ?", (user.id,)).fetchone()["n"]
    if count >= limit:
        raise QuotaExceeded(
            f"This account already has {limit} projects.",
            "Delete a project you no longer need, then try again.",
        )


def ensure_task_capacity(conn: sqlite3.Connection, user: User) -> None:
    if user.is_owner:
        return
    limit = get_settings().tester_max_active_tasks
    owned = {r["id"] for r in conn.execute("SELECT id FROM projects WHERE owner_id = ?", (user.id,))}
    active = [t for t in get_tasks().list(True, None, limit=1_000_000) if t.get("project_id") in owned]
    if len(active) >= limit:
        raise QuotaExceeded(
            f"This account already has {limit} analyses running.",
            "Wait for them to finish, then try again.",
        )
