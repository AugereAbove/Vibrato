from __future__ import annotations

from typing import Any

from ..compare.metrics import CATEGORIES, DEFAULT_CATEGORY_WEIGHTS
from ..db import get_db
from ..store.misc import clear_preferences, get_preferences, set_preferences

DEFAULTS: dict[str, Any] = {
    "audio.input_device": None,
    "audio.output_device": None,
    "audio.latency_ms": 0.0,
    "audio.latency_calibrated": False,
    "audio.preroll_s": 3,
    "audio.metronome": False,
    "audio.metronome_bpm": 84,
    "audio.reference_during_recording": True,
    "audio.reference_level": 0.8,
    "audio.monitor_level": 0.0,
    "audio.gain_match": True,
    "audio.loop_recording": False,
    "analysis.use_pyin": False,
    "analysis.use_crepe": False,
    "analysis.disabled_analyzers": [],
    "analysis.a4_hz": 440.0,
    "analysis.phrase_gap_s": 0.25,
    "models.crepe_model": "tiny",
    "display.theme": "system",
    "display.view_mode": "coach",
    "display.reduced_motion": "system",
    "display.spectrogram_resolution": "medium",
    "display.spectrogram_max_hz": 8000,
    "display.show_note_names": True,
    "display.pitch_display": "cents",
    "display.language_level": "coach",
    "training.auto_loop": True,
    "training.slow_factor": 0.75,
    "training.alternate_ab": False,
    "training.min_takes_before_move_on": 3,
    "training.mastery_threshold": 85,
    "storage.autosave": True,
    "storage.keep_backups": 7,
    "performance.max_workers": 2,
    "performance.progressive_analysis": True,
    "privacy.telemetry": False,
    "privacy.cloud_features": False,
    "advanced.debug_panel": False,
    "advanced.deterministic_mode": False,
    **{f"scoring.enabled.{c}": True for c in CATEGORIES},
    **{f"scoring.weight.{c}": DEFAULT_CATEGORY_WEIGHTS[c] for c in CATEGORIES},
}

