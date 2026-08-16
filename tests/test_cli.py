from pathlib import Path

from family_recorder import cli
from family_recorder.config import AppConfig, AudioConfig, load_config
from family_recorder.devices import AudioDevice
from family_recorder.direction import OutputRoute


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


def test_cli_summary_allowlist_also_enables_local_recording(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"storage:\n  data_dir: {str(tmp_path / 'data')!r}\n",
        encoding="utf-8",
    )
    fixture = Path(__file__).parent / "fixtures" / "home" / "fake_home.json"

    sync_result = cli.main(
        [
            "--config",
            str(config_path),
            "home-sync-fixture",
            "--fixture",
            str(fixture),
        ]
    )
    allow_result = cli.main(
        [
            "--config",
            str(config_path),
            "set-home-capability",
            "--scope",
            "summary",
            "--selection-key",
            "fake-home/coffee-maker",
            "--capability",
            "on_off.on",
            "--enabled",
            "true",
        ]
    )

    config = load_config(config_path)
    assert sync_result == 0
    assert allow_result == 0
    assert config.smart_home.enabled is True
    assert config.smart_home.record_allowlist == {"fake-home/coffee-maker": ("on_off.on",)}
    assert config.smart_home.summary_allowlist == {"fake-home/coffee-maker": ("on_off.on",)}
