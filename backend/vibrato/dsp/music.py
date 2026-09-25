from __future__ import annotations

import math
from typing import Any

import numpy as np

A4_HZ = 440.0
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def hz_to_midi(hz: np.ndarray | float, a4: float = A4_HZ) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 69.0 + 12.0 * np.log2(np.asarray(hz, dtype=np.float64) / a4)


def midi_to_hz(midi: np.ndarray | float, a4: float = A4_HZ) -> np.ndarray:
    return a4 * 2.0 ** ((np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def hz_to_cents(hz: np.ndarray | float, reference_hz: float = 10.0) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1200.0 * np.log2(np.asarray(hz, dtype=np.float64) / reference_hz)


def cents_between(from_hz: float, to_hz: float) -> float:
    return 1200.0 * math.log2(to_hz / from_hz)


def note_name(midi: float) -> str:
    nearest = round(midi)
    return f"{NOTE_NAMES[nearest % 12]}{nearest // 12 - 1}"


def describe_pitch(midi: float) -> dict[str, Any]:
    nearest = round(midi)
    return {
        "midi": round(float(midi), 3),
        "note": note_name(midi),
        "cents_from_note": round((midi - nearest) * 100.0, 1),
        "hz": round(float(midi_to_hz(midi)), 2),
    }
