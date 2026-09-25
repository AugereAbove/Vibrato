from __future__ import annotations

import csv
import html
import io
import json
import platform
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .. import __version__
from ..alignment.aligner import ALIGNMENT_VERSION
from ..analysis.pipeline import pipeline_version
from ..audio.errors import UserFacingError
from ..coaching.engine import COACHING_VERSION
from ..compare.comparator import COMPARISON_VERSION
from ..compare.metrics import CATEGORIES, CATEGORY_LABELS, METRICS
from ..config import get_settings
from ..db import get_db
from ..db.connection import latest_schema_version
from ..storage import comparison_file
from ..store import comparisons as comparison_store
from ..store import projects as project_store
from ..store import recordings as recording_store
from ..util import read_json, utcnow
from .analysis_service import load_audio
from .progress_service import project_progress

BACKUP_FORMAT = 1


def reproducibility() -> dict[str, Any]:
    from ..analysis.base import analyzer_versions

    versions: dict[str, str] = {}
    for module in ("numpy", "scipy", "librosa", "soundfile", "parselmouth", "fastapi"):
        try:
            imported = __import__(module)
            versions[module] = str(getattr(imported, "__version__", "unknown"))
        except ImportError:
            versions[module] = "missing"
    try:
        import parselmouth

        versions["praat"] = str(parselmouth.PRAAT_VERSION)
    except ImportError:
        pass
    return {
        "app_version": __version__,
        "pipeline_version": pipeline_version(),
        "analyzer_versions": analyzer_versions(),
        "comparison_version": COMPARISON_VERSION,
        "alignment_version": ALIGNMENT_VERSION,
        "coaching_version": COACHING_VERSION,
        "schema_version": latest_schema_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "libraries": versions,
        "exported_at": utcnow(),
    }


def comparison_json(comparison_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        row = comparison_store.get_comparison(conn, comparison_id)
        if row is None:
            raise UserFacingError(
                "This comparison no longer exists.",
                "It may have been replaced by a newer analysis.",
                "Run the comparison again.",
                code="not_found",
            )
        reference = recording_store.get_recording(conn, row["reference_recording_id"])
        take = recording_store.get_recording(conn, row["take_recording_id"])
    payload = read_json(comparison_file(comparison_id))
    return {
        "reproducibility": reproducibility(),
        "reference": {
            "id": reference["id"],
            "name": reference["name"],
            "content_hash": reference["content_hash"],
        }
        if reference
        else None,
        "take": {"id": take["id"], "name": take["name"], "content_hash": take["content_hash"]}
        if take
        else None,
        "metric_definitions": {k: v.to_dict() for k, v in METRICS.items()},
        "comparison": payload,
    }


def comparison_csv(comparison_id: str) -> str:
    payload = read_json(comparison_file(comparison_id))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    meta = reproducibility()
    writer.writerow(
        [
            "vibrato_export",
            meta["app_version"],
            "pipeline",
            meta["pipeline_version"],
            "comparison",
            COMPARISON_VERSION,
        ]
    )
    writer.writerow(
        [
            "metric_id",
            "metric",
            "category",
            "level",
            "label",
            "ref_start_s",
            "ref_end_s",
            "user_start_s",
            "user_end_s",
            "reference",
            "take",
            "difference",
            "unit",
            "normalized_difference",
            "direction",
            "score",
            "confidence",
            "validity",
            "tolerance",
        ]
    )
    for m in payload["metrics"]:
        definition = METRICS[m["metric_id"]]
        writer.writerow(
            [
                m["metric_id"],
                definition.name,
                m["category"],
                m["level"],
                m["label"],
                m["ref_start"],
                m["ref_end"],
                m["user_start"],
                m["user_end"],
                m["ref_value"],
                m["user_value"],
                m["difference"],
                definition.unit,
                m["normalized"],
                m["direction"],
                m["score"],
                m["confidence"],
                m["validity"],
                (m.get("evidence") or {}).get("tolerance_used", definition.tolerance),
            ]
        )
    return buffer.getvalue()


def progress_csv(project_id: str) -> str:
    progress = project_progress(project_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "take_number",
            "take_name",
            "created_at",
            "session_id",
            "overall",
            "overall_confidence",
            *[f"{c}_score" for c in CATEGORIES],
        ]
    )
    for take in progress["takes"]:
        writer.writerow(
            [
                take["take_number"],
                take["take_name"],
                take["created_at"],
                take["session_id"],
                take["overall"],
                take["confidence"],
                *[take["categories"].get(c) for c in CATEGORIES],
            ]
        )
    return buffer.getvalue()


