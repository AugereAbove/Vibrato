from __future__ import annotations

import numpy as np
import pytest

from vibrato.alignment.aligner import Anchor, align, realign_region
from vibrato.alignment.dtw import multiscale_dtw


def test_multiscale_dtw_recovers_known_warp() -> None:
    rng = np.random.default_rng(0)
    a = rng.standard_normal((2500, 6)).cumsum(0)
    warp = np.clip((np.arange(3000) * 0.83 + 4 * np.sin(np.arange(3000) / 150)).round().astype(int), 0, 2499)
    b = a[warp] + 0.05 * rng.standard_normal((3000, 6))
    path_i, path_j, _ = multiscale_dtw(a, b)
    mapping = np.zeros(3000)
    for i, j in zip(path_i, path_j):
        mapping[j] = i
    assert np.mean(np.abs(mapping - warp)) < 1.0


def test_take_alignment_maps_words_accurately(analyses, rendered) -> None:
    ref, take = analyses["reference"], analyses["take1"]
    alignment = align(ref.features, take.features, ref.hierarchy, take.hierarchy)
    errors = [
        abs(float(alignment.ref_to_user(r["start"])) - u["start"])
        for r, u in zip(rendered["reference"].truth["words"], rendered["take1"].truth["words"])
    ]
    assert np.mean(errors) < 0.03
    assert alignment.overall_confidence > 0.6
    assert alignment.transposition_semitones == 0


def test_octave_transposition_is_detected(analyses) -> None:
    ref, take = analyses["reference"], analyses["octave"]
    alignment = align(ref.features, take.features, ref.hierarchy, take.hierarchy)
    assert alignment.transposition_semitones == -12
    assert any("transposed" in w for w in alignment.warnings)


def test_unrelated_material_gets_low_confidence(analyses) -> None:
    ref = analyses["reference"]
    other = analyses["take1"]
    reversed_features = other.features
    alignment = align(ref.features, reversed_features, ref.hierarchy, other.hierarchy)
    good = alignment.overall_confidence
    from vibrato.analysis.features import FeatureSet

    scrambled_tracks = {k: v[::-1].copy() for k, v in other.features.tracks.items()}
    scrambled = FeatureSet(
        other.features.n,
        other.features.duration_s,
        other.features.sample_rate,
        scrambled_tracks,
        {k: v[:, ::-1].copy() for k, v in other.features.matrices.items()},
        other.features.meta,
    )
    bad = align(ref.features, scrambled, ref.hierarchy, other.hierarchy)
    assert bad.overall_confidence < good - 0.25
    assert bad.overall_confidence < 0.5


def test_locked_anchor_is_respected_and_region_realign_is_monotonic(analyses) -> None:
    ref, take = analyses["reference"], analyses["take1"]
    anchor = Anchor(ref_time_s=5.0, user_time_s=5.3, locked=True)
    alignment = align(ref.features, take.features, ref.hierarchy, take.hierarchy, anchors=[anchor])
    assert float(alignment.ref_to_user(5.0)) == pytest.approx(5.3, abs=0.02)
    updated = realign_region(alignment, ref.features, take.features, 8.0, 11.0)
    assert np.all(np.diff(updated.user_times) >= 0)
