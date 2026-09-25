from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .voice_quality import breathiness_index

BREATHY_INDEX = 55.0
PRESSED_H1H2_DROP_DB = 4.0
PRESSED_MAX_INDEX = 20.0
MAX_CONFIDENCE = 0.7
MIN_REPORT_CONFIDENCE = 0.45


@register
class PhonationAnalyzer(Analyzer):
    id = "phonation"
    version = "1.0.0"
    category = "phonation"
    label = "Phonation type (inferred)"
    description = "Probable phonation label per note (breathy, modal, pressed-leaning) with the acoustic evidence behind it."
    dependencies = ("cpps_db", "h1h2_db", "hnr_db")
    supported_segment_types = ("note",)
    experimental = True
    method = (
        "Labels are inferred, not measured. 'Breathy' requires a CPPS-based breathiness index of at least 55. "
        "'Pressed-leaning' requires a clean signal (index at most 20) and H1-H2 at least 4 dB below the singer's own "
        "median for the same lyric vowel. Everything else is 'modal'. Labels below 45% confidence are withheld."
    )
    assumptions = (
        "H1-H2 is only compared within the same vowel because F1 strongly affects it.",
        "Without airflow or EGG data, 'flow' phonation cannot be distinguished from modal phonation; it is not reported separately.",
    )
    limitations = ("Noise, reverb and microphone distance shift CPPS and HNR.",)

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        quality = {
            r.segment_id: r for r in ctx.shared.get("voice_quality_results", []) if r.segment_level == "note"
        }
        vowel_of_note: dict[str, str] = ctx.shared.get("note_vowels", {})
        by_vowel: dict[str, list[float]] = defaultdict(list)
        for note_id, result in quality.items():
            h1h2 = result.number("h1h2_db")
            if h1h2 is not None:
                by_vowel[vowel_of_note.get(note_id, "?")].append(h1h2)
        medians = {k: float(np.median(v)) for k, v in by_vowel.items() if len(v) >= 2}
        results: list[AnalysisResult] = []
        for note in ctx.hierarchy.by_level("note"):
            builder = self.builder(note)
            ctx.apply_quality(builder, "phonation")
            vq = quality.get(note.id)
            if vq is None or vq.number("cpps_db") is None:
                results.append(
                    builder.flag("no_voice_quality_data").factor(0.2, "no voice-quality measurements").build()
                )
                continue
            index = breathiness_index(vq.number("cpps_db"))
            h1h2 = vq.number("h1h2_db")
            vowel = vowel_of_note.get(note.id, "?")
            median = medians.get(vowel)
            evidence: list[dict[str, Any]] = [
                {
                    "metric": "breathiness_index",
                    "value": index,
                    "note": "CPPS-based (0 = clear, 100 = very breathy)",
                }
            ]
            label = "modal"
            strength = 0.5
            if index is not None and index >= BREATHY_INDEX:
                label = "breathy"
                strength = min(1.0, 0.5 + (index - BREATHY_INDEX) / 60.0)
            elif (
                index is not None
                and index <= PRESSED_MAX_INDEX
                and h1h2 is not None
                and median is not None
                and h1h2 <= median - PRESSED_H1H2_DROP_DB
            ):
                label = "pressed-leaning"
                strength = min(1.0, 0.45 + (median - h1h2 - PRESSED_H1H2_DROP_DB) / 10.0)
                evidence.append(
                    {
                        "metric": "h1h2_db",
                        "value": h1h2,
                        "note": f"{median - h1h2:.1f} dB below this singer's median on '{vowel}'",
                    }
                )
            else:
                distance_to_breathy = (BREATHY_INDEX - (index or 0.0)) / BREATHY_INDEX
                strength = min(1.0, 0.45 + 0.5 * distance_to_breathy)
            if h1h2 is not None and label != "pressed-leaning":
                evidence.append({"metric": "h1h2_db", "value": h1h2, "note": "uncorrected, vowel-dependent"})
            hnr = vq.number("hnr_db")
            if hnr is not None:
                evidence.append({"metric": "hnr_db", "value": hnr, "note": "harmonics-to-noise ratio"})
            confidence = min(MAX_CONFIDENCE, vq.confidence * strength)
            builder.factor(confidence, "phonation labels are inferred from acoustics")
            withheld = builder.confidence < MIN_REPORT_CONFIDENCE
            builder.add("label", "uncertain" if withheld else label, "", Basis.INFERRED)
            builder.add("candidate_label", label, "", Basis.INFERRED)
            builder.add("breathiness_index", index, "0-100", Basis.DERIVED)
            builder.support(evidence=evidence, vowel=vowel, vowel_h1h2_median=median)
            if withheld:
                builder.flag("label_withheld_low_confidence")
            builder.interpret(
                "uncertain" if withheld else label,
                "Not enough acoustic evidence to label this note."
                if withheld
                else f"Probably {label} phonation, based on the evidence listed.",
                Basis.INFERRED,
            )
            results.append(builder.build())
        return results
