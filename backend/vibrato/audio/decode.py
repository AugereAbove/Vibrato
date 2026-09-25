from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .errors import AudioDecodeError, AudioValidationError

SUPPORTED_EXTENSIONS = (
    ".wav",
    ".wave",
    ".flac",
    ".mp3",
    ".ogg",
    ".oga",
    ".opus",
    ".aif",
    ".aiff",
    ".m4a",
    ".aac",
    ".mp4",
    ".webm",
    ".caf",
    ".w64",
    ".rf64",
)

LOSSY_HINTS = ("MP3", "MPEG", "VORBIS", "OPUS", "AAC", "M4A", "MP4", "WEBM", "WMA", "AC3")

_SUBTYPE_BITS = {
    "PCM_S8": 8,
    "PCM_U8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
    "ALAC_16": 16,
    "ALAC_20": 20,
    "ALAC_24": 24,
    "ALAC_32": 32,
    "DPCM_8": 8,
    "DPCM_16": 16,
    "DWVW_12": 12,
    "DWVW_16": 16,
    "DWVW_24": 24,
}

_PYAV_BITS = {
    "u8": 8,
    "u8p": 8,
    "s16": 16,
    "s16p": 16,
    "s32": 32,
    "s32p": 32,
    "flt": 32,
    "fltp": 32,
    "dbl": 64,
    "dblp": 64,
}


@dataclass
class DecodedAudio:
    samples: np.ndarray
    sample_rate: int
    source_format: str
    source_subtype: str | None
    bit_depth: int | None
    decoder: str
    lossy: bool
    repaired_nonfinite: int = 0

    @property
    def channels(self) -> int:
        return int(self.samples.shape[0])

    @property
    def duration_s(self) -> float:
        return float(self.samples.shape[1]) / float(self.sample_rate)


def _is_lossy(*labels: str | None) -> bool:
    joined = " ".join(label.upper() for label in labels if label)
    return any(hint in joined for hint in LOSSY_HINTS)


def _decode_soundfile(path: Path) -> DecodedAudio:
    info = sf.info(str(path))
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    subtype = info.subtype
    bits = _SUBTYPE_BITS.get(subtype)
    return DecodedAudio(
        samples=np.ascontiguousarray(data.T),
        sample_rate=int(rate),
        source_format=info.format,
        source_subtype=subtype,
        bit_depth=bits,
        decoder="libsndfile",
        lossy=_is_lossy(info.format, subtype),
    )


def _decode_pyav(path: Path) -> DecodedAudio:
    import av

    with av.open(str(path)) as container:
        streams = [s for s in container.streams if s.type == "audio"]
        if not streams:
            raise ValueError("the file contains no audio stream")
        stream: Any = streams[0]
        codec: Any = stream.codec_context
        rate = int(codec.sample_rate or stream.rate or 0)
        if rate <= 0:
            raise ValueError("the audio stream reports no sample rate")
        channel_count = int(codec.layout.nb_channels) if codec.layout is not None else 1
        layout = "mono" if channel_count == 1 else ("stereo" if channel_count == 2 else codec.layout.name)
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        chunks: list[np.ndarray] = []
        frames: Any = container.decode(stream)
        for frame in frames:
            for converted in resampler.resample(frame):
                chunks.append(converted.to_ndarray())
        for converted in resampler.resample(None):
            chunks.append(converted.to_ndarray())
        codec_name = str(codec.name)
        format_name = str(container.format.name)
        sample_format = str(codec.format.name) if codec.format is not None else ""
    if not chunks:
        raise ValueError("no audio frames could be decoded")
    data = np.concatenate(chunks, axis=1).astype(np.float32)
    lossless = codec_name.startswith("pcm_") or codec_name in {"flac", "alac", "wavpack", "tta", "ape"}
    return DecodedAudio(
        samples=np.ascontiguousarray(data),
        sample_rate=rate,
        source_format=format_name.upper(),
        source_subtype=codec_name.upper(),
        bit_depth=_PYAV_BITS.get(sample_format) if lossless else None,
        decoder="ffmpeg (PyAV)",
        lossy=not lossless,
    )


def pyav_available() -> bool:
    try:
        import av

        return bool(av.__version__)
    except ImportError:
        return False


def decode_file(path: Path) -> DecodedAudio:
    if not path.exists():
        raise AudioDecodeError(
            what=f"The file '{path.name}' could not be found.",
            why="It may have been moved or deleted after it was selected.",
            action="Select the file again.",
            code="file_missing",
        )
    if path.stat().st_size == 0:
        raise AudioDecodeError(
            what=f"'{path.name}' is empty.",
            why="The file has zero bytes, so it contains no audio.",
            action="Check that the export or download finished, then import it again.",
            code="file_empty",
        )
    errors: list[str] = []
    decoded: DecodedAudio | None = None
    try:
        decoded = _decode_soundfile(path)
    except Exception as exc:
        errors.append(f"libsndfile: {exc}")
    if decoded is None:
        try:
            decoded = _decode_pyav(path)
        except ImportError:
            errors.append("FFmpeg decoder (PyAV) is not installed")
        except Exception as exc:
            errors.append(f"FFmpeg (PyAV): {exc}")
    if decoded is None:
        extension = path.suffix.lower()
        if extension in {".m4a", ".aac", ".mp4", ".webm", ".opus"} and not pyav_available():
            action = "Install the optional decoder with 'pip install av' (setup does this by default) or convert the file to WAV or FLAC."
        else:
            action = "Convert the file to WAV or FLAC with any audio editor and import it again."
        raise AudioDecodeError(
            what=f"'{path.name}' could not be decoded as audio.",
            why="None of the available decoders recognised the data. The file may be corrupt, DRM-protected, or not an audio file.",
            action=action,
            code="decode_failed",
            details=errors,
        )
    if decoded.samples.size == 0 or decoded.samples.shape[1] == 0:
        raise AudioValidationError(
            what=f"'{path.name}' decoded to zero samples.",
            why="The container was readable but held no audio data.",
            action="Re-export the recording and import it again.",
            code="no_samples",
        )
    nonfinite = ~np.isfinite(decoded.samples)
    if nonfinite.any():
        decoded.repaired_nonfinite = int(nonfinite.sum())
        decoded.samples = np.where(nonfinite, 0.0, decoded.samples).astype(np.float32)
    return decoded


def validate_duration(decoded: DecodedAudio, min_s: float, max_s: float, name: str) -> None:
    duration = decoded.duration_s
    if duration < min_s:
        raise AudioValidationError(
            what=f"'{name}' is only {duration * 1000:.0f} ms long.",
            why=f"At least {min_s:.2f} s of audio is needed to measure pitch, timing and voice quality.",
            action="Import a longer excerpt that contains at least one sung note.",
            code="too_short",
        )
    if duration > max_s:
        raise AudioValidationError(
            what=f"'{name}' is {duration / 60:.1f} minutes long.",
            why=f"Recordings longer than {max_s / 60:.0f} minutes exceed the analysis limit for interactive use.",
            action="Trim the recording to the section you want to practise (a few phrases is ideal).",
            code="too_long",
        )
