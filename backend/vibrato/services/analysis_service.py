from __future__ import annotations

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..analysis.features import FeatureSet
from ..analysis.pipeline import features_key, pipeline_version, run_analysis
from ..audio.errors import UserFacingError
from ..compare.view import RecordingView
from ..db import get_db
from ..logging_setup import get_logger
from ..storage import analysis_path, canonical_path, features_path
from ..store import analyses as analysis_store
from ..store import recordings as recording_store
from ..store.calibration import active_profile
from ..store.misc import get_preferences, list_sections, pronunciation_overrides
from ..tasks.manager import ProgressReporter
from ..util import read_json, stable_hash, write_json_atomic

log = get_logger("analysis")
CACHE_SIZE = 12
_cache: OrderedDict[str, Any] = OrderedDict()
_cache_lock = threading.Lock()
_recording_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _cache_get(key: str) -> Any:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _cache_put(key: str, value: Any) -> None:
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def clear_memory_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _lock_for(recording_id: str) -> threading.Lock:
    with _locks_guard:
        return _recording_locks.setdefault(recording_id, threading.Lock())


def analysis_options() -> dict[str, Any]:
    with get_db().read() as conn:
        prefs = get_preferences(conn)
    return {
        "use_pyin": bool(prefs.get("analysis.use_pyin", False)),
        "use_crepe": bool(prefs.get("analysis.use_crepe", False)),
        "disabled_analyzers": list(prefs.get("analysis.disabled_analyzers", []) or []),
    }


def load_audio(content_hash: str) -> tuple[np.ndarray, int]:
    path = canonical_path(content_hash)
    if not path.exists():
        raise UserFacingError(
            what="The analysis copy of this recording is missing.",
            why="The derived-data folder may have been cleared or moved.",
            action="Re-import the original file, or restore the project from a backup.",
            code="canonical_missing",
        )
    data, sr = sf.read(str(path), dtype="float32")
    return data, int(sr)


def recording_inputs(conn: Any, recording: dict[str, Any]) -> dict[str, Any]:
    lyrics = ""
    overrides: dict[int, str] = {}
    sections: list[dict[str, Any]] = []
    baseline = None
    baseline_id = None
    if recording["kind"] == "reference":
        lyrics = recording.get("lyrics") or ""
        overrides = pronunciation_overrides(conn, recording["id"])
        sections = list_sections(conn, recording["id"])
    elif recording["kind"] == "take":
        reference_id = recording.get("reference_recording_id")
        if reference_id:
            reference = recording_store.get_recording(conn, reference_id)
            if reference is not None:
                lyrics = reference.get("lyrics") or ""
                overrides = pronunciation_overrides(conn, reference_id)
        profile = active_profile(conn)
        if profile and profile.get("results"):
            baseline = profile["results"].get("baseline")
            baseline_id = profile["id"]
    return {
        "lyrics": lyrics,
        "overrides": overrides,
        "sections": sections,
        "baseline": baseline,
        "baseline_id": baseline_id,
    }


def analysis_key(recording: dict[str, Any], inputs: dict[str, Any], options: dict[str, Any]) -> str:
    return stable_hash(
        {
            "pipeline": pipeline_version(),
            "features": features_key(options),
            "lyrics": inputs["lyrics"],
            "overrides": {str(k): v for k, v in inputs["overrides"].items()},
            "sections": [
                (round(float(s["start_s"]), 3), round(float(s["end_s"]), 3), s["label"])
                for s in inputs["sections"]
            ],
            "baseline": inputs["baseline_id"],
            "disabled": sorted(options.get("disabled_analyzers", [])),
            "kind": recording["kind"],
        }
    )


def load_features(
    content_hash: str,
    options: dict[str, Any],
    audio: np.ndarray | None,
    sr: int,
    noise_floor: float,
    context: ProgressReporter | None,
) -> FeatureSet:
    key = features_key(options)
    path = features_path(content_hash, key)
    cached = _cache_get(f"features:{content_hash}:{key}")
    if cached is not None:
        return cached
    if path.exists():
        try:
            features = FeatureSet.load(path)
            _cache_put(f"features:{content_hash}:{key}", features)
            return features
        except Exception:
            log.warning("Feature cache for %s was unreadable; recomputing", content_hash[:10])
    from ..analysis.features import extract_features

    assert audio is not None
    features = extract_features(
        audio.astype(np.float64),
        sr,
        noise_floor,
        use_pyin=bool(options.get("use_pyin")),
        use_crepe=bool(options.get("use_crepe")),
        progress=context.sub(0.05, 0.75) if context else (lambda f, m: None),
        check_cancelled=context.check_cancelled if context else (lambda: None),
    )
    features.save(path)
    _cache_put(f"features:{content_hash}:{key}", features)
    return features


