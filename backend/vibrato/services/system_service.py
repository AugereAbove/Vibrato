from __future__ import annotations

import importlib.util
import os
import platform
import sys
import warnings
from typing import Any

import psutil

from .. import __version__
from ..analysis.base import all_analyzers
from ..analysis.features import FEATURES_VERSION
from ..analysis.pipeline import ANALYZER_ORDER, SEGMENTATION_VERSION, pipeline_version
from ..audio.canonical import CANONICAL_SR, CANONICAL_VERSION, HIGHPASS_HZ
from ..audio.decode import SUPPORTED_EXTENSIONS, pyav_available
from ..coaching.engine import COACHING_VERSION, MIN_FINDING_CONFIDENCE, MIN_FINDING_Z
from ..coaching.knowledge import CATEGORY_HELP, GLOSSARY
from ..compare.comparator import COMPARISON_VERSION
from ..compare.metrics import CATEGORY_WEIGHT_RATIONALE, DEFAULT_CATEGORY_WEIGHTS, METRICS
from ..compare.scoring import SCORE_FORMULA
from ..config import get_settings
from ..db import get_db
from ..db.connection import latest_schema_version
from ..dsp import formants as formant_dsp
from ..dsp import pitch as pitch_dsp
from ..dsp import spectral, voice
from ..dsp.framing import HOP_S
from ..storage import directory_size
from ..synthesis.counterfactual import world_available


def _version(module: str) -> str | None:
    if importlib.util.find_spec(module) is None:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            imported = __import__(module)
        return str(getattr(imported, "__version__", "installed"))
    except Exception:
        return "installed (failed to import)"


def gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "torch": _version("torch"),
        "cuda_available": False,
        "device": "cpu",
        "name": None,
        "memory_gb": None,
    }
    if info["torch"] is None:
        info["note"] = (
            "PyTorch is not installed. All bundled analysis runs on the CPU with NumPy/SciPy/Praat; neural models are optional."
        )
        return info
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info.update(
                {
                    "cuda_available": True,
                    "device": "cuda",
                    "name": props.name,
                    "memory_gb": round(props.total_memory / 1e9, 1),
                }
            )
        else:
            info["note"] = "PyTorch is installed but no CUDA GPU was found; neural models run on the CPU."
    except Exception as exc:
        info["note"] = f"GPU detection failed: {exc}"
    return info


def cache_usage() -> dict[str, Any]:
    settings = get_settings()
    return {
        "derived_bytes": directory_size(settings.derived_dir),
        "originals_bytes": directory_size(settings.originals_dir),
        "renders_bytes": directory_size(settings.renders_dir),
        "exports_bytes": directory_size(settings.exports_dir),
        "database_bytes": settings.db_path.stat().st_size if settings.db_path.exists() else 0,
        "logs_bytes": directory_size(settings.logs_dir),
    }


def model_status() -> list[dict[str, Any]]:
    estimators = pitch_dsp.estimator_status()
    return [
        {
            "id": "praat",
            "name": "Praat (via Parselmouth)",
            "kind": "DSP",
            "available": True,
            "version": _version("parselmouth"),
            "used_for": "Pitch (primary), formants, HNR, jitter/shimmer, PSOLA resynthesis",
            "install": None,
        },
        {
            "id": "yin",
            "name": "YIN pitch estimator",
            "kind": "DSP",
            "available": True,
            "version": pitch_dsp.YIN_VERSION,
            "used_for": "Second pitch estimator and cross-checks",
            "install": None,
        },
        {
            "id": "pyin",
            "name": "Probabilistic YIN",
            "kind": "DSP",
            "available": True,
            "version": pitch_dsp.PYIN_VERSION,
            "used_for": "Optional third pitch estimator (Settings > Analysis)",
            "install": None,
        },
        {
            "id": "crepe",
            "name": "CREPE neural pitch",
            "kind": "neural",
            "available": bool(estimators["crepe"]["available"]),
            "version": _version("torchcrepe"),
            "used_for": "Optional neural pitch estimator; uses the GPU when present",
            "install": "pip install torch torchcrepe (weights ship inside the package; nothing is downloaded at runtime)",
            "device": estimators["crepe"].get("device"),
        },
        {
            "id": "world",
            "name": "WORLD vocoder (pyworld)",
            "kind": "DSP",
            "available": world_available(),
            "version": _version("pyworld"),
            "used_for": "Breathiness counterfactual experiment",
            "install": 'pip install pyworld "setuptools<81"',
        },
        {
            "id": "pyav",
            "name": "FFmpeg decoders (PyAV)",
            "kind": "decoder",
            "available": pyav_available(),
            "version": _version("av"),
            "used_for": "M4A/AAC and other container formats",
            "install": "pip install av",
        },
        {
            "id": "embedding",
            "name": "Learned singing embedding",
            "kind": "neural",
            "available": False,
            "version": None,
            "used_for": "Optional learned style similarity (a non-learned MFCC-statistics embedding is used meanwhile)",
            "install": "Not bundled. The analyzer interface accepts a model; see the Models section of the methods help.",
        },
        {
            "id": "phoneme_aligner",
            "name": "Neural phoneme aligner",
            "kind": "neural",
            "available": False,
            "version": None,
            "used_for": "Phoneme-accurate lyric alignment (the built-in aligner uses lyrics + acoustic phonetic classes)",
            "install": "Not bundled.",
        },
    ]


