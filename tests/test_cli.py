from family_recorder import cli
from family_recorder.config import AppConfig, AudioConfig, load_config
from family_recorder.devices import AudioDevice
from family_recorder.direction import OutputRoute
from family_recorder.schedule import ScheduleUpdateResult
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


def test_cli_sets_structured_weekly_review_rule_and_fixes_wording(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """speakers:
  members: [陳樂融]
calendar:
  enabled: true
  default_calendar_id: family-id
summary:
  prompt: 請建立複習券
""",
        encoding="utf-8",
    )

    result = cli.main(
        [
            "--config",
            str(config_path),
            "set-weekly-review-rule",
            "--enabled",
            "true",
            "--source-weekday",
            "4",
            "--source-start",
            "18:00",
            "--source-end",
            "22:00",
            "--event-day-offset",
            "1",
            "--event-start",
            "11:00",
            "--event-end",
            "12:00",
            "--title",
            "家教複習卷",
            "--member",
            "陳樂融",
        ]
    )

    config = load_config(config_path)
    assert result == 0
    assert config.calendar.weekly_review.enabled is True
    assert config.calendar.weekly_review.event_start == "11:00"
    assert config.calendar.weekly_review.event_end == "12:00"
    assert config.calendar.weekly_review.member == "陳樂融"
    assert "複習卷" in config.summary.prompt
    assert "複習券" not in config.summary.prompt


def test_cli_applies_weekly_review_rule_from_existing_text_without_ai(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""storage:
  data_dir: {tmp_path}
calendar:
  enabled: true
  default_calendar_id: family-id
  weekly_review:
    enabled: true
    min_source_chars: 20
""",
        encoding="utf-8",
    )
    transcript_dir = tmp_path / "transcripts"
    summary_dir = tmp_path / "summaries"
    transcript_dir.mkdir()
    summary_dir.mkdir()
    (transcript_dir / "2026-09-04.md").write_text(
        "### 19:00:00–19:00:30\n" + ("家教內容" * 10), encoding="utf-8"
    )
    (summary_dir / "2026-09-04.md").write_text(
        "## 家教內容摘要與複習卷\n### 複習卷\n1. 第一題", encoding="utf-8"
    )

    result = cli.main(
        [
            "--config",
            str(config_path),
            "apply-weekly-review-rule",
            "--date",
            "2026-09-04",
        ]
    )

    assert result == 0
    with Storage(load_config(config_path).storage) as storage:
        pending = storage.pending_calendar_candidates()
    assert [(item.title, item.starts_at[11:16]) for item in pending] == [("家教複習卷", "11:00")]
