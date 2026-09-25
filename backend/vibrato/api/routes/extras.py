from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from ...db import get_db
from ...services import calibration_service, preferences, profile_service
from ...store import calibration as calibration_store
from ...tasks.manager import get_tasks
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
def steps() -> dict[str, Any]:
    return {"steps": calibration_service.STEPS}


@router.get("/calibrations")
def calibrations() -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "calibrations": calibration_store.list_profiles(conn),
            "active": calibration_store.active_profile(conn),
        }


@router.post("/calibrations")
def create_calibration(body: CalibrationCreate) -> dict[str, Any]:
    return {"calibration": calibration_service.start_calibration(body.name)}


@router.get("/calibrations/compare")
def compare_calibrations(ids: str) -> dict[str, Any]:
    return {"profiles": calibration_service.compare_profiles([i for i in ids.split(",") if i])}


@router.get("/calibrations/{profile_id}")
def calibration(profile_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        profile = calibration_store.get_profile(conn, profile_id)
    if profile is None:
        raise NotFound("This calibration does not exist.")
    return {"calibration": profile}


@router.post("/calibrations/{profile_id}/samples")
async def add_sample(profile_id: str, step: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    path, name = await save_upload(file)
    try:
        return calibration_service.add_sample(profile_id, step, path, name)
    finally:
        path.unlink(missing_ok=True)


@router.post("/calibrations/{profile_id}/finalize")
def finalize(profile_id: str) -> dict[str, Any]:
    return {"calibration": calibration_service.finalize(profile_id)}


@router.post("/calibrations/{profile_id}/activate")
def activate(profile_id: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        calibration_store.set_active(conn, profile_id)
        return {"active": calibration_store.active_profile(conn)}


@router.post("/calibrations/deactivate")
def deactivate() -> dict[str, Any]:
    with get_db().tx() as conn:
        calibration_store.set_active(conn, None)
    return {"active": None}


@router.delete("/calibrations/{profile_id}")
def delete_calibration(profile_id: str) -> dict[str, Any]:
    return {"deleted": calibration_service.delete_calibration(profile_id)}


@router.get("/reference-profiles")
def reference_profiles() -> dict[str, Any]:
    with get_db().read() as conn:
        return {"profiles": calibration_store.list_reference_profiles(conn)}


@router.post("/reference-profiles")
def create_reference_profile(body: ProfileCreate) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {"profile": calibration_store.create_reference_profile(conn, body.name, body.notes)}


@router.get("/reference-profiles/{profile_id}")
def reference_profile(profile_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        if calibration_store.get_reference_profile(conn, profile_id) is None:
            raise NotFound("This reference profile does not exist.")
    return profile_service.aggregate_profile(profile_id)


@router.patch("/reference-profiles/{profile_id}")
def update_reference_profile(profile_id: str, body: ProfileUpdate) -> dict[str, Any]:
    with get_db().tx() as conn:
        profile = calibration_store.update_reference_profile(conn, profile_id, body.name, body.notes)
    if profile is None:
        raise NotFound("This reference profile does not exist.")
    return {"profile": profile}


@router.delete("/reference-profiles/{profile_id}")
def delete_reference_profile(profile_id: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {"deleted": calibration_store.delete_reference_profile(conn, profile_id)}


@router.get("/preferences")
def get_preferences() -> dict[str, Any]:
    return {
        "values": preferences.all_preferences(),
        "defaults": preferences.DEFAULTS,
        "schema": preferences.SCHEMA,
    }


@router.put("/preferences")
def put_preferences(body: PreferencesUpdate) -> dict[str, Any]:
    return {"values": preferences.update_preferences(body.values)}


@router.post("/preferences/reset")
def reset_preferences(section: str | None = None) -> dict[str, Any]:
    return {"values": preferences.reset_preferences(section)}


@router.get("/tasks")
def tasks(active: bool = False, project_id: str | None = None) -> dict[str, Any]:
    return {"tasks": get_tasks().list(active, project_id)}


@router.get("/tasks/{task_id}")
def task(task_id: str) -> dict[str, Any]:
    data = get_tasks().get(task_id)
    if data is None:
        raise NotFound("This task does not exist.")
    return {"task": data}


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: str) -> dict[str, Any]:
    state = get_tasks().cancel(task_id)
    if state is None:
        raise NotFound("This task does not exist or already finished.")
    return {"task": state.to_dict()}
