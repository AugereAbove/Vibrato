from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .phonetic import ClassSegment
from .phrases import PhraseSpan
from .syllables import SyllableSpan

VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
PHONEME_CLASS = {
    **dict.fromkeys(VOWELS, "vowel"),
    **dict.fromkeys(("M", "N", "NG", "L", "R", "W", "Y"), "sonorant"),
    **dict.fromkeys(("Z", "V", "DH", "ZH"), "voiced_fricative"),
    **dict.fromkeys(("S", "SH"), "sibilant"),
    **dict.fromkeys(("F", "TH"), "fricative"),
    "HH": "aspirate",
    **dict.fromkeys(("P", "T", "K", "B", "D", "G"), "stop"),
    **dict.fromkeys(("CH", "JH"), "affricate"),
}
COMPATIBILITY: dict[str, dict[str, float]] = {
    "vowel": {"VOWEL": 0.0, "SON": 0.6, "VFRIC": 0.8},
    "sonorant": {"SON": 0.0, "VOWEL": 0.45, "VFRIC": 0.5, "CLOSURE": 0.8},
    "voiced_fricative": {"VFRIC": 0.0, "SON": 0.3, "FRIC": 0.35, "SIB": 0.4, "ASP": 0.6, "VOWEL": 0.7},
    "sibilant": {"SIB": 0.0, "FRIC": 0.25, "VFRIC": 0.4, "ASP": 0.7},
    "fricative": {"FRIC": 0.0, "ASP": 0.2, "SIB": 0.4, "VFRIC": 0.4},
    "aspirate": {"ASP": 0.0, "FRIC": 0.2, "BREATH": 0.4},
    "stop": {"CLOSURE": 0.0, "BURST": 0.0, "ASP": 0.35, "SON": 0.6, "FRIC": 0.6, "SIB": 0.7},
    "affricate": {"SIB": 0.0, "CLOSURE": 0.1, "BURST": 0.1, "FRIC": 0.2},
}
MISMATCH_COST = 1.0
DROP_COST = {"vowel": 1.4, "stop": 0.8, "sonorant": 0.3}
DEFAULT_DROP_COST = 0.9
SKIP_SEGMENT_COST = 0.7
MERGE_SEGMENT_FACTOR = 0.5
REFERENCE_SEGMENT_FRAMES = 6
LONG_VOWEL_FRAMES = 15
CONSONANT_ON_LONG_VOWEL_COST = 0.5

