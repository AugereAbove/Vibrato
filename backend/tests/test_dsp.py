from __future__ import annotations

import numpy as np
import pytest

from vibrato.analysis.analyzers.vibrato import (
    band_limited_oscillation,
    local_vibrato,
    measure_region,
    refine_onset,
)
from vibrato.analysis.features import extract_features
from vibrato.demo.synth import NoteSpec, Performance, PhraseSpec, VoiceSpec, render
from vibrato.dsp.framing import HOP_S, n_frames, runs
from vibrato.dsp.music import describe_pitch, hz_to_midi
from vibrato.dsp.pitch import analyze_pitch, estimator_status

from .conftest import SR, harmonic_tone, pad


@pytest.mark.parametrize("frequency", [110.0, 220.0, 440.0, 880.0])
def test_pitch_recovers_steady_tones(frequency: float) -> None:
    x = pad(harmonic_tone(np.full(SR * 2, frequency)))
    n = n_frames(len(x) / SR)
    result = analyze_pitch(x, SR, n, np.full(n, -20.0), -100.0)
    voiced = result.f0[np.isfinite(result.f0)]
    assert voiced.size > 150
    cents_error = 1200 * np.log2(np.median(voiced) / frequency)
    assert abs(cents_error) < 2.0
    assert np.nanmean(result.agreement) > 0.95


def test_pitch_is_mostly_unvoiced_for_noise() -> None:
    rng = np.random.default_rng(0)
    x = 0.1 * rng.standard_normal(SR * 2)
    n = n_frames(2.0)
    result = analyze_pitch(x, SR, n, np.full(n, -20.0), -100.0)
    assert result.voiced.mean() < 0.2


def test_optional_crepe_reports_missing_model_gracefully() -> None:
    status = estimator_status()["crepe"]
    x = pad(harmonic_tone(np.full(SR, 200.0)))
    n = n_frames(len(x) / SR)
    result = analyze_pitch(x, SR, n, np.full(n, -20.0), -100.0, use_crepe=True)
    if not status["available"]:
        assert "crepe" in result.unavailable
    assert np.isfinite(result.f0).sum() > 50


@pytest.mark.parametrize("rate,extent,onset", [(5.5, 50.0, 0.35), (6.4, 28.0, 0.12), (4.8, 70.0, 0.6)])
def test_vibrato_parameters_are_recovered(rate: float, extent: float, onset: float) -> None:
    t = np.arange(0, 2.2, HOP_S)
    envelope = np.clip((t - onset) / 0.18, 0, 1)
    cents = (
        6200
        + extent * envelope * np.sin(2 * np.pi * rate * np.maximum(t - onset, 0))
        + np.random.default_rng(1).normal(0, 2, t.size)
    )
    osc, bp = band_limited_oscillation(cents, HOP_S)
    periodicity, amplitude, _ = local_vibrato(bp, HOP_S)
    region = max(runs((periodicity >= 0.45) & (amplitude >= 12)), key=lambda r: r[1] - r[0])
    start = refine_onset(bp, region[0], region[1])
    measured = measure_region(osc, bp, start, region[1], HOP_S)
    assert measured["rate_hz"] == pytest.approx(rate, abs=0.3)
    assert measured["extent_cents"] == pytest.approx(extent, rel=0.12)
    assert start * HOP_S == pytest.approx(onset, abs=0.1)


def test_vibrato_tone_through_full_feature_pipeline() -> None:
    t = np.arange(SR * 3) / SR
    f0 = 330 * 2 ** ((50 / 1200) * np.sin(2 * np.pi * 5.5 * t))
    x = pad(harmonic_tone(f0))
    features = extract_features(x, SR, -100.0)
    midi = hz_to_midi(features.tracks["f0_hz"])
    finite = midi[np.isfinite(midi)]
    assert np.percentile(finite, 95) - np.percentile(finite, 5) == pytest.approx(1.0, abs=0.2)
    assert describe_pitch(float(np.median(finite)))["note"] == "E4"


def test_formants_of_synthetic_vowels_at_low_pitch() -> None:
    notes = [
        NoteSpec("ah", (), "AA", (), midi=48, beats=3.0),
        NoteSpec("ee", (), "IY", (), midi=48, beats=3.0),
    ]
    performance = Performance(
        phrases=[PhraseSpec(start_beat=0, notes=notes)],
        voice=VoiceSpec(tract_scale=1.0, breathiness=0.05),
        tempo_bpm=80,
    )
    rendered = render(performance)
    features = extract_features(rendered.audio.astype(np.float64), rendered.sample_rate, -78.0)
    truths = rendered.truth["vowels"]
    for vowel in truths:
        span = features.span(vowel["start"] + 0.3, vowel["end"] - 0.3)
        f1 = np.nanmedian(features.tracks["f1_hz"][span])
        f2 = np.nanmedian(features.tracks["f2_hz"][span])
        assert f1 == pytest.approx(vowel["f1"], rel=0.12)
        assert f2 == pytest.approx(vowel["f2"], rel=0.1)


def test_breathiness_measures_move_monotonically() -> None:
    values = []
    for breathiness in (0.05, 0.3, 0.6):
        performance = Performance(
            phrases=[PhraseSpec(start_beat=0, notes=[NoteSpec("ah", (), "AA", (), midi=57, beats=3.0)])],
            voice=VoiceSpec(breathiness=breathiness),
            tempo_bpm=80,
        )
        rendered = render(performance)
        features = extract_features(rendered.audio.astype(np.float64), rendered.sample_rate, -78.0)
        span = features.span(1.2, 2.4)
        voiced = features.voiced[span]
        values.append(
            (
                np.nanmean(features.tracks["cpps_db"][span][voiced]),
                np.nanmean(features.tracks["hnr_db"][span][voiced]),
                np.nanmean(features.tracks["h1h2_db"][span][voiced]),
            )
        )
    cpps, hnr, h1h2 = zip(*values)
    assert cpps[0] > cpps[1] > cpps[2]
    assert hnr[0] > hnr[1] > hnr[2]
    assert h1h2[0] < h1h2[1] < h1h2[2]


def test_intensity_envelope_follows_known_amplitude() -> None:
    t = np.arange(SR * 3) / SR
    envelope = 10 ** (np.linspace(-12, 0, t.size) / 20)
    x = pad(harmonic_tone(np.full(t.size, 200.0)) * envelope)
    features = extract_features(x, SR, -100.0)
    start = features.tracks["intensity_db"][features.frame(0.8)]
    end = features.tracks["intensity_db"][features.frame(3.2)]
    assert end - start == pytest.approx(12 * (3.2 - 0.8) / 3.0, abs=1.0)


def test_requested_but_missing_crepe_is_reported() -> None:
    if estimator_status()["crepe"]["available"]:
        pytest.skip("CREPE is installed in this environment")
    from vibrato.analysis.pipeline import run_analysis

    x = pad(harmonic_tone(np.full(SR * 2, 220.0)))
    analysis = run_analysis(x, SR, -90.0, options={"use_crepe": True})
    runs = {run["analyzer_id"]: run for run in analysis.runs}
    crepe = runs["pitch_estimator.crepe"]
    assert crepe["status"] == "unavailable"
    assert crepe["validity"] == "MODEL_UNAVAILABLE"
    assert "not installed" in crepe["error"]
    assert runs["pitch"]["status"] == "ok"
