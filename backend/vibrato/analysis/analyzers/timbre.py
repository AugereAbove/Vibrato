from __future__ import annotations

import numpy as np

from ..base import AnalysisContext, Analyzer, register
from ..contract import AnalysisResult, Basis, Validity
from .common import nan_mean

BROAD_BANDS = ((0, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000))
EMBEDDING_COEFFICIENTS = 20


def broad_band_profile(band_levels: np.ndarray, centers: np.ndarray, mask: np.ndarray) -> list[float | None]:
    if not mask.any():
        return [None] * len(BROAD_BANDS)
    power = 10.0 ** (band_levels[:, mask] / 10.0)
    mean_power = power.mean(axis=1)
    total = mean_power.sum()
    out: list[float | None] = []
    for lo, hi in BROAD_BANDS:
        selected = (centers >= lo) & (centers < hi)
        out.append(
            float(10.0 * np.log10(mean_power[selected].sum() / total + 1e-12)) if selected.any() else None
        )
    return out


@register
class TimbreAnalyzer(Analyzer):
    id = "timbre"
    version = "1.0.0"
    category = "timbre"
    label = "Timbre & spectral balance"
    description = "Level-independent spectral balance in broad bands, centroid, singing power ratio, alpha ratio and an interpretable spectral-statistics embedding."
    dependencies = ("band_levels", "centroid_hz", "spr_db", "mfcc")
    supported_segment_types = ("note", "phrase", "recording")
    method = (
        "Third-octave band powers of voiced frames are averaged and expressed as each broad band's share of the total "
        "(dB), which removes overall level. The singing power ratio compares the strongest peak in 2-4 kHz with 0-2 kHz. "
        "The embedding is the mean and standard deviation of 20 MFCCs over voiced frames: a simple, non-learned "
        "descriptor kept separate from all interpretable scores."
    )
    assumptions = (
        "Spectral balance also depends on the microphone, room and distance; compare recordings made the same way.",
    )
    limitations = (
        "No learned singer or style embedding model is bundled; the MFCC statistics embedding is a baseline.",
    )

    def analyze(self, ctx: AnalysisContext) -> list[AnalysisResult]:
        fs = ctx.features
        bands = fs.matrices["band_levels"].astype(np.float64)
        centers = np.array(fs.meta.get("band_centers_hz", []), dtype=np.float64)
        voiced = fs.voiced
        results: list[AnalysisResult] = []
        for segment in ctx.hierarchy.by_level("phrase") + ctx.hierarchy.by_level("note"):
            if segment.level == "note":
                span = fs.span(
                    float(segment.props.get("core_start_s", segment.start_s)),
                    float(segment.props.get("core_end_s", segment.end_s)),
                )
            else:
                span = ctx.span(segment)
            mask = np.zeros(fs.n, dtype=bool)
            mask[span] = voiced[span]
            builder = self.builder(segment)
            ctx.apply_quality(builder, "timbre")
            if mask.sum() < 5:
                results.append(
                    builder.flag("too_few_voiced_frames").factor(0.2, "too few voiced frames").build()
                )
                continue
            profile = broad_band_profile(bands, centers, mask)
            for (lo, hi), value in zip(BROAD_BANDS, profile):
                builder.add(f"band_{lo}_{hi}_db", value, "dB re total")
            for key, unit in (
                ("centroid_hz", "Hz"),
                ("rolloff_hz", "Hz"),
                ("spr_db", "dB"),
                ("alpha_ratio_db", "dB"),
                ("hammarberg_db", "dB"),
                ("tilt_db_oct", "dB/octave"),
            ):
                builder.add(key, nan_mean(fs.tracks[key][mask]), unit)
            builder.support(mfcc_mean=fs.matrices["mfcc"][:13, mask].mean(axis=1).tolist())
            builder.factor(min(1.0, 0.3 + mask.sum() / 50.0), "amount of voiced audio")
            results.append(builder.build())
        summary = self.builder(None, 0.0, fs.duration_s)
        if voiced.sum() >= 20:
            mfcc = fs.matrices["mfcc"][:EMBEDDING_COEFFICIENTS, voiced].astype(np.float64)
            embedding = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)])
            summary.add("embedding_dimensions", int(embedding.size), "count")
            summary.add("embedding_kind", "MFCC statistics (non-learned baseline)", "", Basis.DERIVED)
            summary.support(embedding=embedding.round(4).tolist())
            profile = broad_band_profile(bands, centers, voiced)
            summary.support(band_profile=profile)
            summary.add("centroid_hz", nan_mean(fs.tracks["centroid_hz"][voiced]), "Hz")
            summary.factor(0.8, None)
        else:
            summary.validity(Validity.UNAVAILABLE)
        results.append(summary.build())
        learned = self.builder(None, 0.0, fs.duration_s)
        learned.add("embedding_kind", "learned singing embedding", "")
        learned.reason("No learned embedding model is installed; see Settings > Models.")
        learned.validity(Validity.MODEL_UNAVAILABLE)
        learned.flag("model_unavailable")
        result = learned.build()
        result.values["available"] = False
        results.append(result)
        return results
