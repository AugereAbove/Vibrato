from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from ..compare.metrics import CATEGORY_LABELS, METRICS
from ..compare.model import MetricComparison
from ..compare.view import RecordingView
from ..util import to_jsonable
from .knowledge import GUIDANCE, Guidance

COACHING_VERSION = "coach/1.1"
MIN_FINDING_CONFIDENCE = 0.45
MIN_FINDING_Z = 0.75
GOOD_Z = 0.5
UNCERTAIN_Z = 1.25
SYSTEMATIC_MIN_INSTANCES = 3
SYSTEMATIC_FRACTION = 0.6
PERSISTENCE_STEP = 0.15
PERSISTENCE_CAP = 4
SYSTEMATIC_BONUS = 1.25
FAMILY_OVERLAP = 0.5
FAMILIES: dict[str, tuple[str, ...]] = {
    "phonation.breathiness": ("phonation.cpps", "phonation.hnr", "phonation.h1h2"),
    "pitch.scoop": ("pitch.attack_time",),
    "vowel.f1": ("vowel.movement",),
    "vowel.f2": ("vowel.movement",),
}
BOOST_FACTOR = 1.5
DISMISS_STEP = 0.1
DISMISS_FLOOR = 0.5
LOW_VALUE_PRIORITY = 0.12
PRACTICE_PAD_S = 0.25
PHRASE_LEAD_S = 0.6


@dataclass
class Finding:
    key: str
    metric_id: str
    category: str
    direction: str
    title: str
    instances: list[MetricComparison]
    magnitude: float
    max_z: float
    confidence: float
    importance: float
    persistence: float
    trainability: float
    override: float
    priority: float
    systematic: bool
    eligible: int
    tier: str = "minor"
    practice: dict[str, Any] = field(default_factory=dict)
    texts: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    ranking: dict[str, Any] = field(default_factory=dict)
    history_takes: int = 0
    corroborating: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["instances"] = [m.ref_segment_id for m in self.instances]
        return to_jsonable(data)


