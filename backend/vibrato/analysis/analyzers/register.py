from __future__ import annotations

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis

HIGH_RANGE_PERCENTILE = 75.0
FALSETTO_H1H2_RISE_DB = 6.0
TRANSITION_JUMP_DB = 6.0
MAX_CONFIDENCE = 0.55
MIN_REPORT_CONFIDENCE = 0.35


@register
class RegisterAnalyzer(Analyzer):
    id = "register"
    version = "1.0.0"
    category = "phonation"
    label = "Register (experimental)"
    description = (
        "Probable register per note (modal-like, light/falsetto-like, fry) and abrupt register transitions."
    )
    dependencies = ("f0_hz", "h1h2_db", "cpps_db")
    supported_segment_types = ("note",)
    experimental = True
    method = (
        "Light/falsetto-like: the note sits in the top quarter of the singer's range, H1-H2 is at least 6 dB above the "
        "singer's median for the same vowel, and CPPS is below the singer's median. Fry comes from the nonlinear-event "
        "detector. Transitions are adjacent legato notes whose H1-H2 changes by 6 dB or more. Confidence is capped at 55%."
    )
    assumptions = ("Register cannot be observed directly from audio; these are acoustic correlates only.",)
    limitations = ("Mixed registers and trained singers' smooth passaggi are usually labelled 'uncertain'.",)

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        quality = {
            r.segment_id: r for r in ctx.shared.get("voice_quality_results", []) if r.segment_level == "note"
        }
        vowel_of_note: dict[str, str] = ctx.shared.get("note_vowels", {})
        notes = ctx.hierarchy.by_level("note")
        centers = np.array([float(n.props.get("center_midi", np.nan)) for n in notes])
        high_threshold = (
            float(np.nanpercentile(centers, HIGH_RANGE_PERCENTILE))
            if np.isfinite(centers).sum() >= 4
            else np.inf
        )
        cpps_values = [q.number("cpps_db") for q in quality.values() if q.number("cpps_db") is not None]
        cpps_median = float(np.median(cpps_values)) if cpps_values else None
        h1h2_by_vowel: dict[str, list[float]] = {}
        for note_id, q in quality.items():
            if q.number("h1h2_db") is not None:
                h1h2_by_vowel.setdefault(vowel_of_note.get(note_id, "?"), []).append(
                    float(q.number("h1h2_db"))
                )
        fry_events = [e for e in ctx.hierarchy.events if e.type == "fry"]
        results: list[AnalysisResult] = []
        previous: tuple[str, float | None, float] | None = None
        for note, center in zip(notes, centers):
            builder = self.builder(note)
            ctx.apply_quality(builder, "phonation")
            q = quality.get(note.id)
            fry_overlap = sum(
                max(0.0, min(e.end_s, note.end_s) - max(e.start_s, note.start_s)) for e in fry_events
            )
            label = "modal-like"
            strength = 0.5
            h1h2 = q.number("h1h2_db") if q else None
            cpps = q.number("cpps_db") if q else None
            vowel_values = h1h2_by_vowel.get(vowel_of_note.get(note.id, "?"), [])
            vowel_median = float(np.median(vowel_values)) if len(vowel_values) >= 2 else None
            if fry_overlap >= 0.3 * note.duration_s:
                label = "fry"
                strength = 0.8
            elif (
                center >= high_threshold
                and h1h2 is not None
                and vowel_median is not None
                and cpps is not None
                and cpps_median is not None
                and h1h2 >= vowel_median + FALSETTO_H1H2_RISE_DB
                and cpps < cpps_median
            ):
                label = "light/falsetto-like"
                strength = 0.6
            confidence = min(MAX_CONFIDENCE, (q.confidence if q else 0.3) * strength)
            builder.factor(confidence, "register is inferred from acoustic correlates")
            withheld = builder.confidence < MIN_REPORT_CONFIDENCE
            builder.add("label", "uncertain" if withheld else label, "", Basis.EXPERIMENTAL)
            builder.add("candidate_label", label, "", Basis.EXPERIMENTAL)
            builder.add(
                "range_position", "upper" if center >= high_threshold else "lower/middle", "", Basis.DERIVED
            )
            builder.interpret(
                "uncertain" if withheld else label,
                "Register cannot be determined confidently here."
                if withheld
                else f"Probably {label} (acoustic correlates only).",
                Basis.EXPERIMENTAL,
            )
            result = builder.build()
            results.append(result)
            if (
                previous is not None
                and h1h2 is not None
                and previous[1] is not None
                and abs(note.start_s - previous[2]) < 0.05
            ):
                jump = h1h2 - previous[1]
                if abs(jump) >= TRANSITION_JUMP_DB and label != previous[0]:
                    ctx.hierarchy.add_event(
                        "register_transition",
                        note.start_s - 0.05,
                        note.start_s + 0.05,
                        min(0.5, result.confidence),
                        note.id,
                        from_label=previous[0],
                        to_label=label,
                        h1h2_jump_db=round(jump, 1),
                    )
            previous = (label, h1h2, note.end_s)
        return results