LEXICON: dict[str, str] = {
    "a": "AH",
    "i": "AY",
    "the": "DH AH",
    "to": "T UW",
    "and": "AE N D",
    "of": "AH V",
    "in": "IH N",
    "on": "AA N",
    "you": "Y UW",
    "your": "Y AO R",
    "me": "M IY",
    "my": "M AY",
    "we": "W IY",
    "our": "AW ER",
    "us": "AH S",
    "he": "HH IY",
    "she": "SH IY",
    "they": "DH EY",
    "it": "IH T",
    "is": "IH Z",
    "was": "W AA Z",
    "be": "B IY",
    "are": "AA R",
    "were": "W ER",
    "been": "B IH N",
    "do": "D UW",
    "does": "D AH Z",
    "done": "D AH N",
    "one": "W AH N",
    "two": "T UW",
    "love": "L AH V",
    "heart": "HH AA R T",
    "night": "N AY T",
    "light": "L AY T",
    "time": "T AY M",
    "life": "L AY F",
    "eyes": "AY Z",
    "know": "N OW",
    "now": "N AW",
    "never": "N EH V ER",
    "ever": "EH V ER",
    "every": "EH V R IY",
    "all": "AO L",
    "go": "G OW",
    "gone": "G AO N",
    "home": "HH OW M",
    "hold": "HH OW L D",
    "stay": "S T EY",
    "with": "W IH TH",
    "carry": "K AE R IY",
    "come": "K AH M",
    "some": "S AH M",
    "from": "F R AH M",
    "what": "W AH T",
    "where": "W EH R",
    "there": "DH EH R",
    "their": "DH EH R",
    "here": "HH IY R",
    "that": "DH AE T",
    "this": "DH IH S",
    "these": "DH IY Z",
    "those": "DH OW Z",
    "then": "DH EH N",
    "than": "DH AE N",
    "them": "DH EH M",
    "when": "W EH N",
    "why": "W AY",
    "who": "HH UW",
    "how": "HH AW",
    "can": "K AE N",
    "can't": "K AE N T",
    "don't": "D OW N T",
    "won't": "W OW N T",
    "i'm": "AY M",
    "i'll": "AY L",
    "you're": "Y UH R",
    "it's": "IH T S",
    "baby": "B EY B IY",
    "oh": "OW",
    "ooh": "UW",
    "ah": "AA",
    "yeah": "Y EH",
    "hey": "HH EY",
    "so": "S OW",
    "no": "N OW",
    "not": "N AA T",
    "just": "JH AH S T",
    "only": "OW N L IY",
    "feel": "F IY L",
    "see": "S IY",
    "say": "S EY",
    "said": "S EH D",
    "way": "W EY",
    "day": "D EY",
    "away": "AH W EY",
    "again": "AH G EH N",
    "world": "W ER L D",
    "word": "W ER D",
    "sky": "S K AY",
    "fly": "F L AY",
    "cry": "K R AY",
    "try": "T R AY",
    "high": "HH AY",
    "by": "B AY",
    "die": "D AY",
    "lie": "L AY",
    "sea": "S IY",
    "water": "W AO T ER",
    "river": "R IH V ER",
    "fire": "F AY ER",
    "dream": "D R IY M",
    "dreams": "D R IY M Z",
    "sun": "S AH N",
    "moon": "M UW N",
    "star": "S T AA R",
    "stars": "S T AA R Z",
    "rain": "R EY N",
    "song": "S AO NG",
    "sing": "S IH NG",
    "long": "L AO NG",
    "longer": "L AO NG G ER",
    "little": "L IH T AH L",
    "morning": "M AO R N IH NG",
    "until": "AH N T IH L",
    "over": "OW V ER",
    "under": "AH N D ER",
    "into": "IH N T UW",
    "through": "TH R UW",
    "down": "D AW N",
    "up": "AH P",
    "out": "AW T",
    "back": "B AE K",
    "take": "T EY K",
    "make": "M EY K",
    "give": "G IH V",
    "live": "L IH V",
    "believe": "B IH L IY V",
    "need": "N IY D",
    "want": "W AA N T",
    "find": "F AY N D",
    "mind": "M AY N D",
    "kind": "K AY N D",
    "right": "R AY T",
    "tonight": "T AH N AY T",
    "alone": "AH L OW N",
    "free": "F R IY",
    "tree": "T R IY",
    "hand": "HH AE N D",
    "hands": "HH AE N D Z",
    "soul": "S OW L",
    "shine": "SH AY N",
    "shining": "SH AY N IH NG",
    "slow": "S L OW",
    "harbor": "HH AA R B ER",
    "open": "OW P AH N",
    "maybe": "M EY B IY",
    "forever": "F ER EH V ER",
    "together": "T AH G EH DH ER",
    "hallelujah": "HH AE L AH L UW Y AH",
    "amazing": "AH M EY Z IH NG",
    "grace": "G R EY S",
}

