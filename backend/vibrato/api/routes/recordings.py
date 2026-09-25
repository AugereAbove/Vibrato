from __future__ import annotations

from pathlib import Path
from typing import Any

import parselmouth
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from parselmouth.praat import call
from pydantic import BaseModel

from ...db import get_db
from ...services import comparison_service, export_service
from ...services.analysis_service import ensure_analysis, load_audio
from ...services.importer import import_recording
from ...storage import peaks_path, playback_path, stretched_path
from ...store import misc as misc_store
from ...store import projects as project_store
from ...store import recordings as recording_store
from ...tasks.manager import get_tasks
from ..errors import NotFound
from .common import save_upload

router = APIRouter(tags=["recordings"])
MIN_SPEED = 0.25


class RecordingUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    favorite: bool | None = None
    lyrics: str | None = None
    singer_label: str | None = None
    is_primary: bool | None = None
    excluded_from_profile: bool | None = None
    reference_profile_id: str | None = None
    reference_recording_id: str | None = None


class LyricsUpdate(BaseModel):
    lyrics: str


class PronunciationUpdate(BaseModel):
    word_index: int
    word: str
    pronunciation: str | None = None


class SectionItem(BaseModel):
    label: str
    start_s: float
    end_s: float


class SectionsUpdate(BaseModel):
    sections: list[SectionItem]


class BookmarkCreate(BaseModel):
    start_s: float
    end_s: float | None = None
    label: str = ""
    color: str = "amber"


class BookmarkUpdate(BaseModel):
    start_s: float | None = None
    end_s: float | None = None
    label: str | None = None
    color: str | None = None


def _recording(recording_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        recording = recording_store.get_recording(conn, recording_id)
    if recording is None:
        raise NotFound("This recording does not exist.")
    return recording


def _with_role_issues(recording: dict[str, Any]) -> dict[str, Any]:
    qc = recording.get("qc") or {}
    if recording["kind"] == "reference":
        serious = [i for i in qc.get("issues", []) if i.get("severity") in {"warning", "critical"}]
        if serious and not any(i.get("code") == "bad_reference" for i in qc.get("issues", [])):
            qc = {
                **qc,
                "issues": [
                    *qc.get("issues", []),
                    {
                        "code": "bad_reference",
                        "severity": "warning",
                        "title": "Reference quality limits the analysis",
                        "what": f"The reference has {len(serious)} quality problem(s): "
                        + ", ".join(i["title"].lower() for i in serious)
                        + ".",
                        "why": "Every comparison inherits the reference's weaknesses; affected categories are shown with reduced confidence.",
                        "action": "If you can, use a cleaner isolated vocal as the reference.",
                        "value": None,
                        "confidence": 1.0,
                        "affects": [],
                    },
                ],
            }
    return {**recording, "qc": qc}


@router.post("/projects/{project_id}/recordings")
async def upload_recording(
    project_id: str,
    file: UploadFile = File(...),
    kind: str = Form("take"),
    name: str | None = Form(None),
    reference_id: str | None = Form(None),
    synced: bool = Form(False),
    latency_ms: float = Form(0.0),
    region_start_s: float | None = Form(None),
    region_end_s: float | None = Form(None),
    allow_duplicate: bool = Form(False),
    lyrics: str = Form(""),
    source: str = Form("import"),
    auto_analyze: bool = Form(True),
) -> dict[str, Any]:
    with get_db().read() as conn:
        if project_store.get_project(conn, project_id) is None:
            raise NotFound("This project does not exist.")
    path, original = await save_upload(file)
    try:
        region = (
            (region_start_s, region_end_s)
            if region_start_s is not None and region_end_s is not None
            else None
        )
        recording = import_recording(
            project_id,
            "reference" if kind == "reference" else "take",
            path,
            original,
            name,
            source if source in {"import", "record"} else "import",
            reference_id,
            synced,
            latency_ms,
            region,
            allow_duplicate,
            lyrics,
        )
    finally:
        path.unlink(missing_ok=True)
    task = None
    if auto_analyze:
        if recording["kind"] == "take" and recording.get("reference_recording_id"):
            task = get_tasks().submit(
                "compare",
                lambda ctx: comparison_service.run_comparison(recording["id"], context=ctx),
                {"take_id": recording["id"]},
                project_id,
                f"compare:{recording['id']}",
                f"Comparing {recording['name']}",
            )
        else:
            task = get_tasks().submit(
                "analyze",
                lambda ctx: {"analysis_id": ensure_analysis(recording["id"], ctx)["id"]},
                {"recording_id": recording["id"]},
                project_id,
                f"analyze:{recording['id']}",
                f"Analysing {recording['name']}",
            )
    return {"recording": _with_role_issues(recording), "task": task.to_dict() if task else None}


@router.get("/projects/{project_id}/recordings")
def list_recordings(project_id: str, kind: str | None = None) -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "recordings": [
                _with_role_issues(r) for r in recording_store.list_recordings(conn, project_id, kind)
            ]
        }


@router.get("/recordings/{recording_id}")
def get_recording(recording_id: str) -> dict[str, Any]:
    return {"recording": _with_role_issues(_recording(recording_id))}


