from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import parselmouth
import soxr

from .framing import HOP_S, centered_frames, interpolate_gaps, nan_median_filter, resample_track_to_grid, runs

PITCH_FLOOR_HZ = 55.0
PITCH_CEILING_HZ = 1400.0
ANALYSIS_SR = 24000
AGREE_CENTS = 50.0
OCTAVE_TOLERANCE_CENTS = 90.0
OCTAVE_REPAIR_THRESHOLD_CENTS = 850.0
OCTAVE_REPAIR_WINDOW = 25
MAX_FILL_GAP_FRAMES = 3
MIN_VOICED_RUN_FRAMES = 4
YIN_THRESHOLD = 0.15
YIN_SILENCE_DBFS = -60.0
YIN_CHUNK = 1024
PRAAT_VERSION = "praat-ac-2pass/1"
YIN_VERSION = "yin-vectorized/1"
PYIN_VERSION = "librosa-pyin/1"
CREPE_VERSION = "torchcrepe/1"


@dataclass
class PitchTrack:
    estimator: str
    label: str
    version: str
    f0: np.ndarray
    voicing: np.ndarray


@dataclass
class PitchResult:
    f0: np.ndarray
    confidence: np.ndarray
    voiced: np.ndarray
    agreement: np.ndarray
    octave_conflict: np.ndarray
    octave_repaired: np.ndarray
    tracks: list[PitchTrack]
    floor_hz: float
    ceiling_hz: float
    unavailable: dict[str, str] = field(default_factory=dict)

    @property
    def estimators_used(self) -> list[str]:
        return [t.estimator for t in self.tracks]


def estimator_status() -> dict[str, dict[str, Any]]:
    torch_spec = importlib.util.find_spec("torch")
    crepe_spec = importlib.util.find_spec("torchcrepe")
    cuda = False
    device_name = None
    if torch_spec is not None:
        try:
            import torch

            cuda = bool(torch.cuda.is_available())
            device_name = torch.cuda.get_device_name(0) if cuda else None
        except Exception:
            cuda = False
    return {
        "praat": {
            "available": True,
            "label": "Praat autocorrelation (two-pass)",
            "version": PRAAT_VERSION,
            "default": True,
        },
        "yin": {
            "available": True,
            "label": "YIN (cumulative mean normalised difference)",
            "version": YIN_VERSION,
            "default": True,
        },
        "pyin": {
            "available": True,
            "label": "Probabilistic YIN (librosa)",
            "version": PYIN_VERSION,
            "default": False,
            "note": "Slower; enable for difficult recordings.",
        },
        "crepe": {
            "available": torch_spec is not None and crepe_spec is not None,
            "label": "CREPE neural pitch (torchcrepe)",
            "version": CREPE_VERSION,
            "default": False,
            "device": "cuda" if cuda else "cpu",
            "gpu_name": device_name,
            "install": "pip install torch torchcrepe",
        },
    }