_DIGRAPHS: list[tuple[str, list[str]]] = [
    ("tch", ["CH"]),
    ("igh", ["AY"]),
    ("ough", ["AO"]),
    ("augh", ["AO"]),
    ("eigh", ["EY"]),
    ("tion", ["SH", "AH", "N"]),
    ("sion", ["ZH", "AH", "N"]),
    ("ture", ["CH", "ER"]),
    ("ph", ["F"]),
    ("sh", ["SH"]),
    ("ch", ["CH"]),
    ("th", ["TH"]),
    ("ng", ["NG"]),
    ("nk", ["NG", "K"]),
    ("ck", ["K"]),
    ("qu", ["K", "W"]),
    ("wh", ["W"]),
    ("wr", ["R"]),
    ("kn", ["N"]),
    ("gn", ["N"]),
    ("ee", ["IY"]),
    ("ea", ["IY"]),
    ("oo", ["UW"]),
    ("ou", ["AW"]),
    ("oa", ["OW"]),
    ("oi", ["OY"]),
    ("oy", ["OY"]),
    ("ai", ["EY"]),
    ("ay", ["EY"]),
    ("ei", ["EY"]),
    ("ey", ["EY"]),
    ("au", ["AO"]),
    ("aw", ["AO"]),
    ("ew", ["UW"]),
    ("ue", ["UW"]),
    ("ar", ["AA", "R"]),
    ("or", ["AO", "R"]),
    ("er", ["ER"]),
    ("ir", ["ER"]),
    ("ur", ["ER"]),
]
_SINGLE = {
    "a": ["AE"],
    "e": ["EH"],
    "i": ["IH"],
    "o": ["AA"],
    "u": ["AH"],
    "b": ["B"],
    "c": ["K"],
    "d": ["D"],
    "f": ["F"],
    "g": ["G"],
    "h": ["HH"],
    "j": ["JH"],
    "k": ["K"],
    "l": ["L"],
    "m": ["M"],
    "n": ["N"],
    "p": ["P"],
    "q": ["K"],
    "r": ["R"],
    "s": ["S"],
    "t": ["T"],
    "v": ["V"],
    "w": ["W"],
    "x": ["K", "S"],
    "z": ["Z"],
}
_MAGIC_E = {"a": "EY", "i": "AY", "o": "OW", "u": "UW", "e": "IY"}


def normalize_word(word: str) -> str:
    return re.sub(r"[^a-z']", "", word.lower())


def rule_pronunciation(word: str) -> list[str]:
    w = normalize_word(word).replace("'", "")
    if not w:
        return []
    phones: list[str] = []
    magic = re.fullmatch(r"(.*?)([aeiou])([bcdfghjklmnpqrstvwxz])e", w)
    magic_index = len(magic.group(1)) if magic else -1
    if magic:
        w = w[:-1]
    index = 0
    while index < len(w):
        if index == magic_index:
            phones.append(_MAGIC_E[w[index]])
            index += 1
            continue
        matched = False
        for pattern, output in _DIGRAPHS:
            if w.startswith(pattern, index):
                phones.extend(output)
                index += len(pattern)
                matched = True
                break
        if matched:
            continue
        char = w[index]
        if char == "y":
            if index == 0:
                phones.append("Y")
            elif index == len(w) - 1:
                phones.append("AY" if not any(p in VOWELS for p in phones) else "IY")
            else:
                phones.append("IH")
        elif char == "c" and index + 1 < len(w) and w[index + 1] in "eiy":
            phones.append("S")
        elif index > 0 and w[index - 1] == char and char not in "aeiou":
            pass
        else:
            phones.extend(_SINGLE.get(char, []))
        index += 1
    if len(phones) > 1 and phones[-1] == "S" and phones[-2] not in {"P", "T", "K", "F", "TH", "S", "SH"}:
        phones[-1] = "Z"
    return phones


def pronounce(word: str, overrides: dict[str, str] | None = None) -> tuple[list[str], str]:
    key = normalize_word(word)
    if overrides and key in overrides:
        return overrides[key].split(), "user"
    if key in LEXICON:
        return LEXICON[key].split(), "lexicon"
    return rule_pronunciation(key), "rules"


def syllable_count(phones: list[str]) -> int:
    return max(1, sum(1 for p in phones if p in VOWELS))


@dataclass
class LyricWord:
    text: str
    line_index: int
    word_index: int
    phones: list[str]
    source: str
    syllables: int


