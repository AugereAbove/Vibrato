from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...dsp.music import describe_pitch
from ..features import FeatureSet
from ..model import Event, Segment, overlap, segment_id
from .lyrics import AlignedPhoneme, AlignedWord, align_phonemes, align_words, parse_lyrics
from .notes import NoteSpan, segment_notes
from .phonetic import CLASS_LABELS, CONSONANT_CLASSES, ClassSegment, class_segments, classify_frames
from .phrases import BreathSpan, PhraseSpan, detect_breaths, detect_phrases, group_sections
from .syllables import SyllableSpan, segment_syllables, split_at_note_boundaries

SUSTAINED_VOWEL_MIN_S = 0.25
LONG_SILENCE_S = 1.5
SECTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Hierarchy:
    segments: list[Segment]
    events: list[Event]
    phrases: list[PhraseSpan]
    breaths: list[BreathSpan]
    syllables: list[SyllableSpan]
    notes: list[NoteSpan]
    class_segments: list[ClassSegment]
    words: list[AlignedWord] = field(default_factory=list)
    phonemes: list[AlignedPhoneme] = field(default_factory=list)
    lyrics_status: dict[str, Any] = field(default_factory=dict)

    def by_level(self, level: str) -> list[Segment]:
        return [s for s in self.segments if s.level == level]

    def get(self, seg_id: str) -> Segment | None:
        for segment in self.segments:
            if segment.id == seg_id:
                return segment
        return None

    def add_event(
        self,
        event_type: str,
        start_s: float,
        end_s: float,
        confidence: float,
        segment: str | None = None,
        **props: object,
    ) -> Event:
        event = Event(
            id=f"ev{len(self.events)}",
            type=event_type,
            start_s=round(start_s, 4),
            end_s=round(end_s, 4),
            confidence=round(float(confidence), 3),
            segment_id=segment,
            props=props,
        )
        self.events.append(event)
        return event

    def containing(self, level: str, t: float) -> Segment | None:
        for segment in self.by_level(level):
            if segment.start_s <= t < segment.end_s:
                return segment
        return None

    def best_overlap(self, level: str, start_s: float, end_s: float) -> Segment | None:
        best: tuple[float, Segment] | None = None
        for segment in self.by_level(level):
            amount = overlap(start_s, end_s, segment.start_s, segment.end_s)
            if amount > 0 and (best is None or amount > best[0]):
                best = (amount, segment)
        return best[1] if best else None


def _t(frame: int, fs: FeatureSet) -> float:
    return round(frame * fs.hop_s, 4)


def build_hierarchy(
    fs: FeatureSet,
    lyrics: str = "",
    pronunciation_overrides: dict[int, str] | None = None,
    user_sections: list[dict[str, Any]] | None = None,
) -> Hierarchy:
    phrases = detect_phrases(fs)
    breaths = detect_breaths(fs, phrases)
    phrase_mask = np.zeros(fs.n, dtype=bool)
    for phrase in phrases:
        phrase_mask[phrase.start : phrase.end] = True
    breath_mask = np.zeros(fs.n, dtype=bool)
    for breath in breaths:
        breath_mask[breath.start : breath.end] = True
    labels, margin = classify_frames(fs, phrase_mask, breath_mask)
    class_segs = class_segments(labels, margin)
    syllables = segment_syllables(fs, phrases, class_segs)
    boundaries = [s.start for s in syllables if not any(p.start == s.start for p in phrases)]
    notes = segment_notes(fs, phrases, boundaries)
    stable_starts = [
        n.start
        for i, n in enumerate(notes)
        if i > 0
        and notes[i - 1].end == n.start
        and n.core_end - n.core_start >= 6
        and notes[i - 1].core_end - notes[i - 1].core_start >= 6
    ]
    syllables, pitch_split = split_at_note_boundaries(syllables, stable_starts)
    words: list[AlignedWord] = []
    phonemes: list[AlignedPhoneme] = []
    lyrics_status: dict[str, Any] = {"provided": bool(lyrics.strip())}
    if lyrics.strip():
        lines = parse_lyrics(lyrics, pronunciation_overrides)
        words = align_words(lines, phrases, syllables)
        for ordinal, word in enumerate(words):
            phonemes.extend(align_phonemes(word, ordinal, class_segs))
        expected = sum(w.syllables for line in lines for w in line)
        lyrics_status.update(
            {
                "lines": len(lines),
                "words_expected": sum(len(line) for line in lines),
                "words_aligned": len(words),
                "syllables_expected": expected,
                "syllables_detected": len(syllables),
                "method": "lyric-assisted syllable alignment (rule-based pronunciations, acoustic phonetic classes)",
            }
        )
    hierarchy = Hierarchy(
        segments=[],
        events=[],
        phrases=phrases,
        breaths=breaths,
        syllables=syllables,
        notes=notes,
        class_segments=class_segs,
        words=words,
        phonemes=phonemes,
        lyrics_status=lyrics_status,
    )
    _assemble_segments(hierarchy, fs, lyrics, user_sections)
    for index in pitch_split:
        syllable = hierarchy.by_level("syllable")[index]
        syllable.props["split_by"] = "pitch change (no consonant or dip)"
    _assemble_events(hierarchy, fs)
    return hierarchy


