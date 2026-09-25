from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d

from .canonical import CanonicalAudio
from .decode import DecodedAudio
from .loudness import integrated_loudness

CATEGORIES = (
    "pitch",
    "timing",
    "vowel",
    "vibrato",
    "dynamics",
    "phonation",
    "articulation",
    "breath",
    "timbre",
)

FRAME_S = 0.05
HOP_S = 0.025
CLIP_LEVEL = 0.999
CLIP_MIN_RUN = 3
CLIP_MERGE_S = 0.05
SILENCE_MIN_S = 1.5
EDGE_SILENCE_TRIM_S = 0.75
FLOOR_DB = -120.0
LOW_LEVEL_PEAK_DBFS = -30.0
LOW_LEVEL_ACTIVE_DBFS = -42.0
TRUE_PEAK_OVERSAMPLE = 4
TRUE_PEAK_MAX_SECONDS = 600.0
REVERB_RT_WARNING_S = 0.6
FLOOR_CLUSTER_DB = 3.0
MIN_PAUSE_S = 0.3
SPECTRUM_FLOOR_DB = -160.0
CLIFF_MIN_HZ = 2000.0
CLIFF_WIDTH_HZ = 600.0
CLIFF_DROP_DB = 18.0
CLIFF_SUSTAIN_DB = 30.0


@dataclass
class QualityIssue:
    code: str
    severity: str
    title: str
    what: str
    why: str
    action: str
    value: float | None = None
    confidence: float = 1.0
    affects: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    duration_s: float
    source_sample_rate: int
    source_channels: int
    lossy: bool
    peak_dbfs: float
    true_peak_dbfs: float | None
    rms_dbfs: float
    lufs_integrated: float | None
    dc_offset: float
    clipped_samples: int
    clipped_fraction: float
    clipped_regions: list[list[float]]
    noise_floor_dbfs: float
    active_level_dbfs: float
    snr_db: float
    snr_reliable: bool
    silence_regions: list[list[float]]
    leading_silence_s: float
    trailing_silence_s: float
    trim_suggestion: list[float] | None
    bandwidth_hz: float | None
    bandwidth_limited: bool
    reverb_rt_estimate_s: float | None
    reverb_confidence: float
    stereo_coherence: float | None
    mixdown: str
    notes: list[str]
    issues: list[QualityIssue]
    factors: dict[str, float]
    factor_reasons: dict[str, list[str]]
    overall_quality: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _db(value: np.ndarray | float) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return np.maximum(20.0 * np.log10(np.maximum(np.asarray(value, dtype=np.float64), 1e-12)), FLOOR_DB)


def frame_rms_db(
    x: np.ndarray, sample_rate: int, frame_s: float = FRAME_S, hop_s: float = HOP_S
) -> tuple[np.ndarray, np.ndarray]:
    frame = max(1, round(frame_s * sample_rate))
    hop = max(1, round(hop_s * sample_rate))
    if len(x) < frame:
        value = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0
        return np.array([0.0]), _db(np.array([value]))
    squared = x.astype(np.float64) ** 2
    cumulative = np.concatenate([[0.0], np.cumsum(squared)])
    starts = np.arange(0, len(x) - frame + 1, hop)
    mean_square = (cumulative[starts + frame] - cumulative[starts]) / frame
    times = (starts + frame / 2) / sample_rate
    return times, _db(np.sqrt(mean_square))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    if mask.size == 0:
        return []
    padded = np.concatenate([[False], mask, [False]])
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2])]


def detect_clipping(samples: np.ndarray, sample_rate: int) -> tuple[int, list[list[float]]]:
    total = 0
    spans: list[tuple[float, float]] = []
    for channel in samples:
        mask = np.abs(channel) >= CLIP_LEVEL
        for start, end in _runs(mask):
            if end - start >= CLIP_MIN_RUN:
                total += end - start
                spans.append((start / sample_rate, end / sample_rate))
    spans.sort()
    merged: list[list[float]] = []
    for span_start, span_end in spans:
        if merged and span_start - merged[-1][1] <= CLIP_MERGE_S:
            merged[-1][1] = max(merged[-1][1], span_end)
        else:
            merged.append([span_start, span_end])
    return total, [[round(a, 3), round(b, 3)] for a, b in merged]


