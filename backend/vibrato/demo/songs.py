from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from .synth import NoteSpec, Performance, PhraseSpec, VoiceSpec

DEMO_TITLE = "Harbor Light"
DEMO_LYRICS = "Hold the light\nStay with me\nCarry us home\nEvery night"
DEMO_TEMPO = 84.0


def _reference_phrases() -> list[PhraseSpec]:
    return [
        PhraseSpec(
            start_beat=0.0,
            notes=[
                NoteSpec("hold", ("H",), "OW", ("L", "D"), midi=62, beats=1.0),
                NoteSpec("the", ("DH",), "AH", (), midi=64, beats=0.5),
                NoteSpec(
                    "light",
                    ("L",),
                    "AY",
                    ("T",),
                    midi=66,
                    beats=2.5,
                    vib_rate=5.4,
                    vib_extent=55,
                    vib_onset=0.45,
                ),
            ],
        ),
        PhraseSpec(
            start_beat=5.5,
            notes=[
                NoteSpec("stay", ("S", "T"), "EI", (), midi=64, beats=1.0, scoop_cents=-150, scoop_s=0.14),
                NoteSpec("with", ("W",), "IH", ("TH",), midi=62, beats=0.5),
                NoteSpec(
                    "me", ("M",), "IY", (), midi=59, beats=2.5, vib_rate=5.3, vib_extent=50, vib_onset=0.5
                ),
            ],
        ),
        PhraseSpec(
            start_beat=11.0,
            notes=[
                NoteSpec("car", ("K",), "AE", (), midi=57, beats=0.5),
                NoteSpec("ry", ("R",), "IY", (), midi=59, beats=0.5, word_start=False),
                NoteSpec("us", (), "AH", ("S",), midi=61, beats=0.5),
                NoteSpec(
                    "home",
                    ("H",),
                    "OW",
                    ("M",),
                    midi=62,
                    beats=2.5,
                    vib_rate=5.5,
                    vib_extent=55,
                    vib_onset=0.45,
                    crescendo_db=5.0,
                ),
            ],
        ),
        PhraseSpec(
            start_beat=16.5,
            release_fall_cents=-80.0,
            notes=[
                NoteSpec("ev", (), "EH", ("V",), midi=66, beats=0.5),
                NoteSpec("ery", ("R",), "IY", (), midi=64, beats=0.5, word_start=False),
                NoteSpec(
                    "night",
                    ("N",),
                    "AY",
                    ("T",),
                    midi=62,
                    beats=3.0,
                    vib_rate=5.4,
                    vib_extent=50,
                    vib_onset=0.5,
                    crescendo_db=-6.0,
                ),
            ],
        ),
    ]


def reference_performance() -> Performance:
    return Performance(
        phrases=_reference_phrases(),
        voice=VoiceSpec(tract_scale=1.12, breathiness=0.1, level_db=-14.0, jitter=0.002, shimmer=0.015),
        tempo_bpm=DEMO_TEMPO,
        seed=11,
    )


def _edit(phrases: list[PhraseSpec], phrase: int, note: int, **changes: Any) -> None:
    phrases[phrase].notes[note] = replace(phrases[phrase].notes[note], **changes)


def take_performance(take: int) -> Performance:
    phrases = deepcopy(_reference_phrases())
    if take == 1:
        vib = {"vib_rate": 6.4, "vib_extent": 28.0, "vib_onset": 0.12}
        breathiness = 0.34
        _edit(phrases, 0, 0, consonant_scale={"D": 1.9})
        _edit(phrases, 0, 2, f1_mult=0.88, f2_mult=1.17, hold_scale=0.86, **vib)
        _edit(phrases, 1, 0, scoop_cents=0.0, consonant_scale={"S": 1.7})
        _edit(phrases, 1, 2, detune_cents=-32.0, **vib)
        _edit(phrases, 2, 3, f2_mult=1.12, crescendo_db=0.0, **vib)
        _edit(phrases, 3, 2, **vib)
        phrases[1] = replace(phrases[1], time_shift_s=0.17)
        phrases[3] = replace(phrases[3], breath_before=False)
        seed = 21
    elif take == 2:
        vib = {"vib_rate": 5.9, "vib_extent": 42.0, "vib_onset": 0.3}
        breathiness = 0.33
        _edit(phrases, 0, 0, consonant_scale={"D": 1.25})
        _edit(phrases, 0, 2, f1_mult=0.93, f2_mult=1.09, hold_scale=0.95, **vib)
        _edit(phrases, 1, 0, scoop_cents=-90.0, consonant_scale={"S": 1.2})
        _edit(phrases, 1, 2, detune_cents=-12.0, **vib)
        _edit(phrases, 2, 3, f2_mult=1.06, crescendo_db=2.5, **vib)
        _edit(phrases, 3, 2, **vib)
        phrases[1] = replace(phrases[1], time_shift_s=0.06)
        seed = 22
    else:
        vib = {"vib_rate": 5.5, "vib_extent": 50.0, "vib_onset": 0.42}
        breathiness = 0.31
        _edit(phrases, 0, 2, f1_mult=0.97, f2_mult=1.04, **vib)
        _edit(phrases, 1, 0, scoop_cents=-140.0, consonant_scale={"S": 1.05})
        _edit(phrases, 1, 2, detune_cents=-4.0, **vib)
        _edit(phrases, 2, 3, f2_mult=1.03, crescendo_db=4.5, **vib)
        _edit(phrases, 3, 2, **vib)
        seed = 23
    return Performance(
        phrases=phrases,
        voice=VoiceSpec(
            tract_scale=1.04, breathiness=breathiness, level_db=-17.0, jitter=0.003, shimmer=0.025
        ),
        tempo_bpm=DEMO_TEMPO,
        seed=seed,
        noise_dbfs=-72.0,
    )


def octave_down_take() -> Performance:
    phrases = deepcopy(_reference_phrases())
    for phrase in phrases:
        phrase.notes = [replace(note, midi=note.midi - 12) for note in phrase.notes]
    return Performance(
        phrases=phrases,
        voice=VoiceSpec(tract_scale=0.93, breathiness=0.12, level_db=-15.0),
        tempo_bpm=DEMO_TEMPO,
        seed=31,
    )
