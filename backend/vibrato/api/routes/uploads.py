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
from ...util import new_id
from ..deps import User, get_current_user
from ..errors import Forbidden, NotFound

router = APIRouter(tags=["uploads"])

# Chunked uploads let a large recording cross a request-size-limited proxy
# (e.g. Cloudflare Tunnel's ~100MB cap) as many small requests instead of one
# giant one. This is a short-lived, in-memory staging area - nothing here is
# persisted data, so it lives outside the SQLite store.
_UPLOAD_TTL_S = 3600.0


@dataclass
class _PendingUpload:
    owner_id: str
    dir: Path
    filename: str
    created_at: float = field(default_factory=time.monotonic)
    received: set[int] = field(default_factory=set)
    assembled: Path | None = None  # set once complete_upload() has run


_uploads: dict[str, _PendingUpload] = {}
_lock = threading.Lock()


def _sweep_expired_locked() -> None:
    now = time.monotonic()
    stale = [uid for uid, u in _uploads.items() if now - u.created_at > _UPLOAD_TTL_S]
    for uid in stale:
        pending = _uploads.pop(uid, None)
        if pending is not None:
            shutil.rmtree(pending.dir, ignore_errors=True)
            if pending.assembled is not None:
                pending.assembled.unlink(missing_ok=True)


class UploadInit(BaseModel):
    filename: str = "upload.wav"


class UploadInitResponse(BaseModel):
    upload_id: str


@router.post("/uploads")
def init_upload(body: UploadInit, user: User = Depends(get_current_user)) -> UploadInitResponse:
    with _lock:
        _sweep_expired_locked()
        upload_id = new_id("upl")
        directory = Path(tempfile.mkdtemp(prefix=f"{upload_id}-", dir=get_settings().uploads_dir))
        _uploads[upload_id] = _PendingUpload(user.id, directory, Path(body.filename).name)
    return UploadInitResponse(upload_id=upload_id)


def _get_pending(upload_id: str, user: User) -> _PendingUpload:
    with _lock:
        pending = _uploads.get(upload_id)
    if pending is None:
        raise NotFound("This upload does not exist or has expired.")
    if pending.owner_id != user.id and not user.is_owner:
        raise Forbidden()
    return pending


@router.put("/uploads/{upload_id}/chunk/{index}")
async def put_chunk(
    upload_id: str, index: int, request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    pending = _get_pending(upload_id, user)
    part_path = pending.dir / f"part-{index:08d}"
    with open(part_path, "wb") as handle:
        async for piece in request.stream():
            handle.write(piece)
    with _lock:
        pending.received.add(index)
    return {"received": index}


class UploadComplete(BaseModel):
    total_chunks: int


@router.post("/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str, body: UploadComplete, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    pending = _get_pending(upload_id, user)
    missing = [i for i in range(body.total_chunks) if i not in pending.received]
    if missing:
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
    """Consume a chunked upload completed via /uploads/{id}/complete. Used by
    other routes (recording import, etc.) in place of `save_upload` when the
    client uploaded in chunks. Raises NotFound if the id is unknown, not
    owned by this user, or not yet completed."""
    with _lock:
        pending = _uploads.get(upload_id)
        if pending is None or pending.assembled is None:
            raise NotFound("This upload does not exist, has expired, or is still in progress.")
        if pending.owner_id != user.id and not user.is_owner:
            raise Forbidden()
        del _uploads[upload_id]
    return pending.assembled, pending.filename
