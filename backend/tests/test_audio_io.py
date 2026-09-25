from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from vibrato.audio.canonical import CANONICAL_SR, canonicalize, mixdown
from vibrato.audio.decode import decode_file, validate_duration
from vibrato.audio.errors import AudioDecodeError, AudioValidationError
from vibrato.audio.loudness import integrated_loudness
from vibrato.audio.peaks import build_peak_pyramid, encode_peak_pyramid
from vibrato.audio.quality import analyze_signal_quality

from .conftest import SR, harmonic_tone, pad


def _write(path: Path, x: np.ndarray, sr: int = SR, subtype: str = "PCM_16") -> Path:
    sf.write(str(path), x, sr, subtype=subtype)
    return path


def test_loudness_of_full_scale_sine_matches_bs1770() -> None:
    sr = 48000
    t = np.arange(sr * 5) / sr
    assert integrated_loudness(np.sin(2 * np.pi * 1000 * t), sr) == pytest.approx(-3.01, abs=0.05)


@pytest.mark.parametrize(
    "suffix,subtype",
    [(".wav", "PCM_16"), (".wav", "PCM_24"), (".wav", "FLOAT"), (".flac", "PCM_24"), (".mp3", None)],
)
def test_decodes_common_formats(tmp_path: Path, suffix: str, subtype: str | None) -> None:
    x = pad(harmonic_tone(np.full(SR, 220.0)))
    path = tmp_path / f"tone{suffix}"
    if subtype:
        sf.write(str(path), x, SR, subtype=subtype)
    else:
        sf.write(str(path), x, SR)
    decoded = decode_file(path)
    assert decoded.sample_rate == SR
    assert decoded.channels == 1
    assert decoded.duration_s == pytest.approx(2.0, abs=0.06)
    if suffix == ".mp3":
        assert decoded.lossy and decoded.bit_depth is None
    elif subtype == "PCM_24":
        assert decoded.bit_depth == 24


def test_invalid_and_empty_files_raise_user_facing_errors(tmp_path: Path) -> None:
    garbage = tmp_path / "noise.wav"
    garbage.write_bytes(b"this is not audio" * 100)
    with pytest.raises(AudioDecodeError) as info:
        decode_file(garbage)
    assert info.value.what and info.value.why and info.value.action
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(AudioDecodeError):
        decode_file(empty)
    with pytest.raises(AudioDecodeError):
        decode_file(tmp_path / "missing.wav")


def test_too_short_audio_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "blip.wav", np.zeros(int(0.1 * SR)))
    decoded = decode_file(path)
    with pytest.raises(AudioValidationError):
        validate_duration(decoded, 0.25, 600.0, "blip.wav")


def test_canonicalization_resamples_and_mixes(tmp_path: Path) -> None:
    sr = 22050
    t = np.arange(sr * 2) / sr
    left = 0.3 * np.sin(2 * np.pi * 300 * t)
    stereo = np.stack([left, 0.9 * left], axis=1)
    path = tmp_path / "stereo.wav"
    sf.write(str(path), stereo, sr)
    canonical = canonicalize(decode_file(path))
    assert canonical.sample_rate == CANONICAL_SR
    assert canonical.duration_s == pytest.approx(2.0, abs=0.01)
    anti = np.stack([left, -left])
    mono, mode, notes = mixdown(anti)
    assert "anti-phase" in mode and notes
    assert np.max(np.abs(mono)) == pytest.approx(0.3, abs=0.01)


def test_quality_detects_clipping_silence_and_noise(tmp_path: Path) -> None:
    x = pad(harmonic_tone(np.full(SR * 3, 220.0), level=0.5), before=2.0, after=2.0)
    clipped = x.copy()
    clipped[SR * 3 : SR * 3 + 500] = 1.0
    decoded = decode_file(_write(tmp_path / "clip.wav", clipped))
    report = analyze_signal_quality(decoded, canonicalize(decoded), is_reference=True)
    codes = {i.code for i in report.issues}
    assert "clipping" in codes and report.clipped_samples >= 400
    assert report.factors["phonation"] < 1.0
    assert "bad_reference" in codes
    assert report.leading_silence_s == pytest.approx(2.0, abs=0.15)
    assert report.snr_db > 40
    rng = np.random.default_rng(1)
    noisy = x + 0.02 * rng.standard_normal(x.size)
    decoded = decode_file(_write(tmp_path / "noisy.wav", noisy))
    noisy_report = analyze_signal_quality(decoded, canonicalize(decoded), is_reference=False)
    assert noisy_report.snr_db < report.snr_db - 20
    assert "low_snr" in {i.code for i in noisy_report.issues}


def test_quality_detects_band_limiting_and_dc(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    x = pad(
        harmonic_tone(np.full(SR * 3, 180.0), harmonics=80, rolloff=0.93), before=0.5, after=0.5
    ) + 0.01 * rng.standard_normal(SR * 4)
    sos = signal.butter(12, 7000, fs=SR, output="sos")
    limited = signal.sosfiltfilt(sos, x) + 0.02
    decoded = decode_file(_write(tmp_path / "limited.wav", limited, subtype="FLOAT"))
    report = analyze_signal_quality(decoded, canonicalize(decoded), is_reference=False)
    assert report.bandwidth_limited
    assert report.bandwidth_hz == pytest.approx(7000, rel=0.15)
    assert report.dc_offset == pytest.approx(0.02, abs=0.005)


def test_peak_pyramid_levels_are_consistent() -> None:
    x = np.sin(np.linspace(0, 200, SR * 3)).astype(np.float32) * 0.5
    pyramid = build_peak_pyramid(x, SR)
    assert int(pyramid["levels"]) >= 3
    level0 = pyramid["level_0"]
    assert level0[1::2].max() == pytest.approx(0.5 * 32767, rel=0.01)
    blob = encode_peak_pyramid(pyramid)
    assert len(blob) > 1000