@dataclass
class AlignedWord:
    word: LyricWord
    start: int
    end: int
    syllable_indices: list[int]
    confidence: float
    phrase_index: int


@dataclass
class AlignedPhoneme:
    symbol: str
    phoneme_class: str
    start: int
    end: int
    acoustic_class: str | None
    confidence: float
    word_ordinal: int
    flags: list[str] = field(default_factory=list)


def parse_lyrics(text: str, overrides: dict[int, str] | None = None) -> list[list[LyricWord]]:
    lines: list[list[LyricWord]] = []
    counter = 0
    for line_index, raw in enumerate(line for line in text.splitlines() if line.strip()):
        words: list[LyricWord] = []
        for token in re.findall(r"[A-Za-z']+", raw):
            if overrides and counter in overrides:
                phones, source = overrides[counter].split(), "user"
            else:
                phones, source = pronounce(token)
            if not phones:
                continue
            words.append(LyricWord(token, line_index, counter, phones, source, syllable_count(phones)))
            counter += 1
        if words:
            lines.append(words)
    return lines


def _assign_lines_to_phrases(
    line_counts: list[int], phrase_counts: list[int]
) -> list[tuple[list[int], list[int]]]:
    m, k = len(line_counts), len(phrase_counts)
    inf = float("inf")
    cost = np.full((m + 1, k + 1), inf)
    back: dict[tuple[int, int], tuple[int, int]] = {}
    cost[0, 0] = 0.0
    for i in range(m + 1):
        for j in range(k + 1):
            if cost[i, j] == inf:
                continue
            for di, dj in ((1, 1), (1, 2), (2, 1), (1, 3), (3, 1)):
                ni, nj = i + di, j + dj
                if ni > m or nj > k:
                    continue
                expected = sum(line_counts[i:ni])
                detected = sum(phrase_counts[j:nj])
                step = abs(expected - detected) / max(expected, detected, 1) + 0.15 * (di + dj - 2)
                if cost[i, j] + step < cost[ni, nj]:
                    cost[ni, nj] = cost[i, j] + step
                    back[(ni, nj)] = (i, j)
    if cost[m, k] == inf:
        return []
    groups: list[tuple[list[int], list[int]]] = []
    node = (m, k)
    while node != (0, 0):
        previous = back[node]
        groups.append((list(range(previous[0], node[0])), list(range(previous[1], node[1]))))
        node = previous
    return list(reversed(groups))


def _align_syllables(expected: list[int], detected: int) -> list[list[int]]:
    m = len(expected)
    inf = float("inf")
    cost = np.full((m + 1, detected + 1), inf)
    back: dict[tuple[int, int], tuple[int, int, str]] = {}
    cost[0, 0] = 0.0
    for i in range(m + 1):
        for j in range(detected + 1):
            if cost[i, j] == inf:
                continue
            options = []
            if i < m and j < detected:
                options.append((i + 1, j + 1, 0.0, "match"))
            if i < m and j + 2 <= detected:
                options.append((i + 1, j + 2, 0.4, "melisma"))
            if i + 2 <= m and j < detected:
                options.append((i + 2, j + 1, 0.5, "merge"))
            if i < m:
                options.append((i + 1, j, 1.0, "drop"))
            if j < detected:
                options.append((i, j + 1, 0.8, "extra"))
            for ni, nj, step, kind in options:
                if cost[i, j] + step < cost[ni, nj]:
                    cost[ni, nj] = cost[i, j] + step
                    back[(ni, nj)] = (i, j, kind)
    assignment: list[list[int]] = [[] for _ in range(m)]
    node = (m, detected)
    while node != (0, 0):
        i, j, kind = back[node]
        if kind == "match":
            assignment[i].append(j)
        elif kind == "melisma":
            assignment[i].extend([j, j + 1])
        elif kind == "merge":
            assignment[i].append(j)
            assignment[i + 1].append(j)
        node = (i, j)
    return [sorted(a) for a in assignment]


