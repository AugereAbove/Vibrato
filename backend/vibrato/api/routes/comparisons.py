from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from ...alignment.aligner import Alignment
from ...db import get_db
from ...services import comparison_service, counterfactual_service, export_service
from ...storage import render_file
from ...store import misc as misc_store
from ...tasks.manager import get_tasks
from ...util import read_json
from ..deps import (
    User,
    ensure_owns_anchor,
    ensure_owns_comparison,
    ensure_owns_recording,
    ensure_owns_render,
    get_current_user,
)
from ..errors import NotFound
from .common import task_response

router = APIRouter(tags=["comparisons"])
ALIGNMENT_DECIMATION = 2


class CompareRequest(BaseModel):
    take_id: str
    reference_id: str | None = None
    force_align: bool = False


class RegionRequest(BaseModel):
    start_s: float
    end_s: float


class RescoreRequest(BaseModel):
    enabled: dict[str, bool] = {}
    weights: dict[str, float] = {}


class AnchorCreate(BaseModel):
    reference_id: str
    take_id: str
    ref_time_s: float
    user_time_s: float
    locked: bool = True
    label: str = ""


class AnchorUpdate(BaseModel):
    ref_time_s: float | None = None
    user_time_s: float | None = None
    locked: bool | None = None
    label: str | None = None


class RenderRequest(BaseModel):
    transform: str


