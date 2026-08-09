import contextlib
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk
from family_recorder.config import AppConfig, StorageConfig
from family_recorder.control import pause_recording
from family_recorder.devices import AudioDevice
from family_recorder.metrics import AudioAnalysis
from family_recorder.storage import Storage


def test_capture_continues_while_previous_chunk_is_transcribed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import family_recorder.listener as listener

    transcription_started = threading.Event()
    release_transcription = threading.Event()

    class FakeTranscriber:
        def __init__(self, _config) -> None:
            pass

        def validate(self) -> None:
            pass

        def transcribe(self, _audio_path: Path) -> str:
            transcription_started.set()
            assert release_transcription.wait(timeout=2)
            return "連續錄音"

    class FakeRecorder:
        def __init__(self, _config) -> None:
            self.device = AudioDevice(1, "reSpeaker XVF3800 4-Mic Array", 2, 16_000)
            self.capture_sample_rate = 16_000
            self.calls = 0

        @contextlib.contextmanager
        def open_stream(self):
            yield object()

        def read_chunk(self, _stream) -> AudioChunk:
            self.calls += 1
            if self.calls == 2:
                assert transcription_started.wait(timeout=2)
                release_transcription.set()
                raise KeyboardInterrupt
            started = datetime(2026, 8, 9, 12, tzinfo=UTC)
            return AudioChunk(
                b"\0" * 32_000,
                16_000,
                started,
                started + timedelta(seconds=1),
            )

    monkeypatch.setattr(listener, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(listener, "WhisperCppTranscriber", FakeTranscriber)
    monkeypatch.setattr(
        listener,
        "analyze_audio",
        lambda *_args: AudioAnalysis(True, -20.0, 10.0, 0.8, 100),
    )

    config = AppConfig(storage=StorageConfig(data_dir=tmp_path))
    listener.run_listener(config)

    with Storage(config.storage) as storage:
        row = storage.connection.execute("select status, text from segments").fetchone()
    assert row == ("transcribed", "連續錄音")


def test_listener_does_not_open_microphone_while_paused(tmp_path: Path, monkeypatch) -> None:
    import family_recorder.listener as listener

    opened = False

    class FakeTranscriber:
        def __init__(self, _config) -> None:
            pass

        def validate(self) -> None:
            pass

    class FakeRecorder:
        def __init__(self, _config) -> None:
            pass

        @contextlib.contextmanager
        def open_stream(self):
            nonlocal opened
            opened = True
            yield object()

    monkeypatch.setattr(listener, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(listener, "WhisperCppTranscriber", FakeTranscriber)
    config = AppConfig(storage=StorageConfig(data_dir=tmp_path))
    pause_recording(tmp_path)

    listener.run_listener(config, once=True)
    assert opened is False
