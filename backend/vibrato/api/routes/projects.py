from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from ...db import get_db
from ...services import demo_service, export_service, progress_service
from ...store import misc as misc_store
from ...store import projects as project_store
from ...store import recordings as recording_store
from ...tasks.manager import get_tasks
from ..deps import User, ensure_owns_project, get_current_user, owner_scope
from ..errors import NotFound
from .common import save_upload, task_response

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    song_title: str = ""
    song_artist: str = ""
    singer_label: str = ""
    notes: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    song_title: str | None = None
    song_artist: str | None = None
    singer_label: str | None = None
    notes: str | None = None
    favorite: bool | None = None
    archived: bool | None = None
    reference_profile_id: str | None = None


class SessionUpdate(BaseModel):
    notes: str | None = None
    end: bool = False


class OverrideCreate(BaseModel):
    finding_type: str
    action: str


@router.get("/projects")
def list_projects(
    search: str | None = None,
    sort: str = "recent",
    archived: bool = False,
    favorites: bool = False,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "projects": project_store.list_projects(
                conn, search, sort, archived, favorites, owner_scope(user)
            )
        }


@router.post("/projects")
def create_project(body: ProjectCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {
            "project": project_store.create_project(
                conn,
                body.name,
                body.song_title,
                body.song_artist,
                body.singer_label,
                body.notes,
                owner_id=user.id,
            )
        }


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        project_store.touch_project(conn, project_id, opened=True)
        project = project_store.get_project(conn, project_id)
        recordings = recording_store.list_recordings(conn, project_id)
        sessions = misc_store.list_sessions(conn, project_id)
    return {"project": project, "recordings": recordings, "sessions": sessions}


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str, body: ProjectUpdate, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        project = project_store.update_project(conn, project_id, **body.model_dump(exclude_unset=True))
    if project is None:
        raise NotFound("This project does not exist.")
    return {"project": project}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        if not project_store.delete_project(conn, project_id):
            raise NotFound("This project does not exist.")
    return {"deleted": True}


@router.post("/projects/{project_id}/duplicate")
def duplicate_project(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        project = project_store.duplicate_project(conn, project_id)
    if project is None:
        raise NotFound("This project does not exist.")
    return {"project": project}


@router.get("/projects/{project_id}/progress")
def project_progress(
    project_id: str, reference_id: str | None = None, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
    return progress_service.project_progress(project_id, reference_id)


@router.get("/projects/{project_id}/progress.csv")
def progress_csv(project_id: str, user: User = Depends(get_current_user)) -> PlainTextResponse:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
    return PlainTextResponse(
        export_service.progress_csv(project_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="progress-{project_id}.csv"'},
    )


@router.get("/projects/{project_id}/report.html")
def report(
    project_id: str,
    comparison_id: str | None = None,
    download: bool = False,
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
    headers = {"Content-Disposition": f'attachment; filename="report-{project_id}.html"'} if download else {}
    return HTMLResponse(export_service.report_html(project_id, comparison_id), headers=headers)


@router.post("/projects/{project_id}/backup")
def backup(project_id: str, user: User = Depends(get_current_user)) -> FileResponse:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
    path = export_service.backup_project(project_id)
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post("/projects/restore")
async def restore(file: UploadFile = File(...), user: User = Depends(get_current_user)) -> dict[str, Any]:
    path, _ = await save_upload(file)
    try:
        return {"project": export_service.restore_project(path, user.id)}
    finally:
        path.unlink(missing_ok=True)


@router.get("/projects/{project_id}/sessions")
def sessions(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
        return {"sessions": misc_store.list_sessions(conn, project_id)}


@router.post("/projects/{project_id}/sessions/active")
def active_session(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        return {"session": misc_store.active_session(conn, project_id)}


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: str, body: SessionUpdate, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().tx() as conn:
        row = conn.execute("SELECT project_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFound("This session does not exist.")
        ensure_owns_project(conn, row["project_id"], user)
        session = misc_store.update_session(conn, session_id, body.notes, body.end)
    if session is None:
        raise NotFound("This session does not exist.")
    return {"session": session}


@router.get("/projects/{project_id}/coaching-overrides")
def overrides(project_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_project(conn, project_id, user)
        return {"overrides": misc_store.list_overrides(conn, project_id)}


@router.post("/projects/{project_id}/coaching-overrides")
def add_override(
    project_id: str, body: OverrideCreate, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    if body.action not in {"ignore", "boost", "dismiss"}:
        raise NotFound("Unknown override action.")
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        misc_store.add_coaching_override(conn, project_id, body.finding_type, body.action)
        return {"overrides": misc_store.list_overrides(conn, project_id)}


@router.delete("/projects/{project_id}/coaching-overrides")
def clear_overrides(
    project_id: str, finding_type: str | None = None, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_project(conn, project_id, user)
        misc_store.clear_coaching_overrides(conn, project_id, finding_type)
        return {"overrides": misc_store.list_overrides(conn, project_id)}


@router.post("/demo")
def create_demo(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return task_response(
        get_tasks().submit(
            "demo",
            lambda ctx: demo_service.create_demo_project(ctx, user.id),
            label="Building the demo project",
            dedupe_key=f"demo:{user.id}",
        )
    )
