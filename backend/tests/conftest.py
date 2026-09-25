from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from vibrato.analysis.pipeline import RecordingAnalysis, run_analysis
from vibrato.config import Settings, configure
from vibrato.demo.songs import DEMO_LYRICS, octave_down_take, reference_performance, take_performance
from vibrato.demo.synth import Rendered, render

SR = 44100


def harmonic_tone(
    f0: np.ndarray, sr: int = SR, harmonics: int = 20, rolloff: float = 0.7, level: float = 0.2
) -> np.ndarray:
    phase = 2 * np.pi * np.cumsum(f0) / sr
    signal = np.zeros_like(phase)
    for k in range(1, harmonics + 1):
        mask = k * f0 < sr * 0.45
        signal += np.where(mask, rolloff ** (k - 1) * np.sin(k * phase), 0.0)
    return level * signal / np.max(np.abs(signal))


def pad(
    x: np.ndarray, before: float = 0.5, after: float = 0.5, sr: int = SR, noise: float = 1e-5, seed: int = 0
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y = np.concatenate([np.zeros(int(before * sr)), x, np.zeros(int(after * sr))])
    return y + noise * rng.standard_normal(y.size)


def wav_bytes(x: np.ndarray, sr: int = SR, subtype: str = "PCM_16", fmt: str = "WAV") -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, x.astype(np.float32), sr, format=fmt, subtype=subtype)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def rendered() -> dict[str, Rendered]:
    return {
        "reference": render(reference_performance()),
        "take1": render(take_performance(1)),
        "take3": render(take_performance(3)),
        "octave": render(octave_down_take()),
    }


@pytest.fixture(scope="session")
def analyses(rendered: dict[str, Rendered]) -> dict[str, RecordingAnalysis]:
    return {
        name: run_analysis(r.audio, r.sample_rate, -78.0, lyrics=DEMO_LYRICS) for name, r in rendered.items()
    }


@pytest.fixture()
def isolated_settings(tmp_path: Path) -> Settings:
    return configure(Settings(data_dir=tmp_path / "data", workers=2, deterministic=True))


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    from vibrato.api.app import create_app

    settings = Settings(data_dir=tmp_path_factory.mktemp("api") / "data", workers=2, deterministic=True)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
