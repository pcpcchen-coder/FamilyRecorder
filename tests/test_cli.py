from family_recorder import cli
from family_recorder.config import AppConfig, AudioConfig, load_config
from family_recorder.devices import AudioDevice
from family_recorder.direction import OutputRoute
from family_recorder.schedule import ScheduleUpdateResult


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


def test_cli_sets_summary_schedule_and_reports_reload(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n")
    calls = []

    def update(path, hour, minute):
        calls.append((path, hour, minute))
        return ScheduleUpdateResult("08:35", True)

    monkeypatch.setattr(cli, "update_summary_schedule", update)
    assert (
        cli.main(
            ["--config", str(config_path), "set-summary-schedule", "--hour", "8", "--minute", "35"]
        )
        == 0
    )
    assert calls == [(config_path.resolve(), 8, 35)]
    output = capsys.readouterr().out
    assert "08:35" in output
    assert "重新載入" in output


def test_cli_sets_audio_retention_days(tmp_path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("storage:\n  keep_audio_days: 7\n", encoding="utf-8")

    assert cli.main(["--config", str(config_path), "set-audio-retention", "--days", "14"]) == 0

    assert load_config(config_path).storage.keep_audio_days == 14
    assert "14 天" in capsys.readouterr().out


def test_cli_rejects_negative_audio_retention_without_changing_config(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    original = "storage:\n  keep_audio_days: 7\n"
    config_path.write_text(original, encoding="utf-8")

    assert cli.main(["--config", str(config_path), "set-audio-retention", "--days", "-1"]) == 1

    assert config_path.read_text(encoding="utf-8") == original