def ensure_analysis(
    recording_id: str, context: ProgressReporter | None = None, force: bool = False
) -> dict[str, Any]:
    with _lock_for(recording_id):
        with get_db().read() as conn:
            recording = recording_store.get_recording(conn, recording_id)
            if recording is None:
                raise UserFacingError(
                    "This recording no longer exists.",
                    "It may have been deleted.",
                    "Refresh the project.",
                    code="not_found",
                )
            inputs = recording_inputs(conn, recording)
        options = analysis_options()
        key = analysis_key(recording, inputs, options)
        content_hash = recording["content_hash"]
        if not force:
            with get_db().read() as conn:
                existing = analysis_store.latest_analysis(conn, recording_id, key)
            if existing and analysis_path(content_hash, key).exists():
                return existing
        started = time.perf_counter()
        if context:
            context.progress(0.02, f"Loading {recording['name']}", stage="load")
        audio, sr = load_audio(content_hash)
        quality = recording.get("qc") or {}
        noise_floor = float(quality.get("noise_floor_dbfs", -90.0))
        features = load_features(content_hash, options, audio, sr, noise_floor, context)
        if context:
            context.progress(0.76, "Segmenting and measuring", stage="analyze")
        analysis = run_analysis(
            audio,
            sr,
            noise_floor,
            quality_factors=quality.get("factors", {}),
            quality_reasons=quality.get("factor_reasons", {}),
            lyrics=inputs["lyrics"],
            pronunciation_overrides=inputs["overrides"],
            sections=inputs["sections"],
            baseline=inputs["baseline"],
            options={**options, "clipped_regions": quality.get("clipped_regions", [])},
            features=features,
            progress=context.sub(0.76, 0.97) if context else (lambda f, m: None),
            check_cancelled=context.check_cancelled if context else (lambda: None),
        )
        payload = analysis.to_json()
        payload["inputs"] = {
            "lyrics": inputs["lyrics"],
            "baseline_id": inputs["baseline_id"],
            "options": options,
        }
        path = analysis_path(content_hash, key)
        write_json_atomic(path, payload)
        duration_ms = (time.perf_counter() - started) * 1000.0
        with get_db().tx() as conn:
            analysis_id = analysis_store.save_analysis(
                conn,
                recording_id,
                content_hash,
                analysis.version,
                key,
                str(features_path(content_hash, features_key(options))),
                str(path),
                analysis.summary,
                duration_ms,
                payload["segments"],
                payload["events"],
                analysis.runs,
            )
            row = analysis_store.latest_analysis(conn, recording_id, key)
        _cache_put(f"view:{analysis_id}", RecordingView.from_analysis(recording_id, analysis))
        _cache_put(f"payload:{analysis_id}", payload)
        if context:
            context.progress(0.99, "Analysis saved")
        return row or {}


def load_payload(analysis: dict[str, Any]) -> dict[str, Any]:
    cached = _cache_get(f"payload:{analysis['id']}")
    if cached is not None:
        return cached
    payload = read_json(analysis_path(analysis["content_hash"], analysis["params_hash"]))
    _cache_put(f"payload:{analysis['id']}", payload)
    return payload


def load_view(
    recording_id: str, context: ProgressReporter | None = None
) -> tuple[RecordingView, dict[str, Any]]:
    analysis = ensure_analysis(recording_id, context)
    cached = _cache_get(f"view:{analysis['id']}")
    if cached is not None:
        return cached, analysis
    payload = load_payload(analysis)
    features = FeatureSet.load(Path(analysis["features_path"]))
    view = RecordingView.from_json(recording_id, payload, features)
    _cache_put(f"view:{analysis['id']}", view)
    return view, analysis


def current_analysis(recording_id: str) -> dict[str, Any] | None:
    with get_db().read() as conn:
        return analysis_store.latest_analysis(conn, recording_id)


def is_outdated(analysis: dict[str, Any] | None) -> bool:
    return analysis is not None and analysis.get("pipeline_version") != pipeline_version()
