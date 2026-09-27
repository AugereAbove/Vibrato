from __future__ import annotations

import re
from typing import Any

from ..compare.model import MetricComparison
from ..compare.view import RecordingView

MAX_PLACES = 3
PHRASE_WORDS = 4

CATEGORY_NAMES = {
    "pitch": "Hitting the notes",
    "timing": "Timing",
    "vowel": "Vowel shapes",
    "vibrato": "Vibrato",
    "dynamics": "Loud and soft",
    "phonation": "Clear tone",
    "articulation": "Clear words",
    "breath": "Breathing",
    "timbre": "Tone colour",
}

GOOD = {
    "pitch": "Your notes were in tune",
    "timing": "You kept good time",
    "vowel": "Your vowels sounded like the singer's",
    "vibrato": "Your vibrato matched",
    "dynamics": "Your loud and soft parts matched",
    "phonation": "Your tone was as clear as the singer's",
    "articulation": "Your words were clear",
    "breath": "You breathed in the right places",
    "timbre": "Your tone colour matched",
}

GOOD_BY_METRIC = {
    "pitch.center": "Your notes were in tune",
    "timing.phrase_onset": "You came in right on time",
    "timing.note_onset": "Your rhythm matched",
    "vibrato.rate": "Your vibrato speed matched",
    "vibrato.extent": "Your vibrato size matched",
}

