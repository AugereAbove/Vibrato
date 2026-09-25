from __future__ import annotations

from collections import deque
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ... import __version__
from ...analysis.base import all_analyzers
from ...analysis.pipeline import pipeline_version
from ...config import get_settings
from ...db import get_db
from ...logging_setup import redact
from ...services import export_service, system_service
from ...services.analysis_service import clear_memory_cache, ensure_analysis
from ...storage import clear_derived_cache
from ...store import analyses as analysis_store
from ...tasks.manager import TaskContext, get_tasks
from ..deps import User, require_owner
from .common import task_response

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, Any]:
    db = get_db()
    return {
        "status": "ok",
        "version": __version__,
        "schema_version": db.schema_version(),
        "pipeline_version": pipeline_version(),
        "active_tasks": len(get_tasks().list(active_only=True)),
    }


@router.get("/system")
def system(user: User = Depends(require_owner)) -> dict[str, Any]:
    return system_service.system_info()


@router.get("/system/models")
def models(user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"models": system_service.model_status()}


@router.get("/system/analyzers")
def analyzers(user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"analyzers": [a.explain() for a in all_analyzers()], "pipeline_version": pipeline_version()}


@router.get("/system/methods")
def methods(user: User = Depends(require_owner)) -> dict[str, Any]:
    return system_service.methods()


@router.get("/system/cache")
def cache(user: User = Depends(require_owner)) -> dict[str, Any]:
    return system_service.cache_usage()


@router.post("/system/cache/clear")
def clear_cache(user: User = Depends(require_owner)) -> dict[str, Any]:
    freed = clear_derived_cache()
    clear_memory_cache()
    with get_db().tx() as conn:
        conn.execute("DELETE FROM recording_analyses")
        conn.execute("DELETE FROM alignments")
        conn.execute("DELETE FROM counterfactual_renders")
    return {
        "freed_bytes": freed,
        "note": "Derived analysis data was removed. Recordings and comparison history are kept; analyses are recomputed when needed.",
    }


@router.get("/system/timing")
def timing(user: User = Depends(require_owner)) -> dict[str, Any]:
    with get_db().read() as conn:
        return {"analyzers": analysis_store.timing_statistics(conn)}


@router.get("/system/outdated")
def outdated(user: User = Depends(require_owner)) -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "recordings": analysis_store.outdated_recordings(conn, pipeline_version()),
            "current_version": pipeline_version(),
        }


@router.post("/system/reanalyze")
def reanalyze_all(only_outdated: bool = True, user: User = Depends(require_owner)) -> dict[str, Any]:
    with get_db().read() as conn:
        if only_outdated:
            targets = analysis_store.outdated_recordings(conn, pipeline_version())
        else:
            targets = [
                r["id"]
                for r in conn.execute("SELECT id FROM recordings WHERE kind != 'calibration'").fetchall()
            ]

    def run(ctx: TaskContext) -> dict[str, Any]:
        done = 0
        for index, recording_id in enumerate(targets):
            ctx.check_cancelled()
            ctx.progress(index / max(1, len(targets)), f"Re-analysing {index + 1} of {len(targets)}")
            ensure_analysis(recording_id, None, force=True)
            done += 1
        return {"reanalyzed": done}

    return task_response(
        get_tasks().submit(
            "reanalyze",
            run,
            {"count": len(targets)},
            None,
            "reanalyze-all",
            f"Re-analysing {len(targets)} recordings",
        )
    )


@router.get("/system/logs")
def logs(lines: int = 200, user: User = Depends(require_owner)) -> dict[str, Any]:
    path = get_settings().logs_dir / "vibrato.log"
    if not path.exists():
        return {"lines": []}
    with open(path, encoding="utf-8", errors="replace") as handle:
        tail = deque(handle, maxlen=max(1, min(lines, 2000)))
    return {"lines": [redact(line.rstrip()) for line in tail]}


@router.get("/system/debug-bundle")
def debug_bundle(user: User = Depends(require_owner)) -> FileResponse:
    path = export_service.debug_bundle()
    return FileResponse(path, filename=path.name, media_type="application/zip")