def _line_texts(words: list[AlignedWord]) -> dict[int, str]:
    lines: dict[int, list[str]] = {}
    for word in words:
        lines.setdefault(word.phrase_index, []).append(word.word.text)
    return {k: " ".join(v) for k, v in lines.items()}


def _assemble_segments(
    h: Hierarchy, fs: FeatureSet, lyrics: str, user_sections: list[dict[str, Any]] | None
) -> None:
    segments: list[Segment] = []
    section_ids: list[str] = []
    if user_sections:
        for index, section in enumerate(sorted(user_sections, key=lambda s: float(s["start_s"]))):
            sid = segment_id("section", index)
            segments.append(
                Segment(
                    sid,
                    "section",
                    index,
                    float(section["start_s"]),
                    float(section["end_s"]),
                    str(section.get("label", f"Section {index + 1}")),
                    1.0,
                    None,
                    {"source": "user", "db_id": section.get("id")},
                )
            )
            section_ids.append(sid)
    else:
        for index, (first, last) in enumerate(group_sections(h.phrases, fs.hop_s)):
            sid = segment_id("section", index)
            label = f"Section {SECTION_LETTERS[index % 26]}"
            segments.append(
                Segment(
                    sid,
                    "section",
                    index,
                    _t(h.phrases[first].start, fs),
                    _t(h.phrases[last].end, fs),
                    label,
                    0.9,
                    None,
                    {"source": "automatic", "phrases": [first, last]},
                )
            )
            section_ids.append(sid)
    line_texts = _line_texts(h.words)
    phrase_ids: list[str] = []
    for index, phrase in enumerate(h.phrases):
        start, end = _t(phrase.start, fs), _t(phrase.end, fs)
        parent = next(
            (s.id for s in segments if s.level == "section" and s.start_s - 0.05 <= start < s.end_s + 0.05),
            section_ids[0] if section_ids else None,
        )
        label = line_texts.get(index, f"Phrase {index + 1}")
        pid = segment_id("phrase", index)
        voiced_conf = (
            float(
                np.mean(fs.tracks["f0_conf"][phrase.start : phrase.end][fs.voiced[phrase.start : phrase.end]])
            )
            if fs.voiced[phrase.start : phrase.end].any()
            else 0.3
        )
        segments.append(
            Segment(
                pid,
                "phrase",
                index,
                start,
                end,
                label,
                round(0.6 + 0.35 * voiced_conf, 3),
                parent,
                {"voiced_s": round(phrase.voiced_frames * fs.hop_s, 3)},
            )
        )
        phrase_ids.append(pid)
    for index, word in enumerate(h.words):
        segments.append(
            Segment(
                segment_id("word", index),
                "word",
                index,
                _t(word.start, fs),
                _t(word.end, fs),
                word.word.text,
                word.confidence,
                phrase_ids[word.phrase_index] if word.phrase_index < len(phrase_ids) else None,
                {
                    "line_index": word.word.line_index,
                    "word_index": word.word.word_index,
                    "phones": word.word.phones,
                    "pronunciation_source": word.word.source,
                    "syllables_expected": word.word.syllables,
                    "method": "lyric-assisted",
                },
            )
        )
    word_segments = [s for s in segments if s.level == "word"]
    for index, syllable in enumerate(h.syllables):
        start, end = _t(syllable.start, fs), _t(syllable.end, fs)
        mid = 0.5 * (start + end)
        parent_word = next((w for w in word_segments if w.start_s <= mid < w.end_s), None)
        parent = parent_word.id if parent_word else phrase_ids[syllable.phrase_index]
        segments.append(
            Segment(
                segment_id("syllable", index),
                "syllable",
                index,
                start,
                end,
                parent_word.label if parent_word else "",
                syllable.confidence,
                parent,
                {
                    "nucleus_start_s": _t(syllable.nucleus_start, fs),
                    "nucleus_end_s": _t(syllable.nucleus_end, fs),
                    "phrase_index": syllable.phrase_index,
                },
            )
        )
    syllable_segments = [s for s in segments if s.level == "syllable"]
    for index, note in enumerate(h.notes):
        start, end = _t(note.start, fs), _t(note.end, fs)
        parent_syllable = max(
            syllable_segments, key=lambda s: overlap(start, end, s.start_s, s.end_s), default=None
        )
        if (
            parent_syllable is not None
            and overlap(start, end, parent_syllable.start_s, parent_syllable.end_s) <= 0
        ):
            parent_syllable = None
        pitch = describe_pitch(note.center_midi)
        segments.append(
            Segment(
                segment_id("note", index),
                "note",
                index,
                start,
                end,
                str(pitch["note"]),
                note.confidence,
                parent_syllable.id if parent_syllable else phrase_ids[note.phrase_index],
                {
                    "center_midi": round(note.center_midi, 3),
                    "core_start_s": _t(note.core_start, fs),
                    "core_end_s": _t(note.core_end, fs),
                    "phrase_index": note.phrase_index,
                    **pitch,
                },
            )
        )
    if h.phonemes:
        for index, phoneme in enumerate(h.phonemes):
            start, end = _t(phoneme.start, fs), _t(phoneme.end, fs)
            mid = 0.5 * (start + end)
            parent = next((s.id for s in syllable_segments if s.start_s <= mid < s.end_s), None)
            if parent is None and phoneme.word_ordinal < len(word_segments):
                parent = word_segments[phoneme.word_ordinal].id
            segments.append(
                Segment(
                    segment_id("phoneme", index),
                    "phoneme",
                    index,
                    start,
                    end,
                    phoneme.symbol,
                    phoneme.confidence,
                    parent,
                    {
                        "symbol": phoneme.symbol,
                        "phoneme_class": phoneme.phoneme_class,
                        "acoustic_class": phoneme.acoustic_class,
                        "flags": phoneme.flags,
                        "word_ordinal": phoneme.word_ordinal,
                        "method": "lyric-assisted",
                    },
                )
            )
    else:
        ordinal = 0
        for cls_segment in h.class_segments:
            if cls_segment.cls in {"SIL", "BREATH"}:
                continue
            start, end = _t(cls_segment.start, fs), _t(cls_segment.end, fs)
            mid = 0.5 * (start + end)
            parent = next((s.id for s in syllable_segments if s.start_s <= mid < s.end_s), None)
            segments.append(
                Segment(
                    segment_id("phoneme", ordinal),
                    "phoneme",
                    ordinal,
                    start,
                    end,
                    CLASS_LABELS[cls_segment.cls],
                    round(0.4 + 0.4 * cls_segment.confidence, 3),
                    parent,
                    {"acoustic_class": cls_segment.cls, "method": "acoustic class"},
                )
            )
            ordinal += 1
    h.segments = segments