PLAIN: dict[tuple[str, str], tuple[str, str]] = {
    ("pitch.center", "flat"): (
        "You sang a little under the note {where}.",
        "Hear the note in your head before you sing it, and keep your breath going to the end of it.",
    ),
    ("pitch.center", "sharp"): (
        "You sang a little over the note {where}.",
        "Sing it a bit softer and let the note settle down instead of pushing.",
    ),
    ("pitch.scoop", "more direct"): (
        "The singer slides up into the note {where}, but you jump straight onto it.",
        "Start just below the note and slide up into it, like the singer does.",
    ),
    ("pitch.scoop", "more scooped"): (
        "You slide up into the note {where}, but the singer starts right on it.",
        "Hear the note first, then start singing right on it.",
    ),
    ("pitch.attack_time", "slower to settle"): (
        "You take a moment to find the note {where}.",
        "Aim for the middle of the note straight away.",
    ),
    ("pitch.attack_time", "faster to settle"): (
        "The singer eases into the note more gently {where}.",
        "Let the note arrive a little more slowly.",
    ),
    ("pitch.overshoot", "more overshoot"): (
        "You go past the note and come back {where}.",
        "Aim for the middle of the note and land on it softly.",
    ),
    ("pitch.overshoot", "less overshoot"): (
        "The singer flicks just past the note and back {where}.",
        "If you like that style, let the note bounce slightly past and settle back.",
    ),
    ("pitch.drift", "sagging more"): (
        "Your note slowly drops while you hold it {where}.",
        "Keep your breath steady right to the end of long notes.",
    ),
    ("pitch.drift", "rising more"): (
        "Your note slowly creeps up while you hold it {where}.",
        "Relax your throat and keep long notes easy, not pushed.",
    ),
    ("pitch.stability", "less steady"): (
        "Your long notes wander a little {where}.",
        "Practise holding the note steady first, then add style.",
    ),
    ("pitch.stability", "steadier"): (
        "The singer lets long notes move around more freely {where}.",
        "This is just style. Copy it only if you like the relaxed feel.",
    ),
    ("pitch.release", "falling more"): (
        "Your notes drop at the end {where}.",
        "Keep the note steady right to the end, then stop cleanly.",
    ),
    ("pitch.release", "lifting more"): (
        "The singer lets the note fall away at the end {where}, but you hold it.",
        "Let the note drop gently as you finish it.",
    ),
    ("pitch.transition", "slower glide"): (
        "You slide between notes more slowly than the singer {where}.",
        "Move to the next note a little later and quicker.",
    ),
    ("pitch.transition", "faster glide"): (
        "The singer slides between notes more smoothly {where}.",
        "Let your voice glide into the next note.",
    ),
    ("timing.phrase_onset", "late"): (
        "You came in a bit late {where}.",
        "Take your breath earlier so you're ready to start on time.",
    ),
    ("timing.phrase_onset", "early"): (
        "You came in a bit early {where}.",
        "Wait a moment longer before you start the line.",
    ),
    ("timing.note_onset", "late"): (
        "Some words come a little late {where}.",
        "Say the words in rhythm with the song first, then sing them.",
    ),
    ("timing.note_onset", "early"): (
        "Some words come a little early {where}.",
        "Say the words in rhythm with the song first, then sing them.",
    ),
    ("timing.duration", "longer"): (
        "You hold some notes longer than the singer {where}.",
        "Move on to the next word a little sooner.",
    ),
    ("timing.duration", "shorter"): (
        "You cut some notes shorter than the singer {where}.",
        "Hold the note until the singer moves on.",
    ),
    ("timing.hold", "held longer"): (
        "You hold the last note of the line too long {where}.",
        "Stop the last note when the singer stops.",
    ),
    ("timing.hold", "cut shorter"): (
        "You stop the last note of the line too early {where}.",
        "Save enough breath to hold the last note until the singer stops.",
    ),
    ("vibrato.presence", "missing vibrato"): (
        "The singer adds a gentle wobble (vibrato) {where}, but you sing it straight.",
        "Start the note straight, then relax and let it wobble gently.",
    ),
    ("vibrato.presence", "added vibrato"): (
        "You add a wobble (vibrato) {where} where the singer sings it straight.",
        "Hold these notes straight and steady.",
    ),
    ("vibrato.rate", "faster"): (
        "Your vibrato (the wobble) is faster than the singer's {where}.",
        "Relax and let the wobble slow down a little.",
    ),
    ("vibrato.rate", "slower"): (
        "Your vibrato (the wobble) is slower than the singer's {where}.",
        "Make the wobble a little quicker and lighter.",
    ),
    ("vibrato.extent", "wider"): (
        "Your vibrato (the wobble) is bigger than the singer's {where}.",
        "Make the wobble smaller: think shimmer, not wobble.",
    ),
    ("vibrato.extent", "narrower"): (
        "Your vibrato (the wobble) is smaller than the singer's {where}.",
        "Let the wobble swing a little wider.",
    ),
    ("vibrato.onset", "starts earlier"): (
        "You start the vibrato (the wobble) too early {where}.",
        "Hold the start of the note straight for a moment, then let the wobble in.",
    ),
    ("vibrato.onset", "starts later"): (
        "You start the vibrato (the wobble) later than the singer {where}.",
        "Let the wobble in a little sooner.",
    ),
    ("vibrato.regularity", "less even"): (
        "Your vibrato (the wobble) is a bit uneven {where}.",
        "Keep your breath steady so each wobble is the same.",
    ),
    ("vibrato.regularity", "more even"): (
        "The singer's vibrato is looser than yours {where}.",
        "This is just style. No need to change it.",
    ),
    ("vowel.f2", "more fronted"): (
        "Your vowel sounds brighter than the singer's {where}.",
        "Make the vowel a little rounder and darker, like shaping an 'oh'.",
    ),
    ("vowel.f2", "more backed"): (
        "Your vowel sounds darker than the singer's {where}.",
        "Make the vowel a little brighter, like smiling slightly as you sing.",
    ),
    ("vowel.f1", "more open"): (
        "Your mouth sounds more open than the singer's {where}.",
        "Close your mouth a little on this word.",
    ),
    ("vowel.f1", "more closed"): (
        "Your mouth sounds more closed than the singer's {where}.",
        "Drop your jaw a little more on this word.",
    ),
    ("vowel.movement", "moves more"): (
        "Your vowel changes shape during the note {where}.",
        "Hold the main vowel and only change it at the very end.",
    ),
    ("vowel.movement", "moves less"): (
        "The singer's vowel changes shape more during the note {where}.",
        "Let the vowel glide toward its ending sound, like the singer.",
    ),
    ("dynamics.contour", "different shape"): (
        "Your volume goes up and down differently from the singer's {where}.",
        "Listen for where the singer gets louder and softer, and copy it.",
    ),
    ("dynamics.phrase_level", "louder"): (
        "You sing this part louder than the singer does {where}.",
        "Bring this part down a little.",
    ),
    ("dynamics.phrase_level", "softer"): (
        "You sing this part softer than the singer does {where}.",
        "Give this part more energy.",
    ),
    ("dynamics.note_change", "fades more"): (
        "The singer gets louder through the note {where}; yours stays flat or fades.",
        "Grow the note by using more breath, not by squeezing.",
    ),
    ("dynamics.note_change", "grows more"): (
        "You get louder through the note more than the singer {where}.",
        "Keep the note at a more even volume.",
    ),
    ("dynamics.emphasis", "more stressed"): (
        "You push some words harder than the singer {where}.",
        "Say the line out loud with natural stress, then sing it the same way.",
    ),
    ("dynamics.emphasis", "less stressed"): (
        "The singer leans on some words more than you {where}.",
        "Give the important words a bit more weight.",
    ),
    ("dynamics.attack", "punchier"): (
        "You start notes more suddenly than the singer {where}.",
        "Start the note gently and let it grow.",
    ),
    ("dynamics.attack", "softer"): (
        "The singer starts notes more clearly than you {where}.",
        "Give the start of each note a clearer beginning.",
    ),
    ("phonation.breathiness", "breathier"): (
        "Your voice sounds a bit breathy {where}.",
        "Start notes cleanly and use a steady stream of air, not more air.",
    ),
    ("phonation.breathiness", "clearer"): (
        "The singer's voice is airier than yours {where}.",
        "Let a little more air into the sound, like a gentle sigh.",
    ),
    ("phonation.h1h2", "lighter / more open"): (
        "Your voice sounds lighter than the singer's {where}.",
        "Sing it more like confident speaking.",
    ),
    ("phonation.h1h2", "heavier / more pressed"): (
        "Your voice sounds a bit squeezed {where}.",
        "Use less effort and let the sound feel easy.",
    ),
    ("phonation.hnr", "noisier"): (
        "Your voice sounds a bit rough or airy {where}.",
        "Aim for a smooth, steady sound.",
    ),
    ("phonation.hnr", "cleaner"): (
        "The singer's voice has more grit than yours {where}.",
        "This is just style. Add grit only if you like it.",
    ),
    ("articulation.consonant_duration", "longer"): (
        "You hold some consonants too long {where}.",
        "Keep consonants short and get to the vowel quickly.",
    ),
    ("articulation.consonant_duration", "shorter"): (
        "The singer lingers on some consonants more than you {where}.",
        "Give those consonants a little more time.",
    ),
    ("articulation.cv_ratio", "stronger"): (
        "Your consonants are louder than the singer's {where}.",
        "Soften the consonants a little.",
    ),
    ("articulation.cv_ratio", "softer"): (
        "The singer says some consonants more clearly {where}.",
        "Say the words a bit more crisply.",
    ),
    ("articulation.missing_consonant", "missing"): (
        "You may be dropping a sound in the word {where}.",
        "Say the word clearly, then sing it keeping every sound.",
    ),
    ("articulation.onset_type", "different"): (
        "You start some lines differently from the singer {where}.",
        "Listen to how the singer starts the first word and copy it.",
    ),
    ("breath.presence", "missing breath"): (
        "The singer takes a breath before {where_bare}, but you don't.",
        "Plan a quick breath here.",
    ),
    ("breath.presence", "extra breath"): (
        "You take a breath before {where_bare} where the singer doesn't.",
        "Try to sing through here without breathing.",
    ),
    ("breath.duration", "longer"): (
        "Your breaths take longer than the singer's {where}.",
        "Take quicker breaths so they fit in the gap.",
    ),
    ("breath.duration", "shorter"): (
        "The singer takes longer breaths than you {where}.",
        "Take a slightly fuller breath if you run out later.",
    ),
    ("breath.level", "louder breath"): (
        "Your breaths are noisier than the singer's {where}.",
        "Relax your throat and breathe through an open mouth.",
    ),
    ("breath.level", "quieter breath"): (
        "The singer's breaths are easier to hear than yours {where}.",
        "This is just style. No need to change it.",
    ),
    ("breath.phrase_end", "airier endings"): (
        "Your voice gets airy at the end of lines {where}.",
        "Save enough breath to keep the tone clear to the end.",
    ),
    ("breath.phrase_end", "clearer endings"): (
        "The singer lets the voice go airy at the end of lines {where}.",
        "Let the end of the line soften into a sigh.",
    ),
    ("timbre.band_balance", "more energy in a band"): (
        "Your tone colour is a bit different from the singer's {where}.",
        "This is partly your voice and microphone. Focus on other things first.",
    ),
    ("timbre.band_balance", "less energy in a band"): (
        "Your tone colour is a bit different from the singer's {where}.",
        "This is partly your voice and microphone. Focus on other things first.",
    ),
    ("timbre.centroid", "brighter"): (
        "Your tone sounds brighter than the singer's {where}.",
        "Make your vowels a little rounder and taller.",
    ),
    ("timbre.centroid", "darker"): (
        "Your tone sounds darker than the singer's {where}.",
        "Make your vowels a little brighter and more forward.",
    ),
    ("timbre.spr", "more ring"): (
        "Your voice sounds a bit edgier than the singer's {where}.",
        "Soften the vowel and use a little less effort.",
    ),
    ("timbre.spr", "less ring"): (
        "The singer's voice rings out more than yours {where}.",
        "Try a brighter, more focused sound.",
    ),
}

