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


def analyze_audio(
    pcm16_mono: bytes,
    sample_rate: int,
    config: VadConfig,
    vad: Any | None = None,
) -> AudioAnalysis:
    overall_dbfs = rms_dbfs(pcm16_mono)
    if not config.enabled:
        keep = overall_dbfs >= config.min_rms_dbfs
        return AudioAnalysis(keep, overall_dbfs, None, float(keep), 1)

    if vad is None:
        import webrtcvad

        vad = webrtcvad.Vad(config.aggressiveness)

    frame_bytes = sample_rate * config.frame_ms // 1_000 * 2
    frames = [
        pcm16_mono[offset : offset + frame_bytes]
        for offset in range(0, len(pcm16_mono) - frame_bytes + 1, frame_bytes)
    ]
    if not frames:
        return AudioAnalysis(False, overall_dbfs, None, 0.0, 0)

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
    return AudioAnalysis(keep, overall_dbfs, snr_db, speech_ratio, len(frames))