def fmt(value: float | str | None, unit: str, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    sign = "+" if signed and value > 0 else ""
    if unit in {"cents", "cents (±)"}:
        return (
            f"{sign}{value:.0f} cents"
            if unit == "cents"
            else f"±{abs(value):.0f} cents"
            if not signed
            else f"{sign}{value:.0f} cents"
        )
    if unit == "ms":
        return f"{sign}{value:.0f} ms"
    if unit == "Hz":
        return f"{sign}{value:.2f} Hz"
    if unit == "%":
        return f"{sign}{value:.0f}%"
    if unit == "dB":
        return f"{sign}{value:.1f} dB"
    if unit == "0-100":
        return f"{sign}{value:.0f}"
    if unit == "cents/s":
        return f"{sign}{value:.0f} cents/s"
    if unit == "log units":
        return f"{sign}{value:.2f}"
    if unit == "1 - r":
        return f"{value:.2f}"
    return f"{sign}{value:.2f} {unit}".strip()


def _where(instances: list[MetricComparison]) -> str:
    labels: list[str] = []
    for m in sorted(instances, key=lambda x: x.ref_start):
        label = m.label.strip()
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return ""
    quoted = [f"“{label}”" for label in labels]
    if len(quoted) == 1:
        return f"on {quoted[0]}"
    if len(quoted) == 2:
        return f"on {quoted[0]} and {quoted[1]}"
    return f"on {quoted[0]}, {quoted[1]} and {len(quoted) - 2} more"


def _median(values: list[Any]) -> float | None:
    clean = [v for v in values if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]
    return float(np.median(clean)) if clean else None


def _fill(template: str, context: dict[str, str]) -> str:
    class Safe(dict):
        def __missing__(self, key: str) -> str:
            return "n/a"

    return template.format_map(Safe(context))


def _text_context(finding: Finding, transposition: float) -> dict[str, str]:
    definition = METRICS[finding.metric_id]
    unit = definition.unit
    refs = [m.ref_value for m in finding.instances if isinstance(m.ref_value, (int, float))]
    users = [m.user_value for m in finding.instances if isinstance(m.user_value, (int, float))]
    diffs = [m.difference for m in finding.instances if m.difference is not None]
    ref_med = _median(refs)
    user_med = _median(users)
    diff_med = _median(diffs)
    worst = max(finding.instances, key=lambda m: (m.normalized or 0.0) * m.confidence)
    display_unit = "ms" if finding.metric_id == "vibrato.onset" else unit
    context = {
        "where": _where(finding.instances),
        "n": str(len(finding.instances)),
        "ref": fmt(ref_med, display_unit),
        "user": fmt(user_med, display_unit),
        "diff": fmt(diff_med, display_unit, signed=True),
        "absdiff": fmt(abs(diff_med) if diff_med is not None else None, display_unit),
        "worst": f"{worst.label} ({fmt(worst.difference, display_unit, signed=True)})",
        "transposition": "no transposition"
        if abs(transposition) < 0.5
        else f"removing a {transposition:+.0f} semitone transposition",
        "ref_abs": fmt(abs(ref_med) if ref_med is not None else None, display_unit),
        "ref_attack": fmt(_median([m.evidence.get("reference_attack_ms") for m in finding.instances]), "ms"),
        "bpm": f"{(ref_med or 5.5) * 60.0 / 4.0:.0f}",
        "band": str(worst.evidence.get("band", "the strongest band")),
    }
    if finding.metric_id in {"articulation.onset_type"}:
        context["ref"] = str(worst.ref_value)
        context["user"] = str(worst.user_value)
    return context


def _practice_region(finding: Finding, ref: RecordingView) -> dict[str, Any]:
    worst = max(finding.instances, key=lambda m: (m.normalized or 0.0) * m.confidence)
    start, end = worst.ref_start, worst.ref_end
    container = None
    if finding.category in {"timing", "breath", "dynamics"} and worst.level == "phrase":
        container = next((p for p in ref.by_level("phrase") if p.id == worst.ref_segment_id), None)
    if container is None:
        for level in ("word", "syllable", "note"):
            container = next(
                (s for s in ref.by_level(level) if s.start_s <= 0.5 * (start + end) < s.end_s), None
            )
            if container is not None:
                break
    phrase = next(
        (p for p in ref.by_level("phrase") if p.start_s - 0.01 <= 0.5 * (start + end) < p.end_s + 0.01), None
    )
    if container is not None:
        start, end = min(start, container.start_s), max(end, container.end_s)
    lead = PHRASE_LEAD_S if finding.category in {"timing", "breath"} else PRACTICE_PAD_S
    loop_start = max(0.0, start - lead)
    loop_end = end + PRACTICE_PAD_S
    if phrase is not None and finding.category not in {"timing", "breath"}:
        loop_start = max(loop_start, phrase.start_s - PRACTICE_PAD_S)
        loop_end = min(loop_end, phrase.end_s + PRACTICE_PAD_S)
    return {
        "ref_start": round(loop_start, 3),
        "ref_end": round(loop_end, 3),
        "focus_start": round(worst.ref_start, 3),
        "focus_end": round(worst.ref_end, 3),
        "segment_id": worst.ref_segment_id,
        "user_segment_id": worst.user_segment_id,
        "user_start": worst.user_start,
        "user_end": worst.user_end,
        "label": worst.label,
        "phrase_id": phrase.id if phrase else None,
        "phrase_label": phrase.label if phrase else None,
    }


def build_findings(
    metrics: list[MetricComparison],
    ref: RecordingView,
    transposition: float = 0.0,
    history: dict[str, int] | None = None,
    overrides: dict[str, str] | None = None,
    dismissals: dict[str, int] | None = None,
) -> list[Finding]:
    history = history or {}
    overrides = overrides or {}
    dismissals = dismissals or {}
    by_metric: dict[str, list[MetricComparison]] = defaultdict(list)
    for m in metrics:
        if m.usable:
            by_metric[m.metric_id].append(m)
    findings: list[Finding] = []
    for metric_id, items in by_metric.items():
        definition = METRICS[metric_id]
        if definition.weight <= 0:
            continue
        groups: dict[str, list[MetricComparison]] = defaultdict(list)
        for m in items:
            if (m.normalized or 0.0) >= MIN_FINDING_Z and m.direction not in {
                "similar",
                "matches",
                "unknown",
            }:
                groups[m.direction].append(m)
        for direction, instances in groups.items():
            zs = [min(m.normalized or 0.0, 4.0) for m in instances]
            confidences = [m.confidence for m in instances]
            systematic = (
                len(instances) >= SYSTEMATIC_MIN_INSTANCES
                and len(instances) / max(1, len(items)) >= SYSTEMATIC_FRACTION
            )
            magnitude = float(np.median(zs)) if systematic else float(np.max(zs))
            confidence = float(np.median(confidences)) + min(0.15, 0.05 * (len(instances) - 1))
            confidence = min(1.0, confidence)
            importance = definition.importance * float(np.mean([m.importance for m in instances]))
            key = f"{metric_id}:{direction}"
            previous = int(history.get(key, 0))
            persistence = 1.0 + PERSISTENCE_STEP * min(previous, PERSISTENCE_CAP)
            trainability = 0.6 + 0.4 * definition.trainability
            action = overrides.get(key) or overrides.get(metric_id)
            override = BOOST_FACTOR if action == "boost" else 1.0
            override *= max(DISMISS_FLOOR, 1.0 - DISMISS_STEP * int(dismissals.get(key, 0)))
            magnitude_term = 1.0 - math.exp(-magnitude)
            priority = (
                magnitude_term
                * confidence
                * importance
                * persistence
                * trainability
                * override
                * (SYSTEMATIC_BONUS if systematic else 1.0)
            )
            guidance = GUIDANCE.get((metric_id, direction))
            finding = Finding(
                key=key,
                metric_id=metric_id,
                category=definition.category,
                direction=direction,
                title=guidance.title if guidance else f"{definition.name}: {direction}",
                instances=sorted(instances, key=lambda m: m.ref_start),
                magnitude=round(magnitude, 3),
                max_z=round(float(np.max(zs)), 3),
                confidence=round(confidence, 3),
                importance=round(importance, 3),
                persistence=round(persistence, 3),
                trainability=round(trainability, 3),
                override=round(override, 3),
                priority=round(priority, 4),
                systematic=systematic,
                eligible=len(items),
                history_takes=previous,
            )
            finding.ranking = {
                "magnitude_term": round(magnitude_term, 3),
                "magnitude_basis": "median of instances (systematic)"
                if systematic
                else "largest instance (one-off)",
                "confidence": finding.confidence,
                "perceptual_importance": finding.importance,
                "persistence_multiplier": finding.persistence,
                "trainability_factor": finding.trainability,
                "systematic_bonus": SYSTEMATIC_BONUS if systematic else 1.0,
                "user_override": finding.override,
                "formula": "priority = (1 - e^-magnitude) x confidence x importance x persistence x trainability x systematic x override",
                "user_action": action,
            }
            if action == "ignore":
                finding.tier = "ignored"
            _attach_texts(finding, guidance, transposition, ref)
            findings.append(finding)
    findings = merge_families(findings, by_metric)
    findings.sort(key=lambda f: f.priority, reverse=True)
    return findings


def merge_families(findings: list[Finding], by_metric: dict[str, list[MetricComparison]]) -> list[Finding]:
    removed: set[int] = set()
    for lead_index, lead in enumerate(findings):
        members = FAMILIES.get(lead.metric_id)
        if not members:
            continue
        lead_segments = {m.ref_segment_id for m in lead.instances}
        for index, other in enumerate(findings):
            if index == lead_index or index in removed or other.metric_id not in members:
                continue
            shared = sum(1 for m in other.instances if m.ref_segment_id in lead_segments)
            if shared / max(1, len(other.instances)) >= FAMILY_OVERLAP:
                lead.corroborating.append(
                    {
                        "metric_id": other.metric_id,
                        "title": other.title,
                        "direction": other.direction,
                        "instances": len(other.instances),
                        "summary": other.texts.get("expert"),
                    }
                )
                removed.add(index)
        for metric_id in members:
            definition = METRICS[metric_id]
            if definition.weight > 0:
                continue
            same = [
                m
                for m in by_metric.get(metric_id, [])
                if m.ref_segment_id in lead_segments and (m.normalized or 0.0) >= MIN_FINDING_Z
            ]
            if same:
                diffs = [m.difference for m in same if m.difference is not None]
                lead.corroborating.append(
                    {
                        "metric_id": metric_id,
                        "title": definition.name,
                        "direction": same[0].direction,
                        "instances": len(same),
                        "summary": f"{definition.name}: median difference {fmt(_median(diffs), definition.unit, signed=True)} on the same notes.",
                    }
                )
    return [f for i, f in enumerate(findings) if i not in removed]


def _attach_texts(
    finding: Finding, guidance: Guidance | None, transposition: float, ref: RecordingView
) -> None:
    definition = METRICS[finding.metric_id]
    context = _text_context(finding, transposition)
    finding.practice = _practice_region(finding, ref)
    if guidance is None:
        finding.texts = {
            "beginner": f"{definition.name} differs from the reference {context['where']}.",
            "expert": f"{definition.name}: median difference {context['diff']} (n={context['n']}).",
            "adjust": "Listen to the A/B comparison on the practice loop and imitate the reference.",
            "adjust_basis": "stylistic",
            "exercise": "Loop the region and alternate reference and take.",
            "why": definition.why,
            "layers": ["waveform"],
        }
    else:
        finding.texts = {
            "beginner": _fill(guidance.beginner, context),
            "expert": _fill(guidance.expert, context),
            "adjust": _fill(guidance.adjust, context),
            "adjust_basis": guidance.adjust_basis,
            "exercise": _fill(guidance.exercise, context),
            "why": definition.why,
            "layers": list(guidance.layers),
        }
    finding.texts["confidence_label"] = confidence_label(finding.confidence)
    finding.texts["importance_label"] = importance_label(finding.importance)
    finding.texts["pattern"] = (
        f"Systematic: {len(finding.instances)} of {finding.eligible} measured places show this."
        if finding.systematic
        else f"One-off: seen in {len(finding.instances)} of {finding.eligible} measured places."
    )
    if finding.history_takes:
        finding.texts["history"] = f"Also found in {finding.history_takes} earlier take(s) of this reference."
    finding.evidence = [
        {
            "label": m.label,
            "ref_start": m.ref_start,
            "ref_end": m.ref_end,
            "reference": fmt(m.ref_value, "ms" if finding.metric_id == "vibrato.onset" else definition.unit)
            if isinstance(m.ref_value, (int, float))
            else m.ref_value,
            "take": fmt(m.user_value, "ms" if finding.metric_id == "vibrato.onset" else definition.unit)
            if isinstance(m.user_value, (int, float))
            else m.user_value,
            "difference": fmt(
                m.difference, "ms" if finding.metric_id == "vibrato.onset" else definition.unit, signed=True
            ),
            "z": m.normalized,
            "confidence": m.confidence,
            "segment_id": m.ref_segment_id,
            "basis": definition.basis,
        }
        for m in sorted(finding.instances, key=lambda x: -(x.normalized or 0.0) * x.confidence)
    ]


def confidence_label(value: float) -> str:
    if value >= 0.8:
        return "High confidence"
    if value >= 0.6:
        return "Medium-high confidence"
    if value >= 0.45:
        return "Medium confidence"
    if value >= 0.25:
        return "Low confidence"
    return "Insufficient confidence"


def importance_label(value: float) -> str:
    if value >= 0.75:
        return "High perceptual importance"
    if value >= 0.55:
        return "Medium-high perceptual importance"
    if value >= 0.4:
        return "Medium perceptual importance"
    return "Lower perceptual importance"


def already_good(metrics: list[MetricComparison], flagged: set[str] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    flagged = flagged or set()
    by_metric: dict[str, list[MetricComparison]] = defaultdict(list)
    for m in metrics:
        if m.usable:
            by_metric[m.metric_id].append(m)
    for metric_id, items in by_metric.items():
        if len(items) < 2 or METRICS[metric_id].weight <= 0 or metric_id in flagged:
            continue
        zs = [m.normalized or 0.0 for m in items]
        conf = float(np.median([m.confidence for m in items]))
        if float(np.median(zs)) < GOOD_Z and float(np.percentile(zs, 90)) < 1.0 and conf >= 0.5:
            definition = METRICS[metric_id]
            diffs = [abs(m.difference) for m in items if m.difference is not None]
            typical = (
                fmt(float(np.median(diffs)), definition.unit)
                if diffs and definition.kind == "difference"
                else "matches"
            )
            out.append(
                {
                    "metric_id": metric_id,
                    "category": definition.category,
                    "name": definition.name,
                    "text": f"{definition.name}: typically {typical} from the reference across {len(items)} places."
                    if definition.kind == "difference"
                    else f"{definition.name}: matches the reference in {len(items)} of {len(items)} places.",
                    "confidence": round(conf, 3),
                    "count": len(items),
                    "importance": definition.importance,
                }
            )
    out.sort(key=lambda x: (-float(x["importance"]), -int(x["count"])))
    return out


def dont_worry(findings: list[Finding]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finding in findings:
        definition = METRICS[finding.metric_id]
        reason = None
        if definition.anatomy_dependent and not (finding.systematic and finding.magnitude >= 2.0):
            reason = "Partly determined by voice anatomy and microphone; chase it only after the items above."
        elif finding.priority < LOW_VALUE_PRIORITY and finding.confidence >= MIN_FINDING_CONFIDENCE:
            reason = "Measurable but unlikely to change how the performance is heard."
        elif finding.tier == "ignored":
            reason = "You chose to ignore this type of feedback."
        if reason:
            out.append(
                {
                    "key": finding.key,
                    "title": finding.title,
                    "category": finding.category,
                    "reason": reason,
                    "magnitude": finding.magnitude,
                    "confidence": finding.confidence,
                }
            )
    return out


def coaching_report(
    metrics: list[MetricComparison],
    ref: RecordingView,
    transposition: float = 0.0,
    history: dict[str, int] | None = None,
    overrides: dict[str, str] | None = None,
    dismissals: dict[str, int] | None = None,
    category_scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings = build_findings(metrics, ref, transposition, history, overrides, dismissals)
    worry = dont_worry(findings)
    worry_keys = {w["key"] for w in worry}
    actionable = [
        f
        for f in findings
        if f.confidence >= MIN_FINDING_CONFIDENCE and f.key not in worry_keys and f.tier != "ignored"
    ]
    uncertain = [
        f
        for f in findings
        if f.confidence < MIN_FINDING_CONFIDENCE and f.max_z >= UNCERTAIN_Z and f.tier != "ignored"
    ]
    for index, finding in enumerate(actionable):
        finding.tier = "primary" if index == 0 else ("secondary" if index <= 2 else "minor")
    for finding in uncertain:
        finding.tier = "uncertain"
    good = already_good(
        metrics,
        {f.metric_id for f in actionable + uncertain}
        | {c["metric_id"] for f in actionable for c in f.corroborating},
    )
    next_focus = None
    if actionable:
        top = actionable[0]
        layers = list(top.texts.get("layers", []))
        next_focus = {
            "finding_key": top.key,
            "title": top.title,
            "category": top.category,
            "headline": f"Work on this first: {top.title.lower()}.",
            "why": top.texts.get("why"),
            "adjust": top.texts.get("adjust"),
            "adjust_basis": top.texts.get("adjust_basis"),
            "exercise": top.texts.get("exercise"),
            "loop": top.practice,
            "show_layers": layers,
            "hide_layers": [
                layer
                for layer in (
                    "formants",
                    "vibrato",
                    "loudness",
                    "breath",
                    "phonetic",
                    "vowel_space",
                    "spectrogram",
                )
                if layer not in layers
            ],
            "confidence": top.confidence,
            "priority": top.priority,
            "reasoning": _focus_reasoning(top, actionable[1:3]),
        }
    summary = _summary_text(actionable, good, category_scores)
    return {
        "version": COACHING_VERSION,
        "summary": summary,
        "primary": [f.to_dict() for f in actionable[:1]],
        "secondary": [f.to_dict() for f in actionable[1:3]],
        "minor": [f.to_dict() for f in actionable[3:]],
        "uncertain": [f.to_dict() for f in uncertain],
        "already_good": good,
        "dont_worry": worry,
        "next_focus": next_focus,
        "findings": [f.to_dict() for f in findings],
    }


def _focus_reasoning(top: Finding, runners_up: list[Finding]) -> str:
    parts = [
        f"{top.title} ranks first: {top.texts.get('confidence_label', '').lower()}, {top.texts.get('importance_label', '').lower()}",
        "systematic across the take" if top.systematic else "most pronounced in one place",
    ]
    if top.history_takes:
        parts.append(f"and it appeared in {top.history_takes} earlier take(s)")
    text = ", ".join(parts) + "."
    if runners_up:
        text += " Next in line: " + "; ".join(f.title.lower() for f in runners_up) + "."
    return text


def _summary_text(
    actionable: list[Finding], good: list[dict[str, Any]], category_scores: dict[str, Any] | None
) -> str:
    if not actionable:
        if good:
            return (
                "No reliable differences large enough to be worth practising were found. "
                + f"Strongest matches: {', '.join(str(g['name']).lower() for g in good[:3])}."
            )
        return "Not enough reliable measurements to give coaching for this take."
    top = actionable[0]
    parts = [
        f"The biggest reliable difference is {top.title.lower()} ({top.texts.get('confidence_label', '').lower()})."
    ]
    if len(actionable) > 1:
        parts.append("Also notable: " + ", ".join(f.title.lower() for f in actionable[1:3]) + ".")
    if good:
        parts.append("Already close: " + ", ".join(str(g["name"]).lower() for g in good[:3]) + ".")
    return " ".join(parts)


def why_different(
    metrics: list[MetricComparison],
    ref: RecordingView,
    start_s: float,
    end_s: float,
    transposition: float = 0.0,
    history: dict[str, int] | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    inside = [m for m in metrics if min(m.ref_end, end_s) - max(m.ref_start, start_s) > 0]
    findings = build_findings(inside, ref, transposition, history, overrides)
    eligible = [f for f in findings if f.confidence >= MIN_FINDING_CONFIDENCE and f.tier != "ignored"]
    ranked = [f for f in eligible if not METRICS[f.metric_id].anatomy_dependent] + [
        f for f in eligible if METRICS[f.metric_id].anatomy_dependent
    ]
    categories_present = sorted({m.category for m in inside if m.usable})
    close: list[dict[str, Any]] = []
    for category in categories_present:
        items = [m for m in inside if m.category == category and m.usable and METRICS[m.metric_id].weight > 0]
        if items and max(m.normalized or 0.0 for m in items) < GOOD_Z * 1.5:
            close.append(
                {
                    "category": category,
                    "label": CATEGORY_LABELS[category],
                    "text": f"{CATEGORY_LABELS[category]} is already close here ({len(items)} measurements within tolerance).",
                }
            )
    low_conf = [
        m
        for m in inside
        if m.normalized is not None
        and m.confidence < MIN_FINDING_CONFIDENCE
        and (m.normalized or 0) >= UNCERTAIN_Z
    ]
    insufficient = sorted({METRICS[m.metric_id].name for m in low_conf})
    explanation = {
        "region": {"start_s": round(start_s, 3), "end_s": round(end_s, 3)},
        "primary": [f.to_dict() for f in ranked[:1]],
        "secondary": [f.to_dict() for f in ranked[1:3]],
        "minor": [f.to_dict() for f in ranked[3:6]],
        "already_close": close,
        "insufficient_confidence": [
            {
                "name": name,
                "text": f"{name} differs here but the measurement confidence is too low to interpret.",
            }
            for name in insufficient
        ],
        "measurements_considered": len(inside),
    }
    if not inside:
        explanation["message"] = "No measurements overlap this region. Select a region inside a sung phrase."
    elif not ranked:
        explanation["message"] = "No reliable difference large enough to matter was found in this region."
    return explanation
