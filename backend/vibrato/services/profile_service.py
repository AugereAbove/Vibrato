from __future__ import annotations

from typing import Any

import numpy as np

from ..db import get_db
from ..store import calibration as calibration_store
from ..store import recordings as recording_store
from .analysis_service import load_view

TRAIT_TOLERANCE = {
    "vibrato_rate_hz": 0.35,
    "vibrato_extent_cents": 12.0,
    "vibrato_onset_s": 0.12,
    "scoop_fraction": 0.2,
    "scoop_extent_cents": 40.0,
    "breaths_per_minute": 3.0,
    "breath_duration_ms": 120.0,
    "breathiness_index": 12.0,
    "h1h2_db": 4.0,
    "consonant_ms": 30.0,
    "dynamic_range_db": 4.0,
    "hard_onset_fraction": 0.25,
}
TRAIT_LABELS = {
    "vibrato_rate_hz": ("Vibrato rate", "Hz"),
    "vibrato_extent_cents": ("Vibrato width", "cents (±)"),
    "vibrato_onset_s": ("Straight tone before vibrato", "s"),
    "scoop_fraction": ("Share of notes scooped", "ratio"),
    "scoop_extent_cents": ("Typical scoop depth", "cents"),
    "breaths_per_minute": ("Breaths per minute", "per min"),
    "breath_duration_ms": ("Inhale length", "ms"),
    "breathiness_index": ("Breathiness", "0-100"),
    "h1h2_db": ("H1-H2", "dB"),
    "consonant_ms": ("Consonant length", "ms"),
    "dynamic_range_db": ("Dynamic range", "dB"),
    "hard_onset_fraction": ("Hard onsets", "ratio"),
}


def _median(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.median(clean)) if clean else None


def recording_traits(recording_id: str) -> dict[str, float | None]:
    view, _ = load_view(recording_id)
    vibrato = [r for r in view.results_for("vibrato", "note") if r.value("present")]
    pitch = [r for r in view.results_for("pitch", "note") if r.value("attack_type") != "legato"]
    scooped = [r for r in pitch if r.value("scoop") in {"up", "down"}]
    breaths = view.events_of("breath")
    quality = view.results_for("voice_quality", "note")
    consonants = [
        r.number("duration_ms")
        for r in view.results_for("articulation", "event")
        if r.value("kind") not in (None, "onset")
    ]
    onsets = [r for r in view.results_for("articulation", "event") if r.value("kind") == "onset"]
    dynamics = next((r for r in view.results_for("dynamics") if r.segment_id is None), None)
    minutes = max(view.features.duration_s / 60.0, 1e-6)
    return {
        "vibrato_rate_hz": _median([r.number("rate_hz") for r in vibrato]),
        "vibrato_extent_cents": _median([r.number("extent_cents") for r in vibrato]),
        "vibrato_onset_s": _median([r.number("onset_s") for r in vibrato]),
        "scoop_fraction": len(scooped) / len(pitch) if pitch else None,
        "scoop_extent_cents": _median([r.number("scoop_extent_cents") for r in scooped]),
        "breaths_per_minute": len(breaths) / minutes,
        "breath_duration_ms": _median([(e.end_s - e.start_s) * 1000.0 for e in breaths]),
        "breathiness_index": _median([r.number("breathiness_index") for r in quality]),
        "h1h2_db": _median([r.number("h1h2_db") for r in quality]),
        "consonant_ms": _median(consonants),
        "dynamic_range_db": dynamics.number("dynamic_range_db") if dynamics else None,
        "hard_onset_fraction": (sum(1 for r in onsets if r.value("onset_type") == "hard") / len(onsets))
        if onsets
        else None,
    }


def aggregate_profile(profile_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        profile = calibration_store.get_reference_profile(conn, profile_id)
        recording_ids = calibration_store.profile_recordings(conn, profile_id)
        recordings = [recording_store.get_recording(conn, rid) for rid in recording_ids]
    included = [r for r in recordings if r and not r.get("excluded_from_profile")]
    per_recording = {r["id"]: recording_traits(r["id"]) for r in included}
    n = len(per_recording)
    confidence = {0: 0.0, 1: 0.4, 2: 0.6, 3: 0.75}.get(n, 0.85)
    traits: list[dict[str, Any]] = []
    for key, (label, unit) in TRAIT_LABELS.items():
        values = [float(v) for v in (t.get(key) for t in per_recording.values()) if v is not None]
        if not values:
            traits.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "median": None,
                    "spread": None,
                    "consistency": "unknown",
                    "n": 0,
                }
            )
            continue
        spread = float(np.max(values) - np.min(values)) if len(values) >= 2 else None
        if len(values) < 2:
            consistency = "single recording"
        elif spread is not None and spread <= TRAIT_TOLERANCE[key]:
            consistency = "consistent"
        else:
            consistency = "varies between recordings"
        traits.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "median": round(float(np.median(values)), 3),
                "spread": None if spread is None else round(spread, 3),
                "range": [round(min(values), 3), round(max(values), 3)],
                "consistency": consistency,
                "n": len(values),
            }
        )
    return {
        "profile": profile,
        "recordings": [
            {
                "id": r["id"],
                "name": r["name"],
                "excluded": bool(r.get("excluded_from_profile")),
                "project_id": r.get("project_id"),
                "duration_s": r.get("duration_s"),
                "quality": (r.get("qc") or {}).get("overall_quality"),
            }
            for r in recordings
            if r
        ],
        "traits": traits,
        "per_recording": per_recording,
        "confidence": confidence,
        "note": "Traits marked 'consistent' recur across this singer's recordings; 'varies' means the trait is probably song-specific. More recordings give a more reliable profile.",
    }
