from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from scipy import signal

SR = 44100
CONTROL_S = 0.001
BLOCK = 256
HARMONIC_LIMIT_HZ = 11000.0

VOWEL_TARGETS: dict[str, tuple[float, float, float, float]] = {
    "IY": (280, 2250, 2950, 3700),
    "IH": (400, 1950, 2550, 3600),
    "EY": (470, 1950, 2550, 3600),
    "EH": (560, 1800, 2500, 3600),
    "AE": (680, 1700, 2450, 3500),
    "AA": (740, 1100, 2450, 3450),
    "AO": (580, 860, 2420, 3400),
    "OH": (500, 880, 2400, 3400),
    "UH": (450, 1030, 2250, 3400),
    "UW": (320, 880, 2250, 3400),
    "AH": (620, 1200, 2400, 3500),
    "ER": (480, 1350, 1700, 3300),
}

DIPHTHONGS: dict[str, tuple[str, str]] = {
    "AY": ("AA", "IH"),
    "OW": ("OH", "UH"),
    "EI": ("EH", "IY"),
    "AW": ("AA", "UH"),
    "OY": ("AO", "IY"),
}

SONORANTS: dict[str, tuple[tuple[float, float, float, float], float, bool]] = {
    "M": ((260, 1100, 2300, 3300), 0.32, True),
    "N": ((260, 1600, 2500, 3400), 0.32, True),
    "NG": ((260, 2000, 2600, 3400), 0.30, True),
    "L": ((360, 1100, 2700, 3500), 0.55, False),
    "R": ((360, 1150, 1650, 3200), 0.6, False),
    "W": ((310, 720, 2250, 3300), 0.55, False),
    "Y": ((290, 2150, 2900, 3600), 0.55, False),
}

FRICATIVES: dict[str, tuple[float, float, float, bool]] = {
    "S": (4800.0, 9500.0, 0.075, False),
    "Z": (4800.0, 9500.0, 0.045, True),
    "SH": (2300.0, 5600.0, 0.075, False),
    "F": (1400.0, 9000.0, 0.022, False),
    "V": (1400.0, 9000.0, 0.016, True),
    "TH": (1500.0, 9000.0, 0.016, False),
    "DH": (1500.0, 9000.0, 0.012, True),
}

STOPS: dict[str, tuple[float, float, float, bool, float]] = {
    "P": (200.0, 1800.0, 0.05, False, 0.045),
    "B": (200.0, 1800.0, 0.03, True, 0.0),
    "T": (3000.0, 8000.0, 0.07, False, 0.05),
    "D": (3000.0, 8000.0, 0.04, True, 0.0),
    "K": (1500.0, 3500.0, 0.06, False, 0.05),
    "G": (1500.0, 3500.0, 0.04, True, 0.0),
}

DEFAULT_CONSONANT_S = {
    "M": 0.08,
    "N": 0.07,
    "NG": 0.08,
    "L": 0.07,
    "R": 0.07,
    "W": 0.06,
    "Y": 0.06,
    "S": 0.11,
    "Z": 0.09,
    "SH": 0.11,
    "F": 0.09,
    "V": 0.07,
    "TH": 0.08,
    "DH": 0.05,
    "H": 0.08,
    "P": 0.09,
    "B": 0.07,
    "T": 0.08,
    "D": 0.06,
    "K": 0.09,
    "G": 0.07,
}

BASE_BANDWIDTHS = (80.0, 100.0, 140.0, 200.0)


@dataclass
class VoiceSpec:
    tract_scale: float = 1.0
    breathiness: float = 0.12
    pressedness: float = 0.0
    jitter: float = 0.0025
    shimmer: float = 0.02
    level_db: float = -14.0
    wander_cents: float = 3.0