def _to_grid(times: np.ndarray, f0: np.ndarray, voicing: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    with np.errstate(divide="ignore", invalid="ignore"):
        log_f0 = np.where(np.isfinite(f0) & (f0 > 0), np.log(f0), np.nan)
    grid_log = resample_track_to_grid(times, log_f0, n, max_gap_s=HOP_S * 1.01)
    grid_voicing = resample_track_to_grid(times, voicing.astype(np.float64), n, max_gap_s=HOP_S * 1.5)
    return np.exp(grid_log), np.nan_to_num(grid_voicing, nan=0.0)


def _praat_pass(
    snd: parselmouth.Sound, n: int, floor: float, ceiling: float
) -> tuple[np.ndarray, np.ndarray]:
    pitch = snd.to_pitch_ac(
        time_step=HOP_S,
        pitch_floor=floor,
        pitch_ceiling=ceiling,
        very_accurate=False,
        silence_threshold=0.03,
        voicing_threshold=0.45,
        octave_cost=0.01,
        octave_jump_cost=0.35,
        voiced_unvoiced_cost=0.14,
    )
    xs = np.asarray(pitch.xs(), dtype=np.float64)
    selected = pitch.selected_array
    f0 = selected["frequency"].astype(np.float64)
    strength = selected["strength"].astype(np.float64)
    f0[f0 <= 0] = np.nan
    return _to_grid(xs, f0, strength, n)


def praat_track(
    x: np.ndarray, sr: int, n: int, floor: float = PITCH_FLOOR_HZ, ceiling: float = PITCH_CEILING_HZ
) -> tuple[PitchTrack, float, float]:
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    f0, strength = _praat_pass(snd, n, floor, ceiling)
    voiced = f0[np.isfinite(f0)]
    adapted_floor, adapted_ceiling = floor, ceiling
    if voiced.size >= 20:
        low, high = np.percentile(voiced, [5, 95])
        adapted_floor = float(np.clip(low * 0.7, floor, 400.0))
        adapted_ceiling = float(np.clip(high * 1.5, max(adapted_floor * 2.5, 200.0), ceiling))
        f0, strength = _praat_pass(snd, n, adapted_floor, adapted_ceiling)
    voicing = np.clip((strength - 0.35) / 0.5, 0.0, 1.0)
    voicing[~np.isfinite(f0)] = 0.0
    track = PitchTrack("praat", "Praat autocorrelation", PRAAT_VERSION, f0, voicing)
    return track, adapted_floor, adapted_ceiling


def yin_track(
    x24k: np.ndarray, n: int, floor: float, ceiling: float, threshold: float = YIN_THRESHOLD
) -> PitchTrack:
    sr = ANALYSIS_SR
    tau_min = max(2, int(np.floor(sr / ceiling)))
    tau_max = int(np.ceil(sr / floor))
    window = max(tau_max, int(0.025 * sr))
    length = window + tau_max + 1
    hop = round(HOP_S * sr)
    nfft = 1 << int(np.ceil(np.log2(window + length)))
    centers = np.arange(n) * hop
    taus = np.arange(tau_max + 1)
    f0 = np.full(n, np.nan)
    aperiodicity = np.ones(n)
    silence_power = 10.0 ** (YIN_SILENCE_DBFS / 10.0)
    x = x24k.astype(np.float64)
    for start in range(0, n, YIN_CHUNK):
        chunk_centers = centers[start : start + YIN_CHUNK]
        frames = centered_frames(x, chunk_centers, length)
        spectrum_a = np.fft.rfft(frames[:, :window], nfft)
        spectrum_b = np.fft.rfft(frames, nfft)
        cross = np.fft.irfft(np.conj(spectrum_a) * spectrum_b, nfft)[:, : tau_max + 1]
        cumulative = np.concatenate([np.zeros((frames.shape[0], 1)), np.cumsum(frames**2, axis=1)], axis=1)
        e0 = cumulative[:, window] - cumulative[:, 0]
        et = cumulative[:, taus + window] - cumulative[:, taus]
        diff = np.maximum(e0[:, None] + et - 2.0 * cross, 0.0)
        running = np.cumsum(diff[:, 1:], axis=1)
        cmnd = np.ones_like(diff)
        with np.errstate(divide="ignore", invalid="ignore"):
            cmnd[:, 1:] = diff[:, 1:] * taus[1:] / np.maximum(running, 1e-12)
        search = cmnd[:, tau_min : tau_max + 1]
        below = search < threshold
        has_dip = below.any(axis=1)
        first = np.argmax(below, axis=1)
        local_min = np.zeros_like(search, dtype=bool)
        local_min[:, 1:-1] = (search[:, 1:-1] <= search[:, :-2]) & (search[:, 1:-1] <= search[:, 2:])
        local_min[:, -1] = True
        columns = np.arange(search.shape[1])[None, :]
        candidate = local_min & (columns >= first[:, None])
        dip_index = np.argmax(candidate, axis=1)
        global_index = np.argmin(search, axis=1)
        index = np.where(has_dip, dip_index, global_index)
        tau = index + tau_min
        rows = np.arange(search.shape[0])
        left = cmnd[rows, np.clip(tau - 1, 1, tau_max)]
        mid = cmnd[rows, tau]
        right = cmnd[rows, np.clip(tau + 1, 1, tau_max)]
        denominator = left - 2.0 * mid + right
        with np.errstate(divide="ignore", invalid="ignore"):
            shift = np.where(np.abs(denominator) > 1e-12, 0.5 * (left - right) / denominator, 0.0)
        shift = np.clip(shift, -0.5, 0.5)
        refined = tau + shift
        power = e0 / window
        voiced = has_dip & (power > silence_power) & (mid < threshold * 2.0)
        chunk_f0 = np.where(voiced, sr / refined, np.nan)
        f0[start : start + len(chunk_centers)] = chunk_f0
        aperiodicity[start : start + len(chunk_centers)] = np.clip(mid, 0.0, 1.0)
    voicing = np.clip(1.0 - aperiodicity / (threshold * 2.0), 0.0, 1.0)
    voicing[~np.isfinite(f0)] = 0.0
    f0[(f0 < floor * 0.95) | (f0 > ceiling * 1.05)] = np.nan
    return PitchTrack("yin", "YIN", YIN_VERSION, f0, voicing)


def pyin_track(x24k: np.ndarray, n: int, floor: float, ceiling: float) -> PitchTrack:
    import librosa

    hop = round(HOP_S * ANALYSIS_SR)
    f0, voiced_flag, voiced_prob = librosa.pyin(
        x24k.astype(np.float64),
        fmin=floor,
        fmax=ceiling,
        sr=ANALYSIS_SR,
        frame_length=2048,
        hop_length=hop,
        center=True,
    )
    out = np.full(n, np.nan)
    prob = np.zeros(n)
    count = min(n, len(f0))
    out[:count] = np.where(voiced_flag[:count], f0[:count], np.nan)
    prob[:count] = np.nan_to_num(voiced_prob[:count])
    return PitchTrack("pyin", "Probabilistic YIN", PYIN_VERSION, out, prob)


def crepe_track(
    x: np.ndarray, sr: int, n: int, floor: float, ceiling: float, model: str = "tiny"
) -> PitchTrack:
    import torch
    import torchcrepe

    x16 = soxr.resample(x.astype(np.float64), sr, 16000).astype(np.float32)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    audio = torch.from_numpy(x16)[None]
    with torch.no_grad():
        pitch, periodicity = torchcrepe.predict(
            audio,
            16000,
            160,
            floor,
            min(ceiling, 1990.0),
            model,
            batch_size=1024,
            device=device,
            return_periodicity=True,
            pad=True,
        )
        periodicity = torchcrepe.filter.median(periodicity, 3)
    f0 = pitch[0].cpu().numpy().astype(np.float64)
    per = periodicity[0].cpu().numpy().astype(np.float64)
    out = np.full(n, np.nan)
    prob = np.zeros(n)
    count = min(n, len(f0))
    out[:count] = np.where(per[:count] >= 0.21, f0[:count], np.nan)
    prob[:count] = per[:count]
    return PitchTrack("crepe", f"CREPE ({model})", CREPE_VERSION, out, prob)


def _cents(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1200.0 * np.log2(a / b)


def repair_octave_jumps(f0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out = f0.copy()
    repaired = np.zeros(len(f0), dtype=bool)
    valid = np.isfinite(out)
    if valid.sum() < OCTAVE_REPAIR_WINDOW:
        return out, repaired
    cents = _cents(out, np.full_like(out, 10.0))
    reference = nan_median_filter(cents, OCTAVE_REPAIR_WINDOW)
    deviation = cents - reference
    for start, end in runs(np.abs(np.nan_to_num(deviation)) > OCTAVE_REPAIR_THRESHOLD_CENTS):
        if end - start > 12:
            continue
        octaves = np.round(deviation[start:end] / 1200.0)
        out[start:end] = out[start:end] / (2.0**octaves)
        repaired[start:end] = octaves != 0
    return out, repaired


def build_consensus(
    primary: PitchTrack, secondaries: list[PitchTrack], level_db: np.ndarray, noise_floor_db: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(primary.f0)
    f0 = primary.f0.copy()
    base = primary.voicing.copy()
    if secondaries:
        sec = np.stack([s.f0 for s in secondaries])
        sec_voicing = np.stack([s.voicing for s in secondaries])
    else:
        sec = np.full((0, n), np.nan)
        sec_voicing = np.zeros((0, n))
    diffs = _cents(sec, f0[None, :]) if secondaries else np.full((0, n), np.nan)
    agree = np.abs(diffs) <= AGREE_CENTS
    octave = np.abs(np.abs(diffs) - 1200.0) <= OCTAVE_TOLERANCE_CENTS
    sec_voiced = np.isfinite(sec)
    n_sec_voiced = sec_voiced.sum(axis=0)
    n_agree = agree.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        agreement = np.where(n_sec_voiced > 0, n_agree / np.maximum(n_sec_voiced, 1), np.nan)
    primary_voiced = np.isfinite(f0)
    octave_conflict = primary_voiced & octave.any(axis=0) & (n_agree == 0)

    if len(secondaries) >= 2:
        rescue = ~primary_voiced & (n_sec_voiced >= 2) & (sec_voicing.min(axis=0) >= 0.6)
        if rescue.any():
            spread = np.nanmax(sec, axis=0) / np.nanmin(np.where(sec_voiced, sec, np.nan), axis=0)
            rescue &= np.nan_to_num(spread, nan=10.0) < 2 ** (AGREE_CENTS / 1200.0)
            f0[rescue] = np.nanmedian(np.where(sec_voiced, sec, np.nan)[:, rescue], axis=0)
            base[rescue] = sec_voicing.min(axis=0)[rescue] * 0.8

    f0, repaired = repair_octave_jumps(f0)
    resolved = octave_conflict & repaired

    agreement_factor = np.full(n, 0.8)
    if secondaries:
        agreement_factor = np.where(n_sec_voiced == 0, 0.6, agreement_factor)
        agreement_factor = np.where(
            (n_sec_voiced > 0) & (np.nan_to_num(agreement) >= 0.999), 1.0, agreement_factor
        )
        agreement_factor = np.where(
            (n_sec_voiced > 0) & (np.nan_to_num(agreement) > 0) & (np.nan_to_num(agreement) < 0.999),
            0.8,
            agreement_factor,
        )
        agreement_factor = np.where((n_sec_voiced > 0) & (n_agree == 0), 0.3, agreement_factor)
        agreement_factor = np.where(octave_conflict, np.where(resolved, 0.55, 0.3), agreement_factor)
    level_factor = np.clip((level_db - noise_floor_db - 6.0) / 20.0, 0.2, 1.0)
    confidence = np.clip(base * agreement_factor * level_factor, 0.0, 1.0)

    voiced = np.isfinite(f0)
    for start, end in runs(voiced):
        if end - start < MIN_VOICED_RUN_FRAMES:
            f0[start:end] = np.nan
    before_fill = np.isfinite(f0)
    f0 = interpolate_gaps(f0, MAX_FILL_GAP_FRAMES, log_domain=True)
    filled = np.isfinite(f0) & ~before_fill
    if filled.any():
        neighbour = nan_median_filter(np.where(before_fill, confidence, np.nan), 9)
        confidence[filled] = np.nan_to_num(neighbour[filled], nan=0.3) * 0.5
    voiced = np.isfinite(f0)
    confidence[~voiced] = 0.0
    return f0, confidence, voiced, agreement, octave_conflict, repaired


def analyze_pitch(
    x: np.ndarray,
    sr: int,
    n: int,
    level_db: np.ndarray,
    noise_floor_db: float,
    use_pyin: bool = False,
    use_crepe: bool = False,
) -> PitchResult:
    primary, floor, ceiling = praat_track(x, sr, n)
    x24 = soxr.resample(x.astype(np.float64), sr, ANALYSIS_SR)
    secondaries = [yin_track(x24, n, floor, ceiling)]
    unavailable: dict[str, str] = {}
    if use_pyin:
        try:
            secondaries.append(pyin_track(x24, n, floor, ceiling))
        except Exception as exc:
            unavailable["pyin"] = f"pYIN failed: {exc}"
    if use_crepe:
        status = estimator_status()["crepe"]
        if not status["available"]:
            unavailable["crepe"] = "CREPE is not installed (pip install torch torchcrepe)."
        else:
            try:
                secondaries.append(crepe_track(x, sr, n, floor, ceiling))
            except Exception as exc:
                unavailable["crepe"] = f"CREPE failed: {exc}"
    f0, confidence, voiced, agreement, conflict, repaired = build_consensus(
        primary, secondaries, level_db, noise_floor_db
    )
    return PitchResult(
        f0=f0,
        confidence=confidence,
        voiced=voiced,
        agreement=agreement,
        octave_conflict=conflict,
        octave_repaired=repaired,
        tracks=[primary, *secondaries],
        floor_hz=floor,
        ceiling_hz=ceiling,
        unavailable=unavailable,
    )
