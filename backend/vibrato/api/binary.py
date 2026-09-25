from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np

from ..analysis.features import FeatureSet

DISPLAY_TRACKS = (
    "f0_hz",
    "f0_conf",
    "voiced",
    "pitch_agreement",
    "octave_conflict",
    "intensity_db",
    "loudness_db",
    "level_rel_db",
    "hnr_db",
    "cpps_db",
    "h1h2_db",
    "f1_hz",
    "f2_hz",
    "f3_hz",
    "f4_hz",
    "b1_hz",
    "b2_hz",
    "formant_conf",
    "formant_agreement",
    "centroid_hz",
    "spr_db",
    "tilt_db_oct",
    "alpha_ratio_db",
    "high_ratio_db",
    "sibilance_ratio_db",
    "flux",
    "zcr",
    "f0_praat",
    "f0_yin",
    "f0_pyin",
    "f0_crepe",
    "f1_lpc_hz",
    "f2_lpc_hz",
)


def encode_bundle(header: dict[str, Any], arrays: list[tuple[str, np.ndarray]]) -> bytes:
    offsets: dict[str, dict[str, int]] = {}
    payload = bytearray()
    for name, array in arrays:
        data = np.ascontiguousarray(array, dtype="<f4")
        offsets[name] = {"offset": len(payload), "length": int(data.size)}
        payload.extend(data.tobytes())
    header = {**header, "arrays": offsets}
    encoded = json.dumps(header, default=str).encode("utf-8")
    padding = (-(4 + len(encoded))) % 4
    encoded += b" " * padding
    return struct.pack("<I", len(encoded)) + encoded + bytes(payload)


def feature_bundle(features: FeatureSet, tracks: tuple[str, ...] = DISPLAY_TRACKS) -> bytes:
    arrays = [(name, features.tracks[name]) for name in tracks if name in features.tracks]
    header = {
        "n": features.n,
        "hop_s": features.hop_s,
        "duration_s": features.duration_s,
        "meta": {k: v for k, v in features.meta.items() if k != "band_centers_hz"},
    }
    return encode_bundle(header, arrays)


def encode_matrix(header: dict[str, Any], matrix: np.ndarray) -> bytes:
    encoded = json.dumps(header, default=str).encode("utf-8")
    padding = (-(4 + len(encoded))) % 4
    encoded += b" " * padding
    return struct.pack("<I", len(encoded)) + encoded + np.ascontiguousarray(matrix, dtype=np.uint8).tobytes()
