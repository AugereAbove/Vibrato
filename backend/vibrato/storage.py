from __future__ import annotations

import shutil
from pathlib import Path

from .config import get_settings


def asset_dir(content_hash: str) -> Path:
    return get_settings().derived_dir / content_hash[:2] / content_hash


def original_path(content_hash: str, extension: str) -> Path:
    return get_settings().originals_dir / f"{content_hash}{extension}"


def canonical_path(content_hash: str) -> Path:
    return asset_dir(content_hash) / "canonical.flac"


def playback_path(content_hash: str) -> Path:
    return asset_dir(content_hash) / "playback.wav"


def peaks_path(content_hash: str) -> Path:
    return asset_dir(content_hash) / "peaks.bin"


def features_path(content_hash: str, key: str) -> Path:
    return asset_dir(content_hash) / f"features-{key}.npz"


def analysis_path(content_hash: str, key: str) -> Path:
    return asset_dir(content_hash) / f"analysis-{key}.json"


def spectrogram_path(content_hash: str, key: str) -> Path:
    return asset_dir(content_hash) / f"spectrogram-{key}.npz"


def stretched_path(content_hash: str, factor: float) -> Path:
    return asset_dir(content_hash) / f"stretch-{round(factor * 100)}.wav"


def alignment_file(ref_id: str, take_id: str, key: str) -> Path:
    return get_settings().derived_dir / "alignments" / f"{ref_id}__{take_id}__{key}.npz"


def comparison_file(comparison_id: str) -> Path:
    return get_settings().derived_dir / "comparisons" / f"{comparison_id}.json"


def render_file(render_id: str) -> Path:
    return get_settings().renders_dir / f"{render_id}.wav"


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def clear_derived_cache() -> int:
    settings = get_settings()
    freed = 0
    for child in settings.derived_dir.iterdir() if settings.derived_dir.exists() else []:
        if child.is_dir() and len(child.name) == 2:
            for asset in child.iterdir():
                for item in asset.iterdir():
                    if item.name.startswith(("features-", "analysis-", "spectrogram-", "stretch-")):
                        freed += item.stat().st_size
                        item.unlink(missing_ok=True)
        elif child.is_dir() and child.name in {"alignments", "comparisons"}:
            freed += directory_size(child)
            shutil.rmtree(child, ignore_errors=True)
    for render in settings.renders_dir.glob("*.wav"):
        freed += render.stat().st_size
        render.unlink(missing_ok=True)
    return freed
