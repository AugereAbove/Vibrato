from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from ...db import get_db
from ...services import calibration_service, preferences, profile_service
from ...store import calibration as calibration_store
from ...tasks.manager import get_tasks
from ..deps import (
    User,
    ensure_owns_calibration_profile,
    ensure_owns_reference_profile,
    ensure_owns_task_project,
    get_current_user,
    owner_scope,
)
from ..errors import NotFound
from .common import save_upload

router = APIRouter(tags=["extras"])


class CalibrationCreate(BaseModel):
    name: str = "Calibration"


class ProfileCreate(BaseModel):
    name: str
    notes: str = ""


class ProfileUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None


class PreferencesUpdate(BaseModel):
    values: dict[str, Any]


@router.get("/calibration/steps")
def steps(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"steps": calibration_service.STEPS}


@router.get("/calibrations")
def calibrations(user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "calibrations": calibration_store.list_profiles(conn, owner_scope(user)),
            "active": calibration_store.active_profile(conn, user.id),
        }


@router.post("/calibrations")
def create_calibration(body: CalibrationCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"calibration": calibration_service.start_calibration(body.name, user.id)}


@router.get("/calibrations/compare")
def compare_calibrations(ids: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    profile_ids = [i for i in ids.split(",") if i]
    with get_db().read() as conn:
        for profile_id in profile_ids:
            ensure_owns_calibration_profile(conn, profile_id, user)
    return {"profiles": calibration_service.compare_profiles(profile_ids)}


@router.get("/calibrations/{profile_id}")
def calibration(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_calibration_profile(conn, profile_id, user)
        profile = calibration_store.get_profile(conn, profile_id)
    if profile is None:
        raise NotFound("This calibration does not exist.")
    return {"calibration": profile}


@router.post("/calibrations/{profile_id}/samples")
async def add_sample(
    profile_id: str, step: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_calibration_profile(conn, profile_id, user)
    path, name = await save_upload(file)
    try:
        return calibration_service.add_sample(profile_id, step, path, name)
    finally:
        path.unlink(missing_ok=True)


@router.post("/calibrations/{profile_id}/finalize")
def finalize(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_calibration_profile(conn, profile_id, user)
    return {"calibration": calibration_service.finalize(profile_id)}


@router.post("/calibrations/{profile_id}/activate")
def activate(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_calibration_profile(conn, profile_id, user)
        calibration_store.set_active(conn, profile_id)
        return {"active": calibration_store.active_profile(conn, user.id)}


@router.post("/calibrations/deactivate")
def deactivate(user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        calibration_store.set_active(conn, None)
    return {"active": None}


@router.delete("/calibrations/{profile_id}")
def delete_calibration(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_calibration_profile(conn, profile_id, user)
    return {"deleted": calibration_service.delete_calibration(profile_id)}


@router.get("/reference-profiles")
def reference_profiles(user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        return {"profiles": calibration_store.list_reference_profiles(conn, owner_scope(user))}


@router.post("/reference-profiles")
def create_reference_profile(body: ProfileCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {
            "profile": calibration_store.create_reference_profile(conn, body.name, body.notes, user.id)
        }


@router.get("/reference-profiles/{profile_id}")
def reference_profile(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_reference_profile(conn, profile_id, user)
    return profile_service.aggregate_profile(profile_id)


@router.patch("/reference-profiles/{profile_id}")
def update_reference_profile(
    profile_id: str, body: ProfileUpdate, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_reference_profile(conn, profile_id, user)
        profile = calibration_store.update_reference_profile(conn, profile_id, body.name, body.notes)
    if profile is None:
        raise NotFound("This reference profile does not exist.")
    return {"profile": profile}


@router.delete("/reference-profiles/{profile_id}")
def delete_reference_profile(profile_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_reference_profile(conn, profile_id, user)
        return {"deleted": calibration_store.delete_reference_profile(conn, profile_id)}


@router.get("/preferences")
def get_preferences(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "values": preferences.all_preferences(user.id),
        "defaults": preferences.DEFAULTS,
        "schema": preferences.SCHEMA,
    }


@router.put("/preferences")
def put_preferences(body: PreferencesUpdate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"values": preferences.update_preferences(user.id, body.values)}


@router.post("/preferences/reset")
def reset_preferences(section: str | None = None, user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"values": preferences.reset_preferences(user.id, section)}


@router.get("/tasks")
def tasks(
    active: bool = False, project_id: str | None = None, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().read() as conn:
        if project_id is not None:
            ensure_owns_task_project(conn, project_id, user)
            return {"tasks": get_tasks().list(active, project_id)}
        results = get_tasks().list(active, None)
        if user.is_owner:
            return {"tasks": results}
        owned = {r["id"] for r in conn.execute("SELECT id FROM projects WHERE owner_id = ?", (user.id,))}
    return {"tasks": [t for t in results if t.get("project_id") in owned]}


@router.get("/tasks/{task_id}")
def task(task_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    data = get_tasks().get(task_id)
    if data is None:
        raise NotFound("This task does not exist.")
    with get_db().read() as conn:
        ensure_owns_task_project(conn, data.get("project_id"), user)
    return {"task": data}


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    data = get_tasks().get(task_id)
    if data is None:
        raise NotFound("This task does not exist or already finished.")
    with get_db().read() as conn:
        ensure_owns_task_project(conn, data.get("project_id"), user)
    state = get_tasks().cancel(task_id)
    if state is None:
        raise NotFound("This task does not exist or already finished.")
    return {"task": state.to_dict()}