@dataclass
class NoteSpec:
    text: str
    onset: tuple[str, ...]
    vowel: str
    coda: tuple[str, ...] = ()
    midi: float = 60.0
    beats: float = 1.0
    word_start: bool = True
    vib_rate: float = 0.0
    vib_extent: float = 0.0
    vib_onset: float = 0.35
    scoop_cents: float = 0.0
    scoop_s: float = 0.12
    overshoot_cents: float = 0.0
    detune_cents: float = 0.0
    level_db: float = 0.0
    crescendo_db: float = 0.0
    f1_mult: float = 1.0
    f2_mult: float = 1.0
    consonant_scale: dict[str, float] = field(default_factory=dict)
    onset_type: str = "balanced"
    breathiness_add: float = 0.0
    hold_scale: float = 1.0
    fry_s: float = 0.0


@dataclass
class PhraseSpec:
    notes: list[NoteSpec]
    start_beat: float
    breath_before: bool = True
    time_shift_s: float = 0.0
    breath_level_db: float = -30.0
    release_fall_cents: float = 0.0


@dataclass
class Performance:
    phrases: list[PhraseSpec]
    voice: VoiceSpec
    tempo_bpm: float = 84.0
    lead_in_s: float = 0.9
    tail_s: float = 0.8
    seed: int = 7
    noise_dbfs: float = -78.0
    reverb_rt: float = 0.0
    tempo_scale: float = 1.0


@dataclass
class Rendered:
    audio: np.ndarray
    sample_rate: int
    truth: dict[str, list[dict[str, Any]]]


def _resonance(freq: np.ndarray, center: np.ndarray, bandwidth: np.ndarray) -> np.ndarray:
    half = bandwidth / 2.0
    numerator = center**2 + half**2
    denominator = np.sqrt((numerator - freq**2) ** 2 + (freq * bandwidth) ** 2)
    return numerator / np.maximum(denominator, 1e-9)


def _tract_response(freq: np.ndarray, formants: np.ndarray, bandwidths: np.ndarray) -> np.ndarray:
    response = np.ones_like(freq)
    for k in range(formants.shape[0]):
        response *= _resonance(freq, formants[k], bandwidths[k])
    return response


class _Timeline:
    def __init__(self, duration: float) -> None:
        self.n = int(np.ceil(duration / CONTROL_S)) + 1
        self.t = np.arange(self.n) * CONTROL_S
        self.f0 = np.full(self.n, np.nan)
        self.voice = np.zeros(self.n)
        self.formants = np.tile(np.array(VOWEL_TARGETS["AH"], dtype=np.float64)[:, None], (1, self.n))
        self.bandwidth_scale = np.ones(self.n)
        self.aspiration = np.zeros(self.n)
        self.nasal = np.zeros(self.n)
        self.breathiness = np.zeros(self.n)
        self.fry = np.zeros(self.n)

    def index(self, t: float) -> int:
        return int(np.clip(round(t / CONTROL_S), 0, self.n - 1))


def _ramp_set(values: np.ndarray, i0: int, i1: int, target: float | np.ndarray, ramp: int) -> None:
    if i1 <= i0:
        return
    values[i0:i1] = target
    if ramp > 0 and i0 > 0:
        start = values[max(0, i0 - 1)]
        span = min(ramp, i1 - i0)
        weights = np.linspace(0.0, 1.0, span, endpoint=False)
        values[i0 : i0 + span] = start + (np.asarray(target) - start) * weights


def _smooth_formants(formants: np.ndarray, width_samples: int) -> np.ndarray:
    kernel = np.hanning(width_samples)
    kernel /= kernel.sum()
    padded = np.pad(formants, ((0, 0), (width_samples, width_samples)), mode="edge")
    out = np.stack([np.convolve(row, kernel, mode="same") for row in padded])
    return out[:, width_samples:-width_samples]


def _vowel_formants(
    symbol: str, scale: float, f1_mult: float, f2_mult: float
) -> tuple[np.ndarray, np.ndarray]:
    if symbol in DIPHTHONGS:
        start, end = DIPHTHONGS[symbol]
        a = np.array(VOWEL_TARGETS[start], dtype=np.float64)
        b = np.array(VOWEL_TARGETS[end], dtype=np.float64)
    else:
        a = np.array(VOWEL_TARGETS[symbol], dtype=np.float64)
        b = a.copy()
    multipliers = np.array([f1_mult, f2_mult, 1.0, 1.0])
    return a * scale * multipliers, b * scale * multipliers