def _assemble_events(h: Hierarchy, fs: FeatureSet) -> None:
    for breath in h.breaths:
        h.add_event(
            "breath",
            _t(breath.start, fs),
            _t(breath.end, fs),
            breath.confidence,
            None,
            level_rel_db=round(breath.level_rel_db, 2),
            centroid_hz=round(breath.centroid_hz, 1),
            before_phrase=breath.before_phrase,
        )
    units: list[list[ClassSegment]] = []
    for segment in h.class_segments:
        if segment.cls not in CONSONANT_CLASSES:
            continue
        if (
            units
            and segment.start <= units[-1][-1].end
            and segment.cls in {"BURST", "ASP"}
            and units[-1][-1].cls in {"CLOSURE", "BURST"}
        ):
            units[-1].append(segment)
        else:
            units.append([segment])
    for unit in units:
        classes = [s.cls for s in unit]
        start, end = _t(unit[0].start, fs), _t(unit[-1].end, fs)
        mid = 0.5 * (start + end)
        syllable = h.containing("syllable", mid)
        kind = "stop" if "CLOSURE" in classes or "BURST" in classes else CLASS_LABELS[classes[0]]
        closure = sum(s.end - s.start for s in unit if s.cls == "CLOSURE") * fs.hop_s
        aspiration = sum(s.end - s.start for s in unit if s.cls == "ASP") * fs.hop_s
        burst = next((s for s in unit if s.cls == "BURST"), None)
        h.add_event(
            "consonant",
            start,
            end,
            float(np.mean([s.confidence for s in unit])) * 0.8 + 0.15,
            syllable.id if syllable else None,
            classes=classes,
            kind=kind,
            closure_s=round(closure, 3),
            aspiration_s=round(aspiration, 3),
            burst_s=None if burst is None else _t(burst.start, fs),
        )
    for segment in h.class_segments:
        if segment.cls == "VOWEL" and (segment.end - segment.start) * fs.hop_s >= SUSTAINED_VOWEL_MIN_S:
            start, end = _t(segment.start, fs), _t(segment.end, fs)
            syllable = h.containing("syllable", 0.5 * (start + end))
            h.add_event(
                "sustained_vowel",
                start,
                end,
                0.5 + 0.4 * segment.confidence,
                syllable.id if syllable else None,
            )
    for index in range(len(h.phrases) - 1):
        gap_start = _t(h.phrases[index].end, fs)
        gap_end = _t(h.phrases[index + 1].start, fs)
        if gap_end - gap_start >= LONG_SILENCE_S:
            h.add_event("silence", gap_start, gap_end, 0.9)
    for index, phrase in enumerate(h.phrases):
        phrase_segment = h.by_level("phrase")[index]
        voiced = np.flatnonzero(fs.voiced[phrase.start : phrase.end])
        onset = phrase.start + (int(voiced[0]) if voiced.size else 0)
        h.add_event("onset", _t(onset, fs), _t(onset, fs) + 0.05, 0.8, phrase_segment.id, phrase_index=index)