def align_words(
    lines: list[list[LyricWord]], phrases: list[PhraseSpan], syllables: list[SyllableSpan]
) -> list[AlignedWord]:
    phrase_syllables: list[list[int]] = [
        [i for i, s in enumerate(syllables) if s.phrase_index == p] for p in range(len(phrases))
    ]
    line_counts = [sum(w.syllables for w in line) for line in lines]
    phrase_counts = [max(1, len(s)) for s in phrase_syllables]
    groups = _assign_lines_to_phrases(line_counts, phrase_counts) if lines and phrases else []
    aligned: list[AlignedWord] = []
    for line_ids, phrase_ids in groups:
        words = [w for li in line_ids for w in lines[li]]
        detected = [idx for p in phrase_ids for idx in phrase_syllables[p]]
        expected: list[int] = []
        for word_position, word in enumerate(words):
            expected.extend([word_position] * word.syllables)
        mapping = _align_syllables(expected, len(detected))
        mismatch = abs(len(expected) - len(detected)) / max(len(expected), len(detected), 1)
        base_conf = 0.7 * (1.0 - mismatch)
        per_word: dict[int, list[int]] = {}
        owners: dict[int, list[int]] = {}
        for exp_index, detected_list in enumerate(mapping):
            word_position = expected[exp_index]
            per_word.setdefault(word_position, []).extend(detected_list)
            for d in detected_list:
                bucket = owners.setdefault(d, [])
                if word_position not in bucket:
                    bucket.append(word_position)
        for word_position, word in enumerate(words):
            indices = sorted(set(per_word.get(word_position, [])))
            if not indices:
                continue
            pieces: list[tuple[int, int]] = []
            for d in indices:
                span = syllables[detected[d]]
                share = owners[d]
                slot = share.index(word_position)
                length = span.end - span.start
                pieces.append(
                    (
                        span.start + round(length * slot / len(share)),
                        span.start + round(length * (slot + 1) / len(share)),
                    )
                )
            shared = any(len(owners[d]) > 1 for d in indices)
            aligned.append(
                AlignedWord(
                    word=word,
                    start=pieces[0][0],
                    end=max(pieces[-1][1], pieces[0][0] + 1),
                    syllable_indices=[detected[i] for i in indices],
                    confidence=round(base_conf * (0.8 if shared else 1.0), 3),
                    phrase_index=syllables[detected[indices[0]]].phrase_index,
                )
            )
    return aligned


def _compat(phoneme_class: str, acoustic: str) -> float:
    return COMPATIBILITY.get(phoneme_class, {}).get(acoustic, MISMATCH_COST)


def _duration_weight(segment: ClassSegment) -> float:
    return min(1.0, (segment.end - segment.start) / REFERENCE_SEGMENT_FRAMES)


def _take_cost(phoneme_class: str, segment: ClassSegment) -> float:
    cost = _compat(phoneme_class, segment.cls) * (0.3 + 0.7 * _duration_weight(segment))
    if (
        phoneme_class != "vowel"
        and segment.cls == "VOWEL"
        and segment.end - segment.start > LONG_VOWEL_FRAMES
    ):
        cost += CONSONANT_ON_LONG_VOWEL_COST
    return cost


