from __future__ import annotations

import numpy as np
import pytest

from vibrato.alignment.aligner import align
from vibrato.analysis.pipeline import run_analysis
from vibrato.compare.view import RecordingView
from vibrato.demo.songs import DEMO_LYRICS
from vibrato.synthesis.counterfactual import TRANSFORMS, render_counterfactual, world_available


@pytest.fixture(scope="module")
def setup(analyses, rendered):
    ref = RecordingView.from_analysis("ref", analyses["reference"])
    take = RecordingView.from_analysis("take1", analyses["take1"])
    alignment = align(
        analyses["reference"].features,
        analyses["take1"].features,
        analyses["reference"].hierarchy,
        analyses["take1"].hierarchy,
    )
    return ref, take, alignment, rendered["take1"].audio.astype(np.float64)


def _vibrato(analysis):
    return [r for r in analysis.results_for("vibrato", "note") if r.value("present")]


def test_note_centres_fix_the_flat_note(setup) -> None:
    ref, take, alignment, audio = setup
    result = render_counterfactual("note_centers", audio, 44100, ref, take, alignment)
    assert result.audio.size == audio.size
    analysis = run_analysis(result.audio, 44100, -78.0, lyrics=DEMO_LYRICS)
    b3 = [
        r
        for r in analysis.results_for("pitch", "note")
        if r.value("note") == "B3" and (r.number("duration_s") or 0) > 1.0
    ]
    assert b3 and abs(b3[0].number("cents_from_equal_temperament")) < 8


def test_vibrato_transform_moves_rate_to_reference(setup) -> None:
    ref, take, alignment, audio = setup
    result = render_counterfactual("vibrato_all", audio, 44100, ref, take, alignment)
    analysis = run_analysis(result.audio, 44100, -78.0, lyrics=DEMO_LYRICS)
    rates = [r.number("rate_hz") for r in _vibrato(analysis)]
    assert rates and np.median(rates) == pytest.approx(5.5, abs=0.3)


def test_timing_transform_lands_on_reference_timeline(setup) -> None:
    ref, take, alignment, audio = setup
    result = render_counterfactual("timing", audio, 44100, ref, take, alignment)
    assert result.output_timeline == "reference"
    analysis = run_analysis(result.audio, 44100, -78.0, lyrics=DEMO_LYRICS)
    starts = [p.start_s for p in analysis.hierarchy.by_level("phrase")]
    expected = [p.start_s for p in ref.by_level("phrase")]
    assert len(starts) == len(expected)
    assert np.max(np.abs(np.array(starts) - np.array(expected))) < 0.08


def test_dynamics_and_eq_keep_length_and_are_labelled(setup) -> None:
    ref, take, alignment, audio = setup
    for transform in ("dynamics", "spectral_balance"):
        result = render_counterfactual(transform, audio, 44100, ref, take, alignment)
        assert result.audio.size == audio.size
        assert result.approximate
    assert TRANSFORMS["spectral_balance"]["experimental"]


def test_world_transform_reports_missing_dependency(setup) -> None:
    ref, take, alignment, audio = setup
    if world_available():
        result = render_counterfactual("breathiness", audio, 44100, ref, take, alignment)
        assert result.audio.size == audio.size
    else:
        from vibrato.audio.errors import UserFacingError

        with pytest.raises(UserFacingError):
            render_counterfactual("breathiness", audio, 44100, ref, take, alignment)
