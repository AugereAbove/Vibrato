from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from ..analysis.analyzers.vibrato import (
    EXTENT_MIN_CENTS,
    PERIODICITY_MIN,
    band_limited_oscillation,
    local_vibrato,
    measure_region,
    refine_onset,
)
from ..analysis.analyzers.voice_quality import breathiness_index
from ..audio.errors import UserFacingError
from ..db import get_db
from ..dsp.framing import HOP_S, remove_short_runs, runs
from ..dsp.music import describe_pitch, hz_to_midi
from ..store import calibration as calibration_store
from ..store import recordings as recording_store
from .analysis_service import analysis_options, load_audio, load_features
from .importer import import_recording

STEPS: list[dict[str, Any]] = [
    {
        "id": "noise",
        "title": "Room noise",
        "instruction": "Stay silent for 3 seconds so the room can be measured.",
        "seconds": 3,
        "optional": False,
        "group": "setup",
    },
    {
        "id": "vowel_a",
        "title": "Vowel 'ah'",
        "instruction": "Sing a steady 'ah' (as in 'father') on a comfortable note for 3 seconds.",
        "seconds": 3,
        "optional": False,
        "group": "vowels",
        "vowel": "AA",
    },
    {
        "id": "vowel_e",
        "title": "Vowel 'eh'",
        "instruction": "Sing a steady 'eh' (as in 'bed') on the same note.",
        "seconds": 3,
        "optional": False,
        "group": "vowels",
        "vowel": "EH",
    },
    {
        "id": "vowel_i",
        "title": "Vowel 'ee'",
        "instruction": "Sing a steady 'ee' (as in 'see').",
        "seconds": 3,
        "optional": False,
        "group": "vowels",
        "vowel": "IY",
    },
    {
        "id": "vowel_o",
        "title": "Vowel 'oh'",
        "instruction": "Sing a steady 'oh' (as in 'go', without gliding).",
        "seconds": 3,
        "optional": False,
        "group": "vowels",
        "vowel": "OW",
    },
    {
        "id": "vowel_u",
        "title": "Vowel 'oo'",
        "instruction": "Sing a steady 'oo' (as in 'moon').",
        "seconds": 3,
        "optional": False,
        "group": "vowels",
        "vowel": "UW",
    },
    {
        "id": "pitch_low",
        "title": "Low note",
        "instruction": "Sing 'ah' on a comfortable low note.",
        "seconds": 3,
        "optional": False,
        "group": "range",
    },
    {
        "id": "pitch_high",
        "title": "High note",
        "instruction": "Sing 'ah' on a comfortable high note (not strained).",
        "seconds": 3,
        "optional": False,
        "group": "range",
    },
    {
        "id": "straight",
        "title": "Straight tone",
        "instruction": "Sing 'ah' for 4 seconds with no vibrato at all.",
        "seconds": 4,
        "optional": False,
        "group": "vibrato",
    },
    {
        "id": "vibrato",
        "title": "Natural vibrato",
        "instruction": "Sing 'ah' for 4 seconds and let your natural vibrato happen.",
        "seconds": 4,
        "optional": False,
        "group": "vibrato",
    },
    {
        "id": "breathy",
        "title": "Breathy tone",
        "instruction": "Sing 'ah' very breathily (airy, like a sigh) for 3 seconds.",
        "seconds": 3,
        "optional": False,
        "group": "phonation",
    },
    {
        "id": "modal",
        "title": "Clear tone",
        "instruction": "Sing 'ah' in a clear, full voice for 3 seconds.",
        "seconds": 3,
        "optional": False,
        "group": "phonation",
    },
    {
        "id": "falsetto",
        "title": "Falsetto / head voice",
        "instruction": "Optional: sing a light falsetto or head-voice 'oo'.",
        "seconds": 3,
        "optional": True,
        "group": "register",
    },
    {
        "id": "fry",
        "title": "Vocal fry",
        "instruction": "Optional: make a gentle creaky 'ah' (vocal fry).",
        "seconds": 3,
        "optional": True,
        "group": "register",
    },
]
STEP_IDS = {s["id"] for s in STEPS}


