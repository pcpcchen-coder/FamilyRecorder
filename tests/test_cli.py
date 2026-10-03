from datetime import datetime, timedelta

import pytest

from family_recorder import cli
from family_recorder.audio import AudioChunk
from family_recorder.config import (
    AppConfig,
    AudioConfig,
    DirectionConfig,
    StorageConfig,
    load_config,
)
from family_recorder.control import pause_recording
from family_recorder.devices import AudioDevice
from family_recorder.direction import (
    AcousticCapture,
    OutputRoute,
    summarize_direction,
    summarize_speech_energy,
)
from family_recorder.metrics import AudioAnalysis
from family_recorder.storage import Storage


class FakeRoutingReader:
    def __init__(self, **_kwargs: object) -> None:
        pass

    @staticmethod
    def read_output_routes() -> tuple[OutputRoute, OutputRoute]:
        return (
            OutputRoute(
                "left",
                8,
                0,
                "user-chosen channel copying processed auto-selected beam",
                True,
                False,
            ),
            OutputRoute("right", 7, 3, "AEC residual / ASR beam 3", False, True),
        )

    def close(self) -> None:
        pass


def _patch_hardware(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "select_input_device",
        lambda _config: AudioDevice(1, "reSpeaker XVF3800 4-Mic Array", 2, 16_000),
    )
    monkeypatch.setattr(cli, "XVF3800USBReader", FakeRoutingReader)


def test_beamforming_diagnostic_verifies_default_left_channel(monkeypatch) -> None:
    _patch_hardware(monkeypatch)

    report = cli._beamforming_diagnostic(AppConfig())

    assert report["capture_mode"] == "left"
    assert report["verified"] is True
    assert report["verdict"] == "verified_beamformed_processed"
    assert report["routes"]["left"]["category"] == 8


def test_beamforming_diagnostic_rejects_stereo_downmix(monkeypatch) -> None:
    _patch_hardware(monkeypatch)

    report = cli._beamforming_diagnostic(AppConfig(audio=AudioConfig(channels=2)))

    assert report["capture_mode"] == "downmix_left_and_right"
    assert report["verified"] is False
    assert report["verdict"] == "ambiguous_stereo_downmix"


def test_cli_updates_hallucination_thresholds(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")

    result = cli.main(
        [
            "--config",
            str(config_path),
            "set-hallucination-filter",
            "--min-avg-logprob",
            "-0.55",
            "--repeat-window-seconds",
            "900",
            "--hardware-silence-guard-enabled",
            "false",
        ]
    )

    config = load_config(config_path)
    assert result == 0
    assert config.hallucination_filter.min_avg_logprob == -0.55
    assert config.hallucination_filter.repeat_window_seconds == 900
    assert config.hallucination_filter.hardware_silence_guard_enabled is False


def test_cli_applies_named_hallucination_preset(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")

    result = cli.main(
        [
            "--config",
            str(config_path),
            "set-hallucination-preset",
            "--name",
            "strict",
        ]
    )

    config = load_config(config_path)
    assert result == 0
    assert config.hallucination_filter.min_avg_logprob == -0.60
    assert config.hallucination_filter.repeat_window_seconds == 600


@pytest.mark.parametrize(
    ("age", "running", "paused", "healthy"),
    [
        (10, True, False, True),
        (300, True, False, False),
        (None, True, False, False),
        (10, False, False, False),
        (10, True, True, False),
    ],
)
def test_menu_status_requires_fresh_captures_even_when_process_is_alive(
    tmp_path, monkeypatch, age, running, paused, healthy
) -> None:
    config = AppConfig(storage=StorageConfig(data_dir=tmp_path))
    monkeypatch.setattr(cli, "_listener_is_running", lambda: running)
    with Storage(config.storage) as storage:
        assert storage.latest_capture_time() is None
        if age is not None:
            ended = datetime.now().astimezone() - timedelta(seconds=age)
            storage.save_capture(
                AudioChunk(b"", 16_000, ended - timedelta(seconds=30), ended),
                AudioAnalysis(False, -80, None, 0, 100),
                AcousticCapture(
                    summarize_direction([], DirectionConfig()),
                    summarize_speech_energy([], DirectionConfig()),
                    (),
                ),
                combined_keep=False,
                gate_reason="silence",
                audio_path=None,
            )
            assert storage.latest_capture_time() == ended
    if paused:
        pause_recording(tmp_path)
    status = cli._menu_status(config, tmp_path / "config.yaml")
    assert status["listener_running"] is running
    assert status["recording_healthy"] is healthy
    if running and not paused:
        assert (status["pause_label"] == "錄音中") is healthy
    if paused:
        assert status["pause_label"] == "已暫停，直到手動恢復"
