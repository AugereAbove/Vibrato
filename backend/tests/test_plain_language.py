import re

from vibrato.coaching.knowledge import GUIDANCE
from vibrato.coaching.plain import PLAIN, describe_places, enrich, plain_texts

JARGON = re.compile(r"\b(Hz|cents|dB|F1|F2|CPPS?|HNR|H1-H2|formant|centroid|kHz)\b")


def test_every_guidance_entry_has_plain_wording():
    assert set(GUIDANCE) <= set(PLAIN)


def test_plain_wording_has_no_jargon():
    for sentence, tip in PLAIN.values():
        assert not JARGON.search(sentence), sentence
        assert not JARGON.search(tip), tip


def test_describe_places():
    assert describe_places([]) == ""
    assert describe_places(["“home”"]) == "on “home”"
    assert describe_places(["“a”", "“b”"]) == "on “a” and “b”"
    assert describe_places(["“a”", "“b”", "“c”"]) == "on “a”, “b” and “c”"
    assert describe_places(["“a”", "“b”", "“c”", "“d”"]) == "on “a”, “b” and 2 other places"


def test_plain_texts_uses_lyric_places():
    finding = {
        "metric_id": "phonation.breathiness",
        "direction": "breathier",
        "category": "phonation",
        "texts": {"places": ["“home”", "“night”"]},
    }
    sentence, tip = plain_texts(finding)
    assert sentence == "Your voice sounds a bit breathy on “home” and “night”."
    assert "air" in tip


def test_many_words_collapse_to_lines():
    finding = {
        "metric_id": "phonation.breathiness",
        "direction": "breathier",
        "category": "phonation",
        "texts": {"places": ["“a”", "“b”", "“c”", "“d”"], "lines": ["“Hold the light”"]},
    }
    assert plain_texts(finding)[0] == "Your voice sounds a bit breathy on “Hold the light”."
    finding["texts"]["lines"] = ["line 1", "line 2", "line 3", "line 4"]
    assert plain_texts(finding)[0] == "Your voice sounds a bit breathy in lots of places."


def test_old_findings_fall_back_to_the_phrase():
    finding = {
        "metric_id": "pitch.center",
        "direction": "flat",
        "category": "pitch",
        "texts": {},
        "practice": {"phrase_label": "Phrase 2"},
    }
    assert plain_texts(finding)[0] == "You sang a little under the note on line 2."
    finding["practice"] = {"phrase_label": "Walking down the harbor road tonight"}
    assert plain_texts(finding)[0] == "You sang a little under the note on “Walking down the harbor…”."
    finding["practice"] = {}
    assert plain_texts(finding)[0] == "You sang a little under the note."


def test_unknown_metric_gets_generic_wording():
    sentence, _ = plain_texts({"metric_id": "x.y", "direction": "z", "category": "timing", "texts": {}})
    assert sentence == "Timing is a bit different from the singer."


def test_enrich_fills_every_tier_and_already_good():
    finding = {"metric_id": "timing.phrase_onset", "direction": "late", "category": "timing", "texts": {}}
    coaching = {
        "primary": [dict(finding, texts={})],
        "findings": [dict(finding, texts={})],
        "already_good": [{"metric_id": "pitch.center", "category": "pitch", "name": "Note centre"}],
    }
    enrich(coaching)
    assert coaching["primary"][0]["texts"]["simple"] == "You came in a bit late."
    assert coaching["findings"][0]["texts"]["simple_tip"]
    assert coaching["already_good"][0]["simple"] == "Your notes were in tune"