GENERIC_TIP = "Listen to the singer and then yourself, and copy what you hear."


def _short(text: str) -> str:
    words = text.split()
    if len(words) <= PHRASE_WORDS:
        return text
    return " ".join(words[:PHRASE_WORDS]) + "…"


def _place_for(label: str | None) -> str | None:
    label = (label or "").strip()
    if not label:
        return None
    match = re.fullmatch(r"Phrase (\d+)", label)
    if match:
        return f"line {match.group(1)}"
    return f"“{_short(label)}”"


def lyric_places(instances: list[MetricComparison], ref: RecordingView) -> tuple[list[str], list[str]]:
    words = ref.by_level("word")
    phrases = ref.by_level("phrase")
    places: list[str] = []
    lines: list[str] = []
    for m in sorted(instances, key=lambda x: x.ref_start):
        mid = 0.5 * (m.ref_start + m.ref_end)
        word = next((w for w in words if w.start_s <= mid < w.end_s), None)
        phrase = next((p for p in phrases if p.start_s - 0.01 <= mid < p.end_s + 0.01), None)
        line = _place_for(phrase.label if phrase else None)
        if line and line not in lines:
            lines.append(line)
        place = f"“{word.label.strip()}”" if word is not None and word.label.strip() else line
        if place and place not in places:
            places.append(place)
    return places, lines


