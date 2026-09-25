from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from ...dsp.framing import runs
from ...dsp.music import hz_to_midi
from ..features import FeatureSet
from .phrases import PhraseSpan

CHANGE_WINDOW = 15
MIN_EDGE_WINDOW = 5
CHANGE_THRESHOLD_ST = 0.5
MIN_BOUNDARY_SPACING = 8
MIN_NOTE_FRAMES = 8
MERGE_THRESHOLD_ST = 0.4
TREND_CUTOFF_HZ = 2.5
CORE_TOLERANCE_ST = 0.4
CORE_MAX_VELOCITY_ST_S = 4.0
MIN_CORE_FRAMES = 3
SHORT_NOTE_FRAMES = 35
PLATEAU_BIN_CENTS = 20.0


@dataclass
class NoteSpan:
    start: int
    end: int
    core_start: int
    core_end: int
    center_midi: float
    confidence: float
    phrase_index: int


def pitch_trend(midi: np.ndarray, hop_s: float) -> np.ndarray:
    if midi.size < 15:
        return np.full(midi.size, float(np.median(midi)))
    sos = signal.butter(2, TREND_CUTOFF_HZ, fs=1.0 / hop_s, output="sos")
    padlen = min(midi.size - 1, 3 * 7)
    return signal.sosfiltfilt(sos, midi, padlen=padlen)


def change_curve(midi: np.ndarray, window: int = CHANGE_WINDOW) -> np.ndarray:
    n = midi.size
    cumulative = np.concatenate([[0.0], np.cumsum(midi)])
    out = np.zeros(n)
    for i in range(1, n):
        left = max(0, i - window)
        right = min(n, i + window)
        if i - left < MIN_EDGE_WINDOW or right - i < MIN_EDGE_WINDOW:
            continue
        mean_left = (cumulative[i] - cumulative[left]) / (i - left)
        mean_right = (cumulative[right] - cumulative[i]) / (right - i)
        out[i] = abs(mean_right - mean_left)
    return out


def _pick_boundaries(curve: np.ndarray) -> list[int]:
    peaks, _ = signal.find_peaks(curve, height=CHANGE_THRESHOLD_ST, distance=MIN_BOUNDARY_SPACING)
    return [int(p) for p in peaks]


def plateau_core(midi: np.ndarray) -> tuple[int, int]:
    cents = midi * 100.0
    bins = np.arange(np.floor(cents.min()), np.ceil(cents.max()) + PLATEAU_BIN_CENTS, PLATEAU_BIN_CENTS)
    if bins.size < 2:
        return 0, midi.size
    counts, edges = np.histogram(cents, bins=bins)
    peak = int(np.argmax(counts))
    center = 0.5 * (edges[peak] + edges[peak + 1])
    near = np.abs(cents - center) <= PLATEAU_BIN_CENTS
    blocks = runs(near)
    if not blocks:
        return 0, midi.size
    start, end = max(blocks, key=lambda b: b[1] - b[0])
    return start, end


def _core(trend: np.ndarray, hop_s: float = 0.01) -> tuple[int, int]:
    reference = float(np.median(trend))
    velocity = np.abs(np.gradient(trend)) / hop_s if trend.size > 2 else np.zeros_like(trend)
    stable = (np.abs(trend - reference) < CORE_TOLERANCE_ST) & (velocity < CORE_MAX_VELOCITY_ST_S)
    if stable.sum() < MIN_CORE_FRAMES:
        stable = np.abs(trend - reference) < CORE_TOLERANCE_ST
    blocks = runs(stable)
    if not blocks:
        return 0, trend.size
    start, end = max(blocks, key=lambda b: b[1] - b[0])
    return start, end


def _absorb_short_pieces(pieces: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result = list(pieces)
    changed = True
    while changed and len(result) > 1:
        changed = False
        for index, (start, end) in enumerate(result):
            if end - start >= MIN_NOTE_FRAMES:
                continue
            if index + 1 < len(result):
                result[index + 1] = (start, result[index + 1][1])
            else:
                result[index - 1] = (result[index - 1][0], end)
            del result[index]
            changed = True
            break
    return [piece for piece in result if piece[1] - piece[0] >= MIN_NOTE_FRAMES]


def segment_notes(
    fs: FeatureSet, phrases: list[PhraseSpan], syllable_boundaries: list[int]
) -> list[NoteSpan]:
    f0 = fs.tracks["f0_hz"]
    confidence = fs.tracks["f0_conf"]
    boundary_set = np.array(sorted(syllable_boundaries), dtype=int)
    notes: list[NoteSpan] = []
    for phrase_index, phrase in enumerate(phrases):
        voiced = np.isfinite(f0[phrase.start : phrase.end])
        for run_start, run_end in runs(voiced):
            a = phrase.start + run_start
            b = phrase.start + run_end
            if b - a < MIN_NOTE_FRAMES:
                continue
            midi = hz_to_midi(f0[a:b])
            cuts = [a + c for c in _pick_boundaries(change_curve(midi))]
            inner = boundary_set[(boundary_set > a + MIN_NOTE_FRAMES) & (boundary_set < b - MIN_NOTE_FRAMES)]
            for boundary in inner:
                if all(abs(int(boundary) - c) >= MIN_NOTE_FRAMES for c in cuts):
                    cuts.append(int(boundary))
            cuts = sorted(cuts)
            edges = [a, *cuts, b]
            pieces = _absorb_short_pieces([(edges[i], edges[i + 1]) for i in range(len(edges) - 1)])
            merged: list[tuple[int, int]] = []
            for piece in pieces:
                if merged:
                    previous_center = float(np.median(hz_to_midi(f0[merged[-1][0] : merged[-1][1]])))
                    current_center = float(np.median(hz_to_midi(f0[piece[0] : piece[1]])))
                    separated = any(merged[-1][1] - 2 <= int(bd) <= piece[0] + 2 for bd in boundary_set)
                    if abs(previous_center - current_center) < MERGE_THRESHOLD_ST and not separated:
                        merged[-1] = (merged[-1][0], piece[1])
                        continue
                merged.append(piece)
            for start, end in merged:
                segment_midi = hz_to_midi(f0[start:end])
                trend = pitch_trend(segment_midi, fs.hop_s)
                if end - start < SHORT_NOTE_FRAMES:
                    core_start, core_end = plateau_core(segment_midi)
                else:
                    core_start, core_end = _core(trend, fs.hop_s)
                core_slice = segment_midi[core_start:core_end]
                center = float(np.mean(core_slice)) if core_slice.size else float(np.median(segment_midi))
                coverage = (core_end - core_start) / max(1, end - start)
                conf = float(np.mean(confidence[start:end])) * (0.5 + 0.5 * coverage)
                notes.append(
                    NoteSpan(
                        start=start,
                        end=end,
                        core_start=start + core_start,
                        core_end=start + core_end,
                        center_midi=center,
                        confidence=round(conf, 3),
                        phrase_index=phrase_index,
                    )
                )
    return notes
