from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import soundfile as sf

from ..config import get_settings
from ..db import get_db
from ..demo.songs import DEMO_LYRICS, DEMO_TITLE, reference_performance, take_performance
from ..demo.synth import render
from ..store import projects as project_store
from ..store import recordings as recording_store
from ..tasks.manager import TaskContext
from ..util import new_id
from .comparison_service import run_comparison
from .importer import import_recording

DEMO_DAYS_AGO = (2, 1, 0)


def _demo_file(name: str, performance: Any) -> Any:
    directory = get_settings().data_dir / "demo-audio"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.wav"
    if not path.exists():
        rendered = render(performance)
        sf.write(str(path), rendered.audio, rendered.sample_rate, subtype="PCM_16")
    return path


def create_demo_project(context: TaskContext | None = None) -> dict[str, Any]:
    if context:
        context.progress(0.02, "Synthesising demo reference")
    with get_db().tx() as conn:
        project = project_store.create_project(
            conn,
            f"Demo: {DEMO_TITLE}",
            song_title=DEMO_TITLE,
            song_artist="Synthetic demo",
            singer_label="Synthetic reference voice",
            notes="All audio in this project is synthesised by Vibrato's built-in source-filter voice model. The takes contain deliberate, known differences from the reference (vibrato, a scoop, a flat note, vowel colour, breathiness, timing, a missing breath) so every analysis view has something real to show.",
            is_demo=True,
        )
    reference_path = _demo_file("demo-reference", reference_performance())
    reference = import_recording(
        project["id"],
        "reference",
        reference_path,
        "demo-reference.wav",
        name="Reference (synthetic)",
        origin="demo",
        lyrics=DEMO_LYRICS,
        singer_label="Synthetic reference voice",
    )
    takes = []
    for index, days in zip((1, 2, 3), DEMO_DAYS_AGO):
        if context:
            context.progress(0.05 + 0.08 * index, f"Synthesising demo take {index}")
        path = _demo_file(f"demo-take-{index}", take_performance(index))
        session_id = new_id("ses")
        stamp = (datetime.now(UTC) - timedelta(days=days, minutes=30 - index)).isoformat(
            timespec="milliseconds"
        )
        with get_db().tx() as conn:
            conn.execute(
                "INSERT INTO sessions (id, project_id, kind, started_at, last_activity_at, ended_at, active_seconds, notes) VALUES (?, ?, 'practice', ?, ?, ?, ?, ?)",
                (
                    session_id,
                    project["id"],
                    stamp,
                    stamp,
                    stamp if days else None,
                    900.0 + 120 * index,
                    f"Demo session {index} (synthetic)",
                ),
            )
        take = import_recording(
            project["id"],
            "take",
            path,
            f"demo-take-{index}.wav",
            name=f"Take {index}",
            origin="demo",
            reference_id=reference["id"],
            allow_duplicate=True,
        )
        with get_db().tx() as conn:
            conn.execute("UPDATE recordings SET created_at = ? WHERE id = ?", (stamp, take["id"]))
            conn.execute(
                "UPDATE user_takes SET session_id = ? WHERE recording_id = ?", (session_id, take["id"])
            )
            conn.execute(
                "DELETE FROM sessions WHERE project_id = ? AND id != ? AND notes = '' AND (SELECT COUNT(*) FROM user_takes WHERE session_id = sessions.id) = 0",
                (project["id"], session_id),
            )
        takes.append(take)
    for index, take in enumerate(takes):
        if context:
            context.progress(0.3 + 0.22 * index, f"Analysing and comparing take {index + 1}")
        run_comparison(take["id"], reference["id"])
    with get_db().read() as conn:
        result = project_store.get_project(conn, project["id"])
        result = {
            **(result or {}),
            "reference_id": reference["id"],
            "take_ids": [t["id"] for t in takes],
            "recordings": recording_store.list_recordings(conn, project["id"]),
        }
    if context:
        context.progress(1.0, "Demo project ready")
    return result
