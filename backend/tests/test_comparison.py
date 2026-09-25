from __future__ import annotations

import pytest

from vibrato.alignment.aligner import align
from vibrato.coaching.engine import coaching_report, why_different
from vibrato.compare.comparator import compare
from vibrato.compare.metrics import METRICS
from vibrato.compare.model import make_comparison, metric_score
from vibrato.compare.scoring import category_scores
from vibrato.compare.view import RecordingView


@pytest.fixture(scope="module")
def results(analyses):
    ref = RecordingView.from_analysis("ref", analyses["reference"])
    out = {}
    for name in ("take1", "take3"):
        take = RecordingView.from_analysis(name, analyses[name])
        alignment = align(
            analyses["reference"].features,
            analyses[name].features,
            analyses["reference"].hierarchy,
            analyses[name].hierarchy,
        )
        result = compare(ref, take, alignment)
        out[name] = (
            result,
            coaching_report(
                result.metrics, ref, alignment.transposition_semitones, category_scores=result.scores
            ),
            ref,
        )
    return out


def _medians(result, metric_id):
    values = [
        m.difference
        for m in result.metrics
        if m.metric_id == metric_id and m.usable and m.difference is not None
    ]
    values.sort()
    return values[len(values) // 2] if values else None


def test_metric_score_formula() -> None:
    assert metric_score(0.0) == pytest.approx(100.0)
    assert metric_score(1.0) == pytest.approx(84.09, abs=0.1)
    assert metric_score(2.0) == pytest.approx(50.0, abs=0.01)


def test_low_confidence_comparisons_are_not_scored() -> None:
    weak = make_comparison("pitch.center", "note", "x", "a", "b", (0, 1), (0, 1), 6000.0, 6050.0, 50.0, 0.1)
    assert not weak.usable
    assert any("Insufficient confidence" in n for n in weak.notes)
    strong = make_comparison("pitch.center", "note", "x", "a", "b", (0, 1), (0, 1), 6000.0, 6015.0, 15.0, 0.9)
    scores = category_scores([weak, strong])
    assert scores["categories"]["pitch"]["count"] == 1
    assert scores["categories"]["pitch"]["score"] == pytest.approx(metric_score(1.0), abs=0.1)


def test_disabled_categories_leave_overall(results) -> None:
    result, _, _ = results["take1"]
    full = category_scores(result.metrics)
    without = category_scores(result.metrics, enabled={"phonation": False})
    assert without["overall"]["score"] > full["overall"]["score"]
    assert "not diagnostic" in full["overall"]["disclaimer"]


def test_planted_differences_are_detected(results) -> None:
    result, _, _ = results["take1"]
    assert _medians(result, "vibrato.rate") == pytest.approx(0.85, abs=0.35)
    assert _medians(result, "vibrato.onset") < -250
    assert _medians(result, "vibrato.extent") < -12
    assert _medians(result, "phonation.breathiness") > 20
    flat = [
        m
        for m in result.metrics
        if m.metric_id == "pitch.center" and m.usable and m.difference is not None and m.difference < -20
    ]
    assert len(flat) == 1 and "B3" in flat[0].label
    scoop = [m for m in result.metrics if m.metric_id == "pitch.scoop" and m.usable]
    assert scoop and scoop[0].difference < -80
    late = [
        m
        for m in result.metrics
        if m.metric_id == "timing.phrase_onset" and m.usable and m.difference and m.difference > 100
    ]
    assert len(late) == 1 and late[0].label.lower().startswith("stay")
    missing_breath = [
        m for m in result.metrics if m.metric_id == "breath.presence" and m.direction == "missing breath"
    ]
    assert len(missing_breath) == 1
    fronted = [
        m for m in result.metrics if m.metric_id == "vowel.f2" and m.usable and (m.normalized or 0) > 1.0
    ]
    assert any("light" in m.label.lower() for m in fronted)


def test_vocal_tract_scaling_is_normalised(results) -> None:
    result, _, _ = results["take1"]
    assert result.extras["vowel_scaling"]["factor"] == pytest.approx(1.04 / 1.12, abs=0.03)


def test_coaching_prioritises_real_problems(results) -> None:
    _, report, _ = results["take1"]
    titles = [f["title"] for tier in ("primary", "secondary") for f in report[tier]]
    assert any("vibrato" in t.lower() or "flat" in t.lower() for t in titles)
    assert report["next_focus"] is not None
    assert report["next_focus"]["loop"]["ref_end"] > report["next_focus"]["loop"]["ref_start"]
    primary = report["primary"][0]
    assert primary["texts"]["beginner"] and primary["texts"]["expert"] and primary["evidence"]
    flagged = {f["metric_id"] for tier in ("primary", "secondary", "minor") for f in report[tier]}
    assert not flagged & {g["metric_id"] for g in report["already_good"]}


def test_improved_take_scores_higher_and_keeps_persistent_habit(results) -> None:
    first, _, _ = results["take1"]
    third, report_third, _ = results["take3"]
    assert third.scores["overall"]["score"] > first.scores["overall"]["score"]
    assert (
        third.scores["categories"]["vibrato"]["score"] > first.scores["categories"]["vibrato"]["score"] + 15
    )
    assert report_third["primary"][0]["metric_id"] == "phonation.breathiness"
    assert any(g["metric_id"] == "pitch.center" for g in report_third["already_good"])


def test_why_different_cites_region_evidence(results) -> None:
    result, _, ref = results["take1"]
    explanation = why_different(result.metrics, ref, 1.9, 3.7)
    assert explanation["primary"]
    assert explanation["primary"][0]["category"] == "vibrato"
    assert all(e["label"] for e in explanation["primary"][0]["evidence"])
    empty = why_different(result.metrics, ref, 16.5, 17.0)
    assert "message" in empty


def test_metric_definitions_are_documented() -> None:
    for definition in METRICS.values():
        assert (
            definition.tolerance > 0
            and definition.description
            and definition.why
            and definition.tolerance_basis
        )
