from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

LEVELS = ("section", "phrase", "word", "syllable", "note", "phoneme")
LEVEL_PREFIX = {
    "section": "sc",
    "phrase": "ph",
    "word": "wd",
    "syllable": "sy",
    "note": "nt",
    "phoneme": "pn",
}

EVENT_TYPES = (
    "onset",
    "pitch_attack",
    "scoop_up",
    "scoop_down",
    "overshoot",
    "sustained_vowel",
    "consonant",
    "vibrato",
    "breath",
    "release",
    "register_transition",
    "roughness",
    "fry",
    "subharmonic",
    "silence",
    "portamento",
)


@dataclass
class Segment:
    id: str
    level: str
    ordinal: int
    start_s: float
    end_s: float
    label: str = ""
    confidence: float = 0.0
    parent_id: str | None = None
    props: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def mid_s(self) -> float:
        return 0.5 * (self.start_s + self.end_s)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Segment:
        return cls(
            **{
                k: data[k]
                for k in (
                    "id",
                    "level",
                    "ordinal",
                    "start_s",
                    "end_s",
                    "label",
                    "confidence",
                    "parent_id",
                    "props",
                )
                if k in data
            }
        )


@dataclass
class Event:
    id: str
    type: str
    start_s: float
    end_s: float
    confidence: float
    segment_id: str | None = None
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            **{
                k: data[k]
                for k in ("id", "type", "start_s", "end_s", "confidence", "segment_id", "props")
                if k in data
            }
        )


def segment_id(level: str, ordinal: int) -> str:
    return f"{LEVEL_PREFIX[level]}{ordinal}"


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))
