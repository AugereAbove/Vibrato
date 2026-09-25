from __future__ import annotations

import json
import struct

import numpy as np

BASE_SAMPLES_PER_PEAK = 64
MIN_PEAKS_PER_LEVEL = 512


def build_peak_pyramid(samples: np.ndarray, sample_rate: int) -> dict[str, np.ndarray | int]:
    x = np.clip(samples.astype(np.float32), -1.0, 1.0)
    count = int(np.ceil(len(x) / BASE_SAMPLES_PER_PEAK))
    padded = np.zeros(count * BASE_SAMPLES_PER_PEAK, dtype=np.float32)
    padded[: len(x)] = x
    blocks = padded.reshape(count, BASE_SAMPLES_PER_PEAK)
    levels_min = [blocks.min(axis=1)]
    levels_max = [blocks.max(axis=1)]
    while len(levels_min[-1]) > MIN_PEAKS_PER_LEVEL:
        lo = levels_min[-1]
        hi = levels_max[-1]
        if len(lo) % 2:
            lo = np.append(lo, lo[-1])
            hi = np.append(hi, hi[-1])
        levels_min.append(np.minimum(lo[0::2], lo[1::2]))
        levels_max.append(np.maximum(hi[0::2], hi[1::2]))
    result: dict[str, np.ndarray | int] = {
        "sample_rate": sample_rate,
        "n_samples": len(x),
        "levels": len(levels_min),
    }
    for index, (lo, hi) in enumerate(zip(levels_min, levels_max)):
        interleaved = np.empty(lo.size * 2, dtype=np.int16)
        interleaved[0::2] = np.round(lo * 32767).astype(np.int16)
        interleaved[1::2] = np.round(hi * 32767).astype(np.int16)
        result[f"level_{index}"] = interleaved
    return result


def encode_peak_pyramid(pyramid: dict[str, np.ndarray | int]) -> bytes:
    levels = int(pyramid["levels"])
    header_levels = []
    payload = bytearray()
    for index in range(levels):
        data = np.asarray(pyramid[f"level_{index}"], dtype=np.int16)
        header_levels.append(
            {
                "samples_per_peak": BASE_SAMPLES_PER_PEAK * (2**index),
                "count": int(data.size // 2),
                "offset": len(payload),
            }
        )
        payload.extend(data.astype("<i2").tobytes())
    header = json.dumps(
        {
            "sample_rate": int(pyramid["sample_rate"]),
            "n_samples": int(pyramid["n_samples"]),
            "levels": header_levels,
        }
    ).encode("utf-8")
    padding = (-(4 + len(header))) % 2
    header += b" " * padding
    return struct.pack("<I", len(header)) + header + bytes(payload)