def align_phonemes(
    word: AlignedWord, ordinal: int, class_segments: list[ClassSegment]
) -> list[AlignedPhoneme]:
    segments = [
        ClassSegment(s.cls, max(s.start, word.start), min(s.end, word.end), s.confidence)
        for s in class_segments
        if s.end > word.start and s.start < word.end and s.cls not in {"SIL", "BREATH"}
    ]
    phones = word.word.phones
    classes = [PHONEME_CLASS.get(p, "vowel") for p in phones]
    m, k = len(phones), len(segments)
    if m == 0:
        return []
    inf = float("inf")
    cost = np.full((m + 1, k + 1), inf)
    back: dict[tuple[int, int], tuple[int, int, str]] = {}
    cost[0, 0] = 0.0
    for i in range(m + 1):
        for j in range(k + 1):
            if cost[i, j] == inf:
                continue
            candidates = []
            if i < m and j < k:
                candidates.append((i + 1, j + 1, _take_cost(classes[i], segments[j]), "take"))
            if i > 0 and j < k:
                candidates.append(
                    (
                        i,
                        j + 1,
                        _take_cost(classes[i - 1], segments[j]) * MERGE_SEGMENT_FACTOR + 0.05,
                        "extend",
                    )
                )
            if i < m:
                candidates.append((i + 1, j, DROP_COST.get(classes[i], DEFAULT_DROP_COST), "drop"))
            if j < k:
                candidates.append((i, j + 1, SKIP_SEGMENT_COST * _duration_weight(segments[j]), "skip"))
            for ni, nj, step, kind in candidates:
                if cost[i, j] + step < cost[ni, nj]:
                    cost[ni, nj] = cost[i, j] + step
                    back[(ni, nj)] = (i, j, kind)
    assigned: list[list[int]] = [[] for _ in range(m)]
    node = (m, k)
    while node != (0, 0):
        i, j, kind = back[node]
        if kind == "take":
            assigned[i].append(j)
        elif kind == "extend":
            assigned[i - 1].append(j)
        node = (i, j)
    result: list[AlignedPhoneme] = []
    for index, symbol in enumerate(phones):
        indices = sorted(assigned[index])
        if indices:
            start = segments[indices[0]].start
            end = segments[indices[-1]].end
            acoustic = segments[indices[0]].cls
            fit = 1.0 - min(_compat(classes[index], segments[i].cls) for i in indices)
            confidence = (
                word.confidence
                * (0.5 + 0.5 * fit)
                * float(np.mean([segments[i].confidence for i in indices]) * 0.5 + 0.5)
            )
            result.append(
                AlignedPhoneme(symbol, classes[index], start, end, acoustic, round(confidence, 3), ordinal)
            )
        else:
            result.append(
                AlignedPhoneme(symbol, classes[index], -1, -1, None, 0.0, ordinal, ["not_detected"])
            )
    _resolve_undetected(result, word)
    return result


def _resolve_undetected(phonemes: list[AlignedPhoneme], word: AlignedWord) -> None:
    for index, phoneme in enumerate(phonemes):
        if phoneme.start >= 0:
            continue
        left = next((p for p in reversed(phonemes[:index]) if p.start >= 0), None)
        right = next((p for p in phonemes[index + 1 :] if p.start >= 0), None)
        host = None
        if (
            left is not None
            and phoneme.phoneme_class in {"sonorant", "vowel", "voiced_fricative"}
            and left.acoustic_class in {"VOWEL", "SON"}
        ):
            host = left
            share = max(1, round((host.end - host.start) * 0.25))
            phoneme.start, phoneme.end = host.end - share, host.end
            host.end = phoneme.start
        elif (
            right is not None
            and phoneme.phoneme_class in {"sonorant", "vowel", "voiced_fricative"}
            and right.acoustic_class in {"VOWEL", "SON"}
        ):
            host = right
            share = max(1, round((host.end - host.start) * 0.25))
            phoneme.start, phoneme.end = host.start, host.start + share
            host.start = phoneme.end
        if host is not None:
            phoneme.acoustic_class = host.acoustic_class
            phoneme.confidence = round(host.confidence * 0.6, 3)
            phoneme.flags = ["merged_with_neighbour"]
            continue
        anchor = left.end if left is not None else (right.start if right is not None else word.start)
        phoneme.start = phoneme.end = anchor
        phoneme.flags = ["not_detected"]
        if phoneme.phoneme_class in {"stop", "sibilant", "fricative", "affricate"}:
            phoneme.flags.append("possibly_dropped")
