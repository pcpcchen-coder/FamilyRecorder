import contextlib
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk
from family_recorder.config import AppConfig, DirectionConfig, SpeakerConfig, StorageConfig
from family_recorder.control import pause_recording
from family_recorder.devices import AudioDevice
from family_recorder.direction import (
    AcousticCapture,
    DirectionSample,
    SpeechEnergySample,
    summarize_direction,
    summarize_speech_energy,
)
from family_recorder.listener import decide_capture_gate
from family_recorder.metrics import AudioAnalysis
from family_recorder.speakers import SpeakerIdentification
from family_recorder.storage import Storage
from family_recorder.transcriber import TranscriptionResult, TranscriptionSegment


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

        def transcribe_detailed(self, _audio_path: Path) -> TranscriptionResult:
            transcription_started.set()
            assert release_transcription.wait(timeout=2)
            return TranscriptionResult(
                "連續錄音",
                (TranscriptionSegment(0, 1_000, "連續錄音"),),
            )

    class FakeRecorder:
        def __init__(self, _config) -> None:
            self.device = AudioDevice(1, "reSpeaker XVF3800 4-Mic Array", 2, 16_000)
            self.capture_sample_rate = 16_000
            self.calls = 0

        @contextlib.contextmanager
        def open_stream(self):
            yield object()

        def read_chunk(self, _stream, **_kwargs) -> AudioChunk:
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

    config = AppConfig(
        storage=StorageConfig(data_dir=tmp_path),
        direction=DirectionConfig(enabled=False),
    )
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


def test_timed_text_segments_align_independent_speaker_and_direction_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import family_recorder.listener as listener

    class FakeTranscriber:
        def __init__(self, _config) -> None:
            pass

        def validate(self) -> None:
            pass

        def transcribe_detailed(self, _audio_path: Path) -> TranscriptionResult:
            return TranscriptionResult(
                "第一句。 第二句。",
                (
                    TranscriptionSegment(0, 1_500, "第一句。"),
                    TranscriptionSegment(2_000, 3_500, "第二句。"),
                ),
            )

    class FakeRecorder:
        def __init__(self, _config) -> None:
            self.device = AudioDevice(1, "reSpeaker XVF3800 4-Mic Array", 2, 16_000)
            self.capture_sample_rate = 16_000

        @contextlib.contextmanager
        def open_stream(self):
            yield object()

        def read_chunk(self, _stream, **_kwargs) -> AudioChunk:
            started = datetime(2026, 8, 9, 12, tzinfo=UTC)
            first = b"\x01\x00" * (16_000 * 2)
            second = b"\x02\x00" * (16_000 * 2)
            return AudioChunk(first + second, 16_000, started, started + timedelta(seconds=4))

    direction = summarize_direction(
        [
            DirectionSample(0, 88, True),
            DirectionSample(250, 90, True),
            DirectionSample(500, 92, True),
            DirectionSample(2_000, 268, True),
            DirectionSample(2_250, 270, True),
            DirectionSample(2_500, 272, True),
        ],
        DirectionConfig(min_speech_samples=2, cluster_tolerance_degrees=20),
    )

    class FakeDirectionSampler:
        def __init__(self, _config) -> None:
            pass

        def start(self) -> None:
            pass

        def stop_acoustic(self):
            return AcousticCapture(
                direction,
                summarize_speech_energy(
                    [],
                    DirectionConfig(speech_energy_enabled=False),
                ),
                (),
            )

    class FakeProfileStore:
        def __init__(self, _data_dir) -> None:
            pass

        def load(self, name: str):
            return object() if name in {"爸爸", "兒子"} else None

    monkeypatch.setattr(listener, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(listener, "DirectionSampler", FakeDirectionSampler)
    monkeypatch.setattr(listener, "WhisperCppTranscriber", FakeTranscriber)
    monkeypatch.setattr(listener, "SpeakerProfileStore", FakeProfileStore)
    monkeypatch.setattr(
        listener,
        "analyze_audio",
        lambda *_args: AudioAnalysis(True, -20.0, 10.0, 0.8, 100),
    )
    monkeypatch.setattr(
        listener,
        "identify_speaker",
        lambda pcm, *_args: SpeakerIdentification(
            "爸爸" if pcm.startswith(b"\x01\x00") else "兒子",
            0.88,
            "recognized",
            1,
            1,
        ),
    )

    config = AppConfig(
        storage=StorageConfig(data_dir=tmp_path),
        speakers=SpeakerConfig(enabled=True, members=("爸爸", "兒子")),
        direction=DirectionConfig(min_speech_samples=2, cluster_tolerance_degrees=20),
    )
    listener.run_listener(config, once=True)

    with Storage(config.storage) as storage:
        rows = storage.connection.execute(
            "select text, speaker_name, direction_label from segments order by started_at"
        ).fetchall()
    assert rows == [
        ("第一句。", "爸爸", "左側"),
        ("第二句。", "兒子", "右側"),
    ]


def test_xvf3800_speech_energy_can_rescue_a_software_vad_miss() -> None:
    config = AppConfig(
        direction=DirectionConfig(
            speech_energy_min_ratio=0.08,
            speech_energy_min_rms_dbfs=-55,
        )
    )
    energy = summarize_speech_energy(
        [
            SpeechEnergySample(0, 0, 1_000, 2_000, 2_000),
            SpeechEnergySample(250, 0, 0, 0, 0),
        ],
        config.direction,
    )

    decision = decide_capture_gate(
        AudioAnalysis(False, -50.0, 5.0, 0.03, 100),
        energy,
        config,
    )

    assert decision.keep is True
    assert decision.reason == "xvf3800_speech_energy"


def test_xvf3800_speech_energy_does_not_rescue_audio_below_rms_floor() -> None:
    config = AppConfig(direction=DirectionConfig(speech_energy_min_rms_dbfs=-55))
    energy = summarize_speech_energy(
        [SpeechEnergySample(0, 0, 1_000, 2_000, 2_000)],
        config.direction,
    )

    decision = decide_capture_gate(
        AudioAnalysis(False, -80.0, None, 0.0, 100),
        energy,
        config,
    )

    assert decision.keep is False
    assert decision.reason == "silence"
