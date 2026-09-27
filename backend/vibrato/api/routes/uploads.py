from __future__ import annotations

import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ...config import get_settings
from ...db import get_db
from ...util import new_id
from ..deps import User, get_current_user, storage_used
from ..errors import Forbidden, NotFound, QuotaExceeded, TooLarge

router = APIRouter(tags=["uploads"])

_UPLOAD_TTL_S = 3600.0
MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_CHUNKS = 4096
MAX_PENDING_PER_USER = 3


@dataclass
class _PendingUpload:
    owner_id: str
    dir: Path
    filename: str
    created_at: float = field(default_factory=time.monotonic)
    parts: dict[int, int] = field(default_factory=dict)
    assembled: Path | None = None

    @property
    def staged_bytes(self) -> int:
        return sum(self.parts.values())


_uploads: dict[str, _PendingUpload] = {}
_lock = threading.Lock()


def _discard_locked(upload_id: str) -> None:
    pending = _uploads.pop(upload_id, None)
    if pending is not None:
        shutil.rmtree(pending.dir, ignore_errors=True)
        if pending.assembled is not None:
            pending.assembled.unlink(missing_ok=True)


def _sweep_expired_locked() -> None:
    now = time.monotonic()
    for uid in [uid for uid, u in _uploads.items() if now - u.created_at > _UPLOAD_TTL_S]:
        _discard_locked(uid)


class UploadInit(BaseModel):
    filename: str = "upload.wav"


class UploadInitResponse(BaseModel):
    upload_id: str


@router.post("/uploads")
def init_upload(body: UploadInit, user: User = Depends(get_current_user)) -> UploadInitResponse:
    with _lock:
        _sweep_expired_locked()
        if not user.is_owner:
            mine = sum(1 for u in _uploads.values() if u.owner_id == user.id and u.assembled is None)
            if mine >= MAX_PENDING_PER_USER:
                raise QuotaExceeded(
                    f"This account already has {MAX_PENDING_PER_USER} uploads in progress.",
                    "Wait for them to finish, then try again.",
                )
        upload_id = new_id("upl")
        directory = Path(tempfile.mkdtemp(prefix=f"{upload_id}-", dir=get_settings().uploads_dir))
        _uploads[upload_id] = _PendingUpload(user.id, directory, Path(body.filename).name[:200])
    return UploadInitResponse(upload_id=upload_id)


def _get_pending(upload_id: str, user: User) -> _PendingUpload:
    with _lock:
        pending = _uploads.get(upload_id)
    if pending is None:
        raise NotFound("This upload does not exist or has expired.")
    if pending.owner_id != user.id and not user.is_owner:
        raise Forbidden()
    return pending


def _check_staged_quota(upload_id: str, pending: _PendingUpload, user: User) -> None:
    settings = get_settings()
    if pending.staged_bytes > settings.max_upload_bytes:
        with _lock:
            _discard_locked(upload_id)
        raise TooLarge(f"Uploads are limited to {settings.max_upload_bytes // (1024 * 1024)} MB.")
    if user.is_owner:
        return
    with _lock:
        staged = sum(u.staged_bytes for u in _uploads.values() if u.owner_id == user.id and u.assembled is None)
    with get_db().read() as conn:
        used = storage_used(conn, user.id)
    if used + staged > settings.tester_storage_bytes:
        with _lock:
            _discard_locked(upload_id)
        raise QuotaExceeded(
            f"This account has used its {settings.tester_storage_bytes // (1024 * 1024)} MB of storage.",
            "Delete recordings or projects you no longer need, then try again.",
        )


@router.put("/uploads/{upload_id}/chunk/{index}")
async def put_chunk(
    upload_id: str, index: int, request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    pending = _get_pending(upload_id, user)
    if pending.assembled is not None:
        raise NotFound("This upload is already complete.")
    if not 0 <= index < MAX_CHUNKS:
        raise NotFound("Chunk index out of range.")
    part_path = pending.dir / f"part-{index:08d}"
    written = 0
    with open(part_path, "wb") as handle:
        async for piece in request.stream():
            written += len(piece)
            if written > MAX_CHUNK_BYTES:
                handle.close()
                part_path.unlink(missing_ok=True)
                raise TooLarge(f"Upload chunks are limited to {MAX_CHUNK_BYTES // (1024 * 1024)} MB.")
            handle.write(piece)
    with _lock:
        pending.parts[index] = written
    _check_staged_quota(upload_id, pending, user)
    return {"received": index}


class UploadComplete(BaseModel):
    total_chunks: int


@router.post("/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str, body: UploadComplete, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    pending = _get_pending(upload_id, user)
    if pending.assembled is not None:
        return {"upload_id": upload_id, "size_bytes": pending.assembled.stat().st_size}
    if not 0 < body.total_chunks <= MAX_CHUNKS:
        raise NotFound("Invalid chunk count.")
    missing = [i for i in range(body.total_chunks) if i not in pending.parts]
    if missing or len(pending.parts) != body.total_chunks:
        raise NotFound(f"Upload is missing {len(missing)} chunk(s); it may have failed partway through.")
    suffix = Path(pending.filename).suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=get_settings().uploads_dir) as out:
        for index in range(body.total_chunks):
            with open(pending.dir / f"part-{index:08d}", "rb") as part:
                shutil.copyfileobj(part, out)
        assembled = Path(out.name)
    shutil.rmtree(pending.dir, ignore_errors=True)
    with _lock:
        pending.assembled = assembled
    return {"upload_id": upload_id, "size_bytes": assembled.stat().st_size}


def take_completed_upload(upload_id: str, user: User) -> tuple[Path, str]:
    with _lock:
        pending = _uploads.get(upload_id)
        if pending is None or pending.assembled is None:
            raise NotFound("This upload does not exist, has expired, or is still in progress.")
        if pending.owner_id != user.id and not user.is_owner:
            raise Forbidden()
        del _uploads[upload_id]
    return pending.assembled, pending.filename