def _stable_region(features: Any) -> np.ndarray:
    level = features.tracks["level_rel_db"]
    voiced = features.voiced & (level > -20.0)
    blocks = runs(voiced)
    mask = np.zeros(features.n, dtype=bool)
    if not blocks:
        return mask
    start, end = max(blocks, key=lambda b: b[1] - b[0])
    trim = int((end - start) * 0.2)
    mask[start + trim : end - trim] = True
    return mask


def _median(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else None


def measure_sample(step: str, features: Any, quality: dict[str, Any]) -> dict[str, Any]:
    if step == "noise":
        return {
            "noise_floor_dbfs": quality.get("noise_floor_dbfs"),
            "active_level_dbfs": quality.get("active_level_dbfs"),
        }
    mask = _stable_region(features)
    if mask.sum() < 20:
        raise UserFacingError(
            what="Not enough steady singing was found in this sample.",
            why="The calibration step needs at least half a second of steady, voiced sound.",
            action="Record the step again, a little louder and closer to the microphone.",
            code="calibration_too_short",
        )
    f0 = features.tracks["f0_hz"][mask]
    result: dict[str, Any] = {"median_f0_hz": _median(f0), "frames": int(mask.sum())}
    if result["median_f0_hz"]:
        result["pitch"] = describe_pitch(float(hz_to_midi(result["median_f0_hz"])))
    good = mask & (features.tracks["formant_conf"] >= 0.3)
    for k in (1, 2, 3):
        result[f"f{k}_hz"] = _median(features.tracks[f"f{k}_hz"][good]) if good.sum() >= 5 else None
    cpps = _median(features.tracks["cpps_db"][mask])
    result.update(
        {
            "cpps_db": cpps,
            "hnr_db": _median(features.tracks["hnr_db"][mask]),
            "h1h2_db": _median(features.tracks["h1h2_db"][mask]),
            "tilt_db_oct": _median(features.tracks["tilt_db_oct"][mask]),
            "breathiness_index": breathiness_index(cpps),
        }
    )
    if step in {"straight", "vibrato"}:
        cents = hz_to_midi(features.tracks["f0_hz"][mask]) * 100.0
        valid = np.isfinite(cents)
        if valid.sum() >= 30:
            cents = np.interp(np.arange(cents.size), np.flatnonzero(valid), cents[valid])
            osc, bp = band_limited_oscillation(cents, HOP_S)
            periodicity, amplitude, _ = local_vibrato(bp, HOP_S)
            present = remove_short_runs(
                (periodicity >= PERIODICITY_MIN) & (amplitude >= EXTENT_MIN_CENTS), 20
            )
            regions = runs(present)
            result["pitch_std_cents"] = float(np.std(cents - np.mean(cents)))
            if regions:
                start, end = max(regions, key=lambda r: r[1] - r[0])
                start = refine_onset(bp, start, end)
                measured = measure_region(osc, bp, start, end, HOP_S)
                result.update(
                    {
                        "vibrato_present": True,
                        "vibrato_rate_hz": measured.get("rate_hz"),
                        "vibrato_extent_cents": measured.get("extent_cents"),
                        "vibrato_regularity": measured.get("regularity"),
                    }
                )
            else:
                result["vibrato_present"] = False
    return result


def start_calibration(name: str, owner_id: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        return calibration_store.create_profile(conn, name or "Calibration", owner_id)


def add_sample(profile_id: str, step: str, source: Path, original_name: str) -> dict[str, Any]:
    if step not in STEP_IDS:
        raise UserFacingError(
            f"Unknown calibration step '{step}'.",
            "The step is not part of the calibration wizard.",
            "Restart the wizard.",
            code="bad_step",
        )
    with get_db().read() as conn:
        profile = calibration_store.get_profile(conn, profile_id)
    if profile is None:
        raise UserFacingError(
            "This calibration no longer exists.",
            "It may have been deleted.",
            "Start a new calibration.",
            code="not_found",
        )
    recording = import_recording(
        None,
        "calibration",
        source,
        original_name,
        name=f"Calibration {step}",
        origin="calibration",
        allow_duplicate=True,
    )
    audio, sr = load_audio(recording["content_hash"])
    quality = recording.get("qc") or {}
    features = load_features(
        recording["content_hash"],
        analysis_options(),
        audio,
        sr,
        float(quality.get("noise_floor_dbfs", -90.0)),
        None,
    )
    results = measure_sample(step, features, quality)
    with get_db().tx() as conn:
        calibration_store.save_sample(conn, profile_id, step, recording["id"], results)
    return {"step": step, "recording_id": recording["id"], "results": results}


def finalize(profile_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        profile = calibration_store.get_profile(conn, profile_id)
    if profile is None:
        raise UserFacingError(
            "This calibration no longer exists.",
            "It may have been deleted.",
            "Start a new calibration.",
            code="not_found",
        )
    samples = {s["step"]: s.get("results") or {} for s in profile.get("samples", [])}
    missing = [s["id"] for s in STEPS if not s["optional"] and s["id"] not in samples]
    vowel_map = {}
    logs = []
    for step in STEPS:
        if step.get("vowel") and step["id"] in samples:
            data = samples[step["id"]]
            if all(data.get(f"f{k}_hz") for k in (1, 2, 3)):
                vowel_map[step["vowel"]] = {k: data[f"{k}_hz"] for k in ("f1", "f2", "f3")}
                logs.append(float(np.mean([math.log(data[f"f{k}_hz"]) for k in (1, 2, 3)])))
    baseline: dict[str, Any] = {}
    if len(logs) >= 3:
        baseline["formant_log_mean"] = float(np.mean(logs))
        baseline["formant_frames"] = 200 * len(logs)
    f0_low = (samples.get("pitch_low") or {}).get("median_f0_hz")
    f0_high = (samples.get("pitch_high") or {}).get("median_f0_hz")
    vib = samples.get("vibrato") or {}
    results = {
        "baseline": baseline,
        "vowel_map": vowel_map,
        "range": {
            "low_hz": f0_low,
            "high_hz": f0_high,
            "semitones": 12 * math.log2(f0_high / f0_low) if f0_low and f0_high else None,
        },
        "vibrato": {
            "rate_hz": vib.get("vibrato_rate_hz"),
            "extent_cents": vib.get("vibrato_extent_cents"),
            "present": vib.get("vibrato_present"),
        },
        "straight_tone": {
            "pitch_std_cents": (samples.get("straight") or {}).get("pitch_std_cents"),
            "vibrato_leak": (samples.get("straight") or {}).get("vibrato_present"),
        },
        "phonation": {
            "breathy": {
                k: (samples.get("breathy") or {}).get(k)
                for k in ("cpps_db", "hnr_db", "h1h2_db", "breathiness_index")
            },
            "modal": {
                k: (samples.get("modal") or {}).get(k)
                for k in ("cpps_db", "hnr_db", "h1h2_db", "breathiness_index")
            },
        },
        "spectral": {"tilt_db_oct": (samples.get("modal") or {}).get("tilt_db_oct")},
        "noise_floor_dbfs": (samples.get("noise") or {}).get("noise_floor_dbfs"),
        "missing_steps": missing,
        "note": "A baseline describes how your voice behaved on the day of calibration. It is not a fixed description of your anatomy; recalibrate when your voice, microphone or room changes.",
    }
    with get_db().tx() as conn:
        return calibration_store.finalize(conn, profile_id, results) or {}


def compare_profiles(ids: list[str]) -> list[dict[str, Any]]:
    with get_db().read() as conn:
        profiles = [calibration_store.get_profile(conn, i) for i in ids]
    out = []
    for profile in profiles:
        if profile is None:
            continue
        results = profile.get("results") or {}
        out.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "finalized_at": profile.get("finalized_at"),
                "vibrato": results.get("vibrato"),
                "range": results.get("range"),
                "phonation": results.get("phonation"),
                "vowel_map": results.get("vowel_map"),
                "noise_floor_dbfs": results.get("noise_floor_dbfs"),
            }
        )
    return out


def delete_calibration(profile_id: str) -> bool:
    with get_db().tx() as conn:
        recordings = [
            s["recording_id"]
            for s in (calibration_store.get_profile(conn, profile_id) or {}).get("samples", [])
        ]
        ok = calibration_store.delete_profile(conn, profile_id)
        for rid in recordings:
            recording_store.delete_recording(conn, rid)
        return ok
