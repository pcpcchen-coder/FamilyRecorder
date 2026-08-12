from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from family_recorder.config import VadConfig

FLOOR_DBFS = -120.0


@dataclass(frozen=True)
class AudioAnalysis:
    keep: bool
    rms_dbfs: float
    snr_db: float | None
    speech_ratio: float
    frame_count: int
    low_frequency_ratio: float = 0.0
    tonal_energy_ratio: float = 0.0


def rms_dbfs(pcm16_mono: bytes) -> float:
    if not pcm16_mono:
        return FLOOR_DBFS
    samples = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float64)
    if not samples.size:
        return FLOOR_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= 0:
        return FLOOR_DBFS
    return max(FLOOR_DBFS, 20 * math.log10(rms / 32768.0))


def _energy(pcm16_mono: bytes) -> float:
    samples = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float64)
    if not samples.size:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def spectral_noise_metrics(pcm16_mono: bytes, sample_rate: int) -> tuple[float, float]:
    """Return low-frequency and narrow tonal energy ratios for noise filtering."""
    samples = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float64)
    if samples.size < 256 or sample_rate <= 0:
        return 0.0, 0.0

    frame_size = min(4_096, int(samples.size))
    if frame_size < 256:
        return 0.0, 0.0
    hop = max(1, frame_size // 2)
    window = np.hanning(frame_size)
    accumulated = np.zeros(frame_size // 2 + 1, dtype=np.float64)
    frame_count = 0
    for offset in range(0, samples.size - frame_size + 1, hop):
        spectrum = np.fft.rfft(samples[offset : offset + frame_size] * window)
        accumulated += np.square(np.abs(spectrum))
        frame_count += 1
    if not frame_count:
        return 0.0, 0.0

    power = accumulated / frame_count
    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    speech_band = (frequencies >= 80.0) & (frequencies <= min(4_000.0, sample_rate / 2))
    low_band = (frequencies >= 80.0) & (frequencies <= 300.0)
    band_power = power[speech_band]
    total = float(np.sum(band_power))
    if total <= 0 or not band_power.size:
        return 0.0, 0.0

    low_frequency_ratio = float(np.sum(power[low_band]) / total)
    peak_bins = min(12, int(band_power.size))
    tonal_energy_ratio = float(np.partition(band_power, -peak_bins)[-peak_bins:].sum() / total)
    return (
        max(0.0, min(1.0, low_frequency_ratio)),
        max(0.0, min(1.0, tonal_energy_ratio)),
    )


def analyze_audio(
    pcm16_mono: bytes,
    sample_rate: int,
    config: VadConfig,
    vad: Any | None = None,
) -> AudioAnalysis:
    overall_dbfs = rms_dbfs(pcm16_mono)
    low_frequency_ratio, tonal_energy_ratio = spectral_noise_metrics(
        pcm16_mono,
        sample_rate,
    )
    if not config.enabled:
        keep = overall_dbfs >= config.min_rms_dbfs
        return AudioAnalysis(
            keep,
            overall_dbfs,
            None,
            float(keep),
            1,
            low_frequency_ratio,
            tonal_energy_ratio,
        )

    if vad is None:
        import webrtcvad

        vad = webrtcvad.Vad(config.aggressiveness)

    frame_bytes = sample_rate * config.frame_ms // 1_000 * 2
    frames = [
        pcm16_mono[offset : offset + frame_bytes]
        for offset in range(0, len(pcm16_mono) - frame_bytes + 1, frame_bytes)
    ]
    if not frames:
        return AudioAnalysis(
            False,
            overall_dbfs,
            None,
            0.0,
            0,
            low_frequency_ratio,
            tonal_energy_ratio,
        )

    speech_flags = [bool(vad.is_speech(frame, sample_rate)) for frame in frames]
    speech_ratio = sum(speech_flags) / len(speech_flags)
    paired_frames = zip(frames, speech_flags, strict=True)
    pairs = list(paired_frames)
    signal_levels = [_energy(frame) for frame, speech in pairs if speech]
    noise_levels = [_energy(frame) for frame, speech in pairs if not speech]

    snr_db: float | None = None
    if signal_levels and noise_levels:
        signal = float(np.median(signal_levels))
        noise = max(float(np.median(noise_levels)), 1.0)
        snr_db = max(-20.0, min(80.0, 20 * math.log10(max(signal, 1.0) / noise)))

    keep = overall_dbfs >= config.min_rms_dbfs and speech_ratio >= config.min_speech_ratio
    return AudioAnalysis(
        keep,
        overall_dbfs,
        snr_db,
        speech_ratio,
        len(frames),
        low_frequency_ratio,
        tonal_energy_ratio,
    )
