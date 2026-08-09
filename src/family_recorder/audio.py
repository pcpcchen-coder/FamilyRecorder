from __future__ import annotations

import contextlib
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from family_recorder.config import AudioConfig
from family_recorder.devices import AudioDevice, select_input_device


@dataclass(frozen=True)
class AudioChunk:
    pcm16_mono: bytes
    sample_rate: int
    started_at: datetime
    ended_at: datetime
    overflowed: bool = False


def downmix_pcm16(pcm: bytes, channels: int) -> bytes:
    if channels == 1:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16)
    usable = len(samples) - (len(samples) % channels)
    if usable == 0:
        return b""
    frames = samples[:usable].reshape(-1, channels).astype(np.int32)
    mono = np.rint(frames.mean(axis=1)).clip(-32768, 32767).astype(np.int16)
    return mono.tobytes()


def resample_pcm16(pcm16_mono: bytes, source_rate: int, target_rate: int) -> bytes:
    if source_rate == target_rate or not pcm16_mono:
        return pcm16_mono
    samples = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float64)
    target_length = max(1, round(len(samples) * target_rate / source_rate))
    source_positions = np.arange(len(samples), dtype=np.float64)
    target_positions = np.linspace(0, max(len(samples) - 1, 0), target_length)
    resampled = np.interp(target_positions, source_positions, samples)
    return np.rint(resampled).clip(-32768, 32767).astype(np.int16).tobytes()


def write_wav(path: Path, pcm16_mono: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm16_mono)


class AudioRecorder:
    def __init__(self, config: AudioConfig, sd_module: Any | None = None) -> None:
        self.config = config
        if sd_module is None:
            import sounddevice as sd_module

        self.sd = sd_module
        self.device: AudioDevice | None = None
        self.capture_sample_rate = config.sample_rate

    @contextlib.contextmanager
    def open_stream(self) -> Iterator[Any]:
        self.device = select_input_device(self.config, self.sd)
        requested_channels = min(self.config.channels, self.device.input_channels)
        self.capture_sample_rate = self.config.sample_rate
        try:
            self.sd.check_input_settings(
                device=self.device.index,
                channels=requested_channels,
                dtype="int16",
                samplerate=self.capture_sample_rate,
            )
        except Exception:
            fallback_rate = round(self.device.default_sample_rate)
            if fallback_rate <= 0 or fallback_rate == self.capture_sample_rate:
                raise
            self.sd.check_input_settings(
                device=self.device.index,
                channels=requested_channels,
                dtype="int16",
                samplerate=fallback_rate,
            )
            self.capture_sample_rate = fallback_rate
        with self.sd.RawInputStream(
            samplerate=self.capture_sample_rate,
            device=self.device.index,
            channels=requested_channels,
            dtype="int16",
            blocksize=max(1, self.capture_sample_rate),
        ) as stream:
            yield stream

    def read_chunk(self, stream: Any, seconds: int | float | None = None) -> AudioChunk:
        duration = seconds if seconds is not None else self.config.chunk_seconds
        target_frames = max(1, round(self.capture_sample_rate * duration))
        frames_left = target_frames
        blocks: list[bytes] = []
        overflowed = False
        channels = min(self.config.channels, self.device.input_channels) if self.device else 1
        started_at = datetime.now().astimezone()

        while frames_left:
            request = min(frames_left, self.capture_sample_rate)
            data, block_overflowed = stream.read(request)
            blocks.append(bytes(data))
            overflowed = overflowed or bool(block_overflowed)
            frames_left -= request

        mono = downmix_pcm16(b"".join(blocks), channels)
        mono = resample_pcm16(mono, self.capture_sample_rate, self.config.sample_rate)
        ended_at = started_at + timedelta(seconds=target_frames / self.capture_sample_rate)
        return AudioChunk(mono, self.config.sample_rate, started_at, ended_at, overflowed)