def true_peak_dbfs(samples: np.ndarray, sample_rate: int) -> float | None:
    if samples.shape[1] / sample_rate > TRUE_PEAK_MAX_SECONDS:
        return None
    chunk = sample_rate * 10
    overlap = 64
    peak = 0.0
    for channel in samples:
        for start in range(0, len(channel), chunk):
            block = channel[max(0, start - overlap) : start + chunk + overlap].astype(np.float64)
            if block.size < 8:
                continue
            upsampled = signal.resample_poly(block, TRUE_PEAK_OVERSAMPLE, 1)
            peak = max(peak, float(np.max(np.abs(upsampled))))
    return float(_db(peak))


def estimate_noise_floor(rms_db: np.ndarray) -> tuple[float, float, bool]:
    ordered = np.sort(rms_db)
    p10 = np.percentile(ordered, 10)
    floor = float(np.mean(ordered[ordered <= p10])) if np.any(ordered <= p10) else float(ordered[0])
    active = rms_db[rms_db > floor + 10.0]
    active_level = float(np.percentile(active, 90)) if active.size else float(np.percentile(rms_db, 95))
    near_floor = rms_db <= floor + FLOOR_CLUSTER_DB
    longest = max((end - start for start, end in _runs(near_floor)), default=0)
    reliable = (longest * HOP_S >= MIN_PAUSE_S and active_level - floor >= 6.0) or floor <= -80.0
    return floor, active_level, reliable


def find_silences(
    times: np.ndarray, rms_db: np.ndarray, floor: float, active: float, duration: float
) -> tuple[list[list[float]], float, float]:
    threshold = min(floor + 10.0, active - 25.0)
    silent = rms_db < threshold
    regions: list[list[float]] = []
    leading = 0.0
    trailing = 0.0
    for start, end in _runs(silent):
        t0 = max(0.0, float(times[start]) - HOP_S)
        t1 = min(duration, float(times[end - 1]) + HOP_S)
        if start == 0:
            leading = t1
        if end == len(silent):
            trailing = duration - t0
        if t1 - t0 >= SILENCE_MIN_S:
            regions.append([round(t0, 3), round(t1, 3)])
    return regions, leading, trailing


def estimate_bandwidth(x: np.ndarray, sample_rate: int) -> tuple[float | None, bool]:
    n_fft = 4096
    if len(x) < n_fft * 2:
        return None, False
    freqs, _, spec = signal.stft(
        x.astype(np.float64), fs=sample_rate, nperseg=n_fft, noverlap=n_fft // 2, boundary=None
    )
    power = np.abs(spec) ** 2
    frame_energy = power.sum(axis=0)
    if frame_energy.size == 0 or frame_energy.max() <= 0:
        return None, False
    loud = frame_energy >= np.percentile(frame_energy, 60)
    ltas_db = np.maximum(10.0 * np.log10(np.maximum(power[:, loud].mean(axis=1), 1e-30)), SPECTRUM_FLOOR_DB)
    smooth = uniform_filter1d(ltas_db, 9, mode="nearest")
    bin_hz = freqs[1] - freqs[0]
    width = max(2, round(CLIFF_WIDTH_HZ / bin_hz))
    lo = int(np.searchsorted(freqs, CLIFF_MIN_HZ))
    hi = len(freqs) - 3 * width - 1
    if hi <= lo:
        return float(freqs[-1]), False
    drops = smooth[lo:hi] - smooth[lo + width : hi + width]
    index = lo + int(np.argmax(drops))
    drop = float(drops[index - lo])
    plateau = float(np.mean(smooth[max(0, index - width) : index + 1]))
    after = float(np.mean(smooth[index + width : index + 3 * width]))
    if drop < CLIFF_DROP_DB or plateau - after < CLIFF_SUSTAIN_DB:
        return float(freqs[-1]), False
    below = np.flatnonzero(smooth[index - width :] < plateau - 6.0)
    cutoff = float(freqs[index - width + below[0]]) if below.size else float(freqs[index])
    nyquist = sample_rate / 2.0
    return cutoff, cutoff < 0.9 * min(nyquist, 20000.0)


