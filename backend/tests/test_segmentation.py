from __future__ import annotations

import numpy as np
import pytest

from vibrato.analysis.segmentation.lyrics import parse_lyrics, pronounce, syllable_count


def test_demo_reference_hierarchy_matches_ground_truth(analyses, rendered) -> None:
    analysis = analyses["reference"]
    truth = rendered["reference"].truth
    phrases = analysis.hierarchy.by_level("phrase")
    assert len(phrases) == len(truth["phrases"])
    for detected, expected in zip(phrases, truth["phrases"]):
        assert detected.start_s == pytest.approx(expected["start"], abs=0.12)
        assert detected.end_s == pytest.approx(expected["end"], abs=0.12)
    breaths = [e for e in analysis.hierarchy.events if e.type == "breath"]
    assert len(breaths) == len(truth["breaths"])
    notes = analysis.hierarchy.by_level("note")
    assert len(notes) == len(truth["notes"])
    for detected, expected in zip(notes, truth["notes"]):
        assert float(detected.props["center_midi"]) == pytest.approx(expected["midi"], abs=0.1)
    words = analysis.hierarchy.by_level("word")
    assert [w.label.lower() for w in words] == [w["text"] for w in truth["words"]]
    errors = [abs(w.start_s - t["start"]) for w, t in zip(words, truth["words"])]
    assert np.median(errors) < 0.08


def test_every_segment_has_valid_parent_and_ordering(analyses) -> None:
    hierarchy = analyses["take1"].hierarchy
    ids = {s.id for s in hierarchy.segments}
    for segment in hierarchy.segments:
        assert segment.end_s > segment.start_s or segment.level == "phoneme"
        if segment.parent_id is not None:
            assert segment.parent_id in ids
    for level in ("phrase", "syllable", "note"):
        starts = [s.start_s for s in hierarchy.by_level(level)]
        assert starts == sorted(starts)


def test_breath_missing_in_take_one_is_detected(analyses) -> None:
    take = analyses["take1"].hierarchy
    before = {e.props.get("before_phrase") for e in take.events if e.type == "breath"}
    assert 3 not in before
    assert {1, 2}.issubset(before)


def test_pronunciation_rules_and_syllable_counts() -> None:
    assert pronounce("light")[0] == ["L", "AY", "T"]
    phones, source = pronounce("carrying")
    assert source == "rules" and syllable_count(phones) == 3
    lines = parse_lyrics("Hold the light\n\nStay with me", overrides={0: "HH OW L D"})
    assert len(lines) == 2 and lines[0][0].source == "user"