def _sparkline(values: list[float | None], width: int = 520, height: int = 120) -> str:
    points = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(points) < 2:
        return "<p class='muted'>Not enough takes for a trend yet.</p>"
    n = max(1, len(values) - 1)
    coords = " ".join(
        f"{20 + (width - 40) * i / n:.1f},{height - 15 - (height - 30) * v / 100:.1f}" for i, v in points
    )
    dots = "".join(
        f"<circle cx='{20 + (width - 40) * i / n:.1f}' cy='{height - 15 - (height - 30) * v / 100:.1f}' r='3'/>"
        for i, v in points
    )
    return f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' role='img' aria-label='Score trend'><line x1='20' y1='{height - 15}' x2='{width - 20}' y2='{height - 15}' class='axis'/><polyline points='{coords}' class='line'/>{dots}</svg>"


def report_html(project_id: str, comparison_id: str | None = None) -> str:
    with get_db().read() as conn:
        project = project_store.get_project(conn, project_id)
    if project is None:
        raise UserFacingError(
            "This project no longer exists.",
            "It may have been deleted.",
            "Open another project.",
            code="not_found",
        )
    progress = project_progress(project_id)
    latest = comparison_id or (progress["latest_take"] or {}).get("comparison_id")
    coaching: dict[str, Any] = {}
    scores: dict[str, Any] = {}
    if latest:
        payload = read_json(comparison_file(latest))
        coaching = payload.get("coaching", {})
        scores = payload.get("scores", {})
    esc = html.escape
    findings = "".join(
        f"<li><strong>{esc(f['title'])}</strong> <span class='tag'>{esc(f['texts']['confidence_label'])}</span><br>{esc(f['texts']['expert'])}<br><em>{esc(f['texts']['adjust'])}</em></li>"
        for tier in ("primary", "secondary", "minor")
        for f in coaching.get(tier, [])[:6]
    )
    good = "".join(f"<li>{esc(g['text'])}</li>" for g in coaching.get("already_good", [])[:6])
    categories = "".join(
        f"<tr><td>{esc(CATEGORY_LABELS[c])}</td><td>{'' if (scores.get('categories', {}).get(c) or {}).get('score') is None else round(scores['categories'][c]['score'])}</td><td>{round(100 * float((scores.get('categories', {}).get(c) or {}).get('confidence') or 0))}%</td></tr>"
        for c in CATEGORIES
    )
    weaknesses = "".join(
        f"<li><strong>{esc(w['title'])}</strong> - {esc(w['label'])}: {w['takes']} take(s), {w['sessions']} session(s), trend {esc(w['trend'])}</li>"
        for w in progress["weaknesses"][:8]
    )
    takes = "".join(
        f"<tr><td>{t['take_number']}</td><td>{esc(t['take_name'] or '')}</td><td>{esc((t['created_at'] or '')[:16].replace('T', ' '))}</td><td>{'' if t['overall'] is None else round(t['overall'])}</td></tr>"
        for t in progress["takes"]
    )
    meta = reproducibility()
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(project["name"])} - practice report</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:32px auto;max-width:860px;color:#1d2330;padding:0 16px}}h1{{margin-bottom:0}}.muted{{color:#667}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #dde;padding:6px 8px;text-align:left}}.tag{{background:#eef3ff;border-radius:6px;padding:1px 6px;font-size:12px}}svg .line{{fill:none;stroke:#3a63d8;stroke-width:2}}svg circle{{fill:#3a63d8}}svg .axis{{stroke:#ccd}}section{{margin-top:28px}}</style></head><body>
<h1>{esc(project["name"])}</h1><p class="muted">{esc(project.get("song_title") or "")} {esc(project.get("singer_label") or "")} - generated {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</p>
<section><h2>Summary</h2><p>{esc(coaching.get("summary", "No comparison yet."))}</p><p class="muted">{esc(scores.get("overall", {}).get("disclaimer", ""))}</p></section>
<section><h2>Overall score trend</h2>{_sparkline(progress["trends"]["overall"]["series"])}</section>
<section><h2>Latest take by category</h2><table><tr><th>Category</th><th>Score</th><th>Confidence</th></tr>{categories}</table></section>
<section><h2>What to work on</h2><ol>{findings or "<li>No reliable differences found.</li>"}</ol></section>
<section><h2>Already close</h2><ul>{good or "<li>-</li>"}</ul></section>
<section><h2>Recurring patterns</h2><ul>{weaknesses or "<li>Not enough takes yet.</li>"}</ul></section>
<section><h2>Takes</h2><table><tr><th>#</th><th>Name</th><th>Recorded</th><th>Overall</th></tr>{takes}</table></section>
<section class="muted"><h2>Reproducibility</h2><p>Vibrato {esc(meta["app_version"])}, pipeline {esc(meta["pipeline_version"])}, comparison {esc(meta["comparison_version"])}, coaching {esc(meta["coaching_version"])}. Physical interpretations are inferred from acoustics and are not direct observations.</p></section>
</body></html>"""


def backup_project(project_id: str) -> Path:
    settings = get_settings()
    with get_db().read() as conn:
        project = project_store.get_project(conn, project_id)
        if project is None:
            raise UserFacingError(
                "This project no longer exists.",
                "It may have been deleted.",
                "Choose another project.",
                code="not_found",
            )
        recordings = recording_store.list_recordings(conn, project_id)
        tables: dict[str, list[dict[str, Any]]] = {}
        recording_ids = [r["id"] for r in recordings]
        marks = ",".join("?" for _ in recording_ids) or "''"
        for table, where, params in (
            ("projects", "id = ?", [project_id]),
            ("recordings", "project_id = ?", [project_id]),
            ("reference_recordings", f"recording_id IN ({marks})", recording_ids),
            ("user_takes", f"recording_id IN ({marks})", recording_ids),
            ("song_sections", f"recording_id IN ({marks})", recording_ids),
            ("bookmarks", f"recording_id IN ({marks})", recording_ids),
            ("pronunciation_overrides", f"recording_id IN ({marks})", recording_ids),
            ("alignment_anchors", f"reference_recording_id IN ({marks})", recording_ids),
            ("sessions", "project_id = ?", [project_id]),
            ("milestones", "project_id = ?", [project_id]),
            ("coaching_overrides", "project_id = ?", [project_id]),
        ):
            rows = conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
            tables[table] = [dict(r) for r in rows]
        hashes = sorted({r["content_hash"] for r in recordings})
        assets = (
            [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM audio_assets WHERE content_hash IN ({','.join('?' for _ in hashes)})",
                    hashes,
                ).fetchall()
            ]
            if hashes
            else []
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = settings.exports_dir / f"{_safe(project['name'])}-backup-{stamp}.vibrato.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": BACKUP_FORMAT,
                    "project": project["name"],
                    "created_at": utcnow(),
                    "reproducibility": reproducibility(),
                },
                indent=2,
                default=str,
            ),
        )
        archive.writestr("tables.json", json.dumps({**tables, "audio_assets": assets}, default=str))
        for asset in assets:
            source = Path(asset["original_path"])
            if source.exists():
                archive.write(source, f"originals/{source.name}")
    return target


def restore_project(archive_path: Path) -> dict[str, Any]:
    from .importer import ingest_file

    with zipfile.ZipFile(archive_path) as archive:
        try:
            manifest = json.loads(archive.read("manifest.json"))
            tables = json.loads(archive.read("tables.json"))
        except KeyError as exc:
            raise UserFacingError(
                "This file is not a Vibrato project backup.",
                "The archive has no manifest.",
                "Choose a .vibrato.zip file created with 'Back up project'.",
                code="bad_backup",
            ) from exc
        if int(manifest.get("format", 0)) > BACKUP_FORMAT:
            raise UserFacingError(
                "This backup was made by a newer version of Vibrato.",
                "Its format is not understood by this version.",
                "Update Vibrato and try again.",
                code="backup_too_new",
            )
        workdir = Path(tempfile.mkdtemp(prefix="vibrato-restore-"))
        try:
            archive.extractall(workdir)
            for asset in tables.get("audio_assets", []):
                name = Path(asset["original_path"]).name
                source = workdir / "originals" / name
                if source.exists():
                    ingest_file(source, name)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    id_map: dict[str, str] = {}
    from ..util import new_id

    def remap(value: Any) -> Any:
        return id_map.get(value, value) if isinstance(value, str) else value

    with get_db().tx() as conn:
        for table, prefix in (("projects", "prj"), ("recordings", "rec"), ("sessions", "ses")):
            for row in tables.get(table, []):
                id_map[row["id"]] = new_id(prefix)
        for table in (
            "projects",
            "sessions",
            "recordings",
            "reference_recordings",
            "user_takes",
            "song_sections",
            "bookmarks",
            "pronunciation_overrides",
            "alignment_anchors",
            "milestones",
            "coaching_overrides",
        ):
            for row in tables.get(table, []):
                values = {k: remap(v) for k, v in row.items()}
                if table in {
                    "song_sections",
                    "bookmarks",
                    "pronunciation_overrides",
                    "alignment_anchors",
                    "milestones",
                    "coaching_overrides",
                }:
                    values["id"] = new_id(table[:3])
                if table == "projects":
                    values["name"] = f"{values['name']} (restored)"
                columns = list(values.keys())
                try:
                    conn.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                        [values[c] for c in columns],
                    )
                except sqlite3.IntegrityError as exc:
                    raise UserFacingError(
                        "The backup could not be restored.",
                        f"Database constraint failed on {table}: {exc}.",
                        "Make sure the backup file is complete and try again.",
                        code="restore_failed",
                    ) from exc
        project_id = id_map[tables["projects"][0]["id"]]
        return project_store.get_project(conn, project_id) or {}


def debug_bundle() -> Path:
    from .system_service import system_info

    settings = get_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = settings.exports_dir / f"vibrato-debug-{stamp}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.json", json.dumps(system_info(), indent=2, default=str))
        archive.writestr("reproducibility.json", json.dumps(reproducibility(), indent=2, default=str))
        with get_db().read() as conn:
            tasks = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, kind, status, progress, stage, message, error_json, created_at, finished_at FROM tasks ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
            ]
            runs = [
                dict(r)
                for r in conn.execute(
                    "SELECT analyzer_id, analyzer_version, status, validity, duration_ms, error, created_at FROM analyzer_runs ORDER BY created_at DESC LIMIT 500"
                ).fetchall()
            ]
        archive.writestr("tasks.json", json.dumps(tasks, indent=2, default=str))
        archive.writestr("analyzer_runs.json", json.dumps(runs, indent=2, default=str))
        for log in sorted(settings.logs_dir.glob("vibrato.log*")):
            archive.write(log, f"logs/{log.name}")
        archive.writestr(
            "README.txt",
            "Debug bundle: system information, task history, analyzer run history and logs. It contains no audio and no project audio paths beyond file names.",
        )
    return target


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")[:60] or "project"


def audio_segment(recording_id: str, start_s: float, end_s: float) -> tuple[bytes, str]:
    with get_db().read() as conn:
        recording = recording_store.get_recording(conn, recording_id)
    if recording is None:
        raise UserFacingError(
            "This recording no longer exists.",
            "It may have been deleted.",
            "Refresh the project.",
            code="not_found",
        )
    audio, sr = load_audio(recording["content_hash"])
    a = int(max(0.0, start_s) * sr)
    b = int(min(len(audio), max(start_s + 0.05, end_s) * sr))
    buffer = io.BytesIO()
    sf.write(buffer, audio[a:b], sr, format="WAV", subtype="PCM_16")
    return buffer.getvalue(), f"{_safe(recording['name'])}_{start_s:.2f}-{end_s:.2f}s.wav"


def ab_snippet(comparison_id: str, start_s: float, end_s: float) -> tuple[bytes, str]:
    from ..alignment.aligner import Alignment

    payload = read_json(comparison_file(comparison_id))
    with get_db().read() as conn:
        reference = recording_store.get_recording(conn, payload["reference_id"])
        take = recording_store.get_recording(conn, payload["take_id"])
        alignment_row = conn.execute(
            "SELECT path_file FROM alignments WHERE reference_recording_id = ? AND take_recording_id = ?",
            (payload["reference_id"], payload["take_id"]),
        ).fetchone()
    if reference is None or take is None or alignment_row is None:
        raise UserFacingError(
            "The comparison audio is unavailable.",
            "A recording or the alignment is missing.",
            "Run the comparison again.",
            code="not_found",
        )
    alignment = Alignment.load(Path(alignment_row["path_file"]))
    ref_audio, sr = load_audio(reference["content_hash"])
    take_audio, _ = load_audio(take["content_hash"])
    us, ue = (float(v) for v in alignment.ref_to_user(np.array([start_s, end_s])))
    ref_part = ref_audio[int(start_s * sr) : int(end_s * sr)]
    take_part = take_audio[int(max(0.0, us) * sr) : int(ue * sr)]
    rms_ref = float(np.sqrt(np.mean(ref_part**2))) if ref_part.size else 1.0
    rms_take = float(np.sqrt(np.mean(take_part**2))) if take_part.size else 1.0
    if rms_take > 0:
        take_part = take_part * (rms_ref / rms_take)
    gap = np.zeros(int(0.4 * sr), dtype=np.float32)
    combined = np.concatenate([ref_part, gap, take_part]).astype(np.float32)
    peak = float(np.max(np.abs(combined))) if combined.size else 0.0
    if peak > 0.98:
        combined *= 0.98 / peak
    buffer = io.BytesIO()
    sf.write(buffer, combined, sr, format="WAV", subtype="PCM_16")
    return buffer.getvalue(), f"AB_reference-then-take_{start_s:.2f}-{end_s:.2f}s.wav"