def _consonant_duration(symbol: str, note: NoteSpec) -> float:
    return DEFAULT_CONSONANT_S.get(symbol, 0.07) * note.consonant_scale.get(symbol, 1.0)


def _noise(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.standard_normal(n)


def _bandpass(x: np.ndarray, lo: float, hi: float, order: int = 4) -> np.ndarray:
    hi = min(hi, SR / 2 * 0.95)
    sos = signal.butter(order, [lo, hi], btype="bandpass", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def _envelope(n: int, attack: int, release: int) -> np.ndarray:
    env = np.ones(n)
    attack = min(attack, n // 2)
    release = min(release, n // 2)
    if attack > 0:
        env[:attack] = np.linspace(0.0, 1.0, attack)
    if release > 0:
        env[-release:] = np.linspace(1.0, 0.0, release)
    return env


def render(performance: Performance) -> Rendered:
    rng = np.random.default_rng(performance.seed)
    voice = performance.voice
    beat_s = 60.0 / performance.tempo_bpm * performance.tempo_scale
    last_phrase = performance.phrases[-1]
    total_beats = last_phrase.start_beat + sum(n.beats for n in last_phrase.notes)
    duration = performance.lead_in_s + total_beats * beat_s + performance.tail_s + 1.0
    timeline = _Timeline(duration)
    events: list[tuple[str, float, float, dict[str, Any]]] = []
    truth: dict[str, list[dict[str, Any]]] = {
        "phrases": [],
        "notes": [],
        "consonants": [],
        "breaths": [],
        "words": [],
        "vowels": [],
    }
    scale = voice.tract_scale

    for phrase_index, phrase in enumerate(performance.phrases):
        cursor = performance.lead_in_s + phrase.start_beat * beat_s + phrase.time_shift_s
        phrase_start: float | None = None
        phrase_end = cursor
        previous_voiced_end: float | None = None
        if phrase.breath_before:
            first_onset = sum(_consonant_duration(c, phrase.notes[0]) for c in phrase.notes[0].onset)
            breath_start = cursor - first_onset - 0.58
            events.append(("breath", breath_start, 0.4, {"level_db": phrase.breath_level_db}))
            truth["breaths"].append(
                {"start": breath_start, "end": breath_start + 0.4, "phrase": phrase_index}
            )
        for note_index, note in enumerate(phrase.notes):
            slot = note.beats * beat_s * note.hold_scale
            vowel_start = cursor
            onset_total = sum(_consonant_duration(c, note) for c in note.onset)
            t = vowel_start - onset_total
            if phrase_start is None:
                phrase_start = t
            if note.word_start:
                truth["words"].append({"text": note.text, "start": t, "phrase": phrase_index})
            else:
                truth["words"][-1]["text"] = str(truth["words"][-1]["text"]) + note.text
            vowel_f_start, vowel_f_end = _vowel_formants(note.vowel, scale, note.f1_mult, note.f2_mult)
            for symbol in note.onset:
                d = _consonant_duration(symbol, note)
                _schedule_consonant(timeline, events, symbol, t, d, vowel_f_start, voice, note)
                truth["consonants"].append(
                    {"symbol": symbol, "start": t, "end": t + d, "phrase": phrase_index, "note": note_index}
                )
                t += d
            coda_total = sum(_consonant_duration(c, note) for c in note.coda)
            following = phrase.notes[note_index + 1] if note_index + 1 < len(phrase.notes) else None
            next_onset = sum(_consonant_duration(c, following) for c in following.onset) if following else 0.0
            vowel_end = vowel_start + slot - coda_total - next_onset
            i0 = timeline.index(vowel_start)
            i1 = timeline.index(vowel_end)
            level = 10.0 ** ((voice.level_db + note.level_db) / 20.0)
            ramp = np.linspace(0.0, note.crescendo_db, max(1, i1 - i0))
            amplitude = level * 10.0 ** (ramp / 20.0)
            attack_ms = {"hard": 6, "balanced": 22, "breathy": 60}.get(note.onset_type, 22)
            previous_amp = timeline.voice[i0 - 1] if i0 > 0 else 0.0
            if previous_amp < level * 0.2:
                amplitude[: min(attack_ms, len(amplitude))] *= np.linspace(
                    0.0, 1.0, min(attack_ms, len(amplitude))
                )
            timeline.voice[i0:i1] = amplitude
            weights = np.linspace(0.0, 1.0, max(1, i1 - i0))[None, :]
            timeline.formants[:, i0:i1] = (
                vowel_f_start[:, None] * (1 - weights) + vowel_f_end[:, None] * weights
            )
            if note.vowel in DIPHTHONGS:
                glide = np.clip((weights - 0.55) / 0.35, 0.0, 1.0)
                timeline.formants[:, i0:i1] = (
                    vowel_f_start[:, None] * (1 - glide) + vowel_f_end[:, None] * glide
                )
            timeline.breathiness[i0:i1] = voice.breathiness + note.breathiness_add
            if note.onset_type == "breathy":
                pre = timeline.index(vowel_start - 0.05)
                timeline.aspiration[pre:i0] = np.maximum(timeline.aspiration[pre:i0], level * 0.18)
            if note.fry_s > 0:
                timeline.fry[i0 : timeline.index(vowel_start + note.fry_s)] = 1.0
            _schedule_pitch(
                timeline,
                note,
                vowel_start - onset_total,
                vowel_start,
                vowel_end + coda_total,
                previous_voiced_end,
                rng,
            )
            truth["notes"].append(
                {
                    "text": note.text,
                    "phrase": phrase_index,
                    "start": vowel_start,
                    "end": vowel_end,
                    "midi": note.midi + note.detune_cents / 100.0,
                    "vib_rate": note.vib_rate,
                    "vib_extent": note.vib_extent,
                    "vib_onset": note.vib_onset if note.vib_rate > 0 else None,
                    "scoop_cents": note.scoop_cents,
                }
            )
            truth["vowels"].append(
                {
                    "symbol": note.vowel,
                    "start": vowel_start,
                    "end": vowel_end,
                    "f1": float(vowel_f_start[0]),
                    "f2": float(vowel_f_start[1]),
                }
            )
            t = vowel_end
            for symbol in note.coda:
                d = _consonant_duration(symbol, note)
                _schedule_consonant(timeline, events, symbol, t, d, vowel_f_end, voice, note)
                truth["consonants"].append(
                    {"symbol": symbol, "start": t, "end": t + d, "phrase": phrase_index, "note": note_index}
                )
                t += d
            previous_voiced_end = vowel_end
            cursor = vowel_start + slot
            phrase_end = max(phrase_end, t)
            truth["words"][-1]["end"] = t
        if phrase.release_fall_cents:
            tail = timeline.index(phrase_end - 0.15)
            end = timeline.index(phrase_end)
            fall = np.linspace(0.0, phrase.release_fall_cents, max(1, end - tail))
            timeline.f0[tail:end] *= 2.0 ** (fall / 1200.0)
        truth["phrases"].append({"start": phrase_start, "end": phrase_end, "index": phrase_index})

    timeline.formants = _smooth_formants(timeline.formants, int(0.03 / CONTROL_S))
    audio = _render_voiced(timeline, voice, rng)
    audio += _render_aspiration(timeline, voice, rng)
    for kind, start, dur, params in events:
        _render_event(audio, kind, start, dur, params, voice, rng)
    if performance.reverb_rt > 0:
        audio = _apply_reverb(audio, performance.reverb_rt, rng)
    audio += _noise(rng, len(audio)) * 10.0 ** (performance.noise_dbfs / 20.0)
    peak = np.max(np.abs(audio))
    if peak > 0.98:
        audio *= 0.98 / peak
    return Rendered(audio=audio.astype(np.float32), sample_rate=SR, truth=truth)


def _schedule_consonant(
    timeline: _Timeline,
    events: list[tuple[str, float, float, dict[str, Any]]],
    symbol: str,
    t: float,
    d: float,
    next_formants: np.ndarray,
    voice: VoiceSpec,
    note: NoteSpec,
) -> None:
    i0 = timeline.index(t)
    i1 = timeline.index(t + d)
    level = 10.0 ** ((voice.level_db + note.level_db) / 20.0)
    if symbol in SONORANTS:
        targets, amplitude, nasal = SONORANTS[symbol]
        timeline.voice[i0:i1] = level * amplitude
        timeline.formants[:, i0:i1] = (np.array(targets) * voice.tract_scale)[:, None]
        timeline.nasal[i0:i1] = 1.0 if nasal else 0.0
        timeline.breathiness[i0:i1] = voice.breathiness
        return
    if symbol in FRICATIVES:
        lo, hi, gain, voiced = FRICATIVES[symbol]
        timeline.voice[i0:i1] = level * (0.12 if voiced else 0.0)
        events.append(("fricative", t, d, {"lo": lo, "hi": hi, "gain": gain * level / 0.2}))
        return
    if symbol == "H":
        timeline.voice[i0:i1] = 0.0
        timeline.aspiration[i0:i1] = level * 0.22
        timeline.formants[:, i0:i1] = next_formants[:, None]
        return
    if symbol in STOPS:
        lo, hi, gain, voiced, aspiration = STOPS[symbol]
        closure = d - aspiration
        timeline.voice[i0:i1] = level * (0.04 if voiced else 0.0)
        if voiced:
            timeline.formants[:, i0:i1] = np.array([220.0, 900.0, 2300.0, 3300.0])[:, None]
        burst_t = t + closure - 0.004
        events.append(("burst", burst_t, 0.012, {"lo": lo, "hi": hi, "gain": gain * level / 0.2}))
        if aspiration > 0:
            a0 = timeline.index(t + closure)
            timeline.aspiration[a0:i1] = level * 0.2
            timeline.formants[:, a0:i1] = next_formants[:, None]


def _schedule_pitch(
    timeline: _Timeline,
    note: NoteSpec,
    voiced_start: float,
    vowel_start: float,
    note_end: float,
    previous_end: float | None,
    rng: np.random.Generator,
) -> None:
    i_start = timeline.index(voiced_start)
    i_end = timeline.index(note_end)
    t = timeline.t[i_start:i_end] - vowel_start
    target = note.midi + note.detune_cents / 100.0
    cents = np.zeros_like(t)
    if note.scoop_cents:
        progress = np.clip(t / max(note.scoop_s, 1e-3), 0.0, 1.0)
        shape = 1.0 - (3 * progress**2 - 2 * progress**3)
        cents += note.scoop_cents * shape * (t < note.scoop_s)
        cents += np.where(t < 0, note.scoop_cents, 0.0)
    if note.overshoot_cents:
        bump = np.exp(-(((t - note.scoop_s * 1.1) / 0.05) ** 2))
        cents += note.overshoot_cents * bump
    if note.vib_rate > 0 and note.vib_extent > 0:
        active = t - note.vib_onset
        envelope = np.clip(active / 0.18, 0.0, 1.0)
        phase = 2 * np.pi * note.vib_rate * np.maximum(active, 0.0)
        cents += note.vib_extent * envelope * np.sin(phase)
    midi = target + cents / 100.0
    if (
        previous_end is not None
        and voiced_start - previous_end < 0.02
        and np.isfinite(timeline.f0[max(0, i_start - 1)])
    ):
        glide = int(0.07 / CONTROL_S)
        previous_midi = 69 + 12 * np.log2(timeline.f0[i_start - 1] / 440.0)
        span = min(glide, len(midi))
        weights = np.linspace(0.0, 1.0, span)
        smooth = 3 * weights**2 - 2 * weights**3
        midi[:span] = previous_midi * (1 - smooth) + midi[:span] * smooth
    timeline.f0[i_start:i_end] = 440.0 * 2 ** ((midi - 69) / 12.0)


def _render_voiced(timeline: _Timeline, voice: VoiceSpec, rng: np.random.Generator) -> np.ndarray:
    n_samples = int(timeline.t[-1] * SR)
    sample_t = np.arange(n_samples) / SR
    f0_control = timeline.f0.copy()
    valid = np.isfinite(f0_control)
    if not valid.any():
        return np.zeros(n_samples)
    fill = np.interp(np.arange(len(f0_control)), np.flatnonzero(valid), f0_control[valid])
    wander = signal.sosfiltfilt(
        signal.butter(2, 3.0, fs=1.0 / CONTROL_S, output="sos"), rng.standard_normal(len(fill))
    )
    wander = wander / (np.std(wander) + 1e-9) * voice.wander_cents
    fill = fill * 2 ** (wander / 1200.0)
    jitter = signal.sosfiltfilt(
        signal.butter(2, 60.0, fs=1.0 / CONTROL_S, output="sos"), rng.standard_normal(len(fill))
    )
    jitter = jitter / (np.std(jitter) + 1e-9) * voice.jitter
    fill = fill * (1.0 + jitter)
    f0_samples = np.interp(sample_t, timeline.t, fill)
    fry_samples = np.interp(sample_t, timeline.t, timeline.fry)
    f0_samples = np.where(
        fry_samples > 0.5,
        np.minimum(f0_samples, 70.0 + 10.0 * rng.standard_normal(n_samples).clip(-2, 2)),
        f0_samples,
    )
    phase = 2 * np.pi * np.cumsum(f0_samples) / SR
    voice_amp = np.interp(sample_t, timeline.t, timeline.voice)
    shimmer = signal.sosfiltfilt(signal.butter(2, 40.0, fs=SR, output="sos"), rng.standard_normal(n_samples))
    shimmer = shimmer / (np.std(shimmer) + 1e-9) * voice.shimmer
    voice_amp = voice_amp * (1.0 + shimmer)
    n_blocks = int(np.ceil(n_samples / BLOCK))
    block_t = (np.arange(n_blocks) * BLOCK + BLOCK / 2) / SR
    f0_b = np.interp(block_t, sample_t, f0_samples)
    formants_b = np.stack([np.interp(block_t, timeline.t, row) for row in timeline.formants])
    breath_b = np.interp(block_t, timeline.t, timeline.breathiness)
    nasal_b = np.interp(block_t, timeline.t, timeline.nasal)
    max_k = int(min(160, HARMONIC_LIMIT_HZ / max(60.0, float(np.min(f0_b)))))
    orders = np.arange(1, max_k + 1, dtype=np.float64)[:, None]
    harmonic_f = orders * f0_b[None, :]
    bandwidths = np.array(BASE_BANDWIDTHS)[:, None] * (1.0 + 0.8 * breath_b[None, :] + 0.6 * nasal_b[None, :])
    tilt_db_oct = -12.0 - 7.0 * breath_b + 4.0 * voice.pressedness
    source_db = tilt_db_oct[None, :] * np.log2(orders)
    source_db[0] += 6.0 * breath_b - 3.0 * voice.pressedness
    source = 10.0 ** (source_db / 20.0)
    response = _tract_response(harmonic_f, formants_b, bandwidths)
    radiation = harmonic_f / 200.0
    nasal_filter = 1.0 / (1.0 + (harmonic_f / 900.0) ** 2) ** nasal_b[None, :]
    amplitude = source * response * radiation * nasal_filter
    amplitude[harmonic_f > HARMONIC_LIMIT_HZ] = 0.0
    norm = np.sqrt(np.sum(amplitude**2, axis=0, keepdims=True)) + 1e-12
    amplitude = amplitude / norm
    out = np.zeros(n_samples)
    chunk = 22050
    block_positions = np.arange(n_blocks) * BLOCK + BLOCK / 2
    for start in range(0, n_samples, chunk):
        stop = min(n_samples, start + chunk)
        positions = np.arange(start, stop)
        interp = np.stack([np.interp(positions, block_positions, row) for row in amplitude])
        out[start:stop] = np.sum(interp * np.sin(orders * phase[None, start:stop]), axis=0)
    return out * voice_amp * 1.2


def _render_aspiration(timeline: _Timeline, voice: VoiceSpec, rng: np.random.Generator) -> np.ndarray:
    n_samples = int(timeline.t[-1] * SR)
    sample_t = np.arange(n_samples) / SR
    breath_level = np.interp(sample_t, timeline.t, timeline.breathiness * timeline.voice * 0.35)
    explicit = np.interp(sample_t, timeline.t, timeline.aspiration)
    level = breath_level + explicit
    if not np.any(level > 0):
        return np.zeros(n_samples)
    noise = _noise(rng, n_samples)
    f0 = np.interp(sample_t, timeline.t, np.nan_to_num(timeline.f0, nan=150.0))
    phase = 2 * np.pi * np.cumsum(f0) / SR
    pulsed = noise * (0.55 + 0.45 * np.cos(phase))
    freqs, frames, spec = signal.stft(pulsed, fs=SR, nperseg=1024, noverlap=768)
    frame_t = frames
    formants = np.stack([np.interp(frame_t, timeline.t, row) for row in timeline.formants])
    bandwidths = np.array(BASE_BANDWIDTHS)[:, None] * 1.8 * np.ones((1, len(frame_t)))
    response = np.stack(
        [
            _tract_response(
                freqs,
                formants[:, j : j + 1].repeat(len(freqs), axis=1),
                bandwidths[:, j : j + 1].repeat(len(freqs), axis=1),
            )
            for j in range(len(frame_t))
        ],
        axis=1,
    )
    tilt = 1.0 / (1.0 + (freqs / 3500.0) ** 2)
    shaped = spec * response * tilt[:, None] * (freqs[:, None] > 300)
    _, shaped_time = signal.istft(shaped, fs=SR, nperseg=1024, noverlap=768)
    shaped_time = shaped_time[:n_samples]
    if len(shaped_time) < n_samples:
        shaped_time = np.pad(shaped_time, (0, n_samples - len(shaped_time)))
    shaped_time /= np.std(shaped_time) + 1e-12
    return shaped_time * level * 0.5


def _render_event(
    audio: np.ndarray,
    kind: str,
    start: float,
    duration: float,
    params: dict[str, Any],
    voice: VoiceSpec,
    rng: np.random.Generator,
) -> None:
    i0 = int(max(0, start * SR))
    n = int(duration * SR)
    if n <= 8 or i0 >= len(audio):
        return
    n = min(n, len(audio) - i0)
    if kind == "breath":
        level = 10.0 ** ((voice.level_db + float(params["level_db"])) / 20.0)
        noise = _bandpass(_noise(rng, n + 2048), 350.0, 4200.0, order=2)[2048:]
        noise /= np.std(noise) + 1e-12
        env = _envelope(n, int(0.12 * SR), int(0.1 * SR))
        audio[i0 : i0 + n] += noise * env * level
    elif kind == "fricative":
        noise = _bandpass(_noise(rng, n + 2048), float(params["lo"]), float(params["hi"]))[2048:]
        noise /= np.std(noise) + 1e-12
        env = _envelope(n, int(0.015 * SR), int(0.015 * SR))
        audio[i0 : i0 + n] += noise * env * float(params["gain"])
    elif kind == "burst":
        noise = _bandpass(_noise(rng, n + 2048), float(params["lo"]), float(params["hi"]), order=2)[2048:]
        noise /= np.std(noise) + 1e-12
        env = np.exp(-np.arange(n) / (0.004 * SR))
        env[: int(0.0008 * SR)] *= np.linspace(0.0, 1.0, int(0.0008 * SR))
        audio[i0 : i0 + n] += noise * env * float(params["gain"]) * 1.5


def _apply_reverb(audio: np.ndarray, rt60: float, rng: np.random.Generator) -> np.ndarray:
    length = int(rt60 * 1.2 * SR)
    t = np.arange(length) / SR
    ir = rng.standard_normal(length) * 10.0 ** (-3.0 * t / rt60)
    ir = signal.sosfilt(signal.butter(2, 6000, fs=SR, output="sos"), ir)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir**2))
    wet = signal.fftconvolve(audio, ir)[: len(audio)]
    return 0.6 * audio + 0.8 * wet


def with_voice(performance: Performance, **changes: Any) -> Performance:
    return replace(performance, voice=replace(performance.voice, **changes))
