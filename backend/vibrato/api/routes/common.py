from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from ...config import get_settings
from ...tasks.manager import TaskState


async def save_upload(upload: UploadFile) -> tuple[Path, str]:
    settings = get_settings()
    name = Path(upload.filename or "upload.wav").name
    suffix = Path(name).suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.uploads_dir) as handle:
        shutil.copyfileobj(upload.file, handle)
    return Path(handle.name), name


def task_response(state: TaskState) -> dict[str, Any]:
    return {"task": state.to_dict()}