def system_info() -> dict[str, Any]:
    settings = get_settings()
    process = psutil.Process(os.getpid())
    memory = psutil.virtual_memory()
    db = get_db()
    return {
        "app_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": {
            "logical_cores": psutil.cpu_count(logical=True),
            "physical_cores": psutil.cpu_count(logical=False),
            "processor": platform.processor() or platform.machine(),
            "load_percent": psutil.cpu_percent(interval=None),
        },
        "memory": {
            "total_gb": round(memory.total / 1e9, 2),
            "available_gb": round(memory.available / 1e9, 2),
            "process_rss_mb": round(process.memory_info().rss / 1e6, 1),
        },
        "gpu": gpu_info(),
        "libraries": {
            m: _version(m)
            for m in (
                "numpy",
                "scipy",
                "librosa",
                "soundfile",
                "parselmouth",
                "numba",
                "fastapi",
                "uvicorn",
                "pydantic",
                "av",
                "pyworld",
                "torch",
                "torchcrepe",
                "psutil",
            )
        },
        "data_dir": str(settings.data_dir),
        "cache": cache_usage(),
        "schema_version": db.schema_version(),
        "latest_schema_version": latest_schema_version(),
        "pipeline_version": pipeline_version(),
        "comparison_version": COMPARISON_VERSION,
        "coaching_version": COACHING_VERSION,
        "recovery": db.recovery_status,
        "workers": settings.workers,
        "privacy": {
            "telemetry": False,
            "network_uploads": False,
            "accounts": False,
            "note": "Vibrato processes everything on this computer. It makes no network requests.",
        },
    }