@router.post("/comparisons")
def create_comparison(body: CompareRequest, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        take = ensure_owns_recording(conn, body.take_id, user)
    state = get_tasks().submit(
        "compare",
        lambda ctx: comparison_service.run_comparison(body.take_id, body.reference_id, ctx, body.force_align),
        {"take_id": body.take_id, "reference_id": body.reference_id},
        take.get("project_id"),
        f"compare:{body.take_id}",
        f"Comparing {take['name']}",
    )
    return task_response(state)


@router.get("/takes/{take_id}/comparison")
def comparison_for_take(take_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_recording(conn, take_id, user)
        row = conn.execute(
            "SELECT id FROM comparisons WHERE take_recording_id = ? ORDER BY created_at DESC LIMIT 1",
            (take_id,),
        ).fetchone()
    if row is None:
        return {"comparison_id": None}
    return {"comparison_id": row["id"]}


@router.get("/comparisons/{comparison_id}")
def get_comparison(comparison_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    return comparison_service.comparison_payload(comparison_id)


@router.post("/comparisons/{comparison_id}/why")
def why(comparison_id: str, body: RegionRequest, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    return comparison_service.explain_region(comparison_id, body.start_s, body.end_s)


@router.post("/comparisons/{comparison_id}/rescore")
def rescore(
    comparison_id: str, body: RescoreRequest, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    return comparison_service.rescore(comparison_id, body.enabled, body.weights)


@router.post("/comparisons/{comparison_id}/realign")
def realign(comparison_id: str, body: RegionRequest, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        comparison = ensure_owns_comparison(conn, comparison_id, user)
    state = get_tasks().submit(
        "realign",
        lambda ctx: comparison_service.realign(comparison_id, body.start_s, body.end_s),
        {"comparison_id": comparison_id},
        comparison.get("project_id"),
        f"realign:{comparison_id}",
        "Realigning the selected region",
    )
    return task_response(state)


@router.get("/comparisons/{comparison_id}/alignment")
def alignment(comparison_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        row = ensure_owns_comparison(conn, comparison_id, user)
        alignment_row = misc_store.get_alignment(
            conn, row["reference_recording_id"], row["take_recording_id"]
        )
        anchors = misc_store.list_anchors(conn, row["reference_recording_id"], row["take_recording_id"])
    if (
        alignment_row is None
        or not alignment_row.get("path_file")
        or not Path(alignment_row["path_file"]).exists()
    ):
        raise NotFound("The alignment for this comparison is missing.")
    data = Alignment.load(Path(alignment_row["path_file"]))
    step = ALIGNMENT_DECIMATION
    return {
        "summary": data.summary(),
        "ref_times": np.round(data.ref_times[::step], 3).tolist(),
        "user_times": np.round(data.user_times[::step], 3).tolist(),
        "confidence": np.round(data.confidence[::step], 3).tolist(),
        "anchors": anchors,
        "reference_id": row["reference_recording_id"],
        "take_id": row["take_recording_id"],
    }


@router.post("/anchors")
def add_anchor(body: AnchorCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_recording(conn, body.reference_id, user)
        ensure_owns_recording(conn, body.take_id, user)
        return {
            "anchor": misc_store.add_anchor(
                conn,
                body.reference_id,
                body.take_id,
                body.ref_time_s,
                body.user_time_s,
                body.locked,
                "manual",
                body.label,
            )
        }


@router.patch("/anchors/{anchor_id}")
def update_anchor(
    anchor_id: str, body: AnchorUpdate, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_anchor(conn, anchor_id, user)
        anchor = misc_store.update_anchor(conn, anchor_id, **body.model_dump(exclude_unset=True))
    if anchor is None:
        raise NotFound("This anchor does not exist.")
    return {"anchor": anchor}


@router.delete("/anchors/{anchor_id}")
def delete_anchor(anchor_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().tx() as conn:
        ensure_owns_anchor(conn, anchor_id, user)
        return {"deleted": misc_store.delete_anchor(conn, anchor_id)}


@router.get("/comparisons/{comparison_id}/export.csv")
def export_csv(comparison_id: str, user: User = Depends(get_current_user)) -> PlainTextResponse:
    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    return PlainTextResponse(
        export_service.comparison_csv(comparison_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="comparison-{comparison_id}.csv"'},
    )


@router.get("/comparisons/{comparison_id}/export.json")
def export_json(comparison_id: str, user: User = Depends(get_current_user)) -> Response:
    import json

    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    return Response(
        json.dumps(export_service.comparison_json(comparison_id), indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="comparison-{comparison_id}.json"'},
    )


@router.get("/comparisons/{comparison_id}/ab.wav")
def ab_snippet(
    comparison_id: str, start: float, end: float, user: User = Depends(get_current_user)
) -> Response:
    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    data, filename = export_service.ab_snippet(comparison_id, start, end)
    return Response(
        data, media_type="audio/wav", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/counterfactual/transforms")
def transforms(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"transforms": counterfactual_service.available_transforms()}


@router.post("/takes/{take_id}/counterfactuals")
def render(take_id: str, body: RenderRequest, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        take = ensure_owns_recording(conn, take_id, user)
    state = get_tasks().submit(
        "counterfactual",
        lambda ctx: counterfactual_service.render(take_id, body.transform, ctx),
        {"take_id": take_id, "transform": body.transform},
        take.get("project_id"),
        f"cf:{take_id}:{body.transform}",
        "Rendering synthetic preview",
    )
    return task_response(state)


@router.get("/takes/{take_id}/counterfactuals")
def list_renders(take_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    with get_db().read() as conn:
        ensure_owns_recording(conn, take_id, user)
        return {"renders": misc_store.list_renders(conn, take_id)}


@router.get("/renders/{render_id}/audio")
def render_audio(
    render_id: str, download: bool = False, user: User = Depends(get_current_user)
) -> FileResponse:
    with get_db().read() as conn:
        ensure_owns_render(conn, render_id, user)
        row = misc_store.get_render(conn, render_id)
    path = render_file(render_id)
    if row is None or not path.exists():
        raise NotFound("This synthetic preview no longer exists.")
    label = str((row.get("description") or {}).get("label", row["transform"])).replace(" ", "-")
    headers = {"X-Synthetic": "true", "Cache-Control": "private, max-age=86400"}
    if download:
        return FileResponse(
            path, media_type="audio/wav", filename=f"SYNTHETIC-preview_{label}.wav", headers=headers
        )
    return FileResponse(path, media_type="audio/wav", headers=headers)


@router.get("/comparisons/{comparison_id}/metrics")
def metrics(comparison_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    from ...storage import comparison_file

    with get_db().read() as conn:
        ensure_owns_comparison(conn, comparison_id, user)
    payload = read_json(comparison_file(comparison_id))
    return {"metrics": payload["metrics"]}
