from __future__ import annotations

import numpy as np

from ...dsp.framing import runs
from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis
from .common import nan_mean, nan_median

SUB_F0_CLEAN_DB = -30.0
SUB_F0_CONTAMINATED_DB = -12.0
GAP_TONAL_FRACTION = 0.2
MIN_GAP_S = 0.3


def sub_fundamental_ratio(
    band_levels: np.ndarray, centers: np.ndarray, f0: np.ndarray, voiced: np.ndarray
) -> float | None:
    ratios = []
    for index in np.flatnonzero(voiced & np.isfinite(f0)):
        below = centers < 0.6 * f0[index]
        at = np.abs(np.log2(centers / f0[index])) < 1.0 / 6.0
        if not below.any() or not at.any():
            continue
        below_power = np.sum(10.0 ** (band_levels[below, index] / 10.0))
        at_power = np.sum(10.0 ** (band_levels[at, index] / 10.0))
        ratios.append(10.0 * np.log10(below_power / max(at_power, 1e-20) + 1e-20))
    return float(np.median(ratios)) if len(ratios) >= 20 else None


@register
class QualityAnalyzer(Analyzer):
    id = "quality"
    version = "1.0.0"
    category = "quality"
    label = "Segment quality & contamination"
    description = "Per-phrase signal quality and content-aware contamination checks (energy below the voice's fundamental, tonal content between phrases)."
    dependencies = ("intensity_db", "band_levels", "f0_hz")
    supported_segment_types = ("phrase", "recording")
    method = (
        "An isolated voice has almost no energy below its fundamental; instruments such as bass and kick drum put energy "
        "there. The median ratio of third-octave energy below 0.6xF0 to the band at F0 is computed over voiced frames. "
        "Gaps between phrases are checked for pitched, loud content that is not breath. Phrase quality combines local "
        "SNR, clipping and contamination."
    )
    limitations = (
        "Very quiet accompaniment and doubled vocals may escape detection; results are warnings, not proof.",
    )

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        noise_floor = float(fs.meta.get("noise_floor_db", -90.0))
        bands = fs.matrices["band_levels"].astype(np.float64)
        centers = np.array(fs.meta.get("band_centers_hz", []), dtype=np.float64)
        sub_ratio = (
            sub_fundamental_ratio(bands, centers, fs.tracks["f0_hz"], fs.voiced) if centers.size else None
        )
        inside = np.zeros(fs.n, dtype=bool)
        for phrase in ctx.hierarchy.by_level("phrase"):
            inside[ctx.span(phrase)] = True
        for event in ctx.hierarchy.events:
            if event.type == "breath":
                inside[fs.span(event.start_s, event.end_s)] = True
        yin_voicing = fs.tracks.get("voicing_yin", np.zeros(fs.n))
        gap_mask = ~inside
        gap_frames = [(a, b) for a, b in runs(gap_mask) if (b - a) * fs.hop_s >= MIN_GAP_S]
        gap_total = sum(b - a for a, b in gap_frames)
        tonal = 0
        for a, b in gap_frames:
            tonal += int(np.sum((yin_voicing[a:b] > 0.8) & (fs.tracks["level_rel_db"][a:b] > -35.0)))
        gap_tonal_fraction = tonal / gap_total if gap_total else None
        contamination = 0.0
        evidence: list[str] = []
        if sub_ratio is not None and sub_ratio > SUB_F0_CLEAN_DB:
            contamination = max(
                contamination,
                float(
                    np.clip(
                        (sub_ratio - SUB_F0_CLEAN_DB) / (SUB_F0_CONTAMINATED_DB - SUB_F0_CLEAN_DB), 0.0, 1.0
                    )
                ),
            )
            evidence.append(f"energy below the fundamental is {sub_ratio:.0f} dB relative to it")
        if gap_tonal_fraction is not None and gap_tonal_fraction > GAP_TONAL_FRACTION:
            contamination = max(contamination, float(np.clip(gap_tonal_fraction, 0.0, 1.0)))
            evidence.append(f"{gap_tonal_fraction * 100:.0f}% of the pauses contain pitched sound")
        results: list[AnalysisResult] = []
        clipped_regions = ctx.options.get("clipped_regions", []) or []
        for phrase in ctx.hierarchy.by_level("phrase"):
            span = ctx.span(phrase)
            builder = self.builder(phrase)
            voiced = fs.voiced[span]
            level = nan_mean(fs.tracks["intensity_db"][span][voiced]) if voiced.any() else None
            snr = None if level is None else level - noise_floor
            clipped = sum(
                max(0.0, min(float(b), phrase.end_s) - max(float(a), phrase.start_s))
                for a, b in clipped_regions
            )
            clip_fraction = clipped / max(phrase.duration_s, 1e-6)
            snr_score = 0.5 if snr is None else float(np.clip((snr - 10.0) / 25.0, 0.0, 1.0))
            quality = snr_score * (1.0 - min(1.0, clip_fraction * 20.0)) * (1.0 - 0.6 * contamination)
            builder.add("snr_db", snr, "dB")
            builder.add("clipped_fraction", clip_fraction, "ratio")
            builder.add("quality", quality, "0-1", Basis.DERIVED)
            builder.add(
                "pitch_confidence",
                nan_median(fs.tracks["f0_conf"][span][voiced]) if voiced.any() else None,
                "0-1",
            )
            builder.add(
                "formant_confidence",
                nan_median(fs.tracks["formant_conf"][span][voiced]) if voiced.any() else None,
                "0-1",
            )
            builder.factor(0.9, None)
            results.append(builder.build())
        summary = self.builder(None, 0.0, fs.duration_s)
        summary.add("sub_fundamental_ratio_db", sub_ratio, "dB")
        summary.add("gap_tonal_fraction", gap_tonal_fraction, "ratio")
        summary.add("contamination_score", contamination, "0-1", Basis.DERIVED)
        summary.add("possible_backing", contamination >= 0.4, "", Basis.INFERRED)
        summary.support(evidence=evidence)
        summary.factor(
            0.7 if sub_ratio is not None else 0.3,
            None if sub_ratio is not None else "too little voiced audio for contamination checks",
        )
        results.append(summary.build())
        ctx.shared["contamination"] = {"score": contamination, "evidence": evidence}
        return results