def methods() -> dict[str, Any]:
    analyzers = [a.explain() for a in all_analyzers()]
    order = {name: i for i, name in enumerate(ANALYZER_ORDER)}
    analyzers.sort(key=lambda a: order.get(str(a["id"]), 99))
    return {
        "global": {
            "canonical_audio": f"Every import is decoded, mixed to mono (averaging channels unless they cancel or one is silent), resampled to {CANONICAL_SR} Hz with the SoX high-quality resampler and high-passed at {HIGHPASS_HZ:.0f} Hz (2nd-order Butterworth, zero phase). The original file is kept unchanged. Canonical version {CANONICAL_VERSION}.",
            "frame_grid": f"All frame-level measurements share one grid with a {HOP_S * 1000:.0f} ms hop. Features version {FEATURES_VERSION}; segmentation {SEGMENTATION_VERSION}.",
            "pitch": f"Praat autocorrelation pitch runs twice: first over {pitch_dsp.PITCH_FLOOR_HZ:.0f}-{pitch_dsp.PITCH_CEILING_HZ:.0f} Hz, then over a range adapted to the singer (0.7 x 5th percentile to 1.5 x 95th percentile). A vectorised YIN (threshold {pitch_dsp.YIN_THRESHOLD}) runs on a {pitch_dsp.ANALYSIS_SR} Hz copy. Frames agree when estimates are within {pitch_dsp.AGREE_CENTS:.0f} cents; octave conflicts are flagged and short octave jumps are repaired against a {pitch_dsp.OCTAVE_REPAIR_WINDOW}-frame median. Gaps up to {pitch_dsp.MAX_FILL_GAP_FRAMES * 10} ms are interpolated in the log domain; voiced runs shorter than {pitch_dsp.MIN_VOICED_RUN_FRAMES * 10} ms are dropped.",
            "pitch_confidence": "Frame confidence = Praat voicing strength x estimator agreement factor (1.0 all agree, 0.8 partial, 0.6 no second opinion, 0.3 disagreement or unresolved octave conflict) x level factor (frame level relative to the noise floor).",
            "formants": f"Praat Burg LPC (5 formants, {formant_dsp.WINDOW_S * 1000:.0f} ms window, pre-emphasis from 50 Hz), with the ceiling chosen per recording from {', '.join(str(int(c)) for c in formant_dsp.CEILING_CANDIDATES)} Hz by the most stable F1/F2 tracks. An autocorrelation LPC of order {formant_dsp.LPC_ORDER} provides an independent estimate; agreement within {formant_dsp.AGREEMENT_TOLERANCE * 100:.0f}% raises confidence. Confidence falls linearly between F0 {formant_dsp.HIGH_F0_START:.0f} and {formant_dsp.HIGH_F0_END:.0f} Hz because harmonics become too sparse.",
            "voice_quality": f"CPPS: {voice.CPP_FRAME}-sample frames, {voice.CPP_TIME_SMOOTH}-frame time and {voice.CPP_QUEF_SMOOTH}-bin quefrency smoothing, peak searched within ±15% of the known period and referenced to a linear regression over 1-16.7 ms. Harmonic amplitudes use {voice.HARMONIC_PERIODS:.0f}-period Hann windows evaluated exactly at multiples of F0.",
            "spectral": f"STFT with a {spectral.N_FFT}-point Hann window; third-octave band levels; tilt = regression slope of band levels against log2 frequency over 125 Hz-5 kHz; {spectral.N_MFCC} MFCCs from a {spectral.N_MELS}-band mel spectrum; loudness = K-weighted power in a 100 ms window.",
            "alignment": "Take and reference are aligned with multiscale dynamic time warping (5, 25 and 100 frames per second, banded refinement) on transposition-invariant features: normalised MFCCs, pitch relative to each singer's median, voicing, level and level changes. Locked anchors split the problem into independent segments. Confidence compares the matched frames' distance with the distance between random frame pairs.",
            "normalisation": "Vowels: log-mean (Nearey) normalisation per singer, and for comparisons the median formant ratio between the two voices across matched vowels (from F2, F3 and F1 where F1 is well above F0) is removed. Loudness: relative to each recording's typical singing level. Pitch: whole-semitone transpositions are removed; residual tuning offsets are reported.",
            "scoring": SCORE_FORMULA,
            "category_weights": DEFAULT_CATEGORY_WEIGHTS,
            "category_weight_rationale": CATEGORY_WEIGHT_RATIONALE,
            "coaching": f"Differences become findings when their normalised size exceeds {MIN_FINDING_Z} tolerances and their confidence is at least {MIN_FINDING_CONFIDENCE:.0%}. Priority multiplies saturating magnitude, confidence, perceptual importance, persistence across earlier takes, trainability, a bonus for systematic patterns and any user override.",
            "confidence": "Every measurement multiplies independent confidence factors (tracking quality, estimator agreement, recording quality factors such as clipping, noise, reverb and bandwidth, alignment confidence). Comparisons combine both sides as min(sqrt(ref x take), min(ref, take) + 0.15) x alignment factor. Nothing below 25% confidence is scored; findings need 45%.",
            "supported_formats": sorted(SUPPORTED_EXTENSIONS),
        },
        "analyzers": analyzers,
        "metrics": [m.to_dict() for m in METRICS.values()],
        "categories": CATEGORY_HELP,
        "glossary": GLOSSARY,
        "versions": {
            "pipeline": pipeline_version(),
            "comparison": COMPARISON_VERSION,
            "coaching": COACHING_VERSION,
        },
    }
