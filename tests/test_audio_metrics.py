import wave
from pathlib import Path

import numpy as np

from family_recorder.audio import downmix_pcm16, resample_pcm16, write_wav
from family_recorder.config import VadConfig
from family_recorder.metrics import analyze_audio, rms_dbfs


class AlternatingVad:
    def __init__(self) -> None:
        self.calls = 0

    def is_speech(self, _frame: bytes, _sample_rate: int) -> bool:
        self.calls += 1
        return self.calls % 2 == 1


def _tone(sample_rate: int, seconds: float, amplitude: int = 10_000) -> bytes:
    time = np.arange(round(sample_rate * seconds)) / sample_rate
    return np.rint(np.sin(2 * np.pi * 440 * time) * amplitude).astype(np.int16).tobytes()


def test_downmix_stereo() -> None:
    stereo = np.array([[1000, -1000], [3000, 1000]], dtype=np.int16).tobytes()
    mono = np.frombuffer(downmix_pcm16(stereo, 2), dtype=np.int16)
    assert mono.tolist() == [0, 2000]


def test_resample_48k_to_16k() -> None:
    source = _tone(48_000, 1)
    target = resample_pcm16(source, 48_000, 16_000)
    assert len(target) == 16_000 * 2
    assert rms_dbfs(target) > -20


def test_write_wav_is_whisper_compatible(tmp_path: Path) -> None:
    path = tmp_path / "clip.wav"
    write_wav(path, _tone(16_000, 0.1), 16_000)
    with wave.open(str(path), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 16_000


def test_analysis_combines_rms_and_vad() -> None:
    analysis = analyze_audio(
        _tone(16_000, 0.3),
        16_000,
        VadConfig(min_speech_ratio=0.4, min_rms_dbfs=-50),
        vad=AlternatingVad(),
    )
    assert analysis.keep is True
    assert 0.4 <= analysis.speech_ratio <= 0.6
    assert analysis.snr_db is not None


def test_silence_is_rejected_without_vad() -> None:
    analysis = analyze_audio(b"\0" * 3200, 16_000, VadConfig(enabled=False))
    assert analysis.keep is False
    assert analysis.rms_dbfs == -120