def estimate_reverb(x: np.ndarray, sample_rate: int) -> tuple[float | None, float, int]:
    _, level = frame_rms_db(x, sample_rate, frame_s=0.02, hop_s=0.01)
    if level.size < 50:
        return None, 0.0, 0
    active_level = float(np.percentile(level, 95))
    loud = level >= active_level - 15.0
    estimates: list[float] = []
    fits: list[float] = []
    index = 15
    while index < len(level) - 30:
        if loud[index - 15 : index].all() and level[index] < level[index - 1] - 1.0:
            start_level = float(np.max(level[index - 5 : index]))
            window = level[index : index + 80]
            if window.size and window.min() < start_level - 25.0:
                rel = window - start_level
                first = np.flatnonzero(rel <= -5.0)
                last = np.flatnonzero(rel <= -25.0)
                if first.size and last.size and last[0] - first[0] >= 3:
                    segment = rel[first[0] : last[0] + 1]
                    t = np.arange(segment.size) * 0.01
                    slope, intercept = np.polyfit(t, segment, 1)
                    predicted = slope * t + intercept
                    ss_res = float(np.sum((segment - predicted) ** 2))
                    ss_tot = float(np.sum((segment - segment.mean()) ** 2)) or 1e-9
                    if slope < 0:
                        estimates.append(-60.0 / slope)
                        fits.append(1.0 - ss_res / ss_tot)
                index += 60
                continue
        index += 1
    if not estimates:
        return None, 0.0, 0
    rt = float(np.median(estimates))
    fit_quality = float(np.clip(np.median(fits), 0.0, 1.0))
    confidence = float(np.clip(len(estimates) / 5.0, 0.0, 1.0) * fit_quality)
    return rt, confidence, len(estimates)


def stereo_coherence(samples: np.ndarray, sample_rate: int) -> float | None:
    if samples.shape[0] < 2 or samples.shape[1] < 4096:
        return None
    left = samples[0].astype(np.float64)
    right = samples[1].astype(np.float64)
    if np.allclose(left, right, atol=1e-6):
        return 1.0
    freqs, coh = signal.coherence(left, right, fs=sample_rate, nperseg=2048)
    band = (freqs >= 200) & (freqs <= 4000)
    return float(np.mean(coh[band])) if band.any() else None


def _add_factor(
    factors: dict[str, float], reasons: dict[str, list[str]], categories: list[str], value: float, reason: str
) -> None:
    for category in categories:
        factors[category] = factors.get(category, 1.0) * value
        reasons.setdefault(category, []).append(reason)


