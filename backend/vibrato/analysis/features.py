from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..dsp import formants as formant_dsp
from ..dsp import pitch as pitch_dsp
from ..dsp import spectral, voice
from ..dsp.framing import HOP_S, n_frames

FEATURES_VERSION = "features/1"
ProgressFn = Callable[[float, str], None]


@dataclass
class FeatureSet:
    n: int
    duration_s: float
    sample_rate: int
    tracks: dict[str, np.ndarray]
    matrices: dict[str, np.ndarray]
    meta: dict[str, Any] = field(default_factory=dict)
    hop_s: float = HOP_S

    def track(self, name: str) -> np.ndarray:
        return self.tracks[name]

    @property
    def times(self) -> np.ndarray:
        return np.arange(self.n) * self.hop_s

    @property
    def voiced(self) -> np.ndarray:
        return self.tracks["voiced"] > 0.5

    def frame(self, t: float) -> int:
        return int(np.clip(round(t / self.hop_s), 0, self.n - 1))

    def span(self, start_s: float, end_s: float) -> slice:
        a = int(np.clip(np.floor(start_s / self.hop_s), 0, self.n))
        b = int(np.clip(np.ceil(end_s / self.hop_s), a, self.n))
        return slice(a, b)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays: dict[str, np.ndarray] = {f"t__{k}": v.astype(np.float32) for k, v in self.tracks.items()}
        arrays.update({f"m__{k}": v.astype(np.float32) for k, v in self.matrices.items()})
        header = {
            "n": self.n,
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "hop_s": self.hop_s,
            "meta": self.meta,
        }
        arrays["header"] = np.frombuffer(json.dumps(header, default=str).encode("utf-8"), dtype=np.uint8)
        tmp = path.with_name(path.name + ".tmp.npz")
        saver: Callable[..., None] = np.savez_compressed
        saver(tmp, **arrays)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> FeatureSet:
        with np.load(path) as data:
            header = json.loads(bytes(data["header"]).decode("utf-8"))
            tracks = {k[3:]: data[k].astype(np.float64) for k in data.files if k.startswith("t__")}
            matrices = {k[3:]: data[k] for k in data.files if k.startswith("m__")}
        return cls(
            n=int(header["n"]),
            duration_s=float(header["duration_s"]),
            sample_rate=int(header["sample_rate"]),
            tracks=tracks,
            matrices=matrices,
            meta=header.get("meta", {}),
            hop_s=float(header.get("hop_s", HOP_S)),
        )


def _noop(fraction: float, message: str) -> None:
    return None


def extract_features(
    x: np.ndarray,
    sr: int,
    noise_floor_db: float,
    use_pyin: bool = False,
    use_crepe: bool = False,
    progress: ProgressFn = _noop,
    check_cancelled: Callable[[], None] = lambda: None,
) -> FeatureSet:
    duration = len(x) / sr
    n = n_frames(duration)
    progress(0.02, "Measuring intensity")
    intensity = spectral.intensity_db(x, sr, n)
    check_cancelled()
    progress(0.08, "Tracking pitch with multiple estimators")
    pitch = pitch_dsp.analyze_pitch(
        x, sr, n, intensity, noise_floor_db, use_pyin=use_pyin, use_crepe=use_crepe
    )
    check_cancelled()
    voiced_levels = intensity[pitch.voiced]
    active_level = (
        float(np.percentile(voiced_levels, 90))
        if voiced_levels.size >= 10
        else float(np.percentile(intensity, 95))
    )
    level_rel = intensity - active_level
    progress(0.3, "Computing spectral features")
    spec = spectral.compute_spectral(x, sr, n)
    check_cancelled()
    progress(0.45, "Estimating harmonics-to-noise ratio")
    hnr = voice.praat_hnr(x, sr, n, pitch.floor_hz)
    check_cancelled()
    progress(0.52, "Computing cepstral peak prominence")
    cpp_raw, cpps = voice.cpp_track(x, sr, n, pitch.f0)
    check_cancelled()
    progress(0.62, "Measuring harmonic amplitudes")
    harmonics = voice.harmonic_amplitudes(x, sr, pitch.f0)
    check_cancelled()
    progress(0.72, "Tracking formants (two estimators)")
    formants = formant_dsp.analyze_formants(x, sr, n, pitch.voiced, pitch.f0, level_rel)
    check_cancelled()
    tracks: dict[str, np.ndarray] = {
        "f0_hz": pitch.f0,
        "f0_conf": pitch.confidence,
        "voiced": pitch.voiced.astype(np.float64),
        "pitch_agreement": pitch.agreement,
        "octave_conflict": pitch.octave_conflict.astype(np.float64),
        "octave_repaired": pitch.octave_repaired.astype(np.float64),
        "intensity_db": intensity,
        "level_rel_db": level_rel,
        "hnr_db": hnr,
        "cpp_db": cpp_raw,
        "cpps_db": cpps,
        "h1h2_db": harmonics[:, 0] - harmonics[:, 1],
        "h2h4_db": harmonics[:, 1] - harmonics[:, 3],
        "formant_conf": formants.confidence,
        "formant_agreement": formants.agreement,
    }
    for track in pitch.tracks:
        tracks[f"f0_{track.estimator}"] = track.f0
        tracks[f"voicing_{track.estimator}"] = track.voicing
    for k in range(formant_dsp.N_TRACKED):
        tracks[f"f{k + 1}_hz"] = formants.frequencies[:, k]
        tracks[f"b{k + 1}_hz"] = formants.bandwidths[:, k]
        tracks[f"f{k + 1}_lpc_hz"] = formants.lpc_frequencies[:, k]
    tracks.update(spec.tracks)
    matrices = {
        "mfcc": spec.mfcc,
        "band_levels": spec.band_levels,
        "harmonics_db": harmonics.astype(np.float32),
    }
    meta: dict[str, Any] = {
        "features_version": FEATURES_VERSION,
        "noise_floor_db": noise_floor_db,
        "active_level_db": active_level,
        "pitch_floor_hz": pitch.floor_hz,
        "pitch_ceiling_hz": pitch.ceiling_hz,
        "pitch_estimators": [
            {"id": t.estimator, "label": t.label, "version": t.version} for t in pitch.tracks
        ],
        "pitch_unavailable": pitch.unavailable,
        "formant_ceiling_hz": formants.ceiling_hz,
        "formant_ceiling_scores": {str(k): v for k, v in formants.ceiling_scores.items()},
        "formant_high_f0_fraction": formants.high_f0_fraction,
        "formant_estimators": [
            {"id": "praat_burg", "version": formant_dsp.PRAAT_VERSION},
            {"id": "lpc", "version": formant_dsp.LPC_VERSION},
        ],
        "band_centers_hz": [float(c) for c in spec.band_centers],
    }
    progress(0.8, "Features complete")
    return FeatureSet(n=n, duration_s=duration, sample_rate=sr, tracks=tracks, matrices=matrices, meta=meta)