def describe_places(places: list[str], bare: bool = False) -> str:
    if not places:
        return ""
    shown = places[:MAX_PLACES] if len(places) <= MAX_PLACES else places[:2]
    rest = len(places) - len(shown)
    if rest:
        text = f"{', '.join(shown)} and {rest} other place{'s' if rest > 1 else ''}"
    elif len(shown) == 1:
        text = shown[0]
    else:
        text = f"{', '.join(shown[:-1])} and {shown[-1]}"
    return text if bare else f"on {text}"


def _tidy(text: str) -> str:
    text = re.sub(r"\s+([.,;])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _finding_places(finding: dict[str, Any]) -> list[str]:
    texts = finding.get("texts") or {}
    places = [str(p) for p in texts.get("places") or []]
    lines = [str(p) for p in texts.get("lines") or []]
    if places and len(places) <= MAX_PLACES:
        return places
    if lines:
        return lines
    if places:
        return places
    practice = finding.get("practice") or {}
    place = _place_for(practice.get("phrase_label"))
    return [place] if place else []


def _where(places: list[str], bare: bool = False) -> str:
    if len(places) > MAX_PLACES:
        return "in lots of places" if not bare else "several lines"
    return describe_places(places, bare)


def plain_texts(finding: dict[str, Any]) -> tuple[str, str]:
    places = _finding_places(finding)
    where = _where(places)
    where_bare = _where(places, bare=True) or "this line"
    template = PLAIN.get((str(finding.get("metric_id")), str(finding.get("direction"))))
    if template is None:
        name = CATEGORY_NAMES.get(str(finding.get("category")), "This part").lower()
        return _tidy(f"{name.capitalize()} is a bit different from the singer {where}."), GENERIC_TIP
    sentence, tip = template
    return _tidy(sentence.format(where=where, where_bare=where_bare)), tip


def _enrich_finding(finding: dict[str, Any]) -> None:
    texts = finding.setdefault("texts", {})
    simple, tip = plain_texts(finding)
    texts["simple"] = simple
    texts["simple_tip"] = tip


def enrich(coaching: dict[str, Any]) -> dict[str, Any]:
    for tier in ("primary", "secondary", "minor", "uncertain", "findings"):
        for finding in coaching.get(tier) or []:
            _enrich_finding(finding)
    for item in coaching.get("already_good") or []:
        item["simple"] = GOOD_BY_METRIC.get(str(item.get("metric_id"))) or GOOD.get(
            str(item.get("category")), f"Your {str(item.get('name', 'singing')).lower()} matched"
        )
    return coaching