def analyze_signal_quality(
    decoded: DecodedAudio, canonical: CanonicalAudio, is_reference: bool
) -> QualityReport:
    x = canonical.samples
    sr = canonical.sample_rate
    duration = canonical.duration_s
    peak = float(_db(np.max(np.abs(decoded.samples)))) if decoded.samples.size else FLOOR_DB
    rms = float(_db(np.sqrt(np.mean(decoded.samples.astype(np.float64) ** 2))))
    lufs = integrated_loudness(decoded.samples.astype(np.float64), decoded.sample_rate)
    dc = float(np.max(np.abs(decoded.samples.mean(axis=1))))
    clipped, clip_regions = detect_clipping(decoded.samples, decoded.sample_rate)
    clipped_fraction = clipped / max(1, decoded.samples.size)
    tpeak = true_peak_dbfs(decoded.samples, decoded.sample_rate)
    times, level = frame_rms_db(x, sr)
    floor, active_level, snr_reliable = estimate_noise_floor(level)
    snr = active_level - floor
    silences, leading, trailing = find_silences(times, level, floor, active_level, duration)
    bandwidth, limited = estimate_bandwidth(x, sr)
    rt, reverb_conf, _ = estimate_reverb(x, sr)
    coherence = stereo_coherence(decoded.samples, decoded.sample_rate)

    issues: list[QualityIssue] = []
    factors: dict[str, float] = dict.fromkeys(CATEGORIES, 1.0)
    reasons: dict[str, list[str]] = {}
    subject = "reference" if is_reference else "take"

    if clipped > 0:
        severe = clipped_fraction > 1e-3
        issues.append(
            QualityIssue(
                code="clipping",
                severity="critical" if severe else "warning",
                title="Clipping detected",
                what=f"{clipped} samples ({clipped_fraction * 100:.3f}%) hit full scale in {len(clip_regions)} region(s).",
                why="The input level was too high for the recorder, so waveform peaks were flattened. This adds distortion that looks like roughness or pressed phonation.",
                action="Lower the input gain so the loudest notes peak around -6 dBFS, then record again.",
                value=clipped_fraction,
                affects=["phonation", "timbre", "dynamics"],
            )
        )
        penalty = 0.55 if severe else 0.8
        _add_factor(
            factors,
            reasons,
            ["phonation", "timbre"],
            penalty,
            "clipping distorts harmonic and noise measurements",
        )
        _add_factor(
            factors, reasons, ["dynamics"], 0.85 if severe else 0.95, "clipping flattens loudness peaks"
        )
    if dc > 0.01:
        issues.append(
            QualityIssue(
                code="dc_offset",
                severity="warning" if dc > 0.03 else "info",
                title="DC offset",
                what=f"The waveform is shifted off-centre by {dc:.3f} of full scale.",
                why="Usually caused by an audio interface or microphone preamp fault. Vibrato removes it with a 20 Hz high-pass filter before analysis.",
                action="No action needed for analysis; fix the interface if it appears on every recording.",
                value=dc,
            )
        )
    if snr_reliable and snr < 30.0:
        severe = snr < 18.0
        issues.append(
            QualityIssue(
                code="low_snr",
                severity="critical" if severe else "warning",
                title="Background noise",
                what=f"Estimated signal-to-noise ratio is {snr:.0f} dB (noise floor {floor:.0f} dBFS).",
                why="Background noise masks breath noise and the high harmonics that breathiness, HNR and CPP depend on.",
                action="Record in a quieter room, move closer to the microphone, or turn off fans and air conditioning.",
                value=snr,
                affects=["phonation", "breath", "articulation", "vowel"],
            )
        )
        _add_factor(
            factors, reasons, ["phonation", "breath"], 0.5 if severe else 0.8, f"estimated SNR {snr:.0f} dB"
        )
        _add_factor(
            factors,
            reasons,
            ["articulation", "vowel", "timbre"],
            0.7 if severe else 0.9,
            f"estimated SNR {snr:.0f} dB",
        )
        _add_factor(factors, reasons, ["pitch"], 0.9 if severe else 1.0, f"estimated SNR {snr:.0f} dB")
    if not snr_reliable:
        issues.append(
            QualityIssue(
                code="snr_unknown",
                severity="info",
                title="Noise floor uncertain",
                what="The recording has no clear pauses, so the noise floor could not be measured reliably.",
                why="Signal-to-noise estimation needs a moment of silence to hear the room on its own.",
                action="Leave half a second of silence at the start of future takes.",
                confidence=0.5,
            )
        )
    if leading > EDGE_SILENCE_TRIM_S or trailing > EDGE_SILENCE_TRIM_S:
        issues.append(
            QualityIssue(
                code="edge_silence",
                severity="info",
                title="Silence at the edges",
                what=f"{leading:.1f} s of silence at the start and {trailing:.1f} s at the end.",
                why="Long silences do not affect measurements but make the timeline harder to navigate.",
                action="Use the suggested trim region when exporting or re-recording.",
            )
        )
    if silences:
        issues.append(
            QualityIssue(
                code="long_silence",
                severity="info",
                title="Long silences",
                what=f"{len(silences)} silence(s) longer than {SILENCE_MIN_S:.1f} s.",
                why="Long gaps are treated as section boundaries.",
                action="None needed.",
            )
        )
    if decoded.sample_rate < 16000:
        issues.append(
            QualityIssue(
                code="low_sample_rate",
                severity="critical",
                title="Very low sample rate",
                what=f"The source sample rate is {decoded.sample_rate} Hz.",
                why=f"Everything above {decoded.sample_rate / 2:.0f} Hz is missing, so sibilance, breath noise and brightness cannot be measured.",
                action="Use a recording made at 44.1 kHz or 48 kHz.",
                affects=["articulation", "timbre", "breath", "phonation"],
            )
        )
        _add_factor(
            factors, reasons, ["articulation", "timbre", "breath"], 0.4, "source sample rate below 16 kHz"
        )
        _add_factor(factors, reasons, ["phonation"], 0.7, "source sample rate below 16 kHz")
    elif decoded.sample_rate < 22050:
        issues.append(
            QualityIssue(
                code="low_sample_rate",
                severity="warning",
                title="Low sample rate",
                what=f"The source sample rate is {decoded.sample_rate} Hz.",
                why="High-frequency detail such as sibilance and air is missing.",
                action="Prefer 44.1 kHz or 48 kHz recordings.",
                affects=["articulation", "timbre"],
            )
        )
        _add_factor(factors, reasons, ["articulation", "timbre"], 0.7, "source sample rate below 22.05 kHz")
    if limited and bandwidth is not None:
        severe = bandwidth < 11000
        issues.append(
            QualityIssue(
                code="band_limited",
                severity="warning" if severe else "info",
                title="Band-limited audio",
                what=f"The spectrum stops abruptly at about {bandwidth / 1000:.1f} kHz.",
                why="This is typical of lossy encoding (MP3, AAC, streaming rips) or a low-quality recording chain; content above the cut-off was discarded.",
                action="Use a lossless or higher-bitrate source if one is available.",
                value=bandwidth,
                affects=["articulation", "timbre"],
            )
        )
        _add_factor(
            factors,
            reasons,
            ["articulation", "timbre"],
            0.65 if severe else 0.9,
            f"band-limited at {bandwidth / 1000:.1f} kHz",
        )
    if decoded.lossy:
        issues.append(
            QualityIssue(
                code="lossy_codec",
                severity="info",
                title="Lossy source format",
                what=f"The file was stored with a lossy codec ({decoded.source_subtype or decoded.source_format}).",
                why="Lossy codecs remove quiet high-frequency detail and can smear breath noise, which slightly affects voice-quality measurements.",
                action="Use WAV or FLAC when you have a choice.",
                affects=["phonation", "timbre"],
            )
        )
        _add_factor(factors, reasons, ["phonation", "timbre"], 0.92, "lossy source codec")
    if peak < LOW_LEVEL_PEAK_DBFS or active_level < LOW_LEVEL_ACTIVE_DBFS:
        issues.append(
            QualityIssue(
                code="low_level",
                severity="warning",
                title="Low recording level",
                what=f"Peaks reach only {peak:.0f} dBFS (typical singing level {active_level:.0f} dBFS).",
                why="Quiet recordings sit close to the noise floor, which lowers the reliability of breath and voice-quality analysis.",
                action="Increase the input gain until the loudest notes peak between -12 and -6 dBFS.",
                value=peak,
                affects=["phonation", "breath"],
            )
        )
        _add_factor(factors, reasons, ["phonation", "breath"], 0.85, "low recording level")
    if rt is not None and rt > REVERB_RT_WARNING_S and reverb_conf >= 0.3:
        issues.append(
            QualityIssue(
                code="reverb",
                severity="warning",
                title="Possible reverb",
                what=f"Sound keeps ringing after phrases end (decay time estimate {rt:.1f} s).",
                why="Room reverb or added effects smear note endings, consonants and breath noise, and inflate formant bandwidths.",
                action="Use a dry vocal (no reverb or delay) and record in a room with soft furnishings.",
                value=rt,
                confidence=reverb_conf,
                affects=["articulation", "breath", "phonation", "timing", "vowel"],
            )
        )
        _add_factor(factors, reasons, ["articulation", "breath"], 0.6, f"reverberant decay (~{rt:.1f} s)")
        _add_factor(factors, reasons, ["phonation", "vowel"], 0.75, f"reverberant decay (~{rt:.1f} s)")
        _add_factor(factors, reasons, ["timing"], 0.9, f"reverberant decay (~{rt:.1f} s)")
    if coherence is not None and coherence < 0.75:
        issues.append(
            QualityIssue(
                code="stereo_decorrelated",
                severity="info",
                title="Wide stereo image",
                what=f"The left and right channels are only partly similar (coherence {coherence:.2f}).",
                why="Stereo reverb, chorus or doubled vocals panned apart produce this. It can indicate a vocal double.",
                action="Use a single dry mono vocal if possible.",
                value=coherence,
                confidence=0.5,
            )
        )
    if duration < 1.0:
        issues.append(
            QualityIssue(
                code="too_short",
                severity="warning",
                title="Very short recording",
                what=f"The recording is {duration:.2f} s long.",
                why="Vibrato, dynamics and timing need several notes to be measured meaningfully.",
                action="Record at least one full phrase.",
                affects=["vibrato", "dynamics", "timing"],
            )
        )
        _add_factor(factors, reasons, ["vibrato", "dynamics", "timing"], 0.6, "very short recording")
    if decoded.repaired_nonfinite:
        issues.append(
            QualityIssue(
                code="nonfinite_samples",
                severity="warning",
                title="Corrupt samples repaired",
                what=f"{decoded.repaired_nonfinite} invalid samples (NaN or infinity) were replaced with silence.",
                why="The file contains damaged data.",
                action="Re-export the recording from its source.",
            )
        )
    if is_reference:
        serious = [i for i in issues if i.severity in {"warning", "critical"}]
        if serious:
            issues.append(
                QualityIssue(
                    code="bad_reference",
                    severity="warning",
                    title="Reference quality limits the analysis",
                    what=f"The {subject} has {len(serious)} quality problem(s): "
                    + ", ".join(i.title.lower() for i in serious)
                    + ".",
                    why="Every comparison inherits the reference's weaknesses; affected categories are shown with reduced confidence.",
                    action="If you can, use a cleaner isolated vocal as the reference.",
                )
            )
    overall = float(np.clip(np.prod([factors[c] for c in CATEGORIES]) ** (1.0 / len(CATEGORIES)), 0.0, 1.0))
    trim = None
    if leading > EDGE_SILENCE_TRIM_S or trailing > EDGE_SILENCE_TRIM_S:
        trim = [round(max(0.0, leading - 0.25), 3), round(min(duration, duration - trailing + 0.25), 3)]
    return QualityReport(
        duration_s=round(duration, 4),
        source_sample_rate=decoded.sample_rate,
        source_channels=decoded.channels,
        lossy=decoded.lossy,
        peak_dbfs=round(peak, 2),
        true_peak_dbfs=None if tpeak is None else round(tpeak, 2),
        rms_dbfs=round(rms, 2),
        lufs_integrated=None if lufs is None else round(lufs, 2),
        dc_offset=round(dc, 5),
        clipped_samples=clipped,
        clipped_fraction=clipped_fraction,
        clipped_regions=clip_regions,
        noise_floor_dbfs=round(floor, 2),
        active_level_dbfs=round(active_level, 2),
        snr_db=round(snr, 2),
        snr_reliable=snr_reliable,
        silence_regions=silences,
        leading_silence_s=round(leading, 3),
        trailing_silence_s=round(trailing, 3),
        trim_suggestion=trim,
        bandwidth_hz=None if bandwidth is None else round(bandwidth, 1),
        bandwidth_limited=limited,
        reverb_rt_estimate_s=None if rt is None else round(rt, 3),
        reverb_confidence=round(reverb_conf, 3),
        stereo_coherence=None if coherence is None else round(coherence, 3),
        mixdown=canonical.mixdown,
        notes=canonical.notes,
        issues=issues,
        factors={k: round(v, 4) for k, v in factors.items()},
        factor_reasons=reasons,
        overall_quality=round(overall, 4),
    )