@router.patch("/recordings/{recording_id}")
def update_recording(recording_id: str, body: RecordingUpdate) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    with get_db().tx() as conn:
        if fields.get("is_primary"):
            current = recording_store.get_recording(conn, recording_id)
            if current and current.get("project_id"):
                conn.execute(
                    "UPDATE reference_recordings SET is_primary = 0 WHERE recording_id IN (SELECT id FROM recordings WHERE project_id = ?)",
                    (current["project_id"],),
                )
        recording = recording_store.update_recording(conn, recording_id, **fields)
    if recording is None:
        raise NotFound("This recording does not exist.")
    return {"recording": _with_role_issues(recording)}


@router.delete("/recordings/{recording_id}")
def delete_recording(recording_id: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        if not recording_store.delete_recording(conn, recording_id):
            raise NotFound("This recording does not exist.")
    return {"deleted": True}


@router.put("/recordings/{recording_id}/lyrics")
def set_lyrics(recording_id: str, body: LyricsUpdate) -> dict[str, Any]:
    with get_db().tx() as conn:
        recording = recording_store.update_recording(conn, recording_id, lyrics=body.lyrics)
    if recording is None:
        raise NotFound("This recording does not exist.")
    return {"recording": recording}


@router.get("/recordings/{recording_id}/pronunciations")
def get_pronunciations(recording_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        return {
            "overrides": {
                str(k): v for k, v in misc_store.pronunciation_overrides(conn, recording_id).items()
            }
        }


@router.put("/recordings/{recording_id}/pronunciations")
def set_pronunciation(recording_id: str, body: PronunciationUpdate) -> dict[str, Any]:
    with get_db().tx() as conn:
        misc_store.set_pronunciation(conn, recording_id, body.word_index, body.word, body.pronunciation)
        return {
            "overrides": {
                str(k): v for k, v in misc_store.pronunciation_overrides(conn, recording_id).items()
            }
        }


@router.get("/recordings/{recording_id}/sections")
def get_sections(recording_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        return {"sections": misc_store.list_sections(conn, recording_id)}


@router.put("/recordings/{recording_id}/sections")
def put_sections(recording_id: str, body: SectionsUpdate) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {
            "sections": misc_store.replace_sections(
                conn, recording_id, [s.model_dump() for s in body.sections]
            )
        }


@router.get("/recordings/{recording_id}/bookmarks")
def bookmarks(recording_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        return {"bookmarks": misc_store.list_bookmarks(conn, recording_id)}


@router.post("/recordings/{recording_id}/bookmarks")
def add_bookmark(recording_id: str, body: BookmarkCreate) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {
            "bookmark": misc_store.add_bookmark(
                conn, recording_id, body.start_s, body.end_s, body.label, body.color
            )
        }


@router.patch("/bookmarks/{bookmark_id}")
def update_bookmark(bookmark_id: str, body: BookmarkUpdate) -> dict[str, Any]:
    with get_db().tx() as conn:
        bookmark = misc_store.update_bookmark(conn, bookmark_id, **body.model_dump(exclude_unset=True))
    if bookmark is None:
        raise NotFound("This bookmark does not exist.")
    return {"bookmark": bookmark}


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        return {"deleted": misc_store.delete_bookmark(conn, bookmark_id)}


@router.get("/recordings/{recording_id}/audio")
def audio(recording_id: str) -> FileResponse:
    recording = _recording(recording_id)
    path = playback_path(recording["content_hash"])
    if not path.exists():
        raise NotFound("The playback audio is missing.")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/recordings/{recording_id}/original")
def original(recording_id: str) -> FileResponse:
    recording = _recording(recording_id)
    with get_db().read() as conn:
        asset = recording_store.get_asset(conn, recording["content_hash"])
    if asset is None or not Path(asset["original_path"]).exists():
        raise NotFound("The original file is missing.")
    return FileResponse(asset["original_path"], filename=recording["original_filename"])


@router.get("/recordings/{recording_id}/peaks")
def peaks(recording_id: str) -> Response:
    recording = _recording(recording_id)
    path = peaks_path(recording["content_hash"])
    if not path.exists():
        raise NotFound("Waveform peaks are missing.")
    return Response(
        path.read_bytes(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/recordings/{recording_id}/stretched")
def stretched(recording_id: str, speed: float = 0.75) -> FileResponse:
    recording = _recording(recording_id)
    speed = float(min(1.0, max(MIN_SPEED, speed)))
    factor = 1.0 / speed
    path = stretched_path(recording["content_hash"], factor)
    if not path.exists():
        data, sr = load_audio(recording["content_hash"])
        snd = parselmouth.Sound(data.astype("float64"), sampling_frequency=sr)
        longer = call(snd, "Lengthen (overlap-add)", 60.0, 1000.0, factor)
        import soundfile as sf

        sf.write(str(path), longer.values[0], sr, subtype="PCM_16")
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Cache-Control": "private, max-age=86400", "X-Stretch-Factor": f"{factor:.4f}"},
    )


@router.get("/recordings/{recording_id}/segment.wav")
def segment(recording_id: str, start: float, end: float) -> Response:
    data, filename = export_service.audio_segment(recording_id, start, end)
    return Response(
        data, media_type="audio/wav", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
