from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from ...analysis.features import FeatureSet
from ...db import get_db
from ...dsp.spectral import display_spectrogram
from ...services.analysis_service import (
    current_analysis,
    ensure_analysis,
    is_outdated,
    load_audio,
    load_payload,
)
from ...storage import spectrogram_path
from ...store import analyses as analysis_store
from ...store import recordings as recording_store
from ...tasks.manager import get_tasks
from ...util import stable_hash
from ..binary import encode_matrix, feature_bundle
from ..errors import NotFound
from .common import task_response

router = APIRouter(tags=["analysis"])
RESOLUTIONS = {"low": (160, 0.02, 2048), "medium": (256, 0.01, 2048), "high": (400, 0.005, 4096)}
DYNAMIC_RANGE_DB = 80.0


class AnalyzeRequest(BaseModel):
    force: bool = False


def _recording(recording_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        recording = recording_store.get_recording(conn, recording_id)
    if recording is None:
        raise NotFound("This recording does not exist.")
    return recording


@router.post("/recordings/{recording_id}/analyze")
def analyze(recording_id: str, body: AnalyzeRequest) -> dict[str, Any]:
    recording = _recording(recording_id)
    state = get_tasks().submit(
        "analyze",
        lambda ctx: {"analysis_id": ensure_analysis(recording_id, ctx, force=body.force)["id"]},
        {"recording_id": recording_id, "force": body.force},
        recording.get("project_id"),
        f"analyze:{recording_id}",
        f"Analysing {recording['name']}",
    )
    return task_response(state)


@router.get("/recordings/{recording_id}/analysis")
def analysis(recording_id: str) -> dict[str, Any]:
    recording = _recording(recording_id)
    row = current_analysis(recording_id)
    if row is None:
        return {"status": "none", "recording_id": recording_id}
    payload = load_payload(row)
    with get_db().read() as conn:
        runs = analysis_store.analyzer_runs(conn, row["id"])
    return {
        "status": "complete",
        "recording_id": recording_id,
        "analysis": {
            "id": row["id"],
            "version": row["pipeline_version"],
            "outdated": is_outdated(row),
            "created_at": row["created_at"],
            "duration_ms": row["duration_ms"],
        },
        "segments": payload["segments"],
        "events": payload["events"],
        "results": payload["results"],
        "summary": payload["summary"],
        "lyrics": payload.get("lyrics"),
        "phonetic_classes": payload.get("phonetic_classes"),
        "contamination": payload.get("contamination"),
        "runs": runs,
        "qc": recording.get("qc"),
    }


@router.get("/recordings/{recording_id}/features")
def features(recording_id: str) -> Response:
    row = current_analysis(recording_id)
    if row is None or not row.get("features_path"):
        raise NotFound("This recording has not been analysed yet.")
    from pathlib import Path

    data = FeatureSet.load(Path(row["features_path"]))
    return Response(
        feature_bundle(data),
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/recordings/{recording_id}/spectrogram")
def spectrogram(recording_id: str, resolution: str = "medium", max_hz: float = 8000.0) -> Response:
    recording = _recording(recording_id)
    bins, hop_s, n_fft = RESOLUTIONS.get(resolution, RESOLUTIONS["medium"])
    max_hz = float(min(16000.0, max(2000.0, max_hz)))
    key = stable_hash({"bins": bins, "hop": hop_s, "fft": n_fft, "max": max_hz, "v": 1})
    path = spectrogram_path(recording["content_hash"], key)
    if path.exists():
        with np.load(path) as cached:
            matrix = cached["matrix"]
            freqs = cached["freqs"]
            top = float(cached["top"])
    else:
        audio, sr = load_audio(recording["content_hash"])
        freqs, db = display_spectrogram(audio, sr, max_hz, bins, hop_s, n_fft)
        top = float(np.percentile(db, 99.9))
        scaled = np.clip((db - (top - DYNAMIC_RANGE_DB)) / DYNAMIC_RANGE_DB, 0.0, 1.0)
        matrix = np.round(scaled.T * 255.0).astype(np.uint8)
        np.savez_compressed(path, matrix=matrix, freqs=freqs, top=np.array(top))
    header = {
        "frames": int(matrix.shape[0]),
        "bins": int(matrix.shape[1]),
        "hop_s": hop_s,
        "fmin": float(freqs[0]),
        "fmax": float(freqs[-1]),
        "scale": "log",
        "db_top": top,
        "db_range": DYNAMIC_RANGE_DB,
    }
    return Response(
        encode_matrix(header, matrix),
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )
