from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import soundfile as sf

from ..audio.canonical import CANONICAL_VERSION, canonicalize
from ..audio.decode import SUPPORTED_EXTENSIONS, decode_file, validate_duration
from ..audio.errors import AudioValidationError
from ..audio.peaks import build_peak_pyramid, encode_peak_pyramid
from ..audio.quality import analyze_signal_quality
from ..config import get_settings
from ..db import get_db
from ..logging_setup import get_logger
from ..storage import canonical_path, original_path, peaks_path, playback_path
from ..store import projects as project_store
from ..store import recordings as recording_store
from ..store.misc import active_session
from ..util import dumps, sha256_file, utcnow

log = get_logger("import")


class DuplicateRecording(Exception):
    def __init__(self, existing: dict[str, Any]) -> None:
        super().__init__("duplicate")
        self.existing = existing


def _asset_ready(asset: dict[str, Any] | None) -> bool:
    if asset is None or int(asset.get("canonical_version", 0)) != CANONICAL_VERSION:
        return False
    return all(Path(asset[k]).exists() for k in ("original_path", "canonical_path", "playback_path"))


def ingest_file(source: Path, original_name: str) -> dict[str, Any]:
    settings = get_settings()
    extension = Path(original_name).suffix.lower() or source.suffix.lower()
    if extension and extension not in SUPPORTED_EXTENSIONS:
        raise AudioValidationError(
            what=f"'{original_name}' has an unsupported file type ({extension}).",
            why="Vibrato reads WAV, FLAC, MP3, OGG/Opus, AIFF and (with the bundled FFmpeg decoder) M4A/AAC.",
            action="Convert the file to WAV or FLAC and import it again.",
            code="unsupported_extension",
        )
    size = source.stat().st_size
    if size > settings.max_upload_bytes:
        raise AudioValidationError(
            what=f"'{original_name}' is {size / 1e6:.0f} MB.",
            why=f"Files above {settings.max_upload_bytes / 1e6:.0f} MB are rejected to keep analysis responsive.",
            action="Trim the recording to the section you want to practise.",
            code="too_large",
        )
    content_hash = sha256_file(source)
    with get_db().read() as conn:
        existing = recording_store.get_asset(conn, content_hash)
    if _asset_ready(existing):
        return existing or {}
    decoded = decode_file(source)
    validate_duration(decoded, settings.min_duration_s, settings.max_duration_s, original_name)
    canonical = canonicalize(decoded)
    quality = analyze_signal_quality(decoded, canonical, is_reference=False)
    target_original = original_path(content_hash, extension or ".bin")
    target_original.parent.mkdir(parents=True, exist_ok=True)
    if not target_original.exists():
        shutil.copyfile(source, target_original)
    target_canonical = canonical_path(content_hash)
    target_canonical.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target_canonical), canonical.samples, canonical.sample_rate, subtype="PCM_24", format="FLAC")
    sf.write(
        str(playback_path(content_hash)),
        canonical.samples,
        canonical.sample_rate,
        subtype="PCM_16",
        format="WAV",
    )
    peaks_path(content_hash).write_bytes(
        encode_peak_pyramid(build_peak_pyramid(canonical.samples, canonical.sample_rate))
    )
    asset = {
        "content_hash": content_hash,
        "original_path": str(target_original),
        "canonical_path": str(target_canonical),
        "playback_path": str(playback_path(content_hash)),
        "original_extension": extension or ".bin",
        "source_format": decoded.source_format,
        "source_subtype": decoded.source_subtype,
        "source_sample_rate": decoded.sample_rate,
        "source_bit_depth": decoded.bit_depth,
        "source_channels": decoded.channels,
        "decoder": decoded.decoder,
        "lossy": int(decoded.lossy),
        "duration_s": canonical.duration_s,
        "canonical_sample_rate": canonical.sample_rate,
        "canonical_version": CANONICAL_VERSION,
        "qc_json": dumps(quality.to_dict()),
        "size_bytes": size,
        "created_at": utcnow(),
    }
    with get_db().tx() as conn:
        recording_store.insert_asset(conn, asset)
        stored = recording_store.get_asset(conn, content_hash)
    log.info("Ingested %s (%s, %.1f s)", original_name, content_hash[:10], canonical.duration_s)
    return stored or {}


def import_recording(
    project_id: str | None,
    kind: str,
    source: Path,
    original_name: str,
    name: str | None = None,
    origin: str = "import",
    reference_id: str | None = None,
    synced: bool = False,
    latency_ms: float = 0.0,
    region: tuple[float, float] | None = None,
    allow_duplicate: bool = False,
    lyrics: str = "",
    singer_label: str = "",
) -> dict[str, Any]:
    asset = ingest_file(source, original_name)
    with get_db().tx() as conn:
        if project_id is not None and not allow_duplicate:
            duplicate = recording_store.find_duplicate(conn, project_id, asset["content_hash"], kind)
            if duplicate is not None:
                raise DuplicateRecording(duplicate)
        display = (name or Path(original_name).stem or "Recording").strip()
        reference_payload = None
        take_payload = None
        if kind == "reference":
            first = project_id is not None and not recording_store.list_recordings(
                conn, project_id, "reference"
            )
            project = project_store.get_project(conn, project_id) if project_id else None
            reference_payload = {
                "lyrics": lyrics,
                "singer_label": singer_label or (project or {}).get("singer_label", ""),
                "is_primary": 1 if first else 0,
                "reference_profile_id": (project or {}).get("reference_profile_id"),
            }
        elif kind == "take" and project_id is not None:
            if reference_id is None:
                primary = recording_store.primary_reference(conn, project_id)
                reference_id = primary["id"] if primary else None
            number = recording_store.next_take_number(conn, project_id)
            session = active_session(conn, project_id)
            take_payload = {
                "reference_recording_id": reference_id,
                "session_id": session.get("id"),
                "take_number": number,
                "synced_to_reference": synced,
                "latency_ms": latency_ms,
                "region_start_s": region[0] if region else None,
                "region_end_s": region[1] if region else None,
            }
            if not name:
                display = f"Take {number}"
        recording = recording_store.create_recording(
            conn,
            project_id,
            kind,
            display,
            original_name,
            asset["content_hash"],
            origin,
            reference_payload,
            take_payload,
        )
        if project_id:
            project_store.touch_project(conn, project_id)
    return recording