SCHEMA: list[dict[str, Any]] = [
    {
        "key": "audio.latency_ms",
        "section": "Audio",
        "label": "Recording latency compensation (ms)",
        "type": "number",
        "min": 0,
        "max": 1000,
        "help": "Round-trip delay removed from takes recorded along with the reference. Use the latency calibration tool to measure it.",
    },
    {
        "key": "audio.preroll_s",
        "section": "Audio",
        "label": "Pre-roll countdown (s)",
        "type": "number",
        "min": 0,
        "max": 10,
        "help": "Countdown before recording starts.",
    },
    {
        "key": "audio.metronome",
        "section": "Audio",
        "label": "Metronome during count-in",
        "type": "boolean",
        "help": "Plays clicks during the pre-roll.",
    },
    {
        "key": "audio.metronome_bpm",
        "section": "Audio",
        "label": "Metronome tempo (BPM)",
        "type": "number",
        "min": 30,
        "max": 240,
        "help": "Click tempo.",
    },
    {
        "key": "audio.reference_during_recording",
        "section": "Audio",
        "label": "Play reference while recording",
        "type": "boolean",
        "help": "Use headphones to avoid the reference leaking into your take.",
    },
    {
        "key": "audio.reference_level",
        "section": "Audio",
        "label": "Reference level while recording",
        "type": "slider",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "help": "Volume of the reference in your headphones.",
    },
    {
        "key": "audio.monitor_level",
        "section": "Audio",
        "label": "Hear yourself (monitoring)",
        "type": "slider",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "help": "Routes the microphone to your headphones. Keep at 0 with speakers to avoid feedback.",
    },
    {
        "key": "audio.gain_match",
        "section": "Audio",
        "label": "Gain-match A/B playback",
        "type": "boolean",
        "help": "Plays reference and take at the same loudness so louder does not sound better.",
    },
    {
        "key": "audio.loop_recording",
        "section": "Audio",
        "label": "Loop recording",
        "type": "boolean",
        "help": "Keeps recording new takes each time the loop repeats.",
    },
    {
        "key": "analysis.use_pyin",
        "section": "Analysis",
        "label": "Add probabilistic YIN pitch estimator",
        "type": "boolean",
        "help": "A third, slower pitch estimator for difficult recordings (about 0.4 s per second of audio).",
    },
    {
        "key": "analysis.a4_hz",
        "section": "Analysis",
        "label": "Tuning reference A4 (Hz)",
        "type": "number",
        "min": 400,
        "max": 480,
        "help": "Used only to name notes.",
    },
    {
        "key": "analysis.disabled_analyzers",
        "section": "Analysis",
        "label": "Disabled analyzers",
        "type": "multiselect",
        "options": ["register", "nonlinear", "phonation", "timbre"],
        "help": "Experimental analyzers can be switched off.",
    },
    {
        "key": "analysis.use_crepe",
        "section": "Models",
        "label": "Use CREPE neural pitch (if installed)",
        "type": "boolean",
        "help": "Adds the CREPE model as a pitch estimator; uses the GPU when available.",
    },
    {
        "key": "models.crepe_model",
        "section": "Models",
        "label": "CREPE model size",
        "type": "select",
        "options": ["tiny", "full"],
        "help": "'full' is more accurate and much slower on CPU.",
    },
    {
        "key": "display.theme",
        "section": "Display",
        "label": "Theme",
        "type": "select",
        "options": ["system", "dark", "light"],
        "help": "Dark mode is the default workstation look.",
    },
    {
        "key": "display.view_mode",
        "section": "Display",
        "label": "Detail level",
        "type": "select",
        "options": ["coach", "analyst", "research"],
        "help": "Coach shows what to change; Analyst adds measurements; Research shows raw data and model details.",
    },
    {
        "key": "display.reduced_motion",
        "section": "Display",
        "label": "Reduce motion",
        "type": "select",
        "options": ["system", "on", "off"],
        "help": "Follows your operating system setting by default.",
    },
    {
        "key": "display.spectrogram_resolution",
        "section": "Display",
        "label": "Spectrogram resolution",
        "type": "select",
        "options": ["low", "medium", "high"],
        "help": "Higher resolution uses more memory.",
    },
    {
        "key": "display.spectrogram_max_hz",
        "section": "Display",
        "label": "Spectrogram top frequency (Hz)",
        "type": "number",
        "min": 2000,
        "max": 16000,
        "help": "Highest frequency shown.",
    },
    {
        "key": "display.show_note_names",
        "section": "Display",
        "label": "Show note names",
        "type": "boolean",
        "help": "Labels on the piano-roll background.",
    },
    {
        "key": "training.auto_loop",
        "section": "Training",
        "label": "Loop the practice region automatically",
        "type": "boolean",
        "help": "When you pick a focus, playback loops it.",
    },
    {
        "key": "training.slow_factor",
        "section": "Training",
        "label": "Slow reference speed",
        "type": "slider",
        "min": 0.5,
        "max": 1.0,
        "step": 0.05,
        "help": "Speed of the slowed (pitch-preserving) reference.",
    },
    {
        "key": "training.alternate_ab",
        "section": "Training",
        "label": "Alternate reference and take on each loop",
        "type": "boolean",
        "help": "Switches A/B automatically every repetition.",
    },
    {
        "key": "training.mastery_threshold",
        "section": "Training",
        "label": "Mastery threshold (score)",
        "type": "number",
        "min": 50,
        "max": 100,
        "help": "Score at which a phrase counts as mastered.",
    },
    {
        "key": "training.min_takes_before_move_on",
        "section": "Training",
        "label": "Takes before suggesting to move on",
        "type": "number",
        "min": 1,
        "max": 10,
        "help": "Minimum attempts at mastery level before Vibrato suggests the next target.",
    },
    {
        "key": "storage.autosave",
        "section": "Storage",
        "label": "Autosave",
        "type": "boolean",
        "help": "Every change is written immediately; this cannot be switched off for recordings.",
    },
    {
        "key": "storage.keep_backups",
        "section": "Storage",
        "label": "Automatic database backups to keep",
        "type": "number",
        "min": 1,
        "max": 30,
        "help": "Backups are taken at startup.",
    },
    {
        "key": "performance.max_workers",
        "section": "Performance",
        "label": "Background analysis workers",
        "type": "number",
        "min": 1,
        "max": 8,
        "help": "Takes effect after restart.",
    },
    {
        "key": "performance.progressive_analysis",
        "section": "Performance",
        "label": "Show quick overview first",
        "type": "boolean",
        "help": "Waveform and QC appear before the full analysis finishes.",
    },
    {
        "key": "privacy.telemetry",
        "section": "Privacy",
        "label": "Telemetry",
        "type": "boolean",
        "help": "Vibrato never sends telemetry; this switch is permanently off.",
        "locked": True,
    },
    {
        "key": "privacy.cloud_features",
        "section": "Privacy",
        "label": "Cloud features",
        "type": "boolean",
        "help": "No cloud features exist. All processing is local.",
        "locked": True,
    },
    {
        "key": "advanced.debug_panel",
        "section": "Advanced",
        "label": "Show developer panel",
        "type": "boolean",
        "help": "Adds raw analyzer output and diagnostics to the inspector.",
    },
    {
        "key": "advanced.deterministic_mode",
        "section": "Advanced",
        "label": "Deterministic mode",
        "type": "boolean",
        "help": "Fixes random seeds used by alignment confidence sampling.",
    },
    *[
        {
            "key": f"scoring.enabled.{c}",
            "section": "Analysis",
            "label": f"Include {c} in the overall score",
            "type": "boolean",
            "help": "Disabled categories are still analysed and shown.",
        }
        for c in CATEGORIES
    ],
    *[
        {
            "key": f"scoring.weight.{c}",
            "section": "Analysis",
            "label": f"{c.title()} weight in the overall score",
            "type": "slider",
            "min": 0,
            "max": 2,
            "step": 0.1,
            "help": "Relative weight of this category in the convenience score.",
        }
        for c in CATEGORIES
    ],
]


def all_preferences(owner_id: str) -> dict[str, Any]:
    with get_db().read() as conn:
        stored = get_preferences(conn, owner_id)
    return {**DEFAULTS, **stored}


def update_preferences(owner_id: str, values: dict[str, Any]) -> dict[str, Any]:
    clean = {
        k: v
        for k, v in values.items()
        if k in DEFAULTS and k not in {"privacy.telemetry", "privacy.cloud_features"}
    }
    with get_db().tx() as conn:
        set_preferences(conn, owner_id, clean)
    return all_preferences(owner_id)


def reset_preferences(owner_id: str, section: str | None = None) -> dict[str, Any]:
    with get_db().tx() as conn:
        if section is None:
            clear_preferences(conn, owner_id)
        else:
            keys = [item["key"] for item in SCHEMA if item["section"].lower() == section.lower()]
            set_preferences(conn, owner_id, dict.fromkeys(keys))
    return all_preferences(owner_id)
